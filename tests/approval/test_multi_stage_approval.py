"""Phase 2 multi-stage approval plans — sequential, parallel/quorum, digest invalidation."""

from __future__ import annotations

import pytest

from rai_gateway.approval.authorization import ApproverContext
from rai_gateway.approval.consumption import ApprovalConsumptionService
from rai_gateway.approval.domain import (
    ApprovalDenialCode,
    ApprovalPlanStatus,
    ApprovalStatus,
    ProposedAction,
)
from rai_gateway.approval.errors import ApprovalDeniedError
from rai_gateway.approval.plan import ApprovalPlanService
from rai_gateway.approval.service import ApprovalService


def _authority(db_session, stack):
    return ApprovalConsumptionService(db_session).resolve_authority_for_identity(
        stack["identity"].id,
        stack["delegation"].id,
    )


def _create_multistage(db_session, stack, *, stages, parameters=None):
    svc = ApprovalService(db_session)
    authority = _authority(db_session, stack)
    return svc.create_request(
        authority,
        integration_type="mcp",
        integration_id=stack["mcp"].id,
        tool_id=stack["tool"].id,
        target_type="PurchaseOrder",
        parameters=parameters
        or {"supplier": "SUP-1", "amount": 250000, "currency": "EGP"},
        created_by="ahmed",
        force=True,
        stages=stages,
    )


def test_sequential_stages_only_final_is_consumable(db_session, approval_stack):
    request = _create_multistage(
        db_session,
        approval_stack,
        stages=[
            {
                "name": "Business Owner",
                "mode": "QUORUM",
                "required_roles": ["business_approver"],
                "quorum_count": 1,
            },
            {
                "name": "AI Governance",
                "mode": "QUORUM",
                "required_roles": ["rai_officer"],
                "quorum_count": 1,
            },
        ],
    )
    svc = ApprovalService(db_session)
    plan = ApprovalPlanService(db_session).get_plan_for_request(request.id)
    assert plan is not None
    assert plan.status == ApprovalPlanStatus.IN_PROGRESS.value
    assert len(plan.stages) == 2

    mid = svc.approve(
        request.id,
        approver=ApproverContext(actor="owner", role="business_approver"),
    )
    assert mid.status == ApprovalStatus.PENDING.value

    # Not consumable yet
    authority = _authority(db_session, approval_stack)
    action = ProposedAction.from_dict(request.canonical_action_payload)
    result = ApprovalConsumptionService(db_session).consume(
        authority, action, approval_request_id=request.id
    )
    assert result.allowed is False

    final = svc.approve(
        request.id,
        approver=ApproverContext(actor="officer", role="rai_officer"),
    )
    assert final.status == ApprovalStatus.APPROVED.value

    result = ApprovalConsumptionService(db_session).consume(
        authority, action, approval_request_id=request.id
    )
    assert result.allowed is True
    db_session.refresh(final)
    assert final.status == ApprovalStatus.CONSUMED.value


def test_parallel_quorum_requires_all_roles(db_session, approval_stack):
    request = _create_multistage(
        db_session,
        approval_stack,
        stages=[
            {
                "name": "Security + Finance",
                "mode": "PARALLEL",
                "required_roles": ["business_approver", "rai_officer"],
            }
        ],
    )
    svc = ApprovalService(db_session)
    first = svc.approve(
        request.id,
        approver=ApproverContext(actor="sec", role="business_approver"),
    )
    assert first.status == ApprovalStatus.PENDING.value

    second = svc.approve(
        request.id,
        approver=ApproverContext(actor="fin", role="rai_officer"),
    )
    assert second.status == ApprovalStatus.APPROVED.value


def test_quorum_two_of_three(db_session, approval_stack):
    request = _create_multistage(
        db_session,
        approval_stack,
        stages=[
            {
                "name": "Quorum board",
                "mode": "QUORUM",
                "required_roles": ["business_approver", "rai_officer", "admin"],
                "quorum_count": 2,
            }
        ],
    )
    svc = ApprovalService(db_session)
    svc.approve(
        request.id,
        approver=ApproverContext(actor="a1", role="business_approver"),
    )
    db_session.refresh(request)
    assert request.status == ApprovalStatus.PENDING.value

    done = svc.approve(
        request.id,
        approver=ApproverContext(actor="a2", role="rai_officer"),
    )
    assert done.status == ApprovalStatus.APPROVED.value


def test_stage_role_mismatch_denied(db_session, approval_stack):
    request = _create_multistage(
        db_session,
        approval_stack,
        stages=[
            {
                "name": "Business only",
                "mode": "QUORUM",
                "required_roles": ["business_approver"],
                "quorum_count": 1,
            }
        ],
    )
    with pytest.raises(ApprovalDeniedError) as exc:
        ApprovalService(db_session).approve(
            request.id,
            approver=ApproverContext(actor="wrong", role="rai_officer"),
        )
    assert exc.value.reason == ApprovalDenialCode.APPROVAL_STAGE_ROLE_MISMATCH.value


def test_sod_applies_on_every_stage(db_session, approval_stack):
    request = _create_multistage(
        db_session,
        approval_stack,
        stages=[
            {
                "name": "Owner",
                "mode": "QUORUM",
                "required_roles": ["business_approver"],
                "quorum_count": 1,
            }
        ],
    )
    # initiating_principal is delegator "ahmed" from approval_stack
    with pytest.raises(ApprovalDeniedError) as exc:
        ApprovalService(db_session).approve(
            request.id,
            approver=ApproverContext(actor="ahmed", role="business_approver"),
        )
    assert exc.value.reason == ApprovalDenialCode.SELF_APPROVAL_DENIED.value


def test_material_change_invalidates_in_flight_plan(db_session, approval_stack):
    first = _create_multistage(
        db_session,
        approval_stack,
        stages=[
            {
                "name": "Owner",
                "mode": "QUORUM",
                "required_roles": ["business_approver"],
                "quorum_count": 1,
            },
            {
                "name": "Gov",
                "mode": "QUORUM",
                "required_roles": ["rai_officer"],
                "quorum_count": 1,
            },
        ],
        parameters={"supplier": "SUP-1", "amount": 100000, "currency": "EGP"},
    )
    ApprovalService(db_session).approve(
        first.id,
        approver=ApproverContext(actor="owner", role="business_approver"),
    )
    db_session.refresh(first)
    assert first.status == ApprovalStatus.PENDING.value

    # New action with different amount → new digest → invalidates prior plan
    second = _create_multistage(
        db_session,
        approval_stack,
        stages=[
            {
                "name": "Owner",
                "mode": "QUORUM",
                "required_roles": ["business_approver"],
                "quorum_count": 1,
            }
        ],
        parameters={"supplier": "SUP-1", "amount": 999999, "currency": "EGP"},
    )
    assert second.action_digest != first.action_digest
    db_session.refresh(first)
    plan = ApprovalPlanService(db_session).get_plan_for_request(first.id)
    assert plan.status == ApprovalPlanStatus.INVALIDATED.value
    assert first.status == ApprovalStatus.CANCELLED.value


def test_cross_stage_sod_rejects_same_approver(db_session, approval_stack):
    request = _create_multistage(
        db_session,
        approval_stack,
        stages=[
            {
                "name": "Business Owner",
                "mode": "QUORUM",
                "required_roles": ["business_approver"],
                "quorum_count": 1,
            },
            {
                "name": "AI Governance",
                "mode": "QUORUM",
                "required_roles": ["rai_officer"],
                "quorum_count": 1,
            },
        ],
    )
    svc = ApprovalService(db_session)
    svc.approve(
        request.id,
        approver=ApproverContext(actor="dual-hatted", role="business_approver"),
    )
    with pytest.raises(ApprovalDeniedError) as exc:
        svc.approve(
            request.id,
            approver=ApproverContext(actor="dual-hatted", role="rai_officer"),
        )
    assert exc.value.reason == ApprovalDenialCode.APPROVAL_CROSS_STAGE_SOD.value


def test_duplicate_stage_approver_rejected(db_session, approval_stack):
    request = _create_multistage(
        db_session,
        approval_stack,
        stages=[
            {
                "name": "Board",
                "mode": "QUORUM",
                "required_roles": ["business_approver", "rai_officer"],
                "quorum_count": 2,
            }
        ],
    )
    svc = ApprovalService(db_session)
    svc.approve(
        request.id,
        approver=ApproverContext(actor="same", role="business_approver"),
    )
    with pytest.raises(ApprovalDeniedError) as exc:
        svc.approve(
            request.id,
            approver=ApproverContext(actor="same", role="rai_officer"),
        )
    assert (
        exc.value.reason == ApprovalDenialCode.APPROVAL_DUPLICATE_STAGE_APPROVER.value
    )


def test_single_stage_without_plan_unchanged(db_session, approval_stack):
    """Backward compatible: no stages → immediate APPROVED on one approve."""
    svc = ApprovalService(db_session)
    authority = _authority(db_session, approval_stack)
    request = svc.create_request(
        authority,
        integration_type="mcp",
        integration_id=approval_stack["mcp"].id,
        tool_id=approval_stack["tool"].id,
        target_type="PurchaseOrder",
        parameters={"amount": 10},
        created_by="ahmed",
        force=True,
    )
    assert ApprovalPlanService(db_session).get_plan_for_request(request.id) is None
    approved = svc.approve(
        request.id,
        approver=ApproverContext(actor="manager", role="admin"),
    )
    assert approved.status == ApprovalStatus.APPROVED.value
