"""Risk engine — evaluates signals, monitors, and drives interventions."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from rai_gateway.risk_intelligence.anomaly import AnomalyDetector
from rai_gateway.risk_intelligence.domain import (
    RiskSignalType,
)
from rai_gateway.risk_intelligence.intervention import InterventionService
from rai_gateway.risk_intelligence.repository import RiskIntelligenceRepository
from rai_gateway.risk_intelligence.risk_state import RiskStateService
from rai_gateway.risk_intelligence.signals import SignalExtractor

logger = logging.getLogger(__name__)


def _nested_get(data: dict[str, Any], path: str) -> Any:
    cur: Any = data
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


class RiskEngine:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._repo = RiskIntelligenceRepository(db)
        self._signals = SignalExtractor(db)
        self._state = RiskStateService(db)
        self._interventions = InterventionService(db)
        self._anomalies = AnomalyDetector(db)

    def process_trajectory(self, trajectory_id: UUID) -> dict[str, Any]:
        signals = self._signals.extract_from_trajectory(trajectory_id)
        for signal in signals:
            self._state.apply_signal(signal)

        # Pull trajectory context for monitor evaluation
        from rai_gateway.models.evidence import RuntimeTrajectory

        trajectory = (
            self._db.query(RuntimeTrajectory)
            .filter(RuntimeTrajectory.id == trajectory_id)
            .first()
        )
        monitor_results = []
        if trajectory:
            monitor_results = self.evaluate_monitor_rules(
                ai_system_id=trajectory.ai_system_id,
                runtime_identity_id=trajectory.runtime_identity_id,
                trajectory_id=trajectory.id,
            )
            # Repeated denial intervention
            for signal in signals:
                if (
                    signal.signal_type == RiskSignalType.REPEATED_DENIAL.value
                    and signal.severity == "HIGH"
                    and (signal.payload or {}).get("deny_count", 0) >= 10
                ):
                    self._interventions.decide_from_repeated_denial(
                        ai_system_id=trajectory.ai_system_id,
                        trajectory_id=trajectory.id,
                        runtime_identity_id=trajectory.runtime_identity_id,
                        deny_count=int((signal.payload or {}).get("deny_count") or 0),
                        signal_ids=[str(signal.id)],
                        auto_suspend=False,
                    )

        return {
            "signals_created": len(signals),
            "monitor_triggers": len(monitor_results),
        }

    def process_enforcement_event(
        self,
        *,
        ai_system_id: UUID,
        agent_id: UUID | None,
        agent_version_id: UUID | None,
        runtime_identity_id: UUID | None,
        trajectory_id: UUID | None,
        decision: str,
        tool_name: str | None = None,
        tool_id: str | None = None,
        parameters: dict[str, Any] | None = None,
        amount: float | None = None,
    ) -> dict[str, Any]:
        prev_state = None
        if runtime_identity_id:
            prev_state = self._repo.get_risk_state(
                "RUNTIME_IDENTITY", str(runtime_identity_id)
            )
        prev_level = prev_state.current_level if prev_state else None
        prev_score = prev_state.cumulative_score if prev_state else 0

        signals = self._signals.extract_from_receipt_context(
            ai_system_id=ai_system_id,
            agent_id=agent_id,
            agent_version_id=agent_version_id,
            runtime_identity_id=runtime_identity_id,
            trajectory_id=trajectory_id,
            decision=decision,
            tool_name=tool_name,
            tool_id=tool_id,
            parameters=parameters,
            amount=amount,
        )
        for signal in signals:
            self._state.apply_signal(signal)

        monitor_results = []
        if runtime_identity_id:
            monitor_results = self.evaluate_monitor_rules(
                ai_system_id=ai_system_id,
                runtime_identity_id=runtime_identity_id,
                trajectory_id=trajectory_id,
                tool_name=tool_name,
                amount=amount,
            )

        # Tool/policy MONITOR must activate a RiskMonitor (feeds /risk/monitoring).
        policy_monitor = None
        if str(decision or "").upper() == "MONITOR":
            policy_monitor = self._interventions.decide_from_policy_monitor(
                ai_system_id=ai_system_id,
                trajectory_id=trajectory_id,
                runtime_identity_id=runtime_identity_id,
                agent_id=agent_id,
                agent_version_id=agent_version_id,
                tool_name=tool_name,
                tool_id=tool_id,
                signal_ids=[str(s.id) for s in signals],
            )
            if policy_monitor is not None:
                monitor_results.append(policy_monitor)

        curr_state = None
        if runtime_identity_id:
            curr_state = self._repo.get_risk_state(
                "RUNTIME_IDENTITY", str(runtime_identity_id)
            )
        anomaly_findings = self._anomalies.detect_after_enforcement(
            ai_system_id=ai_system_id,
            runtime_identity_id=runtime_identity_id,
            agent_id=agent_id,
            agent_version_id=agent_version_id,
            trajectory_id=trajectory_id,
            decision=decision,
            tool_name=tool_name,
            amount=amount,
            previous_risk_level=prev_level,
            current_risk_level=curr_state.current_level if curr_state else None,
            previous_score=prev_score,
            current_score=curr_state.cumulative_score if curr_state else None,
            score_drivers=(
                list((curr_state.score_breakdown or {}).get("drivers") or [])
                if curr_state
                else []
            ),
        )
        return {
            "signals_created": len(signals),
            "monitor_triggers": len(monitor_results),
            "anomalies": len(anomaly_findings),
        }

    def process_content_evaluation(
        self,
        *,
        ai_system_id: UUID,
        trajectory_id: UUID | None,
        runtime_identity_id: UUID | None,
        agent_id: UUID | None,
        agent_version_id: UUID | None,
        evaluation_result: dict[str, Any],
    ) -> dict[str, Any]:
        hints = evaluation_result.get("intervention_hints") or []
        if not hints:
            return {"signals_created": 0, "findings": 0, "interventions": 0}

        signal_ids: list[str] = []
        now = datetime.now(timezone.utc)
        for hint in hints:
            signal = self._repo.create_signal(
                trajectory_id=trajectory_id,
                ai_system_id=ai_system_id,
                agent_id=agent_id,
                agent_version_id=agent_version_id,
                runtime_identity_id=runtime_identity_id,
                signal_type=RiskSignalType.CONTENT_POLICY_VIOLATION.value,
                source_type="DERIVED",
                confidence=float(hint.get("confidence") or 0),
                severity=hint.get("severity") or "MEDIUM",
                sensitivity="NORMAL",
                dimensions={
                    "severity": hint.get("severity") or "MEDIUM",
                    "confidence": float(hint.get("confidence") or 0),
                },
                evidence_refs=[{"spans": hint.get("evidence_spans") or []}],
                category=hint.get("category"),
                payload={
                    "rule_id": hint.get("rule_id"),
                    "rule_effect": hint.get("rule_effect"),
                    "suggested_intervention": hint.get("suggested_intervention"),
                    "reason": hint.get("reason"),
                    "evaluation_id": evaluation_result.get("id"),
                },
                occurred_at=now,
            )
            self._state.apply_signal(signal)
            signal_ids.append(str(signal.id))

        decisions = self._interventions.decide_from_content_hints(
            ai_system_id=ai_system_id,
            trajectory_id=trajectory_id,
            runtime_identity_id=runtime_identity_id,
            agent_id=agent_id,
            agent_version_id=agent_version_id,
            hints=hints,
            signal_ids=signal_ids,
        )
        return {
            "signals_created": len(signal_ids),
            "findings": len(decisions),
            "interventions": len(decisions),
            "intervention_ids": [str(d.id) for d in decisions],
            "dominant_effect": decisions[-1].effect if decisions else "PASS",
        }

    def evaluate_monitor_rules(
        self,
        *,
        ai_system_id: UUID,
        runtime_identity_id: UUID | None,
        trajectory_id: UUID | None = None,
        tool_name: str | None = None,
        amount: float | None = None,
    ) -> list[Any]:
        rules = self._repo.list_monitor_rules(
            ai_system_id=ai_system_id, enabled_only=True
        )
        triggered = []
        for rule in rules:
            if rule.tool_name and tool_name and rule.tool_name != tool_name:
                # Still evaluate from window history even if this event is unrelated
                pass

            measured = 0.0
            if rule.aggregation == "COUNT":
                # Count tool frequency signals matching tool
                since = datetime.now(timezone.utc) - timedelta(
                    seconds=rule.window_seconds
                )
                signals = self._repo.list_signals(
                    ai_system_id=ai_system_id,
                    runtime_identity_id=runtime_identity_id,
                    signal_type=rule.signal_type
                    or RiskSignalType.UNUSUAL_TOOL_FREQUENCY.value,
                    since=since,
                    limit=500,
                )
                if rule.tool_name:
                    measured = float(
                        sum(
                            1
                            for s in signals
                            if (s.payload or {}).get("tool_name") == rule.tool_name
                        )
                    )
                elif rule.signal_type:
                    measured = float(len(signals))
                else:
                    measured = float(len(signals))
            elif rule.aggregation == "SUM":
                since = datetime.now(timezone.utc) - timedelta(
                    seconds=rule.window_seconds
                )
                signals = self._repo.list_signals(
                    ai_system_id=ai_system_id,
                    runtime_identity_id=runtime_identity_id,
                    signal_type=RiskSignalType.HIGH_VALUE_ACTION.value,
                    since=since,
                    limit=500,
                )
                total = 0.0
                for s in signals:
                    if (
                        rule.tool_name
                        and (s.payload or {}).get("tool_name") != rule.tool_name
                    ):
                        continue
                    amt = (s.payload or {}).get("amount")
                    if amt is None and rule.amount_parameter_path:
                        params = (s.payload or {}).get("parameters") or {}
                        amt = _nested_get(params, rule.amount_parameter_path)
                    if amt is not None:
                        try:
                            total += float(amt)
                        except (TypeError, ValueError):
                            continue
                measured = total
            elif rule.aggregation == "MAX":
                since = datetime.now(timezone.utc) - timedelta(
                    seconds=rule.window_seconds
                )
                signals = self._repo.list_signals(
                    ai_system_id=ai_system_id,
                    runtime_identity_id=runtime_identity_id,
                    signal_type=rule.signal_type
                    or RiskSignalType.HIGH_VALUE_ACTION.value,
                    since=since,
                    limit=500,
                )
                peak = 0.0
                for s in signals:
                    if (
                        rule.tool_name
                        and (s.payload or {}).get("tool_name") != rule.tool_name
                    ):
                        continue
                    amt = (s.payload or {}).get("amount")
                    if amt is None and rule.amount_parameter_path:
                        params = (s.payload or {}).get("parameters") or {}
                        amt = _nested_get(params, rule.amount_parameter_path)
                    if amt is not None:
                        try:
                            peak = max(peak, float(amt))
                        except (TypeError, ValueError):
                            continue
                measured = peak
            else:
                continue

            if measured < float(rule.threshold):
                continue

            # Avoid re-triggering if an active monitor already exists for this rule+scope
            existing = self._repo.get_active_monitor(
                scope_type="RUNTIME_IDENTITY" if runtime_identity_id else "AI_SYSTEM",
                scope_id=str(runtime_identity_id or ai_system_id),
            )
            if existing and existing.monitor_rule_id == rule.id:
                continue

            decision = self._interventions.decide_from_monitor(
                ai_system_id=ai_system_id,
                trajectory_id=trajectory_id,
                runtime_identity_id=runtime_identity_id,
                rule=rule,
                measured_value=measured,
                signal_ids=[],
            )
            triggered.append(decision)
        return triggered

    def get_authorization_overlay(
        self,
        *,
        ai_system_id: UUID,
        runtime_identity_id: UUID,
        tool_id: UUID | None = None,
    ) -> dict[str, Any]:
        """WP4 consumes this before final allow — never replaces WP4."""
        effective = self._state.get_effective_risk_for_identity(
            ai_system_id=ai_system_id,
            runtime_identity_id=runtime_identity_id,
        )
        # Also check AI system scope require_approval
        sys_state = self._repo.get_risk_state("AI_SYSTEM", str(ai_system_id))
        require_approval = bool(effective.get("require_approval"))
        if sys_state and sys_state.require_approval:
            require_approval = True

        deny = False
        deny_reason = None
        # Active DENY / EMERGENCY_STOP interventions for this identity or system
        interventions = self._repo.list_interventions(
            ai_system_id=ai_system_id, status="EXECUTED", limit=50
        )
        for iv in interventions:
            if iv.effect == "EMERGENCY_STOP":
                deny = True
                deny_reason = iv.reason or "AI system emergency stopped"
                break
            if iv.scope_id == str(runtime_identity_id) and iv.effect == "DENY":
                # Content DENY is action-scoped; only apply as soft flag for overlay
                # Real DENY for content is applied synchronously on evaluate path.
                pass

        # Authoritative STOPPED lifecycle also deny immediately
        from rai_gateway.models.registry import AISystem
        from rai_gateway.registry.domain import AISystemStatus

        system = self._db.query(AISystem).filter(AISystem.id == ai_system_id).first()
        if system and system.status == AISystemStatus.STOPPED.value:
            deny = True
            deny_reason = deny_reason or "AI system is STOPPED (emergency stop)"

        if sys_state and (sys_state.dimensions or {}).get("emergency_stopped"):
            deny = True
            deny_reason = deny_reason or "AI system emergency stopped"

        constrained_tools: list[str] = []
        for c in effective.get("constraints") or []:
            if c.get("constraint_type") == "DISABLE_TOOL" and c.get("resource_id"):
                constrained_tools.append(c["resource_id"])
            if (
                tool_id
                and c.get("constraint_type") == "DISABLE_TOOL"
                and c.get("resource_id") == str(tool_id)
            ):
                deny = True
                deny_reason = c.get("reason") or "Tool disabled by runtime constraint"

        return {
            "require_approval": require_approval,
            "monitoring": effective.get("monitoring"),
            "risk_state": effective.get("risk_state"),
            "deny": deny,
            "deny_reason": deny_reason,
            "constrained_tools": constrained_tools,
            "constraints": effective.get("constraints") or [],
        }
