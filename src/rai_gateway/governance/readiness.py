"""WP8 pilot readiness evaluation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from rai_gateway.core.observability import log_siem_event
from rai_gateway.governance.controls import automated_assess
from rai_gateway.governance.domain import (
    READINESS_DIMENSIONS,
    ControlApplicability,
    ControlAssessmentStatus,
    MembershipStatus,
    PilotReadinessDecision,
    ReadinessDimensionStatus,
)
from rai_gateway.governance.errors import GovernanceNotFoundError
from rai_gateway.models.governance import (
    AISystemAccountability,
    AISystemGovernanceClassification,
    ControlAssessment,
    OrganizationGovernanceProfile,
    OrganizationMembership,
    PilotReadinessEvaluation,
)
from rai_gateway.models.registry import Agent, AgentVersion, AISystem


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _dim(status: str, reason: str, gaps: list[str] | None = None) -> dict[str, Any]:
    return {
        "status": status,
        "reason": reason,
        "gaps": gaps or [],
    }


def evaluate_pilot_readiness(
    db: Session,
    *,
    ai_system_id: UUID,
    agent_version_id: UUID | None = None,
    pilot_id: UUID | None = None,
    evaluated_by: str,
) -> dict[str, Any]:
    """Evaluate explainable pilot readiness and persist the result."""
    system = db.query(AISystem).filter(AISystem.id == ai_system_id).first()
    if system is None:
        raise GovernanceNotFoundError(f"AI System {ai_system_id} not found")
    # Refresh automated controls so CONTROL_COVERAGE is current.
    automated_assess(db, ai_system_id, agent_version_id)

    dimensions: dict[str, dict[str, Any]] = {}
    all_gaps: list[dict[str, Any]] = []

    def record(name: str, result: dict[str, Any]) -> None:
        dimensions[name] = result
        for gap in result.get("gaps") or []:
            all_gaps.append({"dimension": name, "gap": gap})

    # ORGANIZATION
    profile = (
        db.query(OrganizationGovernanceProfile)
        .filter(OrganizationGovernanceProfile.singleton_key == "default")
        .first()
    )
    memberships = (
        db.query(OrganizationMembership)
        .filter(OrganizationMembership.status == MembershipStatus.ACTIVE.value)
        .count()
    )
    org_gaps: list[str] = []
    if profile is None:
        org_gaps.append("Organization governance profile missing")
    if memberships == 0:
        org_gaps.append("No ACTIVE organization memberships")
    if org_gaps:
        record(
            "ORGANIZATION",
            _dim(
                ReadinessDimensionStatus.NOT_READY.value,
                "Organization incomplete",
                org_gaps,
            ),
        )
    else:
        record(
            "ORGANIZATION",
            _dim(
                ReadinessDimensionStatus.READY.value, "Profile and memberships present"
            ),
        )

    # ACCOUNTABILITY
    accountability = (
        db.query(AISystemAccountability)
        .filter(AISystemAccountability.ai_system_id == ai_system_id)
        .first()
    )
    acc_gaps: list[str] = []
    if accountability is None:
        acc_gaps.append("Accountability record missing")
    else:
        if not accountability.business_owner_membership_id:
            acc_gaps.append("Business owner membership missing")
        if not accountability.technical_owner_membership_id:
            acc_gaps.append("Technical owner membership missing")
        if not accountability.rai_officer_membership_id:
            acc_gaps.append("RAI officer membership missing")
    if acc_gaps:
        status = (
            ReadinessDimensionStatus.NOT_READY.value
            if accountability is None or len(acc_gaps) >= 2
            else ReadinessDimensionStatus.PARTIAL.value
        )
        record(
            "ACCOUNTABILITY",
            _dim(status, "Required accountability roles incomplete", acc_gaps),
        )
    else:
        record(
            "ACCOUNTABILITY",
            _dim(
                ReadinessDimensionStatus.READY.value,
                "Business, technical, and RAI officer assigned",
            ),
        )

    # REGISTRY
    agents = db.query(Agent).filter(Agent.ai_system_id == ai_system_id).all()
    reg_gaps: list[str] = []
    if not agents:
        reg_gaps.append("No agents registered for AI system")
    version = None
    if agent_version_id:
        version = (
            db.query(AgentVersion).filter(AgentVersion.id == agent_version_id).first()
        )
        if version is None:
            reg_gaps.append(f"Agent version {agent_version_id} not found")
    elif agents:
        for agent in agents:
            if agent.current_version_id:
                version = (
                    db.query(AgentVersion)
                    .filter(AgentVersion.id == agent.current_version_id)
                    .first()
                )
                if version:
                    break
        if version is None:
            reg_gaps.append("No current agent version selected")
    if version and (version.lifecycle_status or "").upper() not in {
        "APPROVED",
        "PRODUCTION",
        "ACTIVE",
    }:
        reg_gaps.append(
            f"Version lifecycle_status={version.lifecycle_status} not approved"
        )
    if reg_gaps:
        record(
            "REGISTRY",
            _dim(
                ReadinessDimensionStatus.PARTIAL.value
                if agents
                else ReadinessDimensionStatus.NOT_READY.value,
                "Registry incomplete",
                reg_gaps,
            ),
        )
    else:
        record(
            "REGISTRY",
            _dim(
                ReadinessDimensionStatus.READY.value,
                "AI system, agent, and approved version present",
            ),
        )

    # RISK
    risk_gaps: list[str] = []
    try:
        from rai_gateway.models.registry import RiskAssessment

        ra_q = db.query(RiskAssessment).filter(
            RiskAssessment.ai_system_id == ai_system_id
        )
        if agent_version_id:
            ra_q = ra_q.filter(
                (RiskAssessment.agent_version_id == agent_version_id)
                | (RiskAssessment.agent_version_id.is_(None))
            )
        if ra_q.first() is None:
            risk_gaps.append("No risk assessment for system/version")
    except Exception:
        risk_gaps.append("Risk assessment models unavailable")
    try:
        from rai_gateway.models.risk_intelligence import RuntimeRiskFinding

        open_critical = (
            db.query(RuntimeRiskFinding)
            .filter(
                RuntimeRiskFinding.ai_system_id == ai_system_id,
                RuntimeRiskFinding.severity.in_(["HIGH", "CRITICAL"]),
                ~RuntimeRiskFinding.status.in_(["CLOSED", "RESOLVED"]),
            )
            .count()
        )
        if open_critical:
            risk_gaps.append(
                f"{open_critical} open HIGH/CRITICAL runtime risk findings"
            )
    except Exception:
        pass
    if risk_gaps:
        record(
            "RISK",
            _dim(
                ReadinessDimensionStatus.NOT_READY.value,
                "Risk posture incomplete",
                risk_gaps,
            ),
        )
    else:
        record(
            "RISK",
            _dim(
                ReadinessDimensionStatus.READY.value,
                "Risk assessment current; no open critical findings",
            ),
        )

    # POLICY
    policy_gaps: list[str] = []
    classification = (
        db.query(AISystemGovernanceClassification)
        .filter(AISystemGovernanceClassification.ai_system_id == ai_system_id)
        .first()
    )
    try:
        from rai_gateway.models.policy_engine import PolicyCollection

        collection = (
            db.query(PolicyCollection)
            .filter(PolicyCollection.ai_system_id == ai_system_id)
            .first()
        )
        if collection is None:
            policy_gaps.append("No policy collection for AI system")
        elif classification and classification.consequential_actions:
            from rai_gateway.models.policy_engine import ContentRule, ToolRule

            tool_count = (
                db.query(ToolRule)
                .filter(
                    ToolRule.policy_collection_id == collection.id,
                    ToolRule.enabled.is_(True),
                )
                .count()
            )
            content_count = (
                db.query(ContentRule)
                .filter(
                    ContentRule.policy_collection_id == collection.id,
                    ContentRule.enabled.is_(True),
                )
                .count()
            )
            if tool_count == 0 and content_count == 0:
                policy_gaps.append(
                    "Consequential system has no enabled tool/content rules"
                )
    except Exception:
        policy_gaps.append("Policy models unavailable")
    if policy_gaps:
        record(
            "POLICY",
            _dim(
                ReadinessDimensionStatus.PARTIAL.value
                if classification and not classification.consequential_actions
                else ReadinessDimensionStatus.NOT_READY.value,
                "Policy coverage incomplete",
                policy_gaps,
            ),
        )
    else:
        record(
            "POLICY",
            _dim(ReadinessDimensionStatus.READY.value, "Policy collection present"),
        )

    # IDENTITY
    identity_gaps: list[str] = []
    try:
        from rai_gateway.models.identity import AgentRuntimeIdentity

        if agent_version_id:
            identity = (
                db.query(AgentRuntimeIdentity)
                .filter(
                    AgentRuntimeIdentity.agent_version_id == agent_version_id,
                    AgentRuntimeIdentity.status == "ACTIVE",
                )
                .first()
            )
            if identity is None:
                identity_gaps.append("No ACTIVE runtime identity for agent version")
        else:
            identity_gaps.append("agent_version_id not provided for identity check")
    except Exception:
        identity_gaps.append("Identity models unavailable")
    if identity_gaps:
        record(
            "IDENTITY",
            _dim(
                ReadinessDimensionStatus.NOT_READY.value,
                "Runtime identity incomplete",
                identity_gaps,
            ),
        )
    else:
        record(
            "IDENTITY",
            _dim(ReadinessDimensionStatus.READY.value, "ACTIVE runtime identity bound"),
        )

    # APPROVAL
    approval_gaps: list[str] = []
    if classification and classification.consequential_actions:
        try:
            from rai_gateway.models.approval import ApprovalRequest
            from rai_gateway.models.policy_engine import PolicyCollection, ToolRule

            collection = (
                db.query(PolicyCollection)
                .filter(PolicyCollection.ai_system_id == ai_system_id)
                .first()
            )
            gated = False
            if collection:
                gated = (
                    db.query(ToolRule)
                    .filter(
                        ToolRule.policy_collection_id == collection.id,
                        ToolRule.required_approver_role.isnot(None),
                        ToolRule.enabled.is_(True),
                    )
                    .first()
                    is not None
                )
            has_req = (
                db.query(ApprovalRequest)
                .filter(ApprovalRequest.ai_system_id == ai_system_id)
                .first()
                is not None
            )
            if not gated and not has_req:
                approval_gaps.append(
                    "Consequential system lacks approval-gated rules or approval history"
                )
        except Exception:
            approval_gaps.append("Approval/policy models unavailable")
        if approval_gaps:
            record(
                "APPROVAL",
                _dim(
                    ReadinessDimensionStatus.PARTIAL.value,
                    "Approval controls incomplete",
                    approval_gaps,
                ),
            )
        else:
            record(
                "APPROVAL",
                _dim(ReadinessDimensionStatus.READY.value, "Approval path configured"),
            )
    else:
        record(
            "APPROVAL",
            _dim(
                ReadinessDimensionStatus.NOT_APPLICABLE.value,
                "No consequential actions; approval dimension N/A",
            ),
        )

    # ENFORCEMENT — best-effort presence of policy or budgets as enforcement posture
    enf_gaps: list[str] = []
    try:
        from rai_gateway.models.policy_engine import PolicyCollection

        if (
            db.query(PolicyCollection)
            .filter(PolicyCollection.ai_system_id == ai_system_id)
            .first()
            is None
        ):
            enf_gaps.append("No policy collection to enforce")
    except Exception:
        enf_gaps.append("Enforcement/policy models unavailable")
    if enf_gaps:
        record(
            "ENFORCEMENT",
            _dim(
                ReadinessDimensionStatus.PARTIAL.value,
                "Enforcement posture incomplete",
                enf_gaps,
            ),
        )
    else:
        record(
            "ENFORCEMENT",
            _dim(
                ReadinessDimensionStatus.READY.value,
                "Policy enforcement surface present",
            ),
        )

    # EVIDENCE
    evidence_gaps: list[str] = []
    try:
        from rai_gateway.models.evidence import RuntimeTrajectory

        tq = db.query(RuntimeTrajectory).filter(
            RuntimeTrajectory.ai_system_id == ai_system_id
        )
        if agent_version_id:
            tq = tq.filter(RuntimeTrajectory.agent_version_id == agent_version_id)
        if tq.first() is None:
            # Trajectories may not exist pre-runtime; partial rather than hard fail for pilot.
            evidence_gaps.append(
                "No runtime trajectories yet (pre-runtime acceptable as partial)"
            )
    except Exception:
        evidence_gaps.append("Evidence models unavailable")
    if evidence_gaps:
        record(
            "EVIDENCE",
            _dim(
                ReadinessDimensionStatus.PARTIAL.value,
                "Evidence coverage incomplete",
                evidence_gaps,
            ),
        )
    else:
        record(
            "EVIDENCE",
            _dim(ReadinessDimensionStatus.READY.value, "Runtime evidence present"),
        )

    # OVERSIGHT
    oversight_gaps: list[str] = []
    try:
        from rai_gateway.models.risk_intelligence import RuntimeBudget

        budget = (
            db.query(RuntimeBudget)
            .filter(
                RuntimeBudget.ai_system_id == ai_system_id,
                RuntimeBudget.enabled.is_(True),
            )
            .first()
        )
        if budget is None and classification and classification.consequential_actions:
            oversight_gaps.append("Consequential system has no enabled runtime budget")
        elif budget is None:
            oversight_gaps.append("No runtime budget configured")
    except Exception:
        oversight_gaps.append("Oversight/budget models unavailable")
    if oversight_gaps:
        status = (
            ReadinessDimensionStatus.NOT_READY.value
            if classification and classification.consequential_actions
            else ReadinessDimensionStatus.PARTIAL.value
        )
        record(
            "OVERSIGHT", _dim(status, "Continuous oversight incomplete", oversight_gaps)
        )
    else:
        record(
            "OVERSIGHT",
            _dim(
                ReadinessDimensionStatus.READY.value,
                "Runtime budgets/monitoring present",
            ),
        )

    # ASSURANCE
    assurance_gaps: list[str] = []
    if agent_version_id:
        try:
            from rai_gateway.evaluations.service import EvaluationService

            if not EvaluationService(db).is_environment_eligible(agent_version_id):
                assurance_gaps.append("WP7 environment eligibility failed")
        except Exception:
            assurance_gaps.append("EvaluationService unavailable")
        try:
            from rai_gateway.evaluations.domain import AssuranceStatus
            from rai_gateway.models.evaluations import AssuranceRecord

            record_row = (
                db.query(AssuranceRecord)
                .filter(
                    AssuranceRecord.agent_version_id == agent_version_id,
                    AssuranceRecord.superseded_at.is_(None),
                    AssuranceRecord.status.in_(
                        [AssuranceStatus.VALID.value, AssuranceStatus.CONDITIONAL.value]
                    ),
                )
                .first()
            )
            if record_row is None:
                assurance_gaps.append("No VALID/CONDITIONAL assurance record")
        except Exception:
            assurance_gaps.append("Assurance models unavailable")
    else:
        assurance_gaps.append("agent_version_id required for assurance readiness")
    if assurance_gaps:
        record(
            "ASSURANCE",
            _dim(
                ReadinessDimensionStatus.NOT_READY.value,
                "Deployment assurance incomplete",
                assurance_gaps,
            ),
        )
    else:
        record(
            "ASSURANCE",
            _dim(ReadinessDimensionStatus.READY.value, "WP7 assurance valid"),
        )

    # INCIDENT_RESPONSE
    ir_gaps: list[str] = []
    if accountability is None or not accountability.incident_owner_membership_id:
        mgr = (
            db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.role == "INCIDENT_MANAGER",
                OrganizationMembership.status == MembershipStatus.ACTIVE.value,
            )
            .first()
        )
        if mgr is None:
            ir_gaps.append("No incident owner membership or ACTIVE INCIDENT_MANAGER")
    if ir_gaps:
        record(
            "INCIDENT_RESPONSE",
            _dim(
                ReadinessDimensionStatus.NOT_READY.value,
                "Incident process not established",
                ir_gaps,
            ),
        )
    else:
        record(
            "INCIDENT_RESPONSE",
            _dim(ReadinessDimensionStatus.READY.value, "Incident ownership configured"),
        )

    # CONTROL_COVERAGE
    assessments = (
        db.query(ControlAssessment)
        .filter(ControlAssessment.ai_system_id == ai_system_id)
        .all()
    )
    if agent_version_id:
        assessments = [
            a
            for a in assessments
            if a.agent_version_id is None or a.agent_version_id == agent_version_id
        ]
    control_gaps: list[str] = []
    required_unsat = 0
    required_partial = 0
    for a in assessments:
        if a.applicability != ControlApplicability.REQUIRED.value:
            continue
        if a.status in {
            ControlAssessmentStatus.NOT_SATISFIED.value,
            ControlAssessmentStatus.NOT_ASSESSED.value,
        }:
            required_unsat += 1
            control_gaps.append(
                f"Required control {a.control_requirement_id} status={a.status}"
            )
        elif a.status == ControlAssessmentStatus.PARTIALLY_SATISFIED.value:
            required_partial += 1
            control_gaps.append(
                f"Required control {a.control_requirement_id} partially satisfied"
            )
    if not assessments:
        control_gaps.append("No control assessments available")
        record(
            "CONTROL_COVERAGE",
            _dim(
                ReadinessDimensionStatus.NOT_READY.value,
                "Controls not assessed",
                control_gaps,
            ),
        )
    elif required_unsat:
        record(
            "CONTROL_COVERAGE",
            _dim(
                ReadinessDimensionStatus.NOT_READY.value,
                "Required controls unsatisfied",
                control_gaps,
            ),
        )
    elif required_partial:
        record(
            "CONTROL_COVERAGE",
            _dim(
                ReadinessDimensionStatus.PARTIAL.value,
                "Required controls partially satisfied",
                control_gaps,
            ),
        )
    else:
        record(
            "CONTROL_COVERAGE",
            _dim(
                ReadinessDimensionStatus.READY.value,
                "Required controls satisfied or N/A",
            ),
        )

    # Ensure all declared dimensions are present.
    for name in READINESS_DIMENSIONS:
        if name not in dimensions:
            dimensions[name] = _dim(
                ReadinessDimensionStatus.NOT_READY.value,
                "Dimension not evaluated",
                [f"{name} missing from evaluation"],
            )

    required_statuses = [
        dimensions[name]["status"]
        for name in READINESS_DIMENSIONS
        if dimensions[name]["status"] != ReadinessDimensionStatus.NOT_APPLICABLE.value
    ]
    if any(s == ReadinessDimensionStatus.NOT_READY.value for s in required_statuses):
        decision = PilotReadinessDecision.NOT_READY.value
    elif any(s == ReadinessDimensionStatus.PARTIAL.value for s in required_statuses):
        decision = PilotReadinessDecision.READY_WITH_CONDITIONS.value
    else:
        decision = PilotReadinessDecision.READY.value

    conditions = [
        g
        for g in all_gaps
        if dimensions.get(g["dimension"], {}).get("status")
        == ReadinessDimensionStatus.PARTIAL.value
    ]

    evaluation = PilotReadinessEvaluation(
        pilot_id=pilot_id,
        ai_system_id=ai_system_id,
        agent_version_id=agent_version_id,
        decision=decision,
        dimensions=dimensions,
        gaps=all_gaps,
        conditions=conditions,
        evaluated_by=evaluated_by,
        evaluated_at=_utcnow(),
    )
    db.add(evaluation)
    db.commit()
    db.refresh(evaluation)

    log_siem_event(
        trace_id=str(evaluation.id),
        event_type="pilot.readiness.evaluated",
        decision="allow"
        if decision != PilotReadinessDecision.NOT_READY.value
        else "deny",
        metadata={
            "ai_system_id": str(ai_system_id),
            "agent_version_id": str(agent_version_id) if agent_version_id else None,
            "pilot_id": str(pilot_id) if pilot_id else None,
            "decision": decision,
            "gap_count": len(all_gaps),
            "evaluated_by": evaluated_by,
        },
    )

    return {
        "id": str(evaluation.id),
        "pilot_id": str(pilot_id) if pilot_id else None,
        "ai_system_id": str(ai_system_id),
        "agent_version_id": str(agent_version_id) if agent_version_id else None,
        "decision": decision,
        "dimensions": dimensions,
        "gaps": all_gaps,
        "conditions": conditions,
        "evaluated_by": evaluated_by,
        "evaluated_at": evaluation.evaluated_at.isoformat()
        if evaluation.evaluated_at
        else None,
    }
