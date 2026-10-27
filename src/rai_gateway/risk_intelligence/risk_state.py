"""Risk state aggregation and explainable scoring."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from rai_gateway.models.risk_intelligence import RiskSignal
from rai_gateway.risk_intelligence.domain import (
    SEVERITY_RANK,
    RiskLevel,
    RiskScopeType,
    RiskScoreBreakdown,
    RiskSeverity,
    dominant_severity,
)
from rai_gateway.risk_intelligence.repository import RiskIntelligenceRepository

SCORE_BY_SEVERITY = {
    RiskSeverity.INFO.value: 2,
    RiskSeverity.LOW.value: 8,
    RiskSeverity.MEDIUM.value: 18,
    RiskSeverity.HIGH.value: 30,
    RiskSeverity.CRITICAL.value: 45,
}


def level_from_score(score: int, high_count: int) -> str:
    if high_count >= 1 and score >= 45:
        return RiskLevel.CRITICAL.value
    if score >= 70 or high_count >= 3:
        return RiskLevel.CRITICAL.value
    if score >= 45:
        return RiskLevel.HIGH.value
    if score >= 25:
        return RiskLevel.MEDIUM.value
    if score >= 8:
        return RiskLevel.LOW.value
    return RiskLevel.NONE.value


class RiskStateService:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._repo = RiskIntelligenceRepository(db)

    def apply_signal(self, signal: RiskSignal) -> list[Any]:
        """Update risk states for all relevant scopes of a signal."""
        scopes: list[tuple[str, str]] = []
        if signal.trajectory_id:
            scopes.append((RiskScopeType.TRAJECTORY.value, str(signal.trajectory_id)))
        if signal.runtime_identity_id:
            scopes.append(
                (
                    RiskScopeType.RUNTIME_IDENTITY.value,
                    str(signal.runtime_identity_id),
                )
            )
        if signal.agent_version_id:
            scopes.append(
                (RiskScopeType.AGENT_VERSION.value, str(signal.agent_version_id))
            )
        if signal.agent_id:
            scopes.append((RiskScopeType.AGENT.value, str(signal.agent_id)))
        scopes.append((RiskScopeType.AI_SYSTEM.value, str(signal.ai_system_id)))

        updated = []
        for scope_type, scope_id in scopes:
            updated.append(
                self._upsert_from_signal(
                    signal, scope_type=scope_type, scope_id=scope_id
                )
            )
        return updated

    def _upsert_from_signal(
        self, signal: RiskSignal, *, scope_type: str, scope_id: str
    ) -> Any:
        existing = self._repo.get_risk_state(scope_type, scope_id)
        add = SCORE_BY_SEVERITY.get(signal.severity, 5)
        drivers = []
        if existing and existing.score_breakdown:
            drivers = list(existing.score_breakdown.get("drivers") or [])
        drivers.append(f"+ {signal.severity} {signal.signal_type}")
        drivers = drivers[-12:]

        signal_count = (existing.signal_count if existing else 0) + 1
        high_count = existing.high_severity_count if existing else 0
        if (
            SEVERITY_RANK.get(signal.severity, 0)
            >= SEVERITY_RANK[RiskSeverity.HIGH.value]
        ):
            high_count += 1
        score = min(100, (existing.cumulative_score if existing else 0) + add)
        level = level_from_score(score, high_count)
        dims = {
            "severity": dominant_severity(
                [signal.severity]
                + (
                    [existing.dimensions.get("severity")]
                    if existing and existing.dimensions
                    else []
                )
            ),
            "confidence": signal.confidence,
            "sensitivity": signal.sensitivity,
        }
        return self._repo.upsert_risk_state(
            ai_system_id=signal.ai_system_id,
            scope_type=scope_type,
            scope_id=scope_id,
            current_level=level,
            cumulative_score=score,
            signal_count=signal_count,
            high_severity_count=high_count,
            score_breakdown=RiskScoreBreakdown(score=score, drivers=drivers).to_dict(),
            dimensions=dims,
            last_signal_at=signal.occurred_at or datetime.now(timezone.utc),
            monitoring_status=existing.monitoring_status if existing else "NONE",
            require_approval=existing.require_approval if existing else False,
        )

    def set_monitoring(
        self,
        *,
        ai_system_id: UUID,
        scope_type: str,
        scope_id: str,
        active: bool,
        require_approval: bool = False,
    ) -> Any:
        existing = self._repo.get_risk_state(scope_type, scope_id)
        return self._repo.upsert_risk_state(
            ai_system_id=ai_system_id,
            scope_type=scope_type,
            scope_id=scope_id,
            current_level=existing.current_level if existing else RiskLevel.LOW.value,
            cumulative_score=existing.cumulative_score if existing else 0,
            signal_count=existing.signal_count if existing else 0,
            high_severity_count=existing.high_severity_count if existing else 0,
            score_breakdown=existing.score_breakdown if existing else None,
            dimensions=existing.dimensions if existing else None,
            last_signal_at=existing.last_signal_at if existing else None,
            monitoring_status="ACTIVE" if active else "NONE",
            require_approval=require_approval
            or (existing.require_approval if existing else False),
        )

    def get_effective_risk_for_identity(
        self, *, ai_system_id: UUID, runtime_identity_id: UUID
    ) -> dict[str, Any]:
        state = self._repo.get_risk_state(
            RiskScopeType.RUNTIME_IDENTITY.value, str(runtime_identity_id)
        )
        constraints = self._repo.list_active_constraints(
            ai_system_id=ai_system_id,
            scope_type=RiskScopeType.RUNTIME_IDENTITY.value,
            scope_id=str(runtime_identity_id),
        )
        monitor = self._repo.get_active_monitor(
            scope_type=RiskScopeType.RUNTIME_IDENTITY.value,
            scope_id=str(runtime_identity_id),
        )
        return {
            "risk_state": self.serialize_state(state) if state else None,
            "require_approval": bool(
                (state and state.require_approval) or (monitor is not None and False)
            ),
            "monitoring": monitor is not None,
            "constraints": [self.serialize_constraint(c) for c in constraints],
        }

    @staticmethod
    def serialize_state(state: Any) -> dict[str, Any]:
        return {
            "id": str(state.id),
            "ai_system_id": str(state.ai_system_id),
            "scope_type": state.scope_type,
            "scope_id": state.scope_id,
            "current_level": state.current_level,
            "cumulative_score": state.cumulative_score,
            "signal_count": state.signal_count,
            "high_severity_count": state.high_severity_count,
            "score_breakdown": state.score_breakdown,
            "dimensions": state.dimensions,
            "last_signal_at": state.last_signal_at.isoformat()
            if state.last_signal_at
            else None,
            "monitoring_status": state.monitoring_status,
            "require_approval": state.require_approval,
            "updated_at": state.updated_at.isoformat() if state.updated_at else None,
        }

    @staticmethod
    def serialize_constraint(c: Any) -> dict[str, Any]:
        return {
            "id": str(c.id),
            "scope_type": c.scope_type,
            "scope_id": c.scope_id,
            "resource_type": c.resource_type,
            "resource_id": c.resource_id,
            "constraint_type": c.constraint_type,
            "value": c.value,
            "reason": c.reason,
            "status": c.status,
            "expires_at": c.expires_at.isoformat() if c.expires_at else None,
        }
