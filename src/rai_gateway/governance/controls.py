"""WP8 control framework seeding, applicability, and automated assessment."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from rai_gateway.core.observability import log_siem_event
from rai_gateway.governance.domain import (
    PILOT_CONTROL_OBJECTIVES,
    AssessmentMethod,
    ControlApplicability,
    ControlAssessmentStatus,
)
from rai_gateway.models.governance import (
    AISystemAccountability,
    AISystemGovernanceClassification,
    ControlAssessment,
    ControlFramework,
    ControlMapping,
    ControlObjective,
    ControlRequirement,
    GovernanceAttestation,
    GovernanceReview,
    OrganizationMembership,
)
from rai_gateway.models.registry import Agent, AgentVersion

PILOT_FRAMEWORK_KEY = "rai-pilot-v1"
PILOT_FRAMEWORK_NAME = "RAI Pilot Control Pack v1"

_ALWAYS_REQUIRED = frozenset({"GOV-01", "INC-01"})
_CONSEQUENTIAL_REQUIRED = frozenset({"ACT-01", "ACT-02"})
_PRODUCTION_REQUIRED = frozenset({"EVAL-01", "EVAL-02", "GOV-02", "ID-01"})
_EVIDENCE_REQUIRED = frozenset({"EVD-01"})
_CLOSED_FINDING_STATUSES = frozenset({"CLOSED", "RESOLVED"})
_APPROVED_VERSION_STATUSES = frozenset({"APPROVED", "PRODUCTION", "ACTIVE"})


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_pilot_control_framework(db: Session, created_by: str) -> ControlFramework:
    """Idempotently seed the pilot control framework, objectives, and requirements."""
    existing = (
        db.query(ControlFramework)
        .filter(ControlFramework.framework_key == PILOT_FRAMEWORK_KEY)
        .first()
    )
    if existing:
        return existing

    framework = ControlFramework(
        framework_key=PILOT_FRAMEWORK_KEY,
        name=PILOT_FRAMEWORK_NAME,
        version="1.0",
        description=(
            "Product control objectives for government / regulated-enterprise pilots. "
            "Not a legal certification claim."
        ),
        is_internal=True,
        published=True,
        created_by=created_by,
    )
    db.add(framework)
    db.flush()

    gov01_requirement: ControlRequirement | None = None
    for obj in PILOT_CONTROL_OBJECTIVES:
        code = obj["code"]
        objective = ControlObjective(
            framework_id=framework.id,
            code=code,
            title=obj["title"],
            category=obj["category"],
            description=obj["title"],
        )
        db.add(objective)
        db.flush()

        default_applicability = (
            ControlApplicability.REQUIRED.value
            if code in _ALWAYS_REQUIRED
            else ControlApplicability.CONDITIONAL.value
        )
        requirement = ControlRequirement(
            objective_id=objective.id,
            requirement_key=code,
            statement=obj["title"],
            default_applicability=default_applicability,
            applicability_rules={
                "consequential_actions": list(_CONSEQUENTIAL_REQUIRED),
                "production": list(_PRODUCTION_REQUIRED),
                "personal_data_or_external_facing": list(_EVIDENCE_REQUIRED),
            },
            automated_check=code,
            # Identity binding must not be waived when consequential systems apply.
            non_waivable=(code == "ID-01"),
        )
        db.add(requirement)
        db.flush()
        if code == "GOV-01":
            gov01_requirement = requirement

    if gov01_requirement is not None:
        db.add(
            ControlMapping(
                internal_requirement_id=gov01_requirement.id,
                external_framework="NIST AI RMF",
                external_requirement_id="GOVERN-1.1",
                external_requirement_title="Policies, processes, procedures, and practices across the AI system lifecycle",
                notes="Illustrative mapping for pilot evidence packages; not a certification claim.",
            )
        )

    db.commit()
    db.refresh(framework)
    return framework


def resolve_applicability(
    classification: dict[str, Any] | None,
    requirement: ControlRequirement,
) -> tuple[str, str]:
    """Resolve control applicability for a system classification."""
    classification = classification or {}
    code = requirement.requirement_key or requirement.automated_check or ""

    consequential = bool(classification.get("consequential_actions"))
    production = bool(classification.get("production"))
    personal_data = bool(classification.get("personal_data"))
    external_facing = bool(classification.get("external_facing"))

    if consequential and code in _CONSEQUENTIAL_REQUIRED:
        return (
            ControlApplicability.REQUIRED.value,
            "consequential_actions requires action/approval controls",
        )
    if production and code in _PRODUCTION_REQUIRED:
        return (
            ControlApplicability.REQUIRED.value,
            "production deployment requires evaluation, version approval, and identity binding",
        )
    if (personal_data or external_facing) and code in _EVIDENCE_REQUIRED:
        return (
            ControlApplicability.REQUIRED.value,
            "personal_data or external_facing requires evidence retention",
        )

    default = (
        requirement.default_applicability or ControlApplicability.CONDITIONAL.value
    )
    return default, f"default_applicability={default}"


def _classification_dict(
    row: AISystemGovernanceClassification | None,
) -> dict[str, Any]:
    if row is None:
        return {}
    return {
        "business_criticality": row.business_criticality,
        "data_sensitivity": row.data_sensitivity,
        "customer_citizen_impact": row.customer_citizen_impact,
        "financial_impact": row.financial_impact,
        "autonomy_level": row.autonomy_level,
        "external_facing": bool(row.external_facing),
        "consequential_actions": bool(row.consequential_actions),
        "personal_data": bool(row.personal_data),
        "regulated_process": bool(row.regulated_process),
        "human_oversight_requirement": row.human_oversight_requirement,
        "production": bool(row.production),
    }


def _upsert_assessment(
    db: Session,
    *,
    ai_system_id: UUID,
    agent_version_id: UUID | None,
    requirement: ControlRequirement,
    applicability: str,
    applicability_reason: str,
    status: str,
    evidence_refs: list[dict[str, Any]] | None,
    notes: str | None,
) -> ControlAssessment:
    q = db.query(ControlAssessment).filter(
        ControlAssessment.ai_system_id == ai_system_id,
        ControlAssessment.control_requirement_id == requirement.id,
    )
    if agent_version_id is None:
        q = q.filter(ControlAssessment.agent_version_id.is_(None))
    else:
        q = q.filter(ControlAssessment.agent_version_id == agent_version_id)
    row = q.first()
    now = _utcnow()
    if row is None:
        row = ControlAssessment(
            ai_system_id=ai_system_id,
            agent_version_id=agent_version_id,
            control_requirement_id=requirement.id,
        )
        db.add(row)

    row.applicability = applicability
    row.applicability_reason = applicability_reason
    row.status = status
    row.assessment_method = AssessmentMethod.AUTOMATED.value
    row.evidence_refs = evidence_refs or []
    row.assessed_by = "system:automated"
    row.assessed_at = now
    row.notes = notes
    return row


def _version_ids_for_system(
    db: Session, ai_system_id: UUID, agent_version_id: UUID | None
) -> list[UUID]:
    if agent_version_id:
        return [agent_version_id]
    agents = db.query(Agent).filter(Agent.ai_system_id == ai_system_id).all()
    ids: list[UUID] = []
    for agent in agents:
        versions = (
            db.query(AgentVersion).filter(AgentVersion.agent_id == agent.id).all()
        )
        ids.extend(v.id for v in versions)
    return ids


def automated_assess(
    db: Session,
    ai_system_id: UUID,
    agent_version_id: UUID | None = None,
) -> list[ControlAssessment]:
    """Refresh automated control assessments from WP1–WP7 authoritative state."""
    ensure_pilot_control_framework(db, created_by="system:automated")

    framework = (
        db.query(ControlFramework)
        .filter(ControlFramework.framework_key == PILOT_FRAMEWORK_KEY)
        .first()
    )
    if framework is None:
        return []

    objectives = (
        db.query(ControlObjective)
        .filter(ControlObjective.framework_id == framework.id)
        .all()
    )
    requirements: list[ControlRequirement] = []
    for objective in objectives:
        requirements.extend(
            db.query(ControlRequirement)
            .filter(ControlRequirement.objective_id == objective.id)
            .all()
        )

    classification_row = (
        db.query(AISystemGovernanceClassification)
        .filter(
            AISystemGovernanceClassification.ai_system_id == ai_system_id,
        )
        .first()
    )
    classification = _classification_dict(classification_row)
    consequential = bool(classification.get("consequential_actions"))

    accountability = (
        db.query(AISystemAccountability)
        .filter(
            AISystemAccountability.ai_system_id == ai_system_id,
        )
        .first()
    )

    results: list[ControlAssessment] = []
    for requirement in requirements:
        code = requirement.requirement_key or requirement.automated_check or ""
        applicability, reason = resolve_applicability(classification, requirement)

        if applicability == ControlApplicability.NOT_APPLICABLE.value:
            results.append(
                _upsert_assessment(
                    db,
                    ai_system_id=ai_system_id,
                    agent_version_id=agent_version_id,
                    requirement=requirement,
                    applicability=applicability,
                    applicability_reason=reason,
                    status=ControlAssessmentStatus.NOT_APPLICABLE.value,
                    evidence_refs=[],
                    notes="Not applicable for current classification",
                )
            )
            continue

        status, evidence, notes = _assess_code(
            db,
            code=code,
            ai_system_id=ai_system_id,
            agent_version_id=agent_version_id,
            accountability=accountability,
            consequential=consequential,
            applicability=applicability,
        )
        results.append(
            _upsert_assessment(
                db,
                ai_system_id=ai_system_id,
                agent_version_id=agent_version_id,
                requirement=requirement,
                applicability=applicability,
                applicability_reason=reason,
                status=status,
                evidence_refs=evidence,
                notes=notes,
            )
        )

    db.commit()
    for row in results:
        db.refresh(row)

    log_siem_event(
        trace_id=str(ai_system_id),
        event_type="governance.control.assessed",
        decision="allow",
        metadata={
            "ai_system_id": str(ai_system_id),
            "agent_version_id": str(agent_version_id) if agent_version_id else None,
            "assessment_count": len(results),
            "method": AssessmentMethod.AUTOMATED.value,
        },
    )
    return results


def _assess_code(
    db: Session,
    *,
    code: str,
    ai_system_id: UUID,
    agent_version_id: UUID | None,
    accountability: AISystemAccountability | None,
    consequential: bool,
    applicability: str,
) -> tuple[str, list[dict[str, Any]], str | None]:
    sat = ControlAssessmentStatus.SATISFIED.value
    partial = ControlAssessmentStatus.PARTIALLY_SATISFIED.value
    unsat = ControlAssessmentStatus.NOT_SATISFIED.value
    na = ControlAssessmentStatus.NOT_APPLICABLE.value
    not_assessed = ControlAssessmentStatus.NOT_ASSESSED.value

    if code == "GOV-01":
        if accountability is None:
            return unsat, [], "No accountability record"
        ok = bool(
            accountability.business_owner_membership_id
            and accountability.technical_owner_membership_id
            and accountability.rai_officer_membership_id
        )
        return (
            sat if ok else unsat,
            [{"type": "accountability", "id": str(accountability.id)}],
            None if ok else "Missing business, technical, or RAI officer membership",
        )

    if code == "GOV-02":
        version = None
        if agent_version_id:
            version = (
                db.query(AgentVersion)
                .filter(AgentVersion.id == agent_version_id)
                .first()
            )
        else:
            agents = db.query(Agent).filter(Agent.ai_system_id == ai_system_id).all()
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
            return unsat, [], "No agent version found"
        ok = (version.lifecycle_status or "").upper() in _APPROVED_VERSION_STATUSES
        return (
            sat if ok else unsat,
            [
                {
                    "type": "agent_version",
                    "id": str(version.id),
                    "lifecycle_status": version.lifecycle_status,
                }
            ],
            None
            if ok
            else f"Version lifecycle_status={version.lifecycle_status} not approved/active",
        )

    if code == "RISK-01":
        try:
            from rai_gateway.models.registry import RiskAssessment
        except Exception:
            return not_assessed, [], "RiskAssessment model unavailable"
        version_ids = _version_ids_for_system(db, ai_system_id, agent_version_id)
        q = db.query(RiskAssessment).filter(RiskAssessment.ai_system_id == ai_system_id)
        if version_ids:
            q = q.filter(
                (RiskAssessment.agent_version_id.in_(version_ids))
                | (RiskAssessment.agent_version_id.is_(None))
            )
        row = q.order_by(RiskAssessment.created_at.desc()).first()
        if row is None:
            return unsat, [], "No risk assessment found"
        return (
            sat,
            [{"type": "risk_assessment", "id": str(row.id), "status": row.status}],
            None,
        )

    if code == "RISK-02":
        try:
            from rai_gateway.models.risk_intelligence import RuntimeRiskFinding
        except Exception:
            return sat, [], "RuntimeRiskFinding model unavailable; treated as clear"
        q = db.query(RuntimeRiskFinding).filter(
            RuntimeRiskFinding.ai_system_id == ai_system_id,
            RuntimeRiskFinding.severity.in_(["HIGH", "CRITICAL"]),
            ~RuntimeRiskFinding.status.in_(list(_CLOSED_FINDING_STATUSES)),
        )
        if agent_version_id:
            q = q.filter(
                (RuntimeRiskFinding.agent_version_id == agent_version_id)
                | (RuntimeRiskFinding.agent_version_id.is_(None))
            )
        open_findings = q.limit(20).all()
        if open_findings:
            return (
                unsat,
                [
                    {
                        "type": "runtime_risk_finding",
                        "id": str(f.id),
                        "severity": f.severity,
                        "status": f.status,
                    }
                    for f in open_findings
                ],
                f"{len(open_findings)} open HIGH/CRITICAL runtime risk findings",
            )
        return sat, [], "No open HIGH/CRITICAL runtime risk findings"

    if code == "ID-01":
        try:
            from rai_gateway.models.identity import AgentRuntimeIdentity
        except Exception:
            return not_assessed, [], "Runtime identity model unavailable"
        if agent_version_id is None:
            return partial, [], "agent_version_id required for identity binding check"
        identity = (
            db.query(AgentRuntimeIdentity)
            .filter(
                AgentRuntimeIdentity.agent_version_id == agent_version_id,
                AgentRuntimeIdentity.status == "ACTIVE",
            )
            .first()
        )
        if identity is None:
            return unsat, [], "No ACTIVE runtime identity for agent version"
        return (
            sat,
            [{"type": "runtime_identity", "id": str(identity.id)}],
            None,
        )

    if code == "ID-02":
        try:
            from rai_gateway.models.identity import (
                AgentRuntimeIdentity,
                DelegationGrant,
                RuntimeCredential,
            )
        except Exception:
            return not_assessed, [], "Identity credential models unavailable"
        version_ids = _version_ids_for_system(db, ai_system_id, agent_version_id)
        if not version_ids and agent_version_id is None:
            return unsat, [], "No agent versions to check credentials against"
        identities = (
            db.query(AgentRuntimeIdentity)
            .filter(
                AgentRuntimeIdentity.agent_version_id.in_(
                    version_ids or [agent_version_id]
                ),
                AgentRuntimeIdentity.status == "ACTIVE",
            )
            .all()
            if (version_ids or agent_version_id)
            else []
        )
        if not identities:
            return unsat, [], "No ACTIVE runtime identity"
        identity_ids = [i.id for i in identities]
        cred = (
            db.query(RuntimeCredential)
            .filter(
                RuntimeCredential.runtime_identity_id.in_(identity_ids),
                RuntimeCredential.status == "ACTIVE",
            )
            .first()
        )
        deleg = (
            db.query(DelegationGrant)
            .filter(
                DelegationGrant.delegate_runtime_identity_id.in_(identity_ids),
                DelegationGrant.status == "ACTIVE",
            )
            .first()
        )
        if cred or deleg:
            refs = []
            if cred:
                refs.append({"type": "runtime_credential", "id": str(cred.id)})
            if deleg:
                refs.append({"type": "delegation_grant", "id": str(deleg.id)})
            return sat, refs, None
        return (
            partial,
            [{"type": "runtime_identity", "id": str(identities[0].id)}],
            "Identity exists but no ACTIVE credential/delegation found",
        )

    if code in {"ACT-01", "ACT-02"}:
        if not consequential:
            return na, [], "Not consequential; action controls not applicable"
        has_policy = False
        has_approval = False
        evidence: list[dict[str, Any]] = []
        try:
            from rai_gateway.models.policy_engine import (
                ContentRule,
                PolicyCollection,
                ToolRule,
            )

            collection = (
                db.query(PolicyCollection)
                .filter(PolicyCollection.ai_system_id == ai_system_id)
                .first()
            )
            if collection:
                tool = (
                    db.query(ToolRule)
                    .filter(
                        ToolRule.policy_collection_id == collection.id,
                        ToolRule.enabled.is_(True),
                        ToolRule.archived_at.is_(None),
                    )
                    .first()
                )
                content = (
                    db.query(ContentRule)
                    .filter(
                        ContentRule.policy_collection_id == collection.id,
                        ContentRule.enabled.is_(True),
                        ContentRule.archived_at.is_(None),
                    )
                    .first()
                )
                if tool:
                    has_policy = True
                    evidence.append({"type": "tool_rule", "id": str(tool.id)})
                if content:
                    has_policy = True
                    evidence.append({"type": "content_rule", "id": str(content.id)})
        except Exception:
            pass
        try:
            from rai_gateway.models.approval import ApprovalRequest

            aq = db.query(ApprovalRequest).filter(
                ApprovalRequest.ai_system_id == ai_system_id
            )
            if agent_version_id:
                aq = aq.filter(ApprovalRequest.agent_version_id == agent_version_id)
            approval = aq.order_by(ApprovalRequest.created_at.desc()).first()
            if approval:
                has_approval = True
                evidence.append({"type": "approval_request", "id": str(approval.id)})
        except Exception:
            pass
        if code == "ACT-01":
            if has_policy:
                return sat, evidence, None
            return (
                partial if has_approval else unsat,
                evidence,
                "No tool/content policy rules found for consequential actions",
            )
        # ACT-02
        if has_approval or has_policy:
            return sat if has_approval else partial, evidence, None
        return unsat, evidence, "No approval request or approval-gated policy found"

    if code == "EVAL-01":
        if agent_version_id is None:
            return partial, [], "agent_version_id required for evaluation eligibility"
        try:
            from rai_gateway.evaluations.service import EvaluationService

            eligible = EvaluationService(db).is_environment_eligible(agent_version_id)
            return (
                sat if eligible else unsat,
                [{"type": "evaluation_eligibility", "eligible": eligible}],
                None if eligible else "Environment not evaluation-eligible",
            )
        except Exception as exc:
            return not_assessed, [], f"EvaluationService unavailable: {exc}"

    if code == "EVAL-02":
        if agent_version_id is None:
            return partial, [], "agent_version_id required for assurance check"
        try:
            from rai_gateway.evaluations.domain import AssuranceStatus
            from rai_gateway.models.evaluations import AssuranceRecord

            record = (
                db.query(AssuranceRecord)
                .filter(
                    AssuranceRecord.agent_version_id == agent_version_id,
                    AssuranceRecord.superseded_at.is_(None),
                    AssuranceRecord.status.in_(
                        [
                            AssuranceStatus.VALID.value,
                            AssuranceStatus.CONDITIONAL.value,
                        ]
                    ),
                )
                .order_by(AssuranceRecord.created_at.desc())
                .first()
            )
            if record is None:
                return unsat, [], "No VALID/CONDITIONAL assurance record"
            return (
                sat,
                [
                    {
                        "type": "assurance_record",
                        "id": str(record.id),
                        "status": record.status,
                    }
                ],
                None,
            )
        except Exception as exc:
            return not_assessed, [], f"Assurance models unavailable: {exc}"

    if code == "MON-01":
        evidence = []
        # RuntimeMonitor may not exist; fall back to budgets / risk state monitoring.
        try:
            from rai_gateway.models.risk_intelligence import (
                RuntimeMonitor,  # type: ignore
            )

            mon = (
                db.query(RuntimeMonitor)
                .filter(RuntimeMonitor.ai_system_id == ai_system_id)
                .first()
            )
            if mon:
                evidence.append({"type": "runtime_monitor", "id": str(mon.id)})
        except Exception:
            pass
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
            if budget:
                evidence.append({"type": "runtime_budget", "id": str(budget.id)})
        except Exception:
            pass
        try:
            from rai_gateway.models.risk_intelligence import RiskState

            state = (
                db.query(RiskState)
                .filter(RiskState.ai_system_id == ai_system_id)
                .first()
            )
            if state and (state.monitoring_status or "").upper() not in {"", "NONE"}:
                evidence.append(
                    {
                        "type": "risk_state",
                        "id": str(state.id),
                        "monitoring_status": state.monitoring_status,
                    }
                )
        except Exception:
            pass
        if evidence:
            return sat, evidence, None
        return unsat, [], "No runtime monitor, budget, or monitoring state found"

    if code == "MON-02":
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
        except Exception:
            budget = None
        if consequential:
            if budget:
                return sat, [{"type": "runtime_budget", "id": str(budget.id)}], None
            return unsat, [], "Consequential system requires runtime budget"
        if budget:
            return sat, [{"type": "runtime_budget", "id": str(budget.id)}], None
        if applicability == ControlApplicability.OPTIONAL.value:
            return sat, [], "Optional budget not configured; treated as satisfied"
        return sat, [], "Budgets optional when not consequential"

    if code == "INC-01":
        if accountability and accountability.incident_owner_membership_id:
            return (
                sat,
                [
                    {
                        "type": "incident_owner_membership",
                        "id": str(accountability.incident_owner_membership_id),
                    }
                ],
                None,
            )
        mgr = (
            db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.role == "INCIDENT_MANAGER",
                OrganizationMembership.status == "ACTIVE",
            )
            .first()
        )
        if mgr:
            return (
                sat,
                [{"type": "membership", "id": str(mgr.id), "role": mgr.role}],
                None,
            )
        return unsat, [], "No incident owner membership or ACTIVE INCIDENT_MANAGER"

    if code == "EVD-01":
        try:
            from rai_gateway.models.evidence import RuntimeTrajectory

            tq = db.query(RuntimeTrajectory).filter(
                RuntimeTrajectory.ai_system_id == ai_system_id
            )
            if agent_version_id:
                tq = tq.filter(RuntimeTrajectory.agent_version_id == agent_version_id)
            traj = tq.order_by(RuntimeTrajectory.created_at.desc()).first()
            if traj:
                return sat, [{"type": "runtime_trajectory", "id": str(traj.id)}], None
            return unsat, [], "No runtime trajectory evidence found"
        except Exception:
            return not_assessed, [], "RuntimeTrajectory model unavailable"

    if code == "EVD-02":
        review = (
            db.query(GovernanceReview)
            .filter(
                GovernanceReview.ai_system_id == ai_system_id,
                GovernanceReview.decision.isnot(None),
            )
            .order_by(GovernanceReview.created_at.desc())
            .first()
        )
        if review:
            return (
                sat,
                [
                    {
                        "type": "governance_review",
                        "id": str(review.id),
                        "decision": review.decision,
                    }
                ],
                None,
            )
        attestation = (
            db.query(GovernanceAttestation)
            .filter(
                GovernanceAttestation.ai_system_id == ai_system_id,
            )
            .order_by(GovernanceAttestation.created_at.desc())
            .first()
        )
        if attestation:
            return (
                sat,
                [{"type": "governance_attestation", "id": str(attestation.id)}],
                None,
            )
        return unsat, [], "No governance review decision or attestation found"

    # Unknown automated check — leave not assessed rather than fail hard.
    return not_assessed, [], f"No automated checker for {code}"
