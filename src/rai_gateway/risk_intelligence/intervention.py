"""Intervention decision engine — maps detections to governance effects."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from rai_gateway.risk_intelligence.domain import (
    SEVERITY_RANK,
    FindingStatus,
    InterventionAuthorizationMode,
    InterventionEffect,
    InterventionStatus,
    RiskScopeType,
    RiskSeverity,
)
from rai_gateway.risk_intelligence.repository import RiskIntelligenceRepository
from rai_gateway.risk_intelligence.risk_state import RiskStateService

logger = logging.getLogger(__name__)


class InterventionService:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._repo = RiskIntelligenceRepository(db)
        self._risk_state = RiskStateService(db)

    def decide_from_content_hints(
        self,
        *,
        ai_system_id: UUID,
        trajectory_id: UUID | None,
        runtime_identity_id: UUID | None,
        agent_id: UUID | None,
        agent_version_id: UUID | None,
        hints: list[dict[str, Any]],
        signal_ids: list[str],
        authorization_mode: str = InterventionAuthorizationMode.HUMAN_CONFIRM_HIGH_CRITICAL.value,
    ) -> list[Any]:
        decisions = []
        for hint in hints:
            effect = hint.get("suggested_intervention") or InterventionEffect.MARK.value
            severity = hint.get("severity") or RiskSeverity.MEDIUM.value
            confidence = float(hint.get("confidence") or 0)
            finding = self._repo.create_finding(
                trajectory_id=trajectory_id,
                ai_system_id=ai_system_id,
                agent_id=agent_id,
                agent_version_id=agent_version_id,
                runtime_identity_id=runtime_identity_id,
                finding_type="CONTENT_POLICY_VIOLATION",
                title=f"Content rule violation: {hint.get('category') or hint.get('rule_id')}",
                description=hint.get("reason"),
                severity=severity,
                confidence=confidence,
                sensitivity="NORMAL",
                category=hint.get("category"),
                dimensions={
                    "severity": severity,
                    "confidence": confidence,
                },
                signal_ids=signal_ids,
                evidence_refs=[{"spans": hint.get("evidence_spans") or []}],
                policy_rule_ids=[hint["rule_id"]] if hint.get("rule_id") else [],
                intervention_effect=effect,
                status=FindingStatus.OPEN.value,
                explanation={
                    "observed": hint.get("reason"),
                    "rule_id": hint.get("rule_id"),
                    "rule_effect": hint.get("rule_effect"),
                    "severity": severity,
                    "confidence": confidence,
                    "why_intervention": (
                        f"Configured content rule effect {hint.get('rule_effect')} "
                        f"mapped to {effect} at confidence {confidence}"
                    ),
                },
            )
            decision = self._create_and_maybe_execute(
                ai_system_id=ai_system_id,
                trajectory_id=trajectory_id,
                scope_type=RiskScopeType.RUNTIME_IDENTITY.value
                if runtime_identity_id
                else RiskScopeType.AI_SYSTEM.value,
                scope_id=str(runtime_identity_id or ai_system_id),
                effect=effect,
                reason=hint.get("reason") or "Content policy violation",
                risk_level=severity,
                confidence=confidence,
                signal_ids=signal_ids,
                policy_rule_ids=[hint["rule_id"]] if hint.get("rule_id") else [],
                finding_id=finding.id,
                authorization_mode=authorization_mode,
                explanation=finding.explanation,
            )
            decisions.append(decision)
        return decisions

    def decide_from_monitor(
        self,
        *,
        ai_system_id: UUID,
        trajectory_id: UUID | None,
        runtime_identity_id: UUID | None,
        rule: Any,
        measured_value: float,
        signal_ids: list[str],
        authorization_mode: str = InterventionAuthorizationMode.AUTO_FOR_CONFIGURED_SIGNALS.value,
    ) -> Any:
        effect = rule.effect or InterventionEffect.MARK_AND_MONITOR.value
        finding = self._repo.create_finding(
            trajectory_id=trajectory_id,
            ai_system_id=ai_system_id,
            runtime_identity_id=runtime_identity_id,
            finding_type="FREQUENCY_THRESHOLD"
            if rule.aggregation == "COUNT"
            else "AMOUNT_THRESHOLD",
            title=f"Monitor threshold reached: {rule.name}",
            description=(
                f"{rule.aggregation}={measured_value} exceeded threshold "
                f"{rule.threshold} in {rule.window_seconds}s"
            ),
            severity=RiskSeverity.HIGH.value,
            confidence=1.0,
            sensitivity="HIGH",
            dimensions={"severity": RiskSeverity.HIGH.value, "confidence": 1.0},
            signal_ids=signal_ids,
            evidence_refs=[],
            policy_rule_ids=[str(rule.id)],
            intervention_effect=effect,
            status=FindingStatus.MONITORING.value
            if effect == InterventionEffect.MARK_AND_MONITOR.value
            else FindingStatus.OPEN.value,
            explanation={
                "observed": f"{rule.aggregation}={measured_value}",
                "rule": rule.name,
                "threshold": rule.threshold,
                "window_seconds": rule.window_seconds,
                "why_intervention": f"Monitor rule effect {effect}",
            },
        )
        expires = None
        if rule.monitor_duration_seconds:
            expires = datetime.now(timezone.utc) + timedelta(
                seconds=rule.monitor_duration_seconds
            )
        if effect in (
            InterventionEffect.MARK_AND_MONITOR.value,
            InterventionEffect.REQUIRE_APPROVAL.value,
        ):
            self._repo.create_monitor(
                ai_system_id=ai_system_id,
                monitor_rule_id=rule.id,
                scope_type=RiskScopeType.RUNTIME_IDENTITY.value
                if runtime_identity_id
                else RiskScopeType.AI_SYSTEM.value,
                scope_id=str(runtime_identity_id or ai_system_id),
                reason=finding.description,
                status="ACTIVE",
                current_count=int(measured_value) if rule.aggregation == "COUNT" else 0,
                current_sum=float(measured_value) if rule.aggregation == "SUM" else 0.0,
                threshold=rule.threshold,
                expires_at=expires,
                finding_id=finding.id,
            )
            self._risk_state.set_monitoring(
                ai_system_id=ai_system_id,
                scope_type=RiskScopeType.RUNTIME_IDENTITY.value
                if runtime_identity_id
                else RiskScopeType.AI_SYSTEM.value,
                scope_id=str(runtime_identity_id or ai_system_id),
                active=True,
                require_approval=effect == InterventionEffect.REQUIRE_APPROVAL.value,
            )

        return self._create_and_maybe_execute(
            ai_system_id=ai_system_id,
            trajectory_id=trajectory_id,
            scope_type=RiskScopeType.RUNTIME_IDENTITY.value
            if runtime_identity_id
            else RiskScopeType.AI_SYSTEM.value,
            scope_id=str(runtime_identity_id or ai_system_id),
            effect=effect,
            reason=finding.description,
            risk_level=RiskSeverity.HIGH.value,
            confidence=1.0,
            signal_ids=signal_ids,
            policy_rule_ids=[str(rule.id)],
            finding_id=finding.id,
            authorization_mode=authorization_mode,
            explanation=finding.explanation,
        )

    def decide_from_policy_monitor(
        self,
        *,
        ai_system_id: UUID,
        trajectory_id: UUID | None,
        runtime_identity_id: UUID | None,
        agent_id: UUID | None = None,
        agent_version_id: UUID | None = None,
        tool_name: str | None = None,
        tool_id: str | None = None,
        signal_ids: list[str] | None = None,
        reason: str | None = None,
        monitor_duration_seconds: int = 1800,
    ) -> Any:
        """Activate MARK_AND_MONITOR when a tool/policy effect is MONITOR.

        Tool-rule MONITOR decisions previously only flagged the receipt; they
        never created a RiskMonitor row, so /risk/monitoring stayed empty.
        """
        effect = InterventionEffect.MARK_AND_MONITOR.value
        scope_type = (
            RiskScopeType.RUNTIME_IDENTITY.value
            if runtime_identity_id
            else RiskScopeType.AI_SYSTEM.value
        )
        scope_id = str(runtime_identity_id or ai_system_id)
        tool_label = tool_name or tool_id or "action"
        description = reason or (
            f"Policy MONITOR effect on tool '{tool_label}' — "
            "elevated monitoring activated"
        )
        finding = self._repo.create_finding(
            trajectory_id=trajectory_id,
            ai_system_id=ai_system_id,
            agent_id=agent_id,
            agent_version_id=agent_version_id,
            runtime_identity_id=runtime_identity_id,
            finding_type="POLICY_MONITOR",
            title=f"Policy monitor: {tool_label}",
            description=description,
            severity=RiskSeverity.MEDIUM.value,
            confidence=1.0,
            sensitivity="NORMAL",
            dimensions={
                "severity": RiskSeverity.MEDIUM.value,
                "confidence": 1.0,
            },
            signal_ids=signal_ids or [],
            evidence_refs=[],
            policy_rule_ids=[],
            intervention_effect=effect,
            status=FindingStatus.MONITORING.value,
            explanation={
                "observed": description,
                "tool_name": tool_name,
                "tool_id": tool_id,
                "why_intervention": (
                    "Configured tool/policy effect MONITOR maps to MARK_AND_MONITOR"
                ),
            },
        )
        expires = datetime.now(timezone.utc) + timedelta(
            seconds=monitor_duration_seconds
        )
        existing = self._repo.get_active_monitor(
            scope_type=scope_type, scope_id=scope_id
        )
        if not existing:
            self._repo.create_monitor(
                ai_system_id=ai_system_id,
                monitor_rule_id=None,
                scope_type=scope_type,
                scope_id=scope_id,
                reason=description,
                status="ACTIVE",
                current_count=1,
                current_sum=0.0,
                threshold=None,
                expires_at=expires,
                finding_id=finding.id,
            )
        else:
            existing.current_count = int(existing.current_count or 0) + 1
            existing.reason = description
            if existing.expires_at is None or existing.expires_at < expires:
                existing.expires_at = expires
            if not existing.finding_id:
                existing.finding_id = finding.id
            self._db.flush()

        self._risk_state.set_monitoring(
            ai_system_id=ai_system_id,
            scope_type=scope_type,
            scope_id=scope_id,
            active=True,
            require_approval=False,
        )

        return self._create_and_maybe_execute(
            ai_system_id=ai_system_id,
            trajectory_id=trajectory_id,
            scope_type=scope_type,
            scope_id=scope_id,
            effect=effect,
            reason=description,
            risk_level=RiskSeverity.MEDIUM.value,
            confidence=1.0,
            signal_ids=signal_ids or [],
            policy_rule_ids=[],
            finding_id=finding.id,
            authorization_mode=InterventionAuthorizationMode.AUTO_FOR_CONFIGURED_SIGNALS.value,
            explanation=finding.explanation,
        )

    def decide_from_repeated_denial(
        self,
        *,
        ai_system_id: UUID,
        trajectory_id: UUID | None,
        runtime_identity_id: UUID,
        deny_count: int,
        signal_ids: list[str],
        auto_suspend: bool = False,
    ) -> Any:
        effect = (
            InterventionEffect.SUSPEND_RUNTIME_IDENTITY.value
            if auto_suspend
            else InterventionEffect.MARK_AND_MONITOR.value
        )
        finding = self._repo.create_finding(
            trajectory_id=trajectory_id,
            ai_system_id=ai_system_id,
            runtime_identity_id=runtime_identity_id,
            finding_type="REPEATED_DENIAL",
            title="Repeated denied actions",
            description=f"{deny_count} DENY decisions in 2 minutes",
            severity=RiskSeverity.HIGH.value,
            confidence=1.0,
            sensitivity="HIGH",
            dimensions={"severity": RiskSeverity.HIGH.value, "confidence": 1.0},
            signal_ids=signal_ids,
            intervention_effect=effect,
            status=FindingStatus.OPEN.value,
            explanation={
                "observed": f"{deny_count} denies in 120s",
                "why_intervention": (
                    "Auto-suspend"
                    if auto_suspend
                    else "Recommend suspension / mark and monitor"
                ),
            },
        )
        mode = (
            InterventionAuthorizationMode.AUTO_FOR_CONFIGURED_SIGNALS.value
            if auto_suspend
            else InterventionAuthorizationMode.RECOMMEND_ONLY.value
        )
        return self._create_and_maybe_execute(
            ai_system_id=ai_system_id,
            trajectory_id=trajectory_id,
            scope_type=RiskScopeType.RUNTIME_IDENTITY.value,
            scope_id=str(runtime_identity_id),
            effect=effect
            if auto_suspend
            else InterventionEffect.SUSPEND_RUNTIME_IDENTITY.value,
            reason=finding.description,
            risk_level=RiskSeverity.HIGH.value,
            confidence=1.0,
            signal_ids=signal_ids,
            policy_rule_ids=[],
            finding_id=finding.id,
            authorization_mode=mode,
            explanation=finding.explanation,
            force_recommend=not auto_suspend,
        )

    def confirm_intervention(
        self,
        intervention_id: UUID,
        *,
        executed_by: str,
    ) -> Any:
        intervention = self._repo.get_intervention(intervention_id)
        if not intervention:
            raise LookupError("Intervention not found")
        if intervention.status not in (
            InterventionStatus.RECOMMENDED.value,
            InterventionStatus.PENDING_CONFIRMATION.value,
        ):
            raise ValueError(
                f"Cannot confirm intervention in status {intervention.status}"
            )
        return self._execute(intervention, executed_by=executed_by, automatic=False)

    def cancel_intervention(
        self,
        intervention_id: UUID,
        *,
        cancelled_by: str,
    ) -> Any:
        intervention = self._repo.get_intervention(intervention_id)
        if not intervention:
            raise LookupError("Intervention not found")
        intervention.status = InterventionStatus.CANCELLED.value
        intervention.executed_by = cancelled_by
        self._db.flush()
        return intervention

    def _create_and_maybe_execute(
        self,
        *,
        ai_system_id: UUID,
        trajectory_id: UUID | None,
        scope_type: str,
        scope_id: str,
        effect: str,
        reason: str | None,
        risk_level: str | None,
        confidence: float | None,
        signal_ids: list[str],
        policy_rule_ids: list[str],
        finding_id: UUID | None,
        authorization_mode: str,
        explanation: dict[str, Any] | None,
        force_recommend: bool = False,
    ) -> Any:
        auto = self._should_auto_execute(
            effect=effect,
            risk_level=risk_level,
            authorization_mode=authorization_mode,
            force_recommend=force_recommend,
        )
        status = (
            InterventionStatus.EXECUTED.value
            if False  # set after execute
            else (
                InterventionStatus.PENDING_CONFIRMATION.value
                if not auto
                and effect
                in (
                    InterventionEffect.SUSPEND_RUNTIME_IDENTITY.value,
                    InterventionEffect.DENY.value,
                    InterventionEffect.EMERGENCY_STOP.value,
                )
                and SEVERITY_RANK.get(risk_level or "", 0)
                >= SEVERITY_RANK[RiskSeverity.HIGH.value]
                and authorization_mode
                == InterventionAuthorizationMode.HUMAN_CONFIRM_HIGH_CRITICAL.value
                else InterventionStatus.RECOMMENDED.value
            )
        )
        # Soft effects always auto-apply (MARK / MONITOR)
        if effect in (
            InterventionEffect.PASS.value,
            InterventionEffect.MARK.value,
            InterventionEffect.MARK_AND_MONITOR.value,
            InterventionEffect.REQUIRE_APPROVAL.value,
            InterventionEffect.DENY.value,
        ):
            auto = True if effect != InterventionEffect.PASS.value else False
            if effect == InterventionEffect.DENY.value:
                # DENY is a decision emitted for WP4; mark as executed decision
                auto = True

        if force_recommend:
            auto = False
            status = InterventionStatus.RECOMMENDED.value

        intervention = self._repo.create_intervention(
            trajectory_id=trajectory_id,
            ai_system_id=ai_system_id,
            scope_type=scope_type,
            scope_id=scope_id,
            effect=effect,
            reason=reason,
            risk_level=risk_level,
            confidence=confidence,
            triggering_signal_ids=signal_ids,
            policy_rule_ids=policy_rule_ids,
            finding_id=finding_id,
            status=status,
            authorization_mode=authorization_mode,
            automatic=auto,
            explanation=explanation,
        )
        if auto:
            return self._execute(intervention, executed_by="system", automatic=True)
        return intervention

    def _should_auto_execute(
        self,
        *,
        effect: str,
        risk_level: str | None,
        authorization_mode: str,
        force_recommend: bool,
    ) -> bool:
        if force_recommend:
            return False
        if authorization_mode == InterventionAuthorizationMode.RECOMMEND_ONLY.value:
            return effect in (
                InterventionEffect.MARK.value,
                InterventionEffect.MARK_AND_MONITOR.value,
            )
        if effect in (
            InterventionEffect.MARK.value,
            InterventionEffect.MARK_AND_MONITOR.value,
            InterventionEffect.REQUIRE_APPROVAL.value,
            InterventionEffect.DENY.value,
        ):
            return True
        if effect == InterventionEffect.SUSPEND_RUNTIME_IDENTITY.value:
            if (
                authorization_mode
                == InterventionAuthorizationMode.AUTO_FOR_CONFIGURED_SIGNALS.value
            ):
                return True
            if (
                authorization_mode
                == InterventionAuthorizationMode.AUTO_FOR_LOW_MEDIUM.value
                and SEVERITY_RANK.get(risk_level or "", 0)
                < SEVERITY_RANK[RiskSeverity.HIGH.value]
            ):
                return True
            return False
        if effect == InterventionEffect.EMERGENCY_STOP.value:
            # Kill switch is always human-confirm for HIGH/CRITICAL unless
            # explicitly configured for auto signals.
            return (
                authorization_mode
                == InterventionAuthorizationMode.AUTO_FOR_CONFIGURED_SIGNALS.value
            )
        return False

    def _execute(self, intervention: Any, *, executed_by: str, automatic: bool) -> Any:
        effect = intervention.effect
        if effect == InterventionEffect.MARK_AND_MONITOR.value:
            self._risk_state.set_monitoring(
                ai_system_id=intervention.ai_system_id,
                scope_type=intervention.scope_type,
                scope_id=intervention.scope_id,
                active=True,
                require_approval=False,
            )
            if not self._repo.get_active_monitor(
                scope_type=intervention.scope_type, scope_id=intervention.scope_id
            ):
                self._repo.create_monitor(
                    ai_system_id=intervention.ai_system_id,
                    monitor_rule_id=None,
                    scope_type=intervention.scope_type,
                    scope_id=intervention.scope_id,
                    reason=intervention.reason,
                    status="ACTIVE",
                    expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
                    finding_id=intervention.finding_id,
                )
        elif effect == InterventionEffect.REQUIRE_APPROVAL.value:
            self._risk_state.set_monitoring(
                ai_system_id=intervention.ai_system_id,
                scope_type=intervention.scope_type,
                scope_id=intervention.scope_id,
                active=True,
                require_approval=True,
            )
        elif effect == InterventionEffect.CONSTRAIN.value:
            self._repo.create_constraint(
                ai_system_id=intervention.ai_system_id,
                scope_type=intervention.scope_type,
                scope_id=intervention.scope_id,
                constraint_type="READ_ONLY",
                reason=intervention.reason,
                status="ACTIVE",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                intervention_id=intervention.id,
            )
        elif effect == InterventionEffect.SUSPEND_RUNTIME_IDENTITY.value:
            try:
                from rai_gateway.identity.service import RuntimeIdentityService

                if intervention.scope_type == RiskScopeType.RUNTIME_IDENTITY.value:
                    RuntimeIdentityService(self._db).suspend_runtime_identity(
                        UUID(intervention.scope_id),
                        updated_by=executed_by,
                        reason=intervention.reason,
                    )
            except Exception:
                logger.exception("Failed to suspend runtime identity")
                intervention.status = InterventionStatus.PENDING_CONFIRMATION.value
                self._db.flush()
                return intervention
        elif effect == InterventionEffect.EMERGENCY_STOP.value:
            try:
                self._execute_emergency_stop(intervention, executed_by=executed_by)
            except Exception:
                logger.exception("Failed to execute emergency stop")
                intervention.status = InterventionStatus.PENDING_CONFIRMATION.value
                self._db.flush()
                return intervention

        intervention.status = InterventionStatus.EXECUTED.value
        intervention.executed_at = datetime.now(timezone.utc)
        intervention.executed_by = executed_by
        intervention.automatic = automatic
        self._db.flush()
        try:
            from rai_gateway.evidence.domain import (
                EvidenceEventType,
                EvidenceSourceType,
            )
            from rai_gateway.risk_intelligence.evidence_projection import (
                project_operational_event,
            )

            project_operational_event(
                self._db,
                event_type=EvidenceEventType.INTERVENTION_DECIDED.value,
                source_type=EvidenceSourceType.RAI_AUTHORITATIVE.value,
                payload={
                    "intervention_id": str(intervention.id),
                    "effect": intervention.effect,
                    "status": intervention.status,
                    "automatic": automatic,
                    "executed_by": executed_by,
                    "reason": intervention.reason,
                },
                trajectory_id=intervention.trajectory_id,
                ai_system_id=intervention.ai_system_id,
                runtime_identity_id=(
                    UUID(intervention.scope_id)
                    if intervention.scope_type == RiskScopeType.RUNTIME_IDENTITY.value
                    else None
                ),
            )
        except Exception:
            logger.exception("Failed to project intervention evidence")
        return intervention

    def _execute_emergency_stop(self, intervention: Any, *, executed_by: str) -> None:
        """Authoritative kill: stop AI system + suspend identities + deny overlay."""
        from rai_gateway.identity.domain import RuntimeIdentityStatus
        from rai_gateway.identity.service import RuntimeIdentityService
        from rai_gateway.models.identity import AgentRuntimeIdentity
        from rai_gateway.models.registry import Agent, AISystem
        from rai_gateway.registry.domain import AISystemStatus

        system = (
            self._db.query(AISystem)
            .filter(AISystem.id == intervention.ai_system_id)
            .first()
        )
        if system and system.status != AISystemStatus.STOPPED.value:
            system.status = AISystemStatus.STOPPED.value
            system.updated_by = executed_by

        agents = (
            self._db.query(Agent)
            .filter(Agent.ai_system_id == intervention.ai_system_id)
            .all()
        )
        identity_svc = RuntimeIdentityService(self._db)
        for agent in agents:
            identities = (
                self._db.query(AgentRuntimeIdentity)
                .filter(
                    AgentRuntimeIdentity.agent_id == agent.id,
                    AgentRuntimeIdentity.status == RuntimeIdentityStatus.ACTIVE.value,
                )
                .all()
            )
            for identity in identities:
                try:
                    identity_svc.suspend_runtime_identity(
                        identity.id,
                        updated_by=executed_by,
                        reason=intervention.reason or "EMERGENCY_STOP",
                    )
                except Exception:
                    logger.exception(
                        "Emergency stop failed to suspend identity %s", identity.id
                    )

        # Scope-level deny flag for hot-path overlay (system + optional identity)
        self._risk_state.set_monitoring(
            ai_system_id=intervention.ai_system_id,
            scope_type=RiskScopeType.AI_SYSTEM.value,
            scope_id=str(intervention.ai_system_id),
            active=True,
            require_approval=False,
        )
        sys_state = self._repo.get_risk_state(
            RiskScopeType.AI_SYSTEM.value, str(intervention.ai_system_id)
        )
        if sys_state:
            dims = dict(sys_state.dimensions or {})
            dims["emergency_stopped"] = True
            dims["emergency_stop_intervention_id"] = str(intervention.id)
            sys_state.dimensions = dims
            sys_state.current_level = RiskSeverity.CRITICAL.value
            self._db.flush()

        if intervention.scope_type == RiskScopeType.RUNTIME_IDENTITY.value:
            self._risk_state.set_monitoring(
                ai_system_id=intervention.ai_system_id,
                scope_type=intervention.scope_type,
                scope_id=intervention.scope_id,
                active=True,
                require_approval=False,
            )

    @staticmethod
    def serialize(intervention: Any) -> dict[str, Any]:
        return {
            "id": str(intervention.id),
            "trajectory_id": str(intervention.trajectory_id)
            if intervention.trajectory_id
            else None,
            "ai_system_id": str(intervention.ai_system_id),
            "scope_type": intervention.scope_type,
            "scope_id": intervention.scope_id,
            "effect": intervention.effect,
            "reason": intervention.reason,
            "risk_level": intervention.risk_level,
            "confidence": intervention.confidence,
            "triggering_signal_ids": intervention.triggering_signal_ids,
            "policy_rule_ids": intervention.policy_rule_ids,
            "finding_id": str(intervention.finding_id)
            if intervention.finding_id
            else None,
            "status": intervention.status,
            "authorization_mode": intervention.authorization_mode,
            "automatic": intervention.automatic,
            "explanation": intervention.explanation,
            "executed_at": intervention.executed_at.isoformat()
            if intervention.executed_at
            else None,
            "executed_by": intervention.executed_by,
            "created_at": intervention.created_at.isoformat()
            if intervention.created_at
            else None,
        }
