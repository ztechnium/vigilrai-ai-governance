"""WP8 governance / pilot operating-model DoD tests."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from rai_gateway.governance.controls import ensure_pilot_control_framework
from rai_gateway.governance.domain import (
    ControlApplicability,
    ControlAssessmentStatus,
    CorrectiveActionStatus,
    EvidenceAvailability,
    ExceptionStatus,
    GovernanceRole,
    IncidentSeverity,
    IncidentStatus,
    MembershipStatus,
    PilotOrgStatus,
    PilotReadinessDecision,
    ReadinessDimensionStatus,
    ReviewDecision,
    ReviewStatus,
    ReviewType,
)
from rai_gateway.governance.errors import (
    GovernanceConflictError,
    GovernanceDeniedError,
    SeparationOfDutiesError,
    TenantIsolationError,
)
from rai_gateway.governance.seed import seed_reference_pilots
from rai_gateway.governance.service import GovernanceService
from rai_gateway.models.governance import ControlRequirement
from rai_gateway.registry.domain import AISystemStatus
from rai_gateway.registry.service import RegistryService

_ACCOUNTABILITY_ROLES = (
    GovernanceRole.BUSINESS_OWNER,
    GovernanceRole.TECHNICAL_OWNER,
    GovernanceRole.RAI_OFFICER,
    GovernanceRole.INCIDENT_MANAGER,
    GovernanceRole.BUSINESS_APPROVER,
    GovernanceRole.AUDITOR,
)


@pytest.fixture()
def gov(db_session) -> GovernanceService:
    return GovernanceService(db_session)


@pytest.fixture()
def registry(db_session) -> RegistryService:
    return RegistryService(db_session)


def _org_with_members(gov: GovernanceService) -> dict:
    """Memberships for core WP8 roles with distinct user ids."""
    suffix = uuid.uuid4().hex[:8]
    memberships: dict[str, dict] = {}
    for role in _ACCOUNTABILITY_ROLES:
        user_id = f"user-{role.value.lower()}-{suffix}"
        memberships[role.value] = gov.create_membership(
            user_id=user_id,
            role=role.value,
            created_by="tester",
            status=MembershipStatus.ACTIVE.value,
        )
    return {
        "suffix": suffix,
        "org_id": uuid.uuid4(),
        "memberships": memberships,
        "users": {
            role.value: memberships[role.value]["user_id"]
            for role in _ACCOUNTABILITY_ROLES
        },
    }


def _linked_system(registry: RegistryService, gov: GovernanceService, org_id: UUID):
    """Create AI system, transition to APPROVED, link to org, return system."""
    suffix = uuid.uuid4().hex[:8]
    system = registry.create_ai_system(
        system_key=f"wp8-sys-{suffix}",
        name=f"WP8 System {suffix}",
        created_by="tester",
    )
    for status in (AISystemStatus.UNDER_REVIEW, AISystemStatus.APPROVED):
        registry.transition_ai_system(system.id, status.value, updated_by="tester")
    gov.link_ai_system(system.id, "tester")
    return system


def _requirement_by_key(db_session, key: str) -> ControlRequirement:
    ensure_pilot_control_framework(db_session, created_by="tester")
    row = (
        db_session.query(ControlRequirement)
        .filter(ControlRequirement.requirement_key == key)
        .first()
    )
    assert row is not None, f"Control requirement {key} not seeded"
    return row


def test_organization_governance_profile(gov: GovernanceService):
    gov.patch_governance_profile(
        updated_by="tester",
        sector="Healthcare",
        jurisdiction="UNSPECIFIED",
        pilot_status=PilotOrgStatus.PLANNING.value,
    )
    profile = gov.get_governance_profile()
    assert profile["sector"] == "Healthcare"
    assert profile["jurisdiction"] == "UNSPECIFIED"
    assert profile["pilot_status"] == PilotOrgStatus.PLANNING.value

    patched = gov.patch_governance_profile(
        updated_by="tester",
        sector="Public Sector",
        jurisdiction="EU",
        pilot_status=PilotOrgStatus.CONFIGURING.value,
    )
    assert patched["sector"] == "Public Sector"
    assert patched["jurisdiction"] == "EU"
    assert patched["pilot_status"] == PilotOrgStatus.CONFIGURING.value


def test_membership_authorization(gov: GovernanceService):
    ctx = _org_with_members(gov)
    member = ctx["users"][GovernanceRole.BUSINESS_OWNER.value]

    membership = gov.assert_membership(member)
    assert membership.user_id == member
    assert membership.role == GovernanceRole.BUSINESS_OWNER.value

    with pytest.raises(TenantIsolationError):
        gov.assert_membership(f"stranger-{ctx['suffix']}")


def test_accountability_assignment_and_missing_roles(
    gov: GovernanceService, registry: RegistryService
):
    ctx = _org_with_members(gov)
    system = _linked_system(registry, gov, ctx["org_id"])
    m = ctx["memberships"]

    gov.upsert_accountability(
        system.id,
        created_by="tester",
        business_owner_membership_id=UUID(m[GovernanceRole.BUSINESS_OWNER.value]["id"]),
    )
    accountability = gov.get_accountability(system.id)
    assert set(accountability["missing_required_roles"]) == {
        "TECHNICAL_OWNER",
        "RAI_OFFICER",
    }

    full = gov.upsert_accountability(
        system.id,
        created_by="tester",
        business_owner_membership_id=UUID(m[GovernanceRole.BUSINESS_OWNER.value]["id"]),
        technical_owner_membership_id=UUID(
            m[GovernanceRole.TECHNICAL_OWNER.value]["id"]
        ),
        rai_officer_membership_id=UUID(m[GovernanceRole.RAI_OFFICER.value]["id"]),
    )
    assert (
        full["business_owner_membership_id"]
        == m[GovernanceRole.BUSINESS_OWNER.value]["id"]
    )
    complete = gov.get_accountability(system.id)
    assert complete["missing_required_roles"] == []


def test_separation_of_duties_accountability(
    gov: GovernanceService, registry: RegistryService
):
    ctx = _org_with_members(gov)
    system = _linked_system(registry, gov, ctx["org_id"])
    owner_mid = UUID(ctx["memberships"][GovernanceRole.BUSINESS_OWNER.value]["id"])

    # SoD is enforced only for production systems.
    gov.upsert_classification(
        system.id,
        updated_by="tester",
        production=True,
        consequential_actions=True,
    )

    with pytest.raises(SeparationOfDutiesError):
        gov.upsert_accountability(
            system.id,
            created_by="tester",
            business_owner_membership_id=owner_mid,
            rai_officer_membership_id=owner_mid,
            enforce_sod=True,
        )


def test_control_framework_and_applicability(
    gov: GovernanceService, registry: RegistryService, db_session
):
    ctx = _org_with_members(gov)
    system = _linked_system(registry, gov, ctx["org_id"])

    framework = ensure_pilot_control_framework(db_session, created_by="tester")
    assert framework.framework_key == "rai-pilot-v1"

    gov.upsert_classification(
        system.id,
        updated_by="tester",
        consequential_actions=True,
        production=True,
    )
    assessments = gov.refresh_automated_assessments(system.id)
    by_req = {a["control_requirement_id"]: a for a in assessments}

    act01 = _requirement_by_key(db_session, "ACT-01")
    eval01 = _requirement_by_key(db_session, "EVAL-01")
    assert by_req[str(act01.id)]["applicability"] == ControlApplicability.REQUIRED.value
    assert (
        by_req[str(eval01.id)]["applicability"] == ControlApplicability.REQUIRED.value
    )


def test_manual_assessment(
    gov: GovernanceService, registry: RegistryService, db_session
):
    ctx = _org_with_members(gov)
    system = _linked_system(registry, gov, ctx["org_id"])
    req = _requirement_by_key(db_session, "GOV-01")

    assessed = gov.record_manual_assessment(
        system.id,
        control_requirement_id=req.id,
        status=ControlAssessmentStatus.SATISFIED.value,
        assessed_by=ctx["users"][GovernanceRole.RAI_OFFICER.value],
        evidence_refs=[{"type": "attestation", "ref": "att-1"}],
        notes="Manual evidence review complete",
    )
    assert assessed["status"] == ControlAssessmentStatus.SATISFIED.value
    assert assessed["assessment_method"] == "MANUAL"
    assert assessed["evidence_refs"] == [{"type": "attestation", "ref": "att-1"}]


def test_review_lifecycle_and_decision(
    gov: GovernanceService, registry: RegistryService
):
    ctx = _org_with_members(gov)
    system = _linked_system(registry, gov, ctx["org_id"])
    requester = ctx["users"][GovernanceRole.BUSINESS_OWNER.value]

    review = gov.create_review(
        system.id,
        review_type=ReviewType.PRE_PRODUCTION.value,
        requested_by=requester,
    )
    assert review["review_type"] == ReviewType.PRE_PRODUCTION.value
    assert review["status"] == ReviewStatus.REQUESTED.value
    assert review["checklist"] is not None

    decided = gov.decide_review(
        UUID(review["id"]),
        decision=ReviewDecision.APPROVE.value,
        decision_reason="Pre-production controls meet pilot bar",
        decided_by=ctx["users"][GovernanceRole.BUSINESS_APPROVER.value],
    )
    assert decided["status"] == ReviewStatus.COMPLETED.value
    assert decided["decision"] == ReviewDecision.APPROVE.value
    assert decided["checklist"] is not None

    # Empty reason is rejected before the immutability check would apply.
    review2 = gov.create_review(
        system.id,
        review_type=ReviewType.PRE_PRODUCTION.value,
        requested_by=requester,
    )
    with pytest.raises(GovernanceConflictError):
        gov.decide_review(
            UUID(review2["id"]),
            decision=ReviewDecision.APPROVE.value,
            decision_reason="",
            decided_by=ctx["users"][GovernanceRole.AUDITOR.value],
        )


def test_review_sod_or_authorization(gov: GovernanceService, registry: RegistryService):
    ctx = _org_with_members(gov)
    system = _linked_system(registry, gov, ctx["org_id"])
    requester = ctx["users"][GovernanceRole.BUSINESS_OWNER.value]

    review = gov.create_review(
        system.id,
        review_type=ReviewType.PRE_PRODUCTION.value,
        requested_by=requester,
    )
    # WP8 allows requester to decide unless a stronger SoD rule is added later.
    decided = gov.decide_review(
        UUID(review["id"]),
        decision=ReviewDecision.APPROVE.value,
        decision_reason="Requester decision permitted for WP8",
        decided_by=requester,
    )
    assert decided["status"] == ReviewStatus.COMPLETED.value
    assert decided["decided_by"] == requester

    with pytest.raises(GovernanceConflictError, match="immutable"):
        gov.decide_review(
            UUID(review["id"]),
            decision=ReviewDecision.SUSPEND.value,
            decision_reason="Second decision must fail",
            decided_by=ctx["users"][GovernanceRole.AUDITOR.value],
        )


def test_exception_lifecycle_sod(
    gov: GovernanceService, registry: RegistryService, db_session
):
    ctx = _org_with_members(gov)
    system = _linked_system(registry, gov, ctx["org_id"])
    req = _requirement_by_key(db_session, "ACT-01")
    requester = ctx["users"][GovernanceRole.BUSINESS_OWNER.value]
    approver = ctx["users"][GovernanceRole.BUSINESS_APPROVER.value]

    exc = gov.request_exception(
        system.id,
        business_justification="Temporary compensating control while policy ships",
        requester=requester,
        control_requirement_id=req.id,
        risk="MEDIUM",
        compensating_controls=["manual dual-control"],
        valid_until=datetime.now(timezone.utc) + timedelta(days=30),
    )
    assert exc["status"] == ExceptionStatus.REQUESTED.value

    with pytest.raises(SeparationOfDutiesError):
        gov.approve_exception(
            UUID(exc["id"]),
            approver=requester,
            decision_reason="Self-approve must fail",
        )

    approved = gov.approve_exception(
        UUID(exc["id"]),
        approver=approver,
        decision_reason="Compensating controls accepted for pilot window",
    )
    assert approved["status"] == ExceptionStatus.APPROVED.value
    assert approved["approver"] == approver

    revoked = gov.revoke_exception(
        UUID(exc["id"]),
        actor=approver,
        decision_reason="Window closed",
    )
    assert revoked["status"] == ExceptionStatus.REVOKED.value


def test_exception_non_waivable(
    gov: GovernanceService, registry: RegistryService, db_session
):
    ctx = _org_with_members(gov)
    system = _linked_system(registry, gov, ctx["org_id"])
    # Seed ID-01 as non-waivable; request is blocked up-front.
    id01 = _requirement_by_key(db_session, "ID-01")
    assert id01.non_waivable is True
    with pytest.raises(GovernanceDeniedError):
        gov.request_exception(
            system.id,
            business_justification="Cannot waive identity binding",
            requester=ctx["users"][GovernanceRole.BUSINESS_OWNER.value],
            control_requirement_id=id01.id,
        )

    # Approve path: request against a waivable requirement, then flip non_waivable.
    act01 = _requirement_by_key(db_session, "ACT-01")
    assert act01.non_waivable is False
    exc = gov.request_exception(
        system.id,
        business_justification="Will become non-waivable before approve",
        requester=ctx["users"][GovernanceRole.BUSINESS_OWNER.value],
        control_requirement_id=act01.id,
    )
    act01.non_waivable = True
    db_session.commit()
    try:
        with pytest.raises(GovernanceDeniedError):
            gov.approve_exception(
                UUID(exc["id"]),
                approver=ctx["users"][GovernanceRole.BUSINESS_APPROVER.value],
                decision_reason="Should be denied as non-waivable",
            )
    finally:
        act01.non_waivable = False
        db_session.commit()


def test_incident_lifecycle_containment_corrective(
    gov: GovernanceService, registry: RegistryService
):
    ctx = _org_with_members(gov)
    system = _linked_system(registry, gov, ctx["org_id"])
    reporter = ctx["users"][GovernanceRole.BUSINESS_OWNER.value]
    manager = ctx["users"][GovernanceRole.INCIDENT_MANAGER.value]

    incident = gov.create_incident(
        system.id,
        title="High severity policy breach",
        reported_by=reporter,
        severity=IncidentSeverity.HIGH.value,
        category="POLICY_VIOLATION",
        description="Unauthorized consequential action attempted",
        incident_manager=manager,
    )
    assert incident["status"] == IncidentStatus.OPEN.value
    incident_id = UUID(incident["id"])

    triaged = gov.transition_incident(
        incident_id,
        to_status=IncidentStatus.TRIAGED.value,
        actor=manager,
        reason="Initial triage complete",
    )
    assert triaged["status"] == IncidentStatus.TRIAGED.value

    contained = gov.contain_incident(
        incident_id,
        actor=manager,
        containment_action="suspend_runtime_identity",
        containment_ref={"action": "suspend"},
        reason="Identity suspended",
    )
    assert contained["status"] == IncidentStatus.CONTAINED.value
    assert contained["containment_action"] == "suspend_runtime_identity"

    action = gov.add_corrective_action(
        incident_id,
        description="Tighten consequential-action policy",
        owner=manager,
    )
    done = gov.update_corrective_action(
        UUID(action["id"]),
        status=CorrectiveActionStatus.DONE.value,
        evidence={"ticket": "INC-FIX-1"},
    )
    assert done["status"] == CorrectiveActionStatus.DONE.value
    assert done["completed_at"] is not None

    resolved = gov.transition_incident(
        incident_id,
        to_status=IncidentStatus.RESOLVED.value,
        actor=manager,
        reason="Corrective action complete",
    )
    assert resolved["status"] == IncidentStatus.RESOLVED.value

    closed = gov.transition_incident(
        incident_id,
        to_status=IncidentStatus.CLOSED.value,
        actor=manager,
        reason="Verified and closed",
    )
    assert closed["status"] == IncidentStatus.CLOSED.value

    critical = gov.create_incident(
        system.id,
        title="Critical reporter SoD check",
        reported_by=reporter,
        severity=IncidentSeverity.CRITICAL.value,
        category="SECURITY",
        incident_manager=manager,
    )
    with pytest.raises(SeparationOfDutiesError):
        gov.transition_incident(
            UUID(critical["id"]),
            to_status=IncidentStatus.CLOSED.value,
            actor=reporter,
            reason="Reporter cannot close CRITICAL",
        )


def test_evidence_package_manifest(gov: GovernanceService, registry: RegistryService):
    ctx = _org_with_members(gov)
    system = _linked_system(registry, gov, ctx["org_id"])

    package = gov.generate_evidence_package(
        generated_by=ctx["users"][GovernanceRole.AUDITOR.value],
        ai_system_id=system.id,
        include_html=True,
    )
    assert package["package_digest"]
    assert len(package["package_digest"]) == 64
    manifest = package["manifest"]
    assert "sections" in manifest
    assert "missing_evidence" in manifest
    assert isinstance(manifest["missing_evidence"], list)

    for name, body in manifest["sections"].items():
        assert "availability" in body
        assert body["availability"] in {e.value for e in EvidenceAvailability}
        if body["availability"] == EvidenceAvailability.NOT_AVAILABLE.value:
            assert name in manifest["missing_evidence"]
            assert body["data"] is None


def test_pilot_readiness_not_ready_then_ready(
    gov: GovernanceService, registry: RegistryService
):
    ctx = _org_with_members(gov)
    system = _linked_system(registry, gov, ctx["org_id"])

    before = gov.evaluate_readiness(
        ai_system_id=system.id,
        evaluated_by="tester",
    )
    assert before["decision"] == PilotReadinessDecision.NOT_READY.value
    assert "ACCOUNTABILITY" in before["dimensions"]
    assert before["dimensions"]["ACCOUNTABILITY"]["status"] == (
        ReadinessDimensionStatus.NOT_READY.value
    )
    assert before["dimensions"]["ACCOUNTABILITY"]["reason"]
    assert before["dimensions"]["ACCOUNTABILITY"]["gaps"]

    m = ctx["memberships"]
    gov.upsert_classification(
        system.id,
        updated_by="tester",
        production=True,
        consequential_actions=False,
    )
    gov.upsert_accountability(
        system.id,
        created_by="tester",
        business_owner_membership_id=UUID(m[GovernanceRole.BUSINESS_OWNER.value]["id"]),
        technical_owner_membership_id=UUID(
            m[GovernanceRole.TECHNICAL_OWNER.value]["id"]
        ),
        rai_officer_membership_id=UUID(m[GovernanceRole.RAI_OFFICER.value]["id"]),
        incident_owner_membership_id=UUID(
            m[GovernanceRole.INCIDENT_MANAGER.value]["id"]
        ),
    )

    after = gov.evaluate_readiness(
        ai_system_id=system.id,
        evaluated_by="tester",
    )
    # Other dimensions may still block overall readiness.
    assert after["dimensions"]["ACCOUNTABILITY"]["status"] == (
        ReadinessDimensionStatus.READY.value
    )
    for dim in after["dimensions"].values():
        assert "status" in dim
        assert "reason" in dim
        assert "gaps" in dim
        assert dim["status"] in {s.value for s in ReadinessDimensionStatus}


def test_pilot_activation_requires_readiness(
    gov: GovernanceService, registry: RegistryService
):
    ctx = _org_with_members(gov)
    system = _linked_system(registry, gov, ctx["org_id"])
    pilot = gov.create_pilot(
        name=f"Pilot {ctx['suffix']}",
        created_by="tester",
        sponsor=ctx["users"][GovernanceRole.BUSINESS_OWNER.value],
    )
    gov.add_ai_system_to_pilot(UUID(pilot["id"]), system.id)

    # Soft assert: cannot jump to ACTIVE without a READY readiness evaluation.
    try:
        gov.transition_pilot_status(
            UUID(pilot["id"]),
            to_status=PilotOrgStatus.ACTIVE.value,
            actor="tester",
        )
        pytest.fail("Expected activation without readiness to be rejected")
    except (GovernanceConflictError, GovernanceDeniedError):
        pass

    # Walk to READY status, then still require readiness evaluation for ACTIVE.
    gov.transition_pilot_status(
        UUID(pilot["id"]),
        to_status=PilotOrgStatus.READINESS_REVIEW.value,
        actor="tester",
    )
    gov.transition_pilot_status(
        UUID(pilot["id"]),
        to_status=PilotOrgStatus.READY.value,
        actor="tester",
    )
    with pytest.raises(GovernanceDeniedError, match="readiness"):
        gov.transition_pilot_status(
            UUID(pilot["id"]),
            to_status=PilotOrgStatus.ACTIVE.value,
            actor="tester",
        )


def test_seed_reference_pilots(db_session):
    result = seed_reference_pilots(db_session)
    assert "acme" in result
    assert "public_services" in result
    assert result["acme"]["pilot"]["name"] == "Acme Sales AI Pilot"
    assert (
        result["public_services"]["pilot"]["name"] == "Citizen Service Assistant Pilot"
    )
    assert result["control_framework"]["framework_key"] == "rai-pilot-v1"

    again = seed_reference_pilots(db_session)
    assert again["acme"]["pilot"]["name"] == result["acme"]["pilot"]["name"]
    assert (
        again["public_services"]["pilot"]["name"]
        == result["public_services"]["pilot"]["name"]
    )


def test_attestation_append_only(gov: GovernanceService, registry: RegistryService):
    ctx = _org_with_members(gov)
    system = _linked_system(registry, gov, ctx["org_id"])
    att = gov.create_attestation(
        attestation_type="CONTROL_ASSESSMENT",
        statement="Control pack assessed for pilot readiness",
        actor=ctx["users"][GovernanceRole.RAI_OFFICER.value],
        ai_system_id=system.id,
        actor_role=GovernanceRole.RAI_OFFICER.value,
        valid_until=datetime.now(timezone.utc) + timedelta(days=30),
    )
    assert att["attestation_type"] == "CONTROL_ASSESSMENT"
    assert att["statement"]
    assert att["actor"] == ctx["users"][GovernanceRole.RAI_OFFICER.value]
    listed = gov.list_attestations(ai_system_id=system.id)
    assert any(row["id"] == att["id"] for row in listed)


def test_periodic_review_due_processing(
    gov: GovernanceService, registry: RegistryService, db_session
):
    from rai_gateway.models.governance import PeriodicReviewSchedule

    ctx = _org_with_members(gov)
    system = _linked_system(registry, gov, ctx["org_id"])
    schedule = gov.ensure_periodic_schedule(
        system.id,
        created_by="tester",
        frequency_days=90,
    )
    row = (
        db_session.query(PeriodicReviewSchedule)
        .filter(PeriodicReviewSchedule.id == UUID(schedule["id"]))
        .one()
    )
    row.next_due_at = datetime.now(timezone.utc) - timedelta(days=1)
    db_session.commit()

    created = gov.process_due_periodic_reviews(actor="scheduler")
    assert len(created) >= 1
    assert created[0]["review_type"] == ReviewType.PERIODIC.value
    assert created[0]["ai_system_id"] == str(system.id)

    # Second pass should not duplicate while an open periodic review exists.
    again = gov.process_due_periodic_reviews(actor="scheduler")
    assert again == []


def test_exception_compensating_controls_recorded(
    gov: GovernanceService, registry: RegistryService
):
    ctx = _org_with_members(gov)
    system = _linked_system(registry, gov, ctx["org_id"])
    compensating = [
        {"control": "human-in-the-loop", "description": "Manual approve for outbound"},
        {"control": "budget-cap", "ref": "wp6-budget-1"},
    ]
    exc = gov.request_exception(
        system.id,
        business_justification="Need temporary exception with compensating controls",
        requester=ctx["users"][GovernanceRole.BUSINESS_OWNER.value],
        compensating_controls=compensating,
        risk="Medium residual risk with HITL",
    )
    assert exc["status"] == ExceptionStatus.REQUESTED.value
    assert isinstance(exc["compensating_controls"], list)
    assert len(exc["compensating_controls"]) == 2
    assert exc["compensating_controls"][0]["control"] == "human-in-the-loop"


def test_high_incident_triggers_incident_driven_review(
    gov: GovernanceService, registry: RegistryService
):
    ctx = _org_with_members(gov)
    system = _linked_system(registry, gov, ctx["org_id"])
    incident = gov.create_incident(
        system.id,
        title="Critical breach requiring governance review",
        reported_by=ctx["users"][GovernanceRole.INCIDENT_MANAGER.value],
        severity=IncidentSeverity.CRITICAL.value,
        category="SECURITY",
    )
    reviews = gov.list_reviews(
        ai_system_id=system.id,
    )
    incident_driven = [
        r for r in reviews if r["review_type"] == ReviewType.INCIDENT_DRIVEN.value
    ]
    assert len(incident_driven) >= 1
    assert incident["severity"] == IncidentSeverity.CRITICAL.value


def test_governance_rbac_permissions(db_session):
    """Server-side RBAC: auditor read-only; incident manager can manage incidents."""
    from fastapi import HTTPException

    from rai_gateway.core.auth import AdminIdentity
    from rai_gateway.services.admin_console import require_admin_permission

    def _as(role: str) -> AdminIdentity:
        return AdminIdentity(email=f"{role}@example.com", user_id=role, roles=[role])

    require_admin_permission(
        db_session,
        "organization_governance:read",
        "auditor",
        identity=_as("auditor"),
    )
    require_admin_permission(
        db_session, "pilot:read", "auditor", identity=_as("auditor")
    )
    with pytest.raises(HTTPException) as denied:
        require_admin_permission(
            db_session,
            "organization_governance:manage",
            "auditor",
            identity=_as("auditor"),
        )
    assert denied.value.status_code == 403

    require_admin_permission(
        db_session,
        "incident:read",
        "incident_manager",
        identity=_as("incident_manager"),
    )
    require_admin_permission(
        db_session,
        "incident:manage",
        "incident_manager",
        identity=_as("incident_manager"),
    )
    with pytest.raises(HTTPException) as no_manage:
        require_admin_permission(
            db_session,
            "pilot:manage",
            "incident_manager",
            identity=_as("incident_manager"),
        )
    assert no_manage.value.status_code == 403

    require_admin_permission(
        db_session,
        "organization_governance:manage",
        "rai_officer",
        identity=_as("rai_officer"),
    )
    require_admin_permission(
        db_session,
        "exception:approve",
        "business_approver",
        identity=_as("business_approver"),
    )
