"""Deterministic explainable anomaly detectors for WP6 continuous oversight."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from rai_gateway.risk_intelligence.domain import (
    AnomalyType,
    RiskSeverity,
    RiskSignalType,
)
from rai_gateway.risk_intelligence.repository import RiskIntelligenceRepository

logger = logging.getLogger(__name__)


# Explicit thresholds (explainable baselines — no ML)
REPEATED_DENY_THRESHOLD = 10
REPEATED_DENY_WINDOW_SECONDS = 120
REPEATED_APPROVAL_THRESHOLD = 5
REPEATED_APPROVAL_WINDOW_SECONDS = 300
TOOL_FREQUENCY_DEFAULT_THRESHOLD = 20
TOOL_FREQUENCY_WINDOW_SECONDS = 600
HIGH_VALUE_BURST_DEFAULT = 500_000.0
HIGH_VALUE_BURST_WINDOW_SECONDS = 3600
MODEL_MISMATCH_THRESHOLD = 3
MODEL_MISMATCH_WINDOW_SECONDS = 3600
RISK_SPIKE_SCORE_DELTA = 40


class AnomalyDetector:
    """Run deterministic detectors and materialize findings with explanations."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._repo = RiskIntelligenceRepository(db)

    def detect_after_enforcement(
        self,
        *,
        ai_system_id: UUID,
        runtime_identity_id: UUID | None,
        agent_id: UUID | None = None,
        agent_version_id: UUID | None = None,
        trajectory_id: UUID | None = None,
        decision: str | None = None,
        tool_name: str | None = None,
        amount: float | None = None,
        previous_risk_level: str | None = None,
        current_risk_level: str | None = None,
        current_score: int | None = None,
        previous_score: int | None = None,
        score_drivers: list[str] | None = None,
    ) -> list[Any]:
        findings: list[Any] = []
        if runtime_identity_id:
            findings.extend(
                self._repeated_denied_action(
                    ai_system_id=ai_system_id,
                    runtime_identity_id=runtime_identity_id,
                    agent_id=agent_id,
                    agent_version_id=agent_version_id,
                    trajectory_id=trajectory_id,
                )
            )
            findings.extend(
                self._repeated_approval_required(
                    ai_system_id=ai_system_id,
                    runtime_identity_id=runtime_identity_id,
                    agent_id=agent_id,
                    agent_version_id=agent_version_id,
                    trajectory_id=trajectory_id,
                )
            )
            if tool_name:
                findings.extend(
                    self._unusual_tool_frequency(
                        ai_system_id=ai_system_id,
                        runtime_identity_id=runtime_identity_id,
                        agent_id=agent_id,
                        agent_version_id=agent_version_id,
                        trajectory_id=trajectory_id,
                        tool_name=tool_name,
                    )
                )
            findings.extend(
                self._high_value_burst(
                    ai_system_id=ai_system_id,
                    runtime_identity_id=runtime_identity_id,
                    agent_id=agent_id,
                    agent_version_id=agent_version_id,
                    trajectory_id=trajectory_id,
                    tool_name=tool_name,
                )
            )
            findings.extend(
                self._repeated_model_mismatch(
                    ai_system_id=ai_system_id,
                    runtime_identity_id=runtime_identity_id,
                    agent_id=agent_id,
                    agent_version_id=agent_version_id,
                    trajectory_id=trajectory_id,
                )
            )

        spike = self._risk_score_spike(
            ai_system_id=ai_system_id,
            runtime_identity_id=runtime_identity_id,
            agent_id=agent_id,
            agent_version_id=agent_version_id,
            trajectory_id=trajectory_id,
            previous_risk_level=previous_risk_level,
            current_risk_level=current_risk_level,
            previous_score=previous_score,
            current_score=current_score,
            score_drivers=score_drivers,
        )
        if spike:
            findings.append(spike)
        return findings

    def list_anomalies(
        self,
        *,
        ai_system_id: UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Any]:
        anomaly_types = [t.value for t in AnomalyType]
        findings = self._repo.list_findings(
            ai_system_id=ai_system_id,
            limit=limit * 3,
            offset=0,
        )
        filtered = [f for f in findings if f.finding_type in anomaly_types]
        return filtered[offset : offset + limit]

    def _dedupe_open(
        self,
        *,
        ai_system_id: UUID,
        runtime_identity_id: UUID | None,
        finding_type: str,
    ) -> bool:
        existing = self._repo.list_findings(
            ai_system_id=ai_system_id,
            finding_type=finding_type,
            status="OPEN",
            limit=20,
        )
        for f in existing:
            if runtime_identity_id and f.runtime_identity_id == runtime_identity_id:
                return True
            if not runtime_identity_id:
                return True
        return False

    def _create_finding(
        self,
        *,
        ai_system_id: UUID,
        runtime_identity_id: UUID | None,
        agent_id: UUID | None,
        agent_version_id: UUID | None,
        trajectory_id: UUID | None,
        anomaly_type: str,
        title: str,
        description: str,
        severity: str,
        observed_value: float,
        threshold: float,
        window_seconds: int,
        tool_name: str | None = None,
        drivers: list[str] | None = None,
        signal_ids: list[str] | None = None,
    ) -> Any:
        if self._dedupe_open(
            ai_system_id=ai_system_id,
            runtime_identity_id=runtime_identity_id,
            finding_type=anomaly_type,
        ):
            return None
        explanation = {
            "anomaly_type": anomaly_type,
            "observed_value": observed_value,
            "threshold": threshold,
            "baseline": threshold,
            "window_seconds": window_seconds,
            "tool_name": tool_name,
            "drivers": drivers or [],
            "detector": "deterministic_threshold",
        }
        finding = self._repo.create_finding(
            trajectory_id=trajectory_id,
            ai_system_id=ai_system_id,
            agent_id=agent_id,
            agent_version_id=agent_version_id,
            runtime_identity_id=runtime_identity_id,
            finding_type=anomaly_type,
            title=title,
            description=description,
            severity=severity,
            confidence=1.0,
            sensitivity="HIGH" if severity in ("HIGH", "CRITICAL") else "NORMAL",
            category="anomaly",
            dimensions={
                "severity": severity,
                "confidence": 1.0,
                "frequency": observed_value,
            },
            signal_ids=signal_ids or [],
            evidence_refs=[
                {
                    "type": "anomaly_explanation",
                    **explanation,
                }
            ],
            status="OPEN",
            explanation=explanation,
        )
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
                event_type=EvidenceEventType.ANOMALY_DETECTED.value,
                source_type=EvidenceSourceType.DERIVED.value,
                payload={
                    "finding_id": str(finding.id),
                    "anomaly_type": anomaly_type,
                    "explanation": explanation,
                },
                trajectory_id=trajectory_id,
                ai_system_id=ai_system_id,
                runtime_identity_id=runtime_identity_id,
            )
        except Exception:
            logger.exception("Failed to project anomaly evidence")
        return finding

    def _repeated_denied_action(self, **ctx: Any) -> list[Any]:
        since = datetime.now(timezone.utc) - timedelta(
            seconds=REPEATED_DENY_WINDOW_SECONDS
        )
        signals = self._repo.list_signals(
            ai_system_id=ctx["ai_system_id"],
            runtime_identity_id=ctx["runtime_identity_id"],
            signal_type=RiskSignalType.REPEATED_DENIAL.value,
            since=since,
            limit=500,
        )
        # Count DENY decision payloads (hot-path emits one per deny)
        count = sum(
            1
            for s in signals
            if (s.payload or {}).get("decision") == "DENY"
            or (s.payload or {}).get("deny_count")
        )
        # Also count severity-elevated aggregate signals
        for s in signals:
            if (s.payload or {}).get("deny_count"):
                count = max(count, int((s.payload or {}).get("deny_count") or 0))
        if count < REPEATED_DENY_THRESHOLD:
            return []
        finding = self._create_finding(
            ai_system_id=ctx["ai_system_id"],
            runtime_identity_id=ctx["runtime_identity_id"],
            agent_id=ctx.get("agent_id"),
            agent_version_id=ctx.get("agent_version_id"),
            trajectory_id=ctx.get("trajectory_id"),
            anomaly_type=AnomalyType.REPEATED_DENIED_ACTION.value,
            title="Repeated denied actions",
            description=(
                f"{count} DENY decisions within {REPEATED_DENY_WINDOW_SECONDS}s "
                f"(threshold {REPEATED_DENY_THRESHOLD})"
            ),
            severity=RiskSeverity.HIGH.value,
            observed_value=float(count),
            threshold=float(REPEATED_DENY_THRESHOLD),
            window_seconds=REPEATED_DENY_WINDOW_SECONDS,
            signal_ids=[str(s.id) for s in signals[:20]],
        )
        return [finding] if finding else []

    def _repeated_approval_required(self, **ctx: Any) -> list[Any]:
        since = datetime.now(timezone.utc) - timedelta(
            seconds=REPEATED_APPROVAL_WINDOW_SECONDS
        )
        signals = self._repo.list_signals(
            ai_system_id=ctx["ai_system_id"],
            runtime_identity_id=ctx["runtime_identity_id"],
            signal_type=RiskSignalType.REPEATED_APPROVAL_REQUIRED.value,
            since=since,
            limit=500,
        )
        count = len(signals)
        if count < REPEATED_APPROVAL_THRESHOLD:
            return []
        finding = self._create_finding(
            ai_system_id=ctx["ai_system_id"],
            runtime_identity_id=ctx["runtime_identity_id"],
            agent_id=ctx.get("agent_id"),
            agent_version_id=ctx.get("agent_version_id"),
            trajectory_id=ctx.get("trajectory_id"),
            anomaly_type=AnomalyType.REPEATED_APPROVAL_REQUIRED.value,
            title="Repeated approval-required actions",
            description=(
                f"{count} APPROVAL_REQUIRED outcomes within "
                f"{REPEATED_APPROVAL_WINDOW_SECONDS}s "
                f"(threshold {REPEATED_APPROVAL_THRESHOLD})"
            ),
            severity=RiskSeverity.MEDIUM.value,
            observed_value=float(count),
            threshold=float(REPEATED_APPROVAL_THRESHOLD),
            window_seconds=REPEATED_APPROVAL_WINDOW_SECONDS,
            signal_ids=[str(s.id) for s in signals[:20]],
        )
        return [finding] if finding else []

    def _unusual_tool_frequency(self, *, tool_name: str, **ctx: Any) -> list[Any]:
        since = datetime.now(timezone.utc) - timedelta(
            seconds=TOOL_FREQUENCY_WINDOW_SECONDS
        )
        signals = self._repo.list_signals(
            ai_system_id=ctx["ai_system_id"],
            runtime_identity_id=ctx["runtime_identity_id"],
            signal_type=RiskSignalType.UNUSUAL_TOOL_FREQUENCY.value,
            since=since,
            limit=500,
        )
        count = sum(
            1 for s in signals if (s.payload or {}).get("tool_name") == tool_name
        )
        if count < TOOL_FREQUENCY_DEFAULT_THRESHOLD:
            return []
        finding = self._create_finding(
            ai_system_id=ctx["ai_system_id"],
            runtime_identity_id=ctx["runtime_identity_id"],
            agent_id=ctx.get("agent_id"),
            agent_version_id=ctx.get("agent_version_id"),
            trajectory_id=ctx.get("trajectory_id"),
            anomaly_type=AnomalyType.UNUSUAL_TOOL_FREQUENCY.value,
            title=f"Unusual tool frequency: {tool_name}",
            description=(
                f"Observed {count} calls to {tool_name} within "
                f"{TOOL_FREQUENCY_WINDOW_SECONDS}s "
                f"(threshold {TOOL_FREQUENCY_DEFAULT_THRESHOLD})"
            ),
            severity=RiskSeverity.HIGH.value,
            observed_value=float(count),
            threshold=float(TOOL_FREQUENCY_DEFAULT_THRESHOLD),
            window_seconds=TOOL_FREQUENCY_WINDOW_SECONDS,
            tool_name=tool_name,
            signal_ids=[str(s.id) for s in signals[:20]],
        )
        return [finding] if finding else []

    def _high_value_burst(self, *, tool_name: str | None, **ctx: Any) -> list[Any]:
        since = datetime.now(timezone.utc) - timedelta(
            seconds=HIGH_VALUE_BURST_WINDOW_SECONDS
        )
        signals = self._repo.list_signals(
            ai_system_id=ctx["ai_system_id"],
            runtime_identity_id=ctx["runtime_identity_id"],
            signal_type=RiskSignalType.HIGH_VALUE_ACTION.value,
            since=since,
            limit=500,
        )
        total = 0.0
        for s in signals:
            if tool_name and (s.payload or {}).get("tool_name") != tool_name:
                continue
            amt = (s.payload or {}).get("amount")
            if amt is not None:
                try:
                    total += float(amt)
                except (TypeError, ValueError):
                    continue
        if total < HIGH_VALUE_BURST_DEFAULT:
            return []
        finding = self._create_finding(
            ai_system_id=ctx["ai_system_id"],
            runtime_identity_id=ctx["runtime_identity_id"],
            agent_id=ctx.get("agent_id"),
            agent_version_id=ctx.get("agent_version_id"),
            trajectory_id=ctx.get("trajectory_id"),
            anomaly_type=AnomalyType.HIGH_VALUE_BURST.value,
            title="High-value burst detected",
            description=(
                f"SUM amount {total:.2f} within {HIGH_VALUE_BURST_WINDOW_SECONDS}s "
                f"(threshold {HIGH_VALUE_BURST_DEFAULT})"
            ),
            severity=RiskSeverity.HIGH.value,
            observed_value=total,
            threshold=HIGH_VALUE_BURST_DEFAULT,
            window_seconds=HIGH_VALUE_BURST_WINDOW_SECONDS,
            tool_name=tool_name,
            signal_ids=[str(s.id) for s in signals[:20]],
        )
        return [finding] if finding else []

    def _repeated_model_mismatch(self, **ctx: Any) -> list[Any]:
        since = datetime.now(timezone.utc) - timedelta(
            seconds=MODEL_MISMATCH_WINDOW_SECONDS
        )
        signals = self._repo.list_signals(
            ai_system_id=ctx["ai_system_id"],
            runtime_identity_id=ctx["runtime_identity_id"],
            signal_type=RiskSignalType.MODEL_MISMATCH.value,
            since=since,
            limit=100,
        )
        count = len(signals)
        if count < MODEL_MISMATCH_THRESHOLD:
            return []
        finding = self._create_finding(
            ai_system_id=ctx["ai_system_id"],
            runtime_identity_id=ctx["runtime_identity_id"],
            agent_id=ctx.get("agent_id"),
            agent_version_id=ctx.get("agent_version_id"),
            trajectory_id=ctx.get("trajectory_id"),
            anomaly_type=AnomalyType.REPEATED_MODEL_MISMATCH.value,
            title="Repeated model mismatch",
            description=(
                f"{count} model mismatch signals within "
                f"{MODEL_MISMATCH_WINDOW_SECONDS}s "
                f"(threshold {MODEL_MISMATCH_THRESHOLD})"
            ),
            severity=RiskSeverity.HIGH.value,
            observed_value=float(count),
            threshold=float(MODEL_MISMATCH_THRESHOLD),
            window_seconds=MODEL_MISMATCH_WINDOW_SECONDS,
            signal_ids=[str(s.id) for s in signals[:20]],
        )
        return [finding] if finding else []

    def _risk_score_spike(self, **ctx: Any) -> Any | None:
        prev_level = ctx.get("previous_risk_level")
        curr_level = ctx.get("current_risk_level")
        prev_score = ctx.get("previous_score")
        curr_score = ctx.get("current_score")
        drivers = ctx.get("score_drivers") or []

        spiked = False
        observed = 0.0
        if prev_score is not None and curr_score is not None:
            delta = int(curr_score) - int(prev_score)
            observed = float(delta)
            if delta >= RISK_SPIKE_SCORE_DELTA:
                spiked = True
        level_order = {"NONE": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
        if (
            prev_level
            and curr_level
            and level_order.get(curr_level, 0) - level_order.get(prev_level, 0) >= 2
        ):
            spiked = True
            observed = float(
                level_order.get(curr_level, 0) - level_order.get(prev_level, 0)
            )

        if not spiked:
            return None

        driver_text = ", ".join(drivers[:8]) if drivers else "accumulated risk signals"
        return self._create_finding(
            ai_system_id=ctx["ai_system_id"],
            runtime_identity_id=ctx.get("runtime_identity_id"),
            agent_id=ctx.get("agent_id"),
            agent_version_id=ctx.get("agent_version_id"),
            trajectory_id=ctx.get("trajectory_id"),
            anomaly_type=AnomalyType.RISK_SCORE_SPIKE.value,
            title="Risk score spike",
            description=(
                f"Risk elevated {prev_level or '?'} → {curr_level or '?'} "
                f"(score {prev_score} → {curr_score}) because of: {driver_text}"
            ),
            severity=RiskSeverity.HIGH.value,
            observed_value=observed,
            threshold=float(RISK_SPIKE_SCORE_DELTA),
            window_seconds=0,
            drivers=list(drivers),
        )
