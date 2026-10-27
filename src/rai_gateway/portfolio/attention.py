"""Executive attention queue — deterministic recommended actions + source drill-down."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from rai_gateway.evaluations.domain import AssuranceStatus, WaiverStatus
from rai_gateway.governance.domain import (
    ControlAssessmentStatus,
    ExceptionStatus,
    IncidentSeverity,
    IncidentStatus,
    ReviewStatus,
)
from rai_gateway.models.evaluations import AssuranceRecord, EvaluationWaiver
from rai_gateway.models.evidence import RuntimeTrajectory
from rai_gateway.models.governance import (
    AIIncident,
    AISystemAccountability,
    ControlAssessment,
    GovernanceException,
    GovernanceReview,
    PeriodicReviewSchedule,
    Pilot,
    PilotReadinessEvaluation,
)
from rai_gateway.models.identity import AgentRuntimeIdentity
from rai_gateway.models.registry import Agent, RiskAssessment, RiskFinding
from rai_gateway.models.risk_intelligence import RiskSignal, RuntimeRiskFinding
from rai_gateway.portfolio.domain import (
    ATTENTION_ACTIONS,
    AttentionSeverity,
    AttentionType,
)
from rai_gateway.portfolio.queries import _ser_dt, org_system_ids


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _item(
    *,
    attention_type: AttentionType,
    severity: AttentionSeverity,
    title: str,
    ai_system_id: UUID | None,
    source_type: str,
    source_id: str,
    reason: str,
    due_at: datetime | None = None,
    agent_version_id: UUID | None = None,
    drill_down: str | None = None,
) -> dict[str, Any]:
    return {
        "type": attention_type.value,
        "severity": severity.value,
        "title": title,
        "ai_system_id": str(ai_system_id) if ai_system_id else None,
        "agent_version_id": str(agent_version_id) if agent_version_id else None,
        "source_type": source_type,
        "source_id": source_id,
        "due_at": _ser_dt(due_at),
        "reason": reason,
        "recommended_action": ATTENTION_ACTIONS[attention_type],
        "drill_down": drill_down,
        "created_at": _ser_dt(_utcnow()),
    }


def build_attention_queue(
    db: Session,
    *,
    limit: int = 200,
) -> dict[str, Any]:
    system_ids = org_system_ids(db)
    now = _utcnow()
    items: list[dict[str, Any]] = []

    # Critical / high open runtime findings
    if system_ids:
        for finding in (
            db.query(RuntimeRiskFinding)
            .filter(
                RuntimeRiskFinding.ai_system_id.in_(system_ids),
                RuntimeRiskFinding.status == "OPEN",
                RuntimeRiskFinding.severity.in_(["CRITICAL", "HIGH"]),
            )
            .limit(50)
            .all()
        ):
            sev = (
                AttentionSeverity.CRITICAL
                if finding.severity == "CRITICAL"
                else AttentionSeverity.HIGH
            )
            items.append(
                _item(
                    attention_type=AttentionType.CRITICAL_RISK_FINDING,
                    severity=sev,
                    title=finding.title,
                    ai_system_id=finding.ai_system_id,
                    source_type="RUNTIME_RISK_FINDING",
                    source_id=str(finding.id),
                    reason=f"Open {finding.severity} runtime risk finding",
                    drill_down=f"/risk/findings?ai_system_id={finding.ai_system_id}",
                )
            )
        for finding in (
            db.query(RiskFinding)
            .join(RiskAssessment, RiskAssessment.id == RiskFinding.risk_assessment_id)
            .filter(
                RiskAssessment.ai_system_id.in_(system_ids),
                RiskFinding.status == "OPEN",
                RiskFinding.severity.in_(["CRITICAL", "HIGH"]),
            )
            .limit(50)
            .all()
        ):
            assessment = (
                db.query(RiskAssessment)
                .filter(RiskAssessment.id == finding.risk_assessment_id)
                .first()
            )
            sid = assessment.ai_system_id if assessment else None
            items.append(
                _item(
                    attention_type=AttentionType.CRITICAL_RISK_FINDING,
                    severity=AttentionSeverity.CRITICAL
                    if finding.severity == "CRITICAL"
                    else AttentionSeverity.HIGH,
                    title=finding.title,
                    ai_system_id=sid,
                    source_type="RISK_FINDING",
                    source_id=str(finding.id),
                    reason=f"Open {finding.severity} design-time risk finding",
                    drill_down=f"/risk/findings?ai_system_id={sid}"
                    if sid
                    else "/risk/findings",
                )
            )

        # Expired / failed assurance
        for rec in (
            db.query(AssuranceRecord)
            .filter(
                AssuranceRecord.ai_system_id.in_(system_ids),
                AssuranceRecord.superseded_at.is_(None),
                AssuranceRecord.status.in_(
                    [
                        AssuranceStatus.EXPIRED.value,
                        AssuranceStatus.FAILED.value,
                        AssuranceStatus.INVALIDATED.value,
                    ]
                ),
            )
            .all()
        ):
            items.append(
                _item(
                    attention_type=AttentionType.EXPIRED_PRODUCTION_ASSURANCE,
                    severity=AttentionSeverity.CRITICAL,
                    title=f"Assurance {rec.status}",
                    ai_system_id=rec.ai_system_id,
                    agent_version_id=rec.agent_version_id,
                    source_type="ASSURANCE_RECORD",
                    source_id=str(rec.id),
                    reason=f"Production assurance is {rec.status}",
                    due_at=rec.valid_until,
                    drill_down=f"/assurance/readiness?ai_system_id={rec.ai_system_id}",
                )
            )
        for rec in (
            db.query(AssuranceRecord)
            .filter(
                AssuranceRecord.ai_system_id.in_(system_ids),
                AssuranceRecord.superseded_at.is_(None),
                AssuranceRecord.valid_until.isnot(None),
                AssuranceRecord.valid_until <= now + timedelta(days=14),
                AssuranceRecord.valid_until > now,
                AssuranceRecord.status.in_(
                    [AssuranceStatus.VALID.value, AssuranceStatus.CONDITIONAL.value]
                ),
            )
            .all()
        ):
            items.append(
                _item(
                    attention_type=AttentionType.ASSURANCE_EXPIRING,
                    severity=AttentionSeverity.HIGH,
                    title="Assurance expiring soon",
                    ai_system_id=rec.ai_system_id,
                    agent_version_id=rec.agent_version_id,
                    source_type="ASSURANCE_RECORD",
                    source_id=str(rec.id),
                    reason=f"Assurance expires at {_ser_dt(rec.valid_until)}",
                    due_at=rec.valid_until,
                    drill_down=f"/assurance/readiness?ai_system_id={rec.ai_system_id}",
                )
            )

        # Expiring waivers
        for w in (
            db.query(EvaluationWaiver)
            .filter(
                EvaluationWaiver.ai_system_id.in_(system_ids),
                EvaluationWaiver.status == WaiverStatus.APPROVED.value,
                EvaluationWaiver.revoked_at.is_(None),
                EvaluationWaiver.valid_until.isnot(None),
                EvaluationWaiver.valid_until <= now + timedelta(days=14),
            )
            .all()
        ):
            items.append(
                _item(
                    attention_type=AttentionType.EXPIRING_WAIVER,
                    severity=AttentionSeverity.HIGH,
                    title="Evaluation waiver expiring",
                    ai_system_id=w.ai_system_id,
                    agent_version_id=w.agent_version_id,
                    source_type="EVALUATION_WAIVER",
                    source_id=str(w.id),
                    reason="Active waiver expires within 14 days",
                    due_at=w.valid_until,
                    drill_down=f"/assurance/waivers?ai_system_id={w.ai_system_id}",
                )
            )

        # Suspended runtime identities
        for identity, agent in (
            db.query(AgentRuntimeIdentity, Agent)
            .join(Agent, Agent.id == AgentRuntimeIdentity.agent_id)
            .filter(
                Agent.ai_system_id.in_(system_ids),
                AgentRuntimeIdentity.status == "SUSPENDED",
            )
            .all()
        ):
            items.append(
                _item(
                    attention_type=AttentionType.SUSPENDED_RUNTIME_IDENTITY,
                    severity=AttentionSeverity.HIGH,
                    title=f"Suspended runtime: {identity.name}",
                    ai_system_id=agent.ai_system_id,
                    agent_version_id=identity.agent_version_id,
                    source_type="RUNTIME_IDENTITY",
                    source_id=str(identity.id),
                    reason="Runtime identity is suspended",
                    drill_down=f"/governance/runtime-identities?ai_system_id={agent.ai_system_id}",
                )
            )

        # Evidence gaps
        incomplete_systems = {
            t.ai_system_id
            for t in db.query(RuntimeTrajectory)
            .filter(
                RuntimeTrajectory.ai_system_id.in_(system_ids),
                RuntimeTrajectory.completeness_pct.isnot(None),
                RuntimeTrajectory.completeness_pct < 80,
            )
            .all()
        }
        for sid in incomplete_systems:
            items.append(
                _item(
                    attention_type=AttentionType.PERSISTENT_EVIDENCE_GAP,
                    severity=AttentionSeverity.MEDIUM,
                    title="Evidence completeness gap",
                    ai_system_id=sid,
                    source_type="AI_SYSTEM",
                    source_id=str(sid),
                    reason="Trajectories with completeness below 80%",
                    drill_down=f"/runtime/trajectories?ai_system_id={sid}",
                )
            )

        # Repeated high-risk anomalies
        anomaly_counts: dict[UUID, int] = {}
        for signal in (
            db.query(RiskSignal)
            .filter(
                RiskSignal.ai_system_id.in_(system_ids),
                RiskSignal.signal_type == "ANOMALY",
                RiskSignal.severity.in_(["HIGH", "CRITICAL"]),
                RiskSignal.occurred_at >= now - timedelta(days=30),
            )
            .all()
        ):
            anomaly_counts[signal.ai_system_id] = (
                anomaly_counts.get(signal.ai_system_id, 0) + 1
            )
        for sid, count in anomaly_counts.items():
            if count >= 3:
                items.append(
                    _item(
                        attention_type=AttentionType.REPEATED_HIGH_RISK_ANOMALY,
                        severity=AttentionSeverity.HIGH,
                        title="Repeated high-risk anomalies",
                        ai_system_id=sid,
                        source_type="AI_SYSTEM",
                        source_id=str(sid),
                        reason=f"{count} high/critical anomalies in 30 days",
                        drill_down=f"/risk/anomalies?ai_system_id={sid}",
                    )
                )

    # Critical incidents
    for incident in (
        db.query(AIIncident)
        .filter(
            AIIncident.severity == IncidentSeverity.CRITICAL.value,
            ~AIIncident.status.in_(
                [IncidentStatus.RESOLVED.value, IncidentStatus.CLOSED.value]
            ),
        )
        .all()
    ):
        items.append(
            _item(
                attention_type=AttentionType.OPEN_CRITICAL_INCIDENT,
                severity=AttentionSeverity.CRITICAL,
                title=incident.title,
                ai_system_id=incident.ai_system_id,
                source_type="INCIDENT",
                source_id=str(incident.id),
                reason="Open CRITICAL incident",
                drill_down=f"/governance/incidents/{incident.id}",
            )
        )

    # Overdue reviews
    for review in (
        db.query(GovernanceReview)
        .filter(
            GovernanceReview.status.in_(
                [
                    ReviewStatus.REQUESTED.value,
                    ReviewStatus.IN_REVIEW.value,
                    ReviewStatus.DRAFT.value,
                ]
            ),
            GovernanceReview.due_at.isnot(None),
            GovernanceReview.due_at < now,
        )
        .all()
    ):
        items.append(
            _item(
                attention_type=AttentionType.OVERDUE_GOVERNANCE_REVIEW,
                severity=AttentionSeverity.HIGH,
                title=f"Overdue {review.review_type} review",
                ai_system_id=review.ai_system_id,
                source_type="GOVERNANCE_REVIEW",
                source_id=str(review.id),
                reason="Governance review past due date",
                due_at=review.due_at,
                drill_down=f"/governance/reviews/{review.id}",
            )
        )
    for schedule in (
        db.query(PeriodicReviewSchedule)
        .filter(
            PeriodicReviewSchedule.enabled.is_(True),
            PeriodicReviewSchedule.next_due_at < now,
        )
        .all()
    ):
        items.append(
            _item(
                attention_type=AttentionType.OVERDUE_GOVERNANCE_REVIEW,
                severity=AttentionSeverity.HIGH,
                title="Periodic review overdue",
                ai_system_id=schedule.ai_system_id,
                source_type="PERIODIC_REVIEW_SCHEDULE",
                source_id=str(schedule.id),
                reason="Periodic review schedule past next_due_at",
                due_at=schedule.next_due_at,
                drill_down=f"/governance/reviews?ai_system_id={schedule.ai_system_id}",
            )
        )

    # Expiring exceptions
    for exc in (
        db.query(GovernanceException)
        .filter(
            GovernanceException.status == ExceptionStatus.APPROVED.value,
            GovernanceException.valid_until.isnot(None),
            GovernanceException.valid_until <= now + timedelta(days=14),
        )
        .all()
    ):
        items.append(
            _item(
                attention_type=AttentionType.EXPIRING_EXCEPTION,
                severity=AttentionSeverity.HIGH,
                title="Exception expiring",
                ai_system_id=exc.ai_system_id,
                source_type="EXCEPTION",
                source_id=str(exc.id),
                reason="Approved exception expires within 14 days",
                due_at=exc.valid_until,
                drill_down=f"/governance/exceptions?ai_system_id={exc.ai_system_id}",
            )
        )

    # Missing accountability
    for acc in db.query(AISystemAccountability).all():
        if acc.business_owner_membership_id is None:
            items.append(
                _item(
                    attention_type=AttentionType.MISSING_REQUIRED_OWNER,
                    severity=AttentionSeverity.MEDIUM,
                    title="Missing Business Owner",
                    ai_system_id=acc.ai_system_id,
                    source_type="ACCOUNTABILITY",
                    source_id=str(acc.id),
                    reason="Business owner membership not assigned",
                    drill_down=f"/governance/registry/{acc.ai_system_id}",
                )
            )
    linked = {a.ai_system_id for a in db.query(AISystemAccountability).all()}
    for sid in system_ids:
        if sid not in linked:
            items.append(
                _item(
                    attention_type=AttentionType.MISSING_REQUIRED_OWNER,
                    severity=AttentionSeverity.MEDIUM,
                    title="Missing accountability record",
                    ai_system_id=sid,
                    source_type="AI_SYSTEM",
                    source_id=str(sid),
                    reason="No accountability assignment for AI system",
                    drill_down=f"/governance/registry/{sid}",
                )
            )

    # Pilot not ready
    for pilot in (
        db.query(Pilot)
        .filter(
            Pilot.status.in_(["PLANNING", "CONFIGURING", "READINESS_REVIEW"]),
        )
        .all()
    ):
        latest = (
            db.query(PilotReadinessEvaluation)
            .filter(
                PilotReadinessEvaluation.pilot_id == pilot.id,
            )
            .order_by(PilotReadinessEvaluation.evaluated_at.desc())
            .first()
        )
        if latest is None or latest.decision != "READY":
            items.append(
                _item(
                    attention_type=AttentionType.PILOT_NOT_READY,
                    severity=AttentionSeverity.MEDIUM,
                    title=f"Pilot not ready: {pilot.name}",
                    ai_system_id=None,
                    source_type="PILOT",
                    source_id=str(pilot.id),
                    reason=f"Pilot status={pilot.status}; readiness={latest.decision if latest else 'NOT_EVALUATED'}",
                    drill_down=f"/pilot?pilot_id={pilot.id}",
                )
            )

    # Control gaps (high signal only)
    for assessment in (
        db.query(ControlAssessment)
        .filter(
            ControlAssessment.applicability == "REQUIRED",
            ControlAssessment.status == ControlAssessmentStatus.NOT_SATISFIED.value,
        )
        .limit(50)
        .all()
    ):
        items.append(
            _item(
                attention_type=AttentionType.CONTROL_GAP,
                severity=AttentionSeverity.MEDIUM,
                title="Required control not satisfied",
                ai_system_id=assessment.ai_system_id,
                source_type="CONTROL_ASSESSMENT",
                source_id=str(assessment.id),
                reason="REQUIRED control assessment is NOT_SATISFIED",
                drill_down=f"/governance/controls?ai_system_id={assessment.ai_system_id}",
            )
        )

    severity_rank = {
        AttentionSeverity.CRITICAL.value: 0,
        AttentionSeverity.HIGH.value: 1,
        AttentionSeverity.MEDIUM.value: 2,
        AttentionSeverity.LOW.value: 3,
        AttentionSeverity.INFO.value: 4,
    }
    items.sort(
        key=lambda i: (severity_rank.get(i["severity"], 9), i.get("due_at") or "9999")
    )

    return {
        "freshness": "LIVE",
        "last_refreshed_at": _ser_dt(now),
        "count": min(len(items), limit),
        "items": items[:limit],
    }
