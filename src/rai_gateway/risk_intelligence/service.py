"""WP6 Risk Intelligence application service."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from rai_gateway.models.registry import AISystem
from rai_gateway.risk_intelligence.anomaly import AnomalyDetector
from rai_gateway.risk_intelligence.budgets import BudgetService
from rai_gateway.risk_intelligence.content_evaluation import ContentEvaluationService
from rai_gateway.risk_intelligence.domain import (
    MONITOR_WINDOW_PRESETS,
    ContentEvaluationMode,
    resolve_window_seconds,
)
from rai_gateway.risk_intelligence.evidence_projection import project_operational_event
from rai_gateway.risk_intelligence.intervention import InterventionService
from rai_gateway.risk_intelligence.recommendations import RecommendationService
from rai_gateway.risk_intelligence.repository import RiskIntelligenceRepository
from rai_gateway.risk_intelligence.risk_engine import RiskEngine
from rai_gateway.risk_intelligence.risk_state import RiskStateService

logger = logging.getLogger(__name__)


class RiskIntelligenceService:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._repo = RiskIntelligenceRepository(db)
        self._content = ContentEvaluationService(db)
        self._engine = RiskEngine(db)
        self._interventions = InterventionService(db)
        self._recommendations = RecommendationService(db)
        self._state = RiskStateService(db)
        self._budgets = BudgetService(db)
        self._anomalies = AnomalyDetector(db)

    def _ensure_ai_system_owned(
        self,
        ai_system_id: UUID,
    ) -> AISystem:
        query = self._db.query(AISystem).filter(AISystem.id == ai_system_id)
        system = query.first()
        if not system:
            raise LookupError("AI system not found")
        return system

    # --- Evaluator config -------------------------------------------------

    def get_evaluator_config(
        self,
        ai_system_id: UUID | None = None,
    ) -> dict[str, Any]:
        if ai_system_id is None:
            return {
                "status": "NOT_ACTIVE",
                "reason": "CONTENT_EVALUATOR_NOT_CONFIGURED",
                "enabled": False,
            }
        self._ensure_ai_system_owned(ai_system_id)
        row = self._repo.get_evaluator_config(ai_system_id)
        if not row:
            return {
                "status": "NOT_ACTIVE",
                "reason": "CONTENT_EVALUATOR_NOT_CONFIGURED",
                "enabled": False,
            }
        return self._serialize_evaluator_config(row)

    def upsert_evaluator_config(
        self,
        *,
        ai_system_id: UUID | None,
        provider: str,
        model: str,
        enabled: bool = True,
        api_key: str | None = None,
        temperature: float = 0.0,
        timeout_seconds: int = 30,
        max_rules_per_call: int = 20,
        confidence_threshold: float = 0.5,
        minimum_confidence_to_mark: float = 0.5,
        minimum_confidence_to_monitor: float = 0.7,
        minimum_confidence_to_intervene: float = 0.9,
        fail_closed: bool = False,
        fallback_provider: str | None = None,
    ) -> dict[str, Any]:
        if ai_system_id is None:
            raise LookupError("AI system not found")
        self._ensure_ai_system_owned(ai_system_id)
        fields: dict[str, Any] = {
            "ai_system_id": ai_system_id,
            "provider": provider,
            "model": model,
            "enabled": enabled,
            "temperature": temperature,
            "timeout_seconds": timeout_seconds,
            "max_rules_per_call": max_rules_per_call,
            "confidence_threshold": confidence_threshold,
            "minimum_confidence_to_mark": minimum_confidence_to_mark,
            "minimum_confidence_to_monitor": minimum_confidence_to_monitor,
            "minimum_confidence_to_intervene": minimum_confidence_to_intervene,
            "fail_closed": fail_closed,
            "fallback_provider": fallback_provider,
            "health_status": "HEALTHY" if enabled else "UNAVAILABLE",
        }
        if api_key is not None:
            fields["api_key_encrypted"] = api_key  # server-side only
        row = self._repo.upsert_evaluator_config(**fields)
        self._db.commit()
        return self._serialize_evaluator_config(row)

    # --- Content evaluation -----------------------------------------------

    def evaluate_content(
        self,
        *,
        ai_system_id: UUID,
        content: str,
        content_type: str,
        evaluation_mode: str = ContentEvaluationMode.OFFLINE_EVALUATED.value,
        trajectory_id: UUID | None = None,
        runtime_identity_id: UUID | None = None,
        agent_id: UUID | None = None,
        agent_version_id: UUID | None = None,
        apply_risk: bool = True,
        test_only: bool = False,
    ) -> dict[str, Any]:
        self._ensure_ai_system_owned(ai_system_id)
        result = self._content.evaluate_content(
            ai_system_id=ai_system_id,
            content=content,
            content_type=content_type,
            evaluation_mode=evaluation_mode,
            trajectory_id=trajectory_id,
            use_cache=not test_only,
            test_only=test_only,
        )
        risk_result = None
        if apply_risk and not test_only and result.get("intervention_hints"):
            risk_result = self._engine.process_content_evaluation(
                ai_system_id=ai_system_id,
                trajectory_id=trajectory_id,
                runtime_identity_id=runtime_identity_id,
                agent_id=agent_id,
                agent_version_id=agent_version_id,
                evaluation_result=result,
            )
            # Project evidence events best-effort
            if trajectory_id:
                self._project_content_evidence(trajectory_id, result, risk_result)
        if not test_only:
            self._db.commit()
        return {**result, "risk": risk_result}

    def test_evaluate_content(
        self,
        *,
        ai_system_id: UUID,
        content: str,
        content_type: str,
    ) -> dict[str, Any]:
        result = self.evaluate_content(
            ai_system_id=ai_system_id,
            content=content,
            content_type=content_type,
            evaluation_mode=ContentEvaluationMode.TEST_ONLY.value,
            apply_risk=False,
            test_only=True,
        )
        return {
            **result,
            "test_only": True,
            "label": "Content Evaluator Test — not persisted as production finding",
        }

    # --- Overview / listings ----------------------------------------------

    def overview(
        self,
        ai_system_id: UUID | None = None,
    ) -> dict[str, Any]:
        if ai_system_id is not None:
            self._ensure_ai_system_owned(ai_system_id)
        budget_counts = self._budgets.count_by_status(ai_system_id=ai_system_id)
        anomalies = self._anomalies.list_anomalies(ai_system_id=ai_system_id, limit=20)
        suspended = 0
        try:
            from rai_gateway.models.identity import AgentRuntimeIdentity
            from rai_gateway.models.registry import Agent

            q = (
                self._db.query(AgentRuntimeIdentity)
                .join(Agent, AgentRuntimeIdentity.agent_id == Agent.id)
                .join(AISystem, Agent.ai_system_id == AISystem.id)
                .filter(AgentRuntimeIdentity.status == "SUSPENDED")
            )
            if ai_system_id is not None:
                q = q.filter(AISystem.id == ai_system_id)
            suspended = q.count()
        except Exception:
            suspended = 0
        high_critical = self.count_findings(
            ai_system_id=ai_system_id,
            severity="HIGH",
            include_evidence=True,
        ) + self.count_findings(
            ai_system_id=ai_system_id,
            severity="CRITICAL",
            include_evidence=True,
        )
        return {
            "active_findings": self.count_findings(
                ai_system_id=ai_system_id,
                status="OPEN",
                include_evidence=True,
            ),
            "critical_findings": self.count_findings(
                ai_system_id=ai_system_id,
                severity="CRITICAL",
                include_evidence=True,
            ),
            "high_critical_risks": high_critical,
            "monitored_scopes": len(
                self._repo.list_monitors(
                    ai_system_id=ai_system_id,
                    status="ACTIVE",
                )
            ),
            "budgets_near_limit": budget_counts["warning"],
            "budgets_exceeded": budget_counts["exceeded"],
            "recent_anomalies": len(anomalies),
            "suspended_runtime_identities": suspended,
            "pending_interventions": len(
                self._repo.list_interventions(
                    ai_system_id=ai_system_id,
                    status="PENDING_CONFIRMATION",
                    limit=200,
                )
            ),
            "recent_interventions": len(
                self._repo.list_interventions(
                    ai_system_id=ai_system_id,
                    limit=20,
                )
            ),
            "open_recommendations": len(
                self._repo.list_recommendations(
                    ai_system_id=ai_system_id,
                    status="NEW",
                    limit=200,
                )
            ),
            "evaluator": self.get_evaluator_config(ai_system_id),
            "window_presets": MONITOR_WINDOW_PRESETS,
        }

    def list_findings(self, **kwargs: Any) -> list[dict[str, Any]]:
        include_evidence = bool(kwargs.pop("include_evidence", False))
        if not include_evidence:
            return [
                self._serialize_finding(f) for f in self._repo.list_findings(**kwargs)
            ]

        limit = int(kwargs.pop("limit", 50))
        offset = int(kwargs.pop("offset", 0))
        window = offset + limit
        runtime = [
            self._serialize_finding(f)
            for f in self._repo.list_findings(**kwargs, limit=window, offset=0)
        ]
        evidence = [
            self._serialize_evidence_finding(finding, trajectory)
            for finding, trajectory in self._repo.list_evidence_findings(
                **kwargs, limit=window, offset=0
            )
        ]
        merged = sorted(
            runtime + evidence,
            key=lambda row: row.get("created_at") or "",
            reverse=True,
        )
        return merged[offset : offset + limit]

    def count_findings(self, **kwargs: Any) -> int:
        include_evidence = bool(kwargs.pop("include_evidence", False))
        total = self._repo.count_findings(**kwargs)
        if include_evidence:
            total += self._repo.count_evidence_findings(**kwargs)
        return total

    def get_finding(
        self,
        finding_id: UUID,
    ) -> dict[str, Any] | None:
        row = self._repo.get_finding(finding_id)
        if row:
            return self._serialize_finding(row)
        evidence = self._repo.get_evidence_finding(finding_id)
        if evidence:
            return self._serialize_evidence_finding(evidence[0], evidence[1])
        return None

    def list_signals(self, **kwargs: Any) -> list[dict[str, Any]]:
        return [self._serialize_signal(s) for s in self._repo.list_signals(**kwargs)]

    def list_monitors(self, **kwargs: Any) -> list[dict[str, Any]]:
        return [self._serialize_monitor(m) for m in self._repo.list_monitors(**kwargs)]

    def list_interventions(self, **kwargs: Any) -> list[dict[str, Any]]:
        return [
            InterventionService.serialize(i)
            for i in self._repo.list_interventions(**kwargs)
        ]

    def list_recommendations(self, **kwargs: Any) -> list[dict[str, Any]]:
        return [
            RecommendationService.serialize(r)
            for r in self._repo.list_recommendations(**kwargs)
        ]

    def list_risk_states(self, **kwargs: Any) -> list[dict[str, Any]]:
        return [
            RiskStateService.serialize_state(s)
            for s in self._repo.list_risk_states(**kwargs)
        ]

    def trajectory_risk(
        self,
        trajectory_id: UUID,
    ) -> dict[str, Any]:
        return {
            "signals": self.list_signals(
                trajectory_id=trajectory_id,
                limit=100,
            ),
            "findings": self.list_findings(
                trajectory_id=trajectory_id,
                limit=100,
            ),
            "interventions": self.list_interventions(
                trajectory_id=trajectory_id,
                limit=100,
            ),
            "evaluations": [
                self._serialize_evaluation(e)
                for e in self._repo.list_evaluations(
                    trajectory_id=trajectory_id,
                    limit=50,
                )
            ],
            "risk_state": (
                RiskStateService.serialize_state(s)
                if (s := self._repo.get_risk_state("TRAJECTORY", str(trajectory_id)))
                else None
            ),
        }

    # --- Monitor rules ----------------------------------------------------

    def create_monitor_rule(self, **fields: Any) -> dict[str, Any]:
        ai_system_id = fields.get("ai_system_id")
        if ai_system_id is None:
            raise LookupError("AI system not found")
        self._ensure_ai_system_owned(ai_system_id)
        if "window" in fields and fields.get("window") is not None:
            fields["window_seconds"] = resolve_window_seconds(
                fields.pop("window"), default=fields.get("window_seconds", 600)
            )
        elif isinstance(fields.get("window_seconds"), str):
            fields["window_seconds"] = resolve_window_seconds(fields["window_seconds"])
        row = self._repo.create_monitor_rule(**fields)
        self._db.commit()
        return self._serialize_monitor_rule(row)

    def list_monitor_rules(
        self,
        ai_system_id: UUID,
    ) -> list[dict[str, Any]]:
        self._ensure_ai_system_owned(ai_system_id)
        return [
            self._serialize_monitor_rule(r)
            for r in self._repo.list_monitor_rules(ai_system_id=ai_system_id)
        ]

    # --- Budgets ----------------------------------------------------------

    def create_budget(self, **fields: Any) -> dict[str, Any]:
        if "window" in fields and fields.get("window") is not None:
            fields["window_seconds"] = resolve_window_seconds(
                fields.pop("window"), default=fields.get("window_seconds", 3600)
            )
        row = self._budgets.create_budget(**fields)
        self._db.commit()
        return self._budgets.serialize_budget(
            row,
            check_stats={
                "check_count": 0,
                "trigger_count": 0,
                "warning_count": 0,
                "exceeded_count": 0,
            },
        )

    def list_budgets(self, **kwargs: Any) -> list[dict[str, Any]]:
        rows = self._budgets.list_budgets(**kwargs)
        stats = self._budgets.check_stats_for_budgets([b.id for b in rows])
        return [
            self._budgets.serialize_budget(
                b,
                check_stats=stats.get(
                    b.id,
                    {
                        "check_count": 0,
                        "trigger_count": 0,
                        "warning_count": 0,
                        "exceeded_count": 0,
                    },
                ),
            )
            for b in rows
        ]

    def get_budget(
        self,
        budget_id: UUID,
    ) -> dict[str, Any] | None:
        row = self._budgets.get_budget(budget_id)
        if not row:
            return None
        stats = self._budgets.check_stats_for_budgets([row.id]).get(
            row.id,
            {
                "check_count": 0,
                "trigger_count": 0,
                "warning_count": 0,
                "exceeded_count": 0,
            },
        )
        return self._budgets.serialize_budget(row, check_stats=stats)

    def list_budget_checks(
        self,
        budget_id: UUID,
        *,
        status: str | None = None,
        triggers_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        items, total = self._budgets.list_checks(
            budget_id,
            status=status,
            triggers_only=triggers_only,
            limit=limit,
            offset=offset,
        )
        return {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def update_budget(
        self,
        budget_id: UUID,
        **fields: Any,
    ) -> dict[str, Any]:
        if "window" in fields and fields.get("window") is not None:
            fields["window_seconds"] = resolve_window_seconds(
                fields.pop("window"), default=fields.get("window_seconds", 3600)
            )
        row = self._budgets.update_budget(budget_id, **fields)
        self._db.commit()
        stats = self._budgets.check_stats_for_budgets([row.id]).get(
            row.id,
            {
                "check_count": 0,
                "trigger_count": 0,
                "warning_count": 0,
                "exceeded_count": 0,
            },
        )
        return self._budgets.serialize_budget(row, check_stats=stats)

    def check_budgets(self, **kwargs: Any) -> dict[str, Any]:
        result = self._budgets.check_and_consume(**kwargs)
        # Project budget evidence events
        for check in result.get("checks") or []:
            status = check.get("status")
            if status in ("WARNING", "EXCEEDED"):
                from rai_gateway.evidence.domain import (
                    EvidenceEventType,
                    EvidenceSourceType,
                )

                event = (
                    EvidenceEventType.BUDGET_EXCEEDED.value
                    if status == "EXCEEDED"
                    else EvidenceEventType.BUDGET_WARNING.value
                )
                project_operational_event(
                    self._db,
                    event_type=event,
                    source_type=EvidenceSourceType.RAI_AUTHORITATIVE.value,
                    payload=check,
                    trajectory_id=kwargs.get("trajectory_id"),
                    ai_system_id=kwargs.get("ai_system_id"),
                    runtime_identity_id=kwargs.get("runtime_identity_id"),
                )
        return result

    def list_anomalies(self, **kwargs: Any) -> list[dict[str, Any]]:
        return [
            self._serialize_finding(f) for f in self._anomalies.list_anomalies(**kwargs)
        ]

    # --- Interventions / recommendations actions --------------------------

    def confirm_intervention(
        self,
        intervention_id: UUID,
        *,
        actor: str,
    ) -> dict[str, Any]:
        row = self._interventions.confirm_intervention(
            intervention_id, executed_by=actor
        )
        self._db.commit()
        return InterventionService.serialize(row)

    def cancel_intervention(
        self,
        intervention_id: UUID,
        *,
        actor: str,
    ) -> dict[str, Any]:
        row = self._interventions.cancel_intervention(
            intervention_id, cancelled_by=actor
        )
        self._db.commit()
        return InterventionService.serialize(row)

    def accept_recommendation(
        self,
        recommendation_id: UUID,
        *,
        actor: str,
    ) -> dict[str, Any]:
        result = self._recommendations.accept_as_draft_rule(
            recommendation_id, actor=actor
        )
        self._db.commit()
        return result

    def dismiss_recommendation(
        self,
        recommendation_id: UUID,
        *,
        reject: bool = False,
    ) -> dict[str, Any]:
        row = self._recommendations.dismiss(
            recommendation_id,
            status="REJECTED" if reject else "DISMISSED",
        )
        self._db.commit()
        return RecommendationService.serialize(row)

    def scan_recommendations(
        self,
        ai_system_id: UUID,
    ) -> list[dict[str, Any]]:
        rows = self._recommendations.scan_for_recommendations(ai_system_id)
        self._db.commit()
        return [RecommendationService.serialize(r) for r in rows]

    def process_trajectory_safe(self, trajectory_id: UUID) -> None:
        try:
            self._engine.process_trajectory(trajectory_id)
            self._db.commit()
        except Exception:
            logger.exception("WP6 trajectory risk processing failed")
            self._db.rollback()

    def process_enforcement_safe(self, **kwargs: Any) -> None:
        try:
            self._engine.process_enforcement_event(**kwargs)
            self._db.commit()
        except Exception:
            logger.exception("WP6 enforcement risk processing failed")
            try:
                self._db.rollback()
            except Exception:
                pass

    def authorization_overlay(
        self,
        *,
        ai_system_id: UUID,
        runtime_identity_id: UUID,
        tool_id: UUID | None = None,
    ) -> dict[str, Any]:
        return self._engine.get_authorization_overlay(
            ai_system_id=ai_system_id,
            runtime_identity_id=runtime_identity_id,
            tool_id=tool_id,
        )

    def budget_authorization_check(
        self,
        *,
        ai_system_id: UUID,
        runtime_identity_id: UUID | None,
        agent_id: UUID | None = None,
        agent_version_id: UUID | None = None,
        delegation_id: UUID | None = None,
        tool_name: str | None = None,
        tool_id: UUID | None = None,
        provider: str | None = None,
        model: str | None = None,
        parameters: dict[str, Any] | None = None,
        amount: float | None = None,
        token_usage: float | None = None,
        cost: float | None = None,
        trajectory_id: UUID | None = None,
        idempotency_key: str | None = None,
        finops_usage_reservation_id: UUID | None = None,
    ) -> dict[str, Any]:
        result = self.check_budgets(
            ai_system_id=ai_system_id,
            runtime_identity_id=runtime_identity_id,
            agent_id=agent_id,
            agent_version_id=agent_version_id,
            delegation_id=delegation_id,
            tool_name=tool_name,
            tool_id=tool_id,
            provider=provider,
            model=model,
            parameters=parameters,
            amount=amount,
            token_usage=token_usage,
            cost=cost,
            trajectory_id=trajectory_id,
            idempotency_key=idempotency_key,
            finops_usage_reservation_id=finops_usage_reservation_id,
            commit_usage=True,
        )
        if result.get("suspend") and runtime_identity_id:
            try:
                from rai_gateway.identity.service import RuntimeIdentityService

                RuntimeIdentityService(self._db).suspend_runtime_identity(
                    runtime_identity_id,
                    updated_by="budget_enforcement",
                    reason=result.get("deny_reason") or "Budget exceeded",
                )
                from rai_gateway.evidence.domain import (
                    EvidenceEventType,
                    EvidenceSourceType,
                )

                project_operational_event(
                    self._db,
                    event_type=EvidenceEventType.RUNTIME_IDENTITY_SUSPENDED.value,
                    source_type=EvidenceSourceType.RAI_AUTHORITATIVE.value,
                    payload={
                        "reason": result.get("deny_reason"),
                        "source": "budget_exceeded",
                        "checks": result.get("checks"),
                    },
                    trajectory_id=trajectory_id,
                    ai_system_id=ai_system_id,
                    runtime_identity_id=runtime_identity_id,
                )
            except Exception:
                logger.exception("Budget-driven suspension failed")
        return result

    # --- Serialization ----------------------------------------------------

    def _serialize_evaluator_config(self, row: Any) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "ai_system_id": str(row.ai_system_id) if row.ai_system_id else None,
            "status": "ACTIVE" if row.enabled else "NOT_ACTIVE",
            "enabled": row.enabled,
            "provider": row.provider,
            "model": row.model,
            "temperature": row.temperature,
            "timeout_seconds": row.timeout_seconds,
            "max_rules_per_call": row.max_rules_per_call,
            "confidence_threshold": row.confidence_threshold,
            "minimum_confidence_to_mark": row.minimum_confidence_to_mark,
            "minimum_confidence_to_monitor": row.minimum_confidence_to_monitor,
            "minimum_confidence_to_intervene": row.minimum_confidence_to_intervene,
            "fail_closed": row.fail_closed,
            "fallback_provider": row.fallback_provider,
            "has_api_key": bool(row.api_key_encrypted),
            "health_status": row.health_status,
            "last_success_at": row.last_success_at.isoformat()
            if row.last_success_at
            else None,
            "last_error_at": row.last_error_at.isoformat()
            if row.last_error_at
            else None,
            "latency_ms_avg": row.latency_ms_avg,
            "error_rate": row.error_rate,
            # Never expose api_key
        }

    @staticmethod
    def _policy_kind(finding_type: str | None, category: str | None) -> str:
        text = f"{finding_type or ''} {category or ''}".upper()
        if "BUDGET" in text:
            return "budget"
        if "CONTENT" in text:
            return "content"
        if any(
            token in text
            for token in (
                "TOOL",
                "DENIAL",
                "ANOMALY",
                "FREQUENCY",
                "UNVERIFIED",
                "AUTHORITY",
            )
        ):
            return "tool"
        return "governance"

    def _serialize_finding(self, f: Any) -> dict[str, Any]:
        from rai_gateway.models.registry import (
            Agent,
            AgentVersion,
            AgentVersionDependency,
            AISystem,
            ModelResource,
        )

        system = (
            self._db.query(AISystem).filter(AISystem.id == f.ai_system_id).first()
            if f.ai_system_id
            else None
        )
        agent = (
            self._db.query(Agent).filter(Agent.id == f.agent_id).first()
            if f.agent_id
            else None
        )
        version = (
            self._db.query(AgentVersion)
            .filter(AgentVersion.id == f.agent_version_id)
            .first()
            if getattr(f, "agent_version_id", None)
            else None
        )
        model_name = None
        if version is not None:
            dep = (
                self._db.query(AgentVersionDependency)
                .filter(
                    AgentVersionDependency.agent_version_id == version.id,
                    AgentVersionDependency.resource_type == "model",
                )
                .first()
            )
            if dep and dep.resource_id:
                model = (
                    self._db.query(ModelResource)
                    .filter(ModelResource.id == dep.resource_id)
                    .first()
                )
                if model:
                    model_name = f"{model.provider}/{model.model_name}"

        return {
            "id": str(f.id),
            "trajectory_id": str(f.trajectory_id) if f.trajectory_id else None,
            "ai_system_id": str(f.ai_system_id),
            "ai_system_name": system.name if system else None,
            "agent_id": str(f.agent_id) if f.agent_id else None,
            "agent_name": agent.name if agent else None,
            "agent_version_id": str(f.agent_version_id)
            if getattr(f, "agent_version_id", None)
            else None,
            "agent_version_number": version.version_number if version else None,
            "model_name": model_name,
            "runtime_identity_id": str(f.runtime_identity_id)
            if f.runtime_identity_id
            else None,
            "finding_type": f.finding_type,
            "policy_kind": self._policy_kind(f.finding_type, f.category),
            "title": f.title,
            "description": f.description,
            "severity": f.severity,
            "confidence": f.confidence,
            "sensitivity": f.sensitivity,
            "category": f.category,
            "dimensions": f.dimensions,
            "signal_ids": f.signal_ids,
            "evidence_refs": f.evidence_refs,
            "policy_rule_ids": f.policy_rule_ids,
            "intervention_effect": f.intervention_effect,
            "status": f.status,
            "explanation": f.explanation,
            "created_at": f.created_at.isoformat() if f.created_at else None,
        }

    def _serialize_evidence_finding(
        self, finding: Any, trajectory: Any
    ) -> dict[str, Any]:
        """Map a trajectory evidence finding into the risk-findings response."""
        from rai_gateway.models.registry import ToolResource
        from rai_gateway.models.runtime_enforcement import RuntimeEnforcementReceipt

        receipt = None
        if trajectory.correlation_id:
            receipt = (
                self._db.query(RuntimeEnforcementReceipt)
                .filter(
                    RuntimeEnforcementReceipt.correlation_id
                    == trajectory.correlation_id
                )
                .order_by(RuntimeEnforcementReceipt.started_at.desc())
                .first()
            )
        tool_name = None
        if receipt is not None and receipt.tool_id:
            tool = (
                self._db.query(ToolResource)
                .filter(ToolResource.id == receipt.tool_id)
                .first()
            )
            if tool is not None:
                tool_name = tool.name or tool.tool_key
        rule_title = None
        explanation_text = finding.description or ""
        if ":" in explanation_text:
            rule_title = explanation_text.split(":", 1)[0].strip() or None
        effect = {
            "POLICY_DENIAL": "DENY",
            "AUTHORITY_DENIAL": "DENY",
            "APPROVAL_MISMATCH": "REQUIRE_APPROVAL",
        }.get(finding.finding_type)
        rule_ids = []
        if receipt is not None and receipt.matched_rule_ids:
            rule_ids = [str(item) for item in receipt.matched_rule_ids]

        row = type("EvidenceFindingView", (), {})()
        row.id = finding.id
        row.trajectory_id = finding.trajectory_id
        row.ai_system_id = trajectory.ai_system_id
        row.agent_id = trajectory.agent_id
        row.agent_version_id = trajectory.agent_version_id
        row.runtime_identity_id = trajectory.runtime_identity_id
        row.finding_type = finding.finding_type
        row.category = None
        row.title = finding.title
        row.description = finding.description
        row.severity = finding.severity
        row.confidence = 1.0
        row.sensitivity = "NORMAL"
        row.dimensions = {"severity": finding.severity, "confidence": 1.0}
        row.signal_ids = []
        row.evidence_refs = [{"source_event_ids": finding.source_event_ids or []}]
        row.policy_rule_ids = rule_ids
        row.intervention_effect = effect
        row.status = finding.status
        row.explanation = {
            "observed": finding.description,
            "rule": rule_title,
            "tool_name": tool_name,
            "why_intervention": finding.description,
        }
        row.created_at = finding.created_at
        return self._serialize_finding(row)

    @staticmethod
    def _serialize_signal(s: Any) -> dict[str, Any]:
        return {
            "id": str(s.id),
            "trajectory_id": str(s.trajectory_id) if s.trajectory_id else None,
            "ai_system_id": str(s.ai_system_id),
            "runtime_identity_id": str(s.runtime_identity_id)
            if s.runtime_identity_id
            else None,
            "signal_type": s.signal_type,
            "confidence": s.confidence,
            "severity": s.severity,
            "sensitivity": s.sensitivity,
            "dimensions": s.dimensions,
            "category": s.category,
            "payload": s.payload,
            "evidence_refs": s.evidence_refs,
            "occurred_at": s.occurred_at.isoformat() if s.occurred_at else None,
        }

    @staticmethod
    def _serialize_monitor(m: Any) -> dict[str, Any]:
        return {
            "id": str(m.id),
            "ai_system_id": str(m.ai_system_id),
            "monitor_rule_id": str(m.monitor_rule_id) if m.monitor_rule_id else None,
            "scope_type": m.scope_type,
            "scope_id": m.scope_id,
            "reason": m.reason,
            "status": m.status,
            "current_count": m.current_count,
            "current_sum": m.current_sum,
            "threshold": m.threshold,
            "started_at": m.started_at.isoformat() if m.started_at else None,
            "expires_at": m.expires_at.isoformat() if m.expires_at else None,
        }

    @staticmethod
    def _serialize_monitor_rule(r: Any) -> dict[str, Any]:
        return {
            "id": str(r.id),
            "ai_system_id": str(r.ai_system_id),
            "name": r.name,
            "scope": r.scope,
            "signal_type": r.signal_type,
            "tool_id": str(r.tool_id) if r.tool_id else None,
            "tool_name": r.tool_name,
            "window_seconds": r.window_seconds,
            "aggregation": r.aggregation,
            "threshold": r.threshold,
            "amount_parameter_path": r.amount_parameter_path,
            "effect": r.effect,
            "monitor_duration_seconds": r.monitor_duration_seconds,
            "enabled": r.enabled,
        }

    @staticmethod
    def _serialize_evaluation(e: Any) -> dict[str, Any]:
        return {
            "id": str(e.id),
            "content_type": e.content_type,
            "evaluation_mode": e.evaluation_mode,
            "status": e.status,
            "failure_type": e.failure_type,
            "provider": e.provider,
            "model": e.model,
            "evaluations": e.evaluations,
            "latency_ms": e.latency_ms,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }

    def _project_content_evidence(
        self,
        trajectory_id: UUID,
        evaluation: dict[str, Any],
        risk_result: dict[str, Any] | None,
    ) -> None:
        try:
            from rai_gateway.evidence.domain import (
                EvidenceEventType,
                EvidenceSourceType,
            )
            from rai_gateway.evidence.service import TrajectoryService

            svc = TrajectoryService(self._db)
            # Best-effort: record evaluation result as evidence event if API exists
            if hasattr(svc, "record_derived_event"):
                svc.record_derived_event(
                    trajectory_id,
                    event_type=EvidenceEventType.CONTENT_EVALUATION_RESULT.value,
                    source_type=EvidenceSourceType.DERIVED.value,
                    payload={
                        "evaluation": {
                            "id": evaluation.get("id"),
                            "status": evaluation.get("status"),
                            "provider": evaluation.get("provider"),
                            "evaluations": evaluation.get("evaluations"),
                        },
                        "risk": risk_result,
                    },
                )
        except Exception:
            logger.exception("Failed to project content evaluation evidence")
