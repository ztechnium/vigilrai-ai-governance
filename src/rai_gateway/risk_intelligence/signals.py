"""Deterministic risk signal extraction from WP5 evidence patterns."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from rai_gateway.models.evidence import (
    EvidenceEvent,
    EvidenceFinding,
    RuntimeTrajectory,
)
from rai_gateway.risk_intelligence.domain import (
    RiskScopeType,
    RiskSensitivity,
    RiskSeverity,
    RiskSignalType,
)
from rai_gateway.risk_intelligence.repository import RiskIntelligenceRepository


class SignalExtractor:
    """Extract continuous deterministic risk signals from evidence."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._repo = RiskIntelligenceRepository(db)

    def extract_from_trajectory(self, trajectory_id: UUID) -> list[Any]:
        trajectory = (
            self._db.query(RuntimeTrajectory)
            .filter(RuntimeTrajectory.id == trajectory_id)
            .first()
        )
        if not trajectory:
            return []

        created = []
        created.extend(self._from_evidence_findings(trajectory))
        created.extend(self._repeated_denials(trajectory))
        created.extend(self._tool_frequency(trajectory))
        return created

    def extract_from_receipt_context(
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
    ) -> list[Any]:
        """Lightweight signal extraction on enforcement decisions (hot path safe)."""
        created = []
        now = datetime.now(timezone.utc)
        if decision == "DENY" and runtime_identity_id:
            signal = self._repo.create_signal(
                trajectory_id=trajectory_id,
                ai_system_id=ai_system_id,
                agent_id=agent_id,
                agent_version_id=agent_version_id,
                runtime_identity_id=runtime_identity_id,
                signal_type=RiskSignalType.REPEATED_DENIAL.value,
                source_type="RAI_AUTHORITATIVE",
                confidence=1.0,
                severity=RiskSeverity.MEDIUM.value,
                sensitivity=RiskSensitivity.NORMAL.value,
                dimensions={
                    "severity": RiskSeverity.MEDIUM.value,
                    "confidence": 1.0,
                },
                evidence_refs=[],
                payload={
                    "decision": decision,
                    "tool_name": tool_name,
                    "tool_id": tool_id,
                },
                occurred_at=now,
            )
            created.append(signal)

        if (
            decision in ("REQUIRE_APPROVAL", "APPROVAL_REQUIRED")
            and runtime_identity_id
        ):
            signal = self._repo.create_signal(
                trajectory_id=trajectory_id,
                ai_system_id=ai_system_id,
                agent_id=agent_id,
                agent_version_id=agent_version_id,
                runtime_identity_id=runtime_identity_id,
                signal_type=RiskSignalType.REPEATED_APPROVAL_REQUIRED.value,
                source_type="RAI_AUTHORITATIVE",
                confidence=1.0,
                severity=RiskSeverity.MEDIUM.value,
                sensitivity=RiskSensitivity.NORMAL.value,
                dimensions={
                    "severity": RiskSeverity.MEDIUM.value,
                    "confidence": 1.0,
                },
                evidence_refs=[],
                payload={
                    "decision": decision,
                    "tool_name": tool_name,
                    "tool_id": tool_id,
                },
                occurred_at=now,
            )
            created.append(signal)

        if tool_name or tool_id:
            signal = self._repo.create_signal(
                trajectory_id=trajectory_id,
                ai_system_id=ai_system_id,
                agent_id=agent_id,
                agent_version_id=agent_version_id,
                runtime_identity_id=runtime_identity_id,
                signal_type=RiskSignalType.UNUSUAL_TOOL_FREQUENCY.value,
                source_type="RAI_AUTHORITATIVE",
                confidence=1.0,
                severity=RiskSeverity.INFO.value,
                sensitivity=RiskSensitivity.NORMAL.value,
                dimensions={
                    "severity": RiskSeverity.INFO.value,
                    "confidence": 1.0,
                },
                evidence_refs=[],
                payload={
                    "tool_name": tool_name,
                    "tool_id": tool_id,
                    "decision": decision,
                    "amount": amount,
                    "parameters": parameters or {},
                },
                occurred_at=now,
            )
            created.append(signal)

        if amount is not None and amount > 0:
            signal = self._repo.create_signal(
                trajectory_id=trajectory_id,
                ai_system_id=ai_system_id,
                agent_id=agent_id,
                agent_version_id=agent_version_id,
                runtime_identity_id=runtime_identity_id,
                signal_type=RiskSignalType.HIGH_VALUE_ACTION.value,
                source_type="RAI_AUTHORITATIVE",
                confidence=1.0,
                severity=RiskSeverity.MEDIUM.value
                if amount >= 10000
                else RiskSeverity.LOW.value,
                sensitivity=RiskSensitivity.HIGH.value
                if amount >= 100000
                else RiskSensitivity.NORMAL.value,
                dimensions={
                    "severity": RiskSeverity.MEDIUM.value,
                    "confidence": 1.0,
                    "impact": amount,
                },
                evidence_refs=[],
                payload={
                    "amount": amount,
                    "tool_name": tool_name,
                    "tool_id": tool_id,
                },
                occurred_at=now,
            )
            created.append(signal)

        return created

    def _from_evidence_findings(self, trajectory: RuntimeTrajectory) -> list[Any]:
        findings = (
            self._db.query(EvidenceFinding)
            .filter(EvidenceFinding.trajectory_id == trajectory.id)
            .all()
        )
        mapping = {
            "OBSERVED_MODEL_MISMATCH": (
                RiskSignalType.MODEL_MISMATCH.value,
                RiskSeverity.HIGH.value,
            ),
            "REPEATED_DENIED_ACTION": (
                RiskSignalType.REPEATED_DENIAL.value,
                RiskSeverity.HIGH.value,
            ),
            "EVIDENCE_GAP": (
                RiskSignalType.MISSING_EVIDENCE.value,
                RiskSeverity.MEDIUM.value,
            ),
            "MISSING_EXECUTION_RESULT": (
                RiskSignalType.MISSING_EVIDENCE.value,
                RiskSeverity.MEDIUM.value,
            ),
            "UNVERIFIED_ENFORCEMENT": (
                RiskSignalType.UNVERIFIED_RUNTIME.value,
                RiskSeverity.HIGH.value,
            ),
        }
        created = []
        for finding in findings:
            mapped = mapping.get(finding.finding_type)
            if not mapped:
                continue
            signal_type, severity = mapped
            # Avoid duplicate signals for same evidence finding
            recent = self._repo.list_signals(
                trajectory_id=trajectory.id,
                signal_type=signal_type,
                limit=50,
            )
            if any(
                (s.payload or {}).get("evidence_finding_id") == str(finding.id)
                for s in recent
            ):
                continue
            signal = self._repo.create_signal(
                trajectory_id=trajectory.id,
                ai_system_id=trajectory.ai_system_id,
                agent_id=trajectory.agent_id,
                agent_version_id=trajectory.agent_version_id,
                runtime_identity_id=trajectory.runtime_identity_id,
                signal_type=signal_type,
                source_type="DERIVED",
                confidence=1.0,
                severity=severity,
                sensitivity=RiskSensitivity.NORMAL.value,
                dimensions={"severity": severity, "confidence": 1.0},
                evidence_refs=[{"type": "evidence_finding", "id": str(finding.id)}],
                payload={
                    "evidence_finding_id": str(finding.id),
                    "finding_type": finding.finding_type,
                    "title": finding.title,
                },
                occurred_at=finding.created_at or datetime.now(timezone.utc),
            )
            created.append(signal)
        return created

    def _repeated_denials(self, trajectory: RuntimeTrajectory) -> list[Any]:
        """Emit HIGH REPEATED_DENIAL when >=10 DENY events in 2 minutes for identity."""
        if not trajectory.runtime_identity_id:
            return []
        since = datetime.now(timezone.utc) - timedelta(minutes=2)
        deny_events = (
            self._db.query(EvidenceEvent)
            .join(
                RuntimeTrajectory,
                RuntimeTrajectory.id == EvidenceEvent.trajectory_id,
            )
            .filter(
                RuntimeTrajectory.runtime_identity_id == trajectory.runtime_identity_id,
                EvidenceEvent.event_type == "ACTION_DENIED",
                EvidenceEvent.occurred_at >= since,
            )
            .count()
        )
        if deny_events < 10:
            return []
        signal = self._repo.create_signal(
            trajectory_id=trajectory.id,
            ai_system_id=trajectory.ai_system_id,
            agent_id=trajectory.agent_id,
            agent_version_id=trajectory.agent_version_id,
            runtime_identity_id=trajectory.runtime_identity_id,
            signal_type=RiskSignalType.REPEATED_DENIAL.value,
            source_type="DERIVED",
            confidence=1.0,
            severity=RiskSeverity.HIGH.value,
            sensitivity=RiskSensitivity.HIGH.value,
            dimensions={
                "severity": RiskSeverity.HIGH.value,
                "confidence": 1.0,
                "frequency": float(deny_events),
            },
            evidence_refs=[],
            payload={
                "deny_count": deny_events,
                "window_seconds": 120,
                "scope": RiskScopeType.RUNTIME_IDENTITY.value,
            },
            occurred_at=datetime.now(timezone.utc),
        )
        return [signal]

    def _tool_frequency(self, trajectory: RuntimeTrajectory) -> list[Any]:
        # Frequency thresholds are evaluated by RiskEngine against monitor rules.
        return []
