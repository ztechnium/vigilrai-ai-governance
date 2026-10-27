"""Read-oriented aggregation queries over WP1–WP8 authoritative state."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from rai_gateway.evaluations.domain import AssuranceStatus, WaiverStatus
from rai_gateway.governance.domain import (
    ControlAssessmentStatus,
    ExceptionStatus,
    IncidentSeverity,
    IncidentStatus,
    ReviewStatus,
)
from rai_gateway.models.approval import ApprovalRequest
from rai_gateway.models.evaluations import AssuranceRecord, EvaluationWaiver
from rai_gateway.models.evidence import RuntimeTrajectory
from rai_gateway.models.governance import (
    AIIncident,
    AISystemAccountability,
    AISystemGovernanceClassification,
    ControlAssessment,
    ControlMapping,
    ControlObjective,
    ControlRequirement,
    GovernanceException,
    GovernanceReview,
    PeriodicReviewSchedule,
    Pilot,
    PilotAISystem,
)
from rai_gateway.models.identity import AgentRuntimeIdentity
from rai_gateway.models.registry import (
    Agent,
    AgentVersion,
    AISystem,
    RiskAssessment,
    RiskFinding,
)
from rai_gateway.models.risk_intelligence import (
    RiskSignal,
    RiskState,
    RuntimeRiskFinding,
)
from rai_gateway.models.runtime_enforcement import RuntimeEnforcementReceipt
from rai_gateway.portfolio.domain import Freshness
from rai_gateway.portfolio.errors import PortfolioNotFoundError
from rai_gateway.registry.domain import AgentVersionStatus, AISystemStatus


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ser_dt(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _freshness_meta(freshness: Freshness = Freshness.LIVE) -> dict[str, Any]:
    return {
        "freshness": freshness.value,
        "last_refreshed_at": _ser_dt(_utcnow()),
    }


def org_systems(db: Session) -> list[AISystem]:
    return db.query(AISystem).order_by(AISystem.name.asc()).all()


def org_system_ids(db: Session) -> list[UUID]:
    return [s.id for s in org_systems(db)]


def assert_system_in_org(db: Session, ai_system_id: UUID) -> AISystem:
    system = db.query(AISystem).filter(AISystem.id == ai_system_id).first()
    if system is None:
        raise PortfolioNotFoundError(f"AI system {ai_system_id} not found")
    return system


def _production_version_ids(
    db: Session, system_ids: list[UUID]
) -> dict[UUID, UUID | None]:
    """Map ai_system_id → current APPROVED agent version id (best effort)."""
    result: dict[UUID, UUID | None] = {sid: None for sid in system_ids}
    if not system_ids:
        return result
    agents = db.query(Agent).filter(Agent.ai_system_id.in_(system_ids)).all()
    for agent in agents:
        if agent.current_version_id and result.get(agent.ai_system_id) is None:
            version = (
                db.query(AgentVersion)
                .filter(AgentVersion.id == agent.current_version_id)
                .first()
            )
            if (
                version
                and version.lifecycle_status == AgentVersionStatus.APPROVED.value
            ):
                result[agent.ai_system_id] = version.id
    return result


def _latest_assurance_by_system(
    db: Session, system_ids: list[UUID]
) -> dict[UUID, AssuranceRecord]:
    out: dict[UUID, AssuranceRecord] = {}
    if not system_ids:
        return out
    rows = (
        db.query(AssuranceRecord)
        .filter(
            AssuranceRecord.ai_system_id.in_(system_ids),
            AssuranceRecord.superseded_at.is_(None),
        )
        .order_by(AssuranceRecord.created_at.desc())
        .all()
    )
    for row in rows:
        if row.ai_system_id not in out:
            out[row.ai_system_id] = row
    return out


def _risk_level_by_system(db: Session, system_ids: list[UUID]) -> dict[UUID, str]:
    levels: dict[UUID, str] = {sid: "NONE" for sid in system_ids}
    if not system_ids:
        return levels
    rank = {
        "NONE": 0,
        "LOW": 1,
        "MEDIUM": 2,
        "HIGH": 3,
        "CRITICAL": 4,
    }
    # Design-time assessments
    assessments = (
        db.query(RiskAssessment)
        .filter(RiskAssessment.ai_system_id.in_(system_ids))
        .order_by(RiskAssessment.created_at.desc())
        .all()
    )
    seen: set[UUID] = set()
    for ra in assessments:
        if ra.ai_system_id in seen:
            continue
        seen.add(ra.ai_system_id)
        tier = (ra.risk_tier or "NONE").upper()
        if rank.get(tier, 0) > rank.get(levels[ra.ai_system_id], 0):
            levels[ra.ai_system_id] = tier
    # Runtime risk state
    states = (
        db.query(RiskState)
        .filter(
            RiskState.ai_system_id.in_(system_ids),
            RiskState.scope_type == "AI_SYSTEM",
        )
        .all()
    )
    for state in states:
        level = (state.current_level or "NONE").upper()
        if rank.get(level, 0) > rank.get(levels[state.ai_system_id], 0):
            levels[state.ai_system_id] = level
    return levels


def get_summary(db: Session) -> dict[str, Any]:
    systems = org_systems(db)
    system_ids = [s.id for s in systems]
    now = _utcnow()

    status_counts = Counter(s.status for s in systems)
    pilot_system_ids = {
        row.ai_system_id
        for row in db.query(PilotAISystem)
        .join(Pilot, Pilot.id == PilotAISystem.pilot_id)
        .all()
    }

    risk_levels = _risk_level_by_system(db, system_ids)
    high_risk = sum(1 for v in risk_levels.values() if v == "HIGH")
    critical_risk = sum(1 for v in risk_levels.values() if v == "CRITICAL")

    open_critical_findings = 0
    if system_ids:
        open_critical_findings = (
            db.query(RuntimeRiskFinding)
            .filter(
                RuntimeRiskFinding.ai_system_id.in_(system_ids),
                RuntimeRiskFinding.severity.in_(["HIGH", "CRITICAL"]),
                RuntimeRiskFinding.status == "OPEN",
            )
            .count()
        )
        open_critical_findings += (
            db.query(RiskFinding)
            .join(RiskAssessment, RiskAssessment.id == RiskFinding.risk_assessment_id)
            .filter(
                RiskAssessment.ai_system_id.in_(system_ids),
                RiskFinding.severity.in_(["HIGH", "CRITICAL"]),
                RiskFinding.status == "OPEN",
            )
            .count()
        )

    assurances = _latest_assurance_by_system(db, system_ids)
    assurance_counts = Counter(
        (a.status or "UNKNOWN").upper() for a in assurances.values()
    )

    open_incidents = (
        db.query(AIIncident)
        .filter(
            ~AIIncident.status.in_(
                [IncidentStatus.RESOLVED.value, IncidentStatus.CLOSED.value]
            ),
        )
        .count()
    )
    critical_incidents = (
        db.query(AIIncident)
        .filter(
            AIIncident.severity == IncidentSeverity.CRITICAL.value,
            ~AIIncident.status.in_(
                [IncidentStatus.RESOLVED.value, IncidentStatus.CLOSED.value]
            ),
        )
        .count()
    )

    open_exceptions = (
        db.query(GovernanceException)
        .filter(
            GovernanceException.status == ExceptionStatus.APPROVED.value,
        )
        .count()
    )
    expiring_exceptions = (
        db.query(GovernanceException)
        .filter(
            GovernanceException.status == ExceptionStatus.APPROVED.value,
            GovernanceException.valid_until.isnot(None),
            GovernanceException.valid_until <= now + timedelta(days=14),
        )
        .count()
    )

    active_waivers = 0
    expiring_waivers = 0
    if system_ids:
        active_waivers = (
            db.query(EvaluationWaiver)
            .filter(
                EvaluationWaiver.ai_system_id.in_(system_ids),
                EvaluationWaiver.status == WaiverStatus.APPROVED.value,
                EvaluationWaiver.revoked_at.is_(None),
            )
            .count()
        )
        expiring_waivers = (
            db.query(EvaluationWaiver)
            .filter(
                EvaluationWaiver.ai_system_id.in_(system_ids),
                EvaluationWaiver.status == WaiverStatus.APPROVED.value,
                EvaluationWaiver.revoked_at.is_(None),
                EvaluationWaiver.valid_until.isnot(None),
                EvaluationWaiver.valid_until <= now + timedelta(days=14),
            )
            .count()
        )

    pending_reviews = (
        db.query(GovernanceReview)
        .filter(
            GovernanceReview.status.in_(
                [
                    ReviewStatus.REQUESTED.value,
                    ReviewStatus.IN_REVIEW.value,
                    ReviewStatus.DRAFT.value,
                ]
            ),
        )
        .count()
    )
    overdue_reviews = (
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
        .count()
    )
    # Also count overdue periodic schedules without open reviews
    overdue_schedules = (
        db.query(PeriodicReviewSchedule)
        .filter(
            PeriodicReviewSchedule.enabled.is_(True),
            PeriodicReviewSchedule.next_due_at < now,
        )
        .count()
    )
    overdue_reviews = max(overdue_reviews, overdue_schedules)

    evidence_incomplete = 0
    if system_ids:
        evidence_incomplete = (
            db.query(RuntimeTrajectory.ai_system_id)
            .filter(
                RuntimeTrajectory.ai_system_id.in_(system_ids),
                RuntimeTrajectory.completeness_pct.isnot(None),
                RuntimeTrajectory.completeness_pct < 80,
            )
            .distinct()
            .count()
        )

    prod_versions = sum(
        1 for v in _production_version_ids(db, system_ids).values() if v
    )

    return {
        **_freshness_meta(),
        "metrics": {
            "total_ai_systems": len(systems),
            "active_ai_systems": status_counts.get(AISystemStatus.APPROVED.value, 0),
            "production_versions": prod_versions,
            "pilot_systems": len(pilot_system_ids),
            "suspended_systems": status_counts.get(AISystemStatus.SUSPENDED.value, 0),
            "retired_systems": status_counts.get(AISystemStatus.RETIRED.value, 0),
            "high_risk_systems": high_risk,
            "critical_risk_systems": critical_risk,
            "open_critical_findings": open_critical_findings,
            "valid_assurance": assurance_counts.get(AssuranceStatus.VALID.value, 0),
            "conditional_assurance": assurance_counts.get(
                AssuranceStatus.CONDITIONAL.value, 0
            ),
            "expired_assurance": assurance_counts.get(AssuranceStatus.EXPIRED.value, 0),
            "failed_assurance": assurance_counts.get(AssuranceStatus.FAILED.value, 0)
            + assurance_counts.get(AssuranceStatus.INVALIDATED.value, 0),
            "open_incidents": open_incidents,
            "critical_incidents": critical_incidents,
            "open_exceptions": open_exceptions,
            "expiring_exceptions": expiring_exceptions,
            "active_waivers": active_waivers,
            "expiring_waivers": expiring_waivers,
            "pending_reviews": pending_reviews,
            "overdue_reviews": overdue_reviews,
            "evidence_incomplete_systems": evidence_incomplete,
        },
    }


def get_inventory(
    db: Session,
    *,
    business_unit: str | None = None,
    owner: str | None = None,
    lifecycle: str | None = None,
    risk: str | None = None,
    assurance: str | None = None,
    control_status: str | None = None,
    incident_state: str | None = None,
    pilot_state: str | None = None,
) -> dict[str, Any]:
    systems = org_systems(db)
    system_ids = [s.id for s in systems]
    risk_levels = _risk_level_by_system(db, system_ids)
    assurances = _latest_assurance_by_system(db, system_ids)
    prod_versions = _production_version_ids(db, system_ids)

    accountabilities = {
        a.ai_system_id: a for a in db.query(AISystemAccountability).all()
    }
    classifications = {
        c.ai_system_id: c for c in db.query(AISystemGovernanceClassification).all()
    }
    schedules = {s.ai_system_id: s for s in db.query(PeriodicReviewSchedule).all()}

    open_incident_counts: Counter[UUID] = Counter()
    for row in (
        db.query(AIIncident.ai_system_id, func.count(AIIncident.id))
        .filter(
            ~AIIncident.status.in_(
                [IncidentStatus.RESOLVED.value, IncidentStatus.CLOSED.value]
            ),
        )
        .group_by(AIIncident.ai_system_id)
        .all()
    ):
        open_incident_counts[row[0]] = row[1]

    exception_counts: Counter[UUID] = Counter()
    for row in (
        db.query(GovernanceException.ai_system_id, func.count(GovernanceException.id))
        .filter(
            GovernanceException.status == ExceptionStatus.APPROVED.value,
        )
        .group_by(GovernanceException.ai_system_id)
        .all()
    ):
        exception_counts[row[0]] = row[1]

    control_worst: dict[UUID, str] = {}
    status_rank = {
        ControlAssessmentStatus.NOT_SATISFIED.value: 5,
        ControlAssessmentStatus.NOT_ASSESSED.value: 4,
        ControlAssessmentStatus.PARTIALLY_SATISFIED.value: 3,
        ControlAssessmentStatus.EXCEPTION_APPROVED.value: 2,
        ControlAssessmentStatus.SATISFIED.value: 1,
        ControlAssessmentStatus.NOT_APPLICABLE.value: 0,
    }
    for assessment in db.query(ControlAssessment).all():
        current = control_worst.get(assessment.ai_system_id)
        if current is None or status_rank.get(assessment.status, 0) > status_rank.get(
            current, 0
        ):
            control_worst[assessment.ai_system_id] = assessment.status

    pilot_by_system: dict[UUID, str] = {}
    for link, pilot in (
        db.query(PilotAISystem, Pilot)
        .join(Pilot, Pilot.id == PilotAISystem.pilot_id)
        .all()
    ):
        pilot_by_system[link.ai_system_id] = pilot.status

    last_reviews: dict[UUID, GovernanceReview] = {}
    for review in (
        db.query(GovernanceReview)
        .filter(
            GovernanceReview.status == ReviewStatus.COMPLETED.value,
        )
        .order_by(GovernanceReview.completed_at.desc())
        .all()
    ):
        if review.ai_system_id not in last_reviews:
            last_reviews[review.ai_system_id] = review

    runtime_status: dict[UUID, str] = {sid: "UNKNOWN" for sid in system_ids}
    if system_ids:
        identities = (
            db.query(AgentRuntimeIdentity, Agent)
            .join(Agent, Agent.id == AgentRuntimeIdentity.agent_id)
            .filter(Agent.ai_system_id.in_(system_ids))
            .all()
        )
        for identity, agent in identities:
            if identity.status == "SUSPENDED":
                runtime_status[agent.ai_system_id] = "SUSPENDED"
            elif (
                identity.status == "ACTIVE"
                and runtime_status[agent.ai_system_id] != "SUSPENDED"
            ):
                runtime_status[agent.ai_system_id] = "ACTIVE"

    items: list[dict[str, Any]] = []
    for system in systems:
        assurance_rec = assurances.get(system.id)
        assurance_status = assurance_rec.status if assurance_rec else "NONE"
        risk_level = risk_levels.get(system.id, "NONE")
        control = control_worst.get(system.id, "NOT_ASSESSED")
        open_inc = open_incident_counts.get(system.id, 0)
        pilot_st = pilot_by_system.get(system.id)
        schedule = schedules.get(system.id)
        last_review = last_reviews.get(system.id)
        accountability = accountabilities.get(system.id)
        classification = classifications.get(system.id)

        row = {
            "ai_system_id": str(system.id),
            "system_key": system.system_key,
            "name": system.name,
            "business_unit": system.business_unit,
            "owner_id": system.owner_id,
            "criticality": (
                classification.business_criticality
                if classification and classification.business_criticality
                else system.criticality
            ),
            "lifecycle": system.status,
            "production_version_id": str(prod_versions[system.id])
            if prod_versions.get(system.id)
            else None,
            "risk": risk_level,
            "assurance": assurance_status,
            "assurance_valid_until": _ser_dt(assurance_rec.valid_until)
            if assurance_rec
            else None,
            "controls": control,
            "open_incidents": open_inc,
            "open_exceptions": exception_counts.get(system.id, 0),
            "runtime_status": runtime_status.get(system.id, "UNKNOWN"),
            "last_review_at": _ser_dt(last_review.completed_at)
            if last_review
            else None,
            "next_review_at": _ser_dt(schedule.next_due_at) if schedule else None,
            "pilot_status": pilot_st,
            "missing_accountability": accountability is None
            or accountability.business_owner_membership_id is None,
            "drill_down": {
                "registry": f"/governance/registry/{system.id}",
                "risk": f"/risk/findings?ai_system_id={system.id}",
                "assurance": f"/assurance/readiness?ai_system_id={system.id}",
                "incidents": f"/governance/incidents?ai_system_id={system.id}",
                "exceptions": f"/governance/exceptions?ai_system_id={system.id}",
            },
        }

        if business_unit and (system.business_unit or "") != business_unit:
            continue
        if owner and (system.owner_id or "") != owner:
            continue
        if lifecycle and system.status != lifecycle:
            continue
        if risk and risk_level != risk:
            continue
        if assurance and assurance_status != assurance:
            continue
        if control_status and control != control_status:
            continue
        if incident_state == "OPEN" and open_inc == 0:
            continue
        if incident_state == "NONE" and open_inc > 0:
            continue
        if pilot_state and pilot_st != pilot_state:
            continue
        items.append(row)

    return {
        **_freshness_meta(),
        "count": len(items),
        "items": items,
    }


def get_risk_posture(db: Session) -> dict[str, Any]:
    systems = org_systems(db)
    system_ids = [s.id for s in systems]
    risk_levels = _risk_level_by_system(db, system_ids)

    by_system = [
        {
            "ai_system_id": str(s.id),
            "name": s.name,
            "business_unit": s.business_unit,
            "risk": risk_levels.get(s.id, "NONE"),
            "drill_down": f"/risk/findings?ai_system_id={s.id}",
        }
        for s in systems
    ]
    by_bu: dict[str, Counter[str]] = defaultdict(Counter)
    for s in systems:
        bu = s.business_unit or "UNASSIGNED"
        by_bu[bu][risk_levels.get(s.id, "NONE")] += 1

    by_severity: Counter[str] = Counter()
    by_category: Counter[str] = Counter()
    if system_ids:
        for finding in (
            db.query(RuntimeRiskFinding)
            .filter(
                RuntimeRiskFinding.ai_system_id.in_(system_ids),
                RuntimeRiskFinding.status == "OPEN",
            )
            .all()
        ):
            by_severity[finding.severity] += 1
            by_category[finding.category or "UNCATEGORIZED"] += 1
        for finding in (
            db.query(RiskFinding)
            .join(RiskAssessment, RiskAssessment.id == RiskFinding.risk_assessment_id)
            .filter(
                RiskAssessment.ai_system_id.in_(system_ids),
                RiskFinding.status == "OPEN",
            )
            .all()
        ):
            by_severity[finding.severity] += 1
            by_category[finding.category or "UNCATEGORIZED"] += 1

    # Heatmaps (explicit axes)
    classifications = {
        c.ai_system_id: c for c in db.query(AISystemGovernanceClassification).all()
    }
    heatmap_criticality_risk: Counter[tuple[str, str]] = Counter()
    heatmap_sensitivity_risk: Counter[tuple[str, str]] = Counter()
    heatmap_assurance_risk: Counter[tuple[str, str]] = Counter()
    heatmap_bu_critical: Counter[tuple[str, str]] = Counter()
    assurances = _latest_assurance_by_system(db, system_ids)
    for s in systems:
        risk = risk_levels.get(s.id, "NONE")
        cl = classifications.get(s.id)
        crit = cl.business_criticality if cl and cl.business_criticality else "UNKNOWN"
        sens = cl.data_sensitivity if cl and cl.data_sensitivity else "UNKNOWN"
        assurance = assurances.get(s.id).status if assurances.get(s.id) else "NONE"
        heatmap_criticality_risk[(crit, risk)] += 1
        heatmap_sensitivity_risk[(sens, risk)] += 1
        heatmap_assurance_risk[(assurance, risk)] += 1
        if risk in ("HIGH", "CRITICAL"):
            heatmap_bu_critical[(s.business_unit or "UNASSIGNED", risk)] += 1

    def _hm(counter: Counter[tuple[str, str]]) -> list[dict[str, Any]]:
        return [{"x": k[0], "y": k[1], "count": v} for k, v in sorted(counter.items())]

    return {
        **_freshness_meta(),
        "by_system": by_system,
        "by_business_unit": {bu: dict(counts) for bu, counts in sorted(by_bu.items())},
        "by_severity": dict(by_severity),
        "by_category": dict(by_category),
        "heatmaps": {
            "business_criticality_x_risk": _hm(heatmap_criticality_risk),
            "data_sensitivity_x_runtime_risk": _hm(heatmap_sensitivity_risk),
            "assurance_status_x_risk_severity": _hm(heatmap_assurance_risk),
            "business_unit_x_critical_findings": _hm(heatmap_bu_critical),
        },
        "methodology": {
            "aggregate_score": None,
            "drivers": [
                "Latest design-time RiskAssessment.risk_tier",
                "Runtime RiskState.current_level for AI_SYSTEM scope",
                "Open design-time and runtime findings by severity/category",
            ],
            "note": "Portfolio aggregates authoritative WP1/WP6 state; it does not invent a second risk score.",
        },
    }


def get_assurance_posture(db: Session) -> dict[str, Any]:
    systems = org_systems(db)
    system_ids = [s.id for s in systems]
    assurances = _latest_assurance_by_system(db, system_ids)
    now = _utcnow()

    by_status: Counter[str] = Counter()
    items: list[dict[str, Any]] = []
    expiring_7: list[dict[str, Any]] = []
    expiring_30: list[dict[str, Any]] = []
    expiring_90: list[dict[str, Any]] = []
    invalid_production: list[dict[str, Any]] = []

    name_by_id = {s.id: s.name for s in systems}
    for sid, rec in assurances.items():
        status = (rec.status or "UNKNOWN").upper()
        by_status[status] += 1
        item = {
            "ai_system_id": str(sid),
            "name": name_by_id.get(sid),
            "assurance_id": str(rec.id),
            "status": status,
            "environment": rec.environment,
            "valid_until": _ser_dt(rec.valid_until),
            "drill_down": f"/assurance/readiness?ai_system_id={sid}",
        }
        items.append(item)
        if status in (
            AssuranceStatus.EXPIRED.value,
            AssuranceStatus.INVALIDATED.value,
            AssuranceStatus.FAILED.value,
        ):
            invalid_production.append(item)
        if rec.valid_until:
            delta = rec.valid_until - now
            payload = item
            if delta <= timedelta(days=7):
                expiring_7.append(payload)
            if delta <= timedelta(days=30):
                expiring_30.append(payload)
            if delta <= timedelta(days=90):
                expiring_90.append(payload)

    waiver_items = []
    if system_ids:
        for w in (
            db.query(EvaluationWaiver)
            .filter(
                EvaluationWaiver.ai_system_id.in_(system_ids),
                EvaluationWaiver.status == WaiverStatus.APPROVED.value,
                EvaluationWaiver.revoked_at.is_(None),
            )
            .all()
        ):
            waiver_items.append(
                {
                    "waiver_id": str(w.id),
                    "ai_system_id": str(w.ai_system_id),
                    "valid_until": _ser_dt(w.valid_until),
                    "drill_down": f"/assurance/waivers?ai_system_id={w.ai_system_id}",
                }
            )

    return {
        **_freshness_meta(),
        "by_status": dict(by_status),
        "items": items,
        "invalid_or_expired_production": invalid_production,
        "expiring_in_7_days": expiring_7,
        "expiring_in_30_days": expiring_30,
        "expiring_in_90_days": expiring_90,
        "active_waivers": waiver_items,
        "disclaimer": "Assurance posture aggregates WP7 records; it is not a regulatory certification.",
    }


def get_control_posture(db: Session) -> dict[str, Any]:
    assessments = db.query(ControlAssessment).all()
    by_status: Counter[str] = Counter(a.status for a in assessments)
    by_system: dict[str, Counter[str]] = defaultdict(Counter)
    by_category: Counter[str] = Counter()
    by_method: Counter[str] = Counter()
    gap_by_requirement: Counter[str] = Counter()

    req_ids = {a.control_requirement_id for a in assessments}
    requirements = (
        {
            r.id: r
            for r in db.query(ControlRequirement)
            .filter(ControlRequirement.id.in_(req_ids))
            .all()
        }
        if req_ids
        else {}
    )
    obj_ids = {r.objective_id for r in requirements.values()}
    objectives = (
        {
            o.id: o
            for o in db.query(ControlObjective)
            .filter(ControlObjective.id.in_(obj_ids))
            .all()
        }
        if obj_ids
        else {}
    )

    for a in assessments:
        by_system[str(a.ai_system_id)][a.status] += 1
        by_method[a.assessment_method] += 1
        req = requirements.get(a.control_requirement_id)
        if req:
            obj = objectives.get(req.objective_id)
            if obj:
                by_category[obj.category] += 1
            if a.status in (
                ControlAssessmentStatus.NOT_SATISFIED.value,
                ControlAssessmentStatus.PARTIALLY_SATISFIED.value,
                ControlAssessmentStatus.NOT_ASSESSED.value,
            ):
                gap_by_requirement[req.requirement_key] += 1

    repeated_gaps = [
        {"requirement_key": k, "systems_affected": v}
        for k, v in gap_by_requirement.most_common()
        if v >= 2
    ]

    mappings = []
    for m in db.query(ControlMapping).limit(200).all():
        mappings.append(
            {
                "external_framework": m.external_framework,
                "external_requirement_id": m.external_requirement_id,
                "external_requirement_title": m.external_requirement_title,
                "internal_requirement_id": str(m.internal_requirement_id),
            }
        )

    return {
        **_freshness_meta(),
        "by_status": dict(by_status),
        "by_system": {k: dict(v) for k, v in by_system.items()},
        "by_category": dict(by_category),
        "by_assessment_source": dict(by_method),
        "repeated_control_gaps": repeated_gaps,
        "external_mappings_sample": mappings,
        "disclaimer": "Control mapping / assessment coverage ≠ certification. Never automatically compliant with an external framework.",
    }


def get_incident_posture(db: Session) -> dict[str, Any]:
    now = _utcnow()
    incidents = db.query(AIIncident).all()
    open_incidents = [
        i
        for i in incidents
        if i.status not in (IncidentStatus.RESOLVED.value, IncidentStatus.CLOSED.value)
    ]
    critical = [
        i for i in open_incidents if i.severity == IncidentSeverity.CRITICAL.value
    ]

    ages: list[float] = []
    contain_times: list[float] = []
    resolve_times: list[float] = []
    by_category: Counter[str] = Counter()
    systems_repeated: Counter[UUID] = Counter()

    for i in open_incidents:
        if i.detected_at:
            ages.append((now - i.detected_at).total_seconds() / 3600.0)
        by_category[i.category] += 1
        systems_repeated[i.ai_system_id] += 1

    for i in incidents:
        if i.containment_action and i.detected_at and i.updated_at:
            # Approximate contain time from first update after open when containment recorded
            contain_times.append(
                max(0.0, (i.updated_at - i.detected_at).total_seconds() / 3600.0)
            )
        if i.closed_at and i.detected_at:
            resolve_times.append(
                max(0.0, (i.closed_at - i.detected_at).total_seconds() / 3600.0)
            )

    exceptions = db.query(GovernanceException).all()
    active_exceptions = [
        e for e in exceptions if e.status == ExceptionStatus.APPROVED.value
    ]
    expiring_exceptions = [
        e
        for e in active_exceptions
        if e.valid_until and e.valid_until <= now + timedelta(days=14)
    ]

    system_ids = org_system_ids(db)
    waivers = []
    if system_ids:
        waivers = (
            db.query(EvaluationWaiver)
            .filter(
                EvaluationWaiver.ai_system_id.in_(system_ids),
                EvaluationWaiver.status == WaiverStatus.APPROVED.value,
                EvaluationWaiver.revoked_at.is_(None),
            )
            .all()
        )
    expiring_waivers = [
        w
        for w in waivers
        if w.valid_until and w.valid_until <= now + timedelta(days=14)
    ]

    repeated_exception_controls: Counter[str] = Counter()
    for e in active_exceptions:
        if e.control_requirement_id:
            repeated_exception_controls[str(e.control_requirement_id)] += 1

    return {
        **_freshness_meta(),
        "open_incidents": len(open_incidents),
        "critical_incidents": len(critical),
        "average_incident_age_hours": (
            round(sum(ages) / len(ages), 2) if ages else None
        ),
        "average_time_to_contain_hours": (
            round(sum(contain_times) / len(contain_times), 2) if contain_times else None
        ),
        "average_time_to_resolve_hours": (
            round(sum(resolve_times) / len(resolve_times), 2) if resolve_times else None
        ),
        "sla_compliance_claimed": False,
        "by_category": dict(by_category),
        "systems_with_repeated_incidents": [
            {"ai_system_id": str(sid), "open_count": count}
            for sid, count in systems_repeated.items()
            if count >= 2
        ],
        "active_exceptions": len(active_exceptions),
        "expiring_exceptions": len(expiring_exceptions),
        "active_evaluation_waivers": len(waivers),
        "expiring_waivers": len(expiring_waivers),
        "repeated_exceptions_on_same_control": [
            {"control_requirement_id": k, "count": v}
            for k, v in repeated_exception_controls.items()
            if v >= 2
        ],
        "items": [
            {
                "id": str(i.id),
                "ai_system_id": str(i.ai_system_id),
                "title": i.title,
                "severity": i.severity,
                "status": i.status,
                "category": i.category,
                "detected_at": _ser_dt(i.detected_at),
                "drill_down": f"/governance/incidents/{i.id}",
            }
            for i in open_incidents[:100]
        ],
    }


def get_runtime_activity(
    db: Session,
    *,
    period_days: int = 30,
) -> dict[str, Any]:
    system_ids = org_system_ids(db)
    since = _utcnow() - timedelta(days=period_days)
    if not system_ids:
        return {
            **_freshness_meta(),
            "period_days": period_days,
            "metrics": {},
            "note": "Activity volume is not itself risk.",
        }

    receipts = (
        db.query(RuntimeEnforcementReceipt)
        .filter(
            RuntimeEnforcementReceipt.ai_system_id.in_(system_ids),
            RuntimeEnforcementReceipt.started_at >= since,
        )
        .all()
    )
    decisions: Counter[str] = Counter(
        r.enforcement_decision for r in receipts if r.enforcement_decision
    )
    executions: Counter[str] = Counter(
        r.execution_status for r in receipts if r.execution_status
    )

    approvals = (
        db.query(ApprovalRequest)
        .filter(
            ApprovalRequest.ai_system_id.in_(system_ids),
            ApprovalRequest.created_at >= since,
        )
        .all()
    )
    approval_status: Counter[str] = Counter(a.status for a in approvals)

    anomalies = (
        db.query(RiskSignal)
        .filter(
            RiskSignal.ai_system_id.in_(system_ids),
            RiskSignal.signal_type == "ANOMALY",
            RiskSignal.occurred_at >= since,
        )
        .count()
    )
    content_violations = (
        db.query(RiskSignal)
        .filter(
            RiskSignal.ai_system_id.in_(system_ids),
            RiskSignal.category == "CONTENT_VIOLATION",
            RiskSignal.occurred_at >= since,
        )
        .count()
    )
    suspensions = (
        db.query(AgentRuntimeIdentity)
        .join(Agent, Agent.id == AgentRuntimeIdentity.agent_id)
        .filter(
            Agent.ai_system_id.in_(system_ids),
            AgentRuntimeIdentity.status == "SUSPENDED",
        )
        .count()
    )

    return {
        **_freshness_meta(),
        "period_days": period_days,
        "metrics": {
            "governed_actions": len(receipts),
            "ALLOW": decisions.get("ALLOW", 0),
            "DENY": decisions.get("DENY", 0),
            "REQUIRE_APPROVAL": decisions.get("REQUIRE_APPROVAL", 0),
            "approvals_requested": len(approvals),
            "approvals_approved": approval_status.get("APPROVED", 0),
            "approvals_rejected": approval_status.get("REJECTED", 0),
            "executions_succeeded": executions.get("SUCCEEDED", 0)
            + executions.get("SUCCESS", 0),
            "executions_failed": executions.get("FAILED", 0),
            "budget_exceeded_events": (
                db.query(RiskSignal)
                .filter(
                    RiskSignal.ai_system_id.in_(system_ids),
                    RiskSignal.signal_type == "BUDGET_EXCEEDED",
                    RiskSignal.occurred_at >= since,
                )
                .count()
            ),
            "runtime_suspensions": suspensions,
            "content_violations": content_violations,
            "anomalies": anomalies,
        },
        "note": "Activity volume is not itself risk.",
    }


def get_evidence_completeness(db: Session) -> dict[str, Any]:
    system_ids = org_system_ids(db)
    if not system_ids:
        return {
            **_freshness_meta(),
            "metrics": {},
        }

    trajectories = (
        db.query(RuntimeTrajectory)
        .filter(RuntimeTrajectory.ai_system_id.in_(system_ids))
        .all()
    )
    complete = sum(
        1
        for t in trajectories
        if t.completeness_pct is not None and t.completeness_pct >= 80
    )
    incomplete = sum(
        1
        for t in trajectories
        if t.completeness_pct is not None and t.completeness_pct < 80
    )
    missing_exec = sum(
        1
        for t in trajectories
        if (t.coverage_summary or {}).get("missing_execution_evidence")
    )
    low_assurance = sum(
        1
        for t in trajectories
        if (t.assurance_summary or {}).get("client_reported_low_assurance")
    )
    unverified = sum(
        1
        for t in trajectories
        if t.enforcement_mode in ("CLIENT_REPORTED", "UNVERIFIED")
        or (t.coverage_summary or {}).get("unverified_enforcement")
    )

    return {
        **_freshness_meta(),
        "metrics": {
            "complete_trajectories": complete,
            "incomplete_trajectories": incomplete,
            "missing_execution_evidence": missing_exec,
            "prompt_output_unavailable": sum(
                1
                for t in trajectories
                if (t.coverage_summary or {}).get("prompt_output_unavailable")
            ),
            "low_assurance_client_reported": low_assurance,
            "unverified_enforcement": unverified,
            "total_trajectories": len(trajectories),
        },
    }


def get_ownership_view(db: Session) -> dict[str, Any]:
    systems = org_systems(db)
    system_ids = [s.id for s in systems]
    risk_levels = _risk_level_by_system(db, system_ids)
    accountabilities = {
        a.ai_system_id: a for a in db.query(AISystemAccountability).all()
    }
    overdue = {
        r.ai_system_id
        for r in db.query(PeriodicReviewSchedule)
        .filter(
            PeriodicReviewSchedule.enabled.is_(True),
            PeriodicReviewSchedule.next_due_at < _utcnow(),
        )
        .all()
    }

    by_bu: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "systems": 0,
            "critical_risk": 0,
            "overdue_reviews": 0,
            "missing_accountability": 0,
        }
    )
    missing_accountability: list[dict[str, Any]] = []
    for s in systems:
        bu = s.business_unit or "UNASSIGNED"
        by_bu[bu]["systems"] += 1
        if risk_levels.get(s.id) in ("HIGH", "CRITICAL"):
            by_bu[bu]["critical_risk"] += 1
        if s.id in overdue:
            by_bu[bu]["overdue_reviews"] += 1
        acc = accountabilities.get(s.id)
        if acc is None or acc.business_owner_membership_id is None:
            by_bu[bu]["missing_accountability"] += 1
            missing_accountability.append(
                {
                    "ai_system_id": str(s.id),
                    "name": s.name,
                    "business_unit": s.business_unit,
                }
            )

    return {
        **_freshness_meta(),
        "by_business_unit": dict(by_bu),
        "missing_accountability": missing_accountability,
        "note": "Ownership view is for governance accountability, not employee performance scoring.",
    }


def get_trends(
    db: Session,
    *,
    period_days: int = 30,
) -> dict[str, Any]:
    system_ids = org_system_ids(db)
    since = _utcnow() - timedelta(days=period_days)
    systems = org_systems(db)

    new_systems = sum(1 for s in systems if s.created_at and s.created_at >= since)
    new_findings = 0
    critical_findings = 0
    if system_ids:
        new_findings = (
            db.query(RuntimeRiskFinding)
            .filter(
                RuntimeRiskFinding.ai_system_id.in_(system_ids),
                RuntimeRiskFinding.created_at >= since,
            )
            .count()
        )
        critical_findings = (
            db.query(RuntimeRiskFinding)
            .filter(
                RuntimeRiskFinding.ai_system_id.in_(system_ids),
                RuntimeRiskFinding.created_at >= since,
                RuntimeRiskFinding.severity.in_(["HIGH", "CRITICAL"]),
            )
            .count()
        )

    incidents = (
        db.query(AIIncident)
        .filter(
            AIIncident.created_at >= since,
        )
        .count()
    )
    denials = 0
    if system_ids:
        denials = (
            db.query(RuntimeEnforcementReceipt)
            .filter(
                RuntimeEnforcementReceipt.ai_system_id.in_(system_ids),
                RuntimeEnforcementReceipt.started_at >= since,
                RuntimeEnforcementReceipt.enforcement_decision == "DENY",
            )
            .count()
        )
    approvals_escalated = 0
    if system_ids:
        approvals_escalated = (
            db.query(ApprovalRequest)
            .filter(
                ApprovalRequest.ai_system_id.in_(system_ids),
                ApprovalRequest.created_at >= since,
            )
            .count()
        )

    expired_assurance = 0
    if system_ids:
        expired_assurance = (
            db.query(AssuranceRecord)
            .filter(
                AssuranceRecord.ai_system_id.in_(system_ids),
                AssuranceRecord.status == AssuranceStatus.EXPIRED.value,
                AssuranceRecord.updated_at >= since,
            )
            .count()
        )

    exceptions = (
        db.query(GovernanceException)
        .filter(
            GovernanceException.created_at >= since,
        )
        .count()
    )
    control_gaps = (
        db.query(ControlAssessment)
        .filter(
            ControlAssessment.status.in_(
                [
                    ControlAssessmentStatus.NOT_SATISFIED.value,
                    ControlAssessmentStatus.PARTIALLY_SATISFIED.value,
                ]
            ),
            ControlAssessment.updated_at >= since,
        )
        .count()
    )

    return {
        **_freshness_meta(),
        "period_days": period_days,
        "trends": {
            "ai_system_count": len(systems),
            "new_ai_systems": new_systems,
            "production_versions": sum(
                1 for v in _production_version_ids(db, system_ids).values() if v
            ),
            "risk_findings": new_findings,
            "critical_findings": critical_findings,
            "incidents": incidents,
            "denials": denials,
            "approval_escalations": approvals_escalated,
            "expired_assurance": expired_assurance,
            "exceptions": exceptions,
            "control_gaps": control_gaps,
        },
    }


def get_change_feed(
    db: Session,
    *,
    period_days: int = 30,
    limit: int = 100,
) -> dict[str, Any]:
    system_ids = org_system_ids(db)
    since = _utcnow() - timedelta(days=period_days)
    events: list[dict[str, Any]] = []

    for s in org_systems(db):
        if s.created_at and s.created_at >= since:
            events.append(
                {
                    "type": "new_ai_system",
                    "occurred_at": _ser_dt(s.created_at),
                    "ai_system_id": str(s.id),
                    "title": f"New AI System: {s.name}",
                    "source_type": "AI_SYSTEM",
                    "source_id": str(s.id),
                }
            )

    if system_ids:
        for finding in (
            db.query(RuntimeRiskFinding)
            .filter(
                RuntimeRiskFinding.ai_system_id.in_(system_ids),
                RuntimeRiskFinding.created_at >= since,
                RuntimeRiskFinding.severity.in_(["HIGH", "CRITICAL"]),
            )
            .order_by(RuntimeRiskFinding.created_at.desc())
            .limit(50)
            .all()
        ):
            events.append(
                {
                    "type": "new_critical_risk",
                    "occurred_at": _ser_dt(finding.created_at),
                    "ai_system_id": str(finding.ai_system_id),
                    "title": finding.title,
                    "source_type": "RUNTIME_RISK_FINDING",
                    "source_id": str(finding.id),
                }
            )
        for rec in (
            db.query(AssuranceRecord)
            .filter(
                AssuranceRecord.ai_system_id.in_(system_ids),
                AssuranceRecord.status == AssuranceStatus.EXPIRED.value,
                AssuranceRecord.updated_at >= since,
            )
            .limit(50)
            .all()
        ):
            events.append(
                {
                    "type": "assurance_expired",
                    "occurred_at": _ser_dt(rec.updated_at),
                    "ai_system_id": str(rec.ai_system_id),
                    "title": "Assurance expired",
                    "source_type": "ASSURANCE_RECORD",
                    "source_id": str(rec.id),
                }
            )
        for identity, agent in (
            db.query(AgentRuntimeIdentity, Agent)
            .join(Agent, Agent.id == AgentRuntimeIdentity.agent_id)
            .filter(
                Agent.ai_system_id.in_(system_ids),
                AgentRuntimeIdentity.status == "SUSPENDED",
            )
            .limit(50)
            .all()
        ):
            events.append(
                {
                    "type": "runtime_suspended",
                    "occurred_at": _ser_dt(identity.updated_at or identity.created_at),
                    "ai_system_id": str(agent.ai_system_id),
                    "title": "Runtime identity suspended",
                    "source_type": "RUNTIME_IDENTITY",
                    "source_id": str(identity.id),
                }
            )

    for incident in (
        db.query(AIIncident)
        .filter(
            AIIncident.created_at >= since,
        )
        .limit(50)
        .all()
    ):
        events.append(
            {
                "type": "incident_opened",
                "occurred_at": _ser_dt(incident.created_at),
                "ai_system_id": str(incident.ai_system_id),
                "title": incident.title,
                "source_type": "INCIDENT",
                "source_id": str(incident.id),
            }
        )
        if incident.closed_at and incident.closed_at >= since:
            events.append(
                {
                    "type": "incident_closed",
                    "occurred_at": _ser_dt(incident.closed_at),
                    "ai_system_id": str(incident.ai_system_id),
                    "title": f"Closed: {incident.title}",
                    "source_type": "INCIDENT",
                    "source_id": str(incident.id),
                }
            )

    for exc in (
        db.query(GovernanceException)
        .filter(
            GovernanceException.created_at >= since,
        )
        .limit(50)
        .all()
    ):
        events.append(
            {
                "type": "exception_event",
                "occurred_at": _ser_dt(exc.decided_at or exc.created_at),
                "ai_system_id": str(exc.ai_system_id),
                "title": f"Exception {exc.status}",
                "source_type": "EXCEPTION",
                "source_id": str(exc.id),
            }
        )

    for review in (
        db.query(GovernanceReview)
        .filter(
            GovernanceReview.status == ReviewStatus.COMPLETED.value,
            GovernanceReview.completed_at.isnot(None),
            GovernanceReview.completed_at >= since,
        )
        .limit(50)
        .all()
    ):
        events.append(
            {
                "type": "review_completed",
                "occurred_at": _ser_dt(review.completed_at),
                "ai_system_id": str(review.ai_system_id),
                "title": f"Review completed ({review.review_type})",
                "source_type": "GOVERNANCE_REVIEW",
                "source_id": str(review.id),
            }
        )

    events.sort(key=lambda e: e.get("occurred_at") or "", reverse=True)
    return {
        **_freshness_meta(),
        "period_days": period_days,
        "count": min(len(events), limit),
        "items": events[:limit],
    }
