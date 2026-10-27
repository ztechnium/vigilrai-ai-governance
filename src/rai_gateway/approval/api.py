"""WP3 Durable Action-Bound Human Approval REST API."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import rai_gateway.models.approval  # noqa: F401
from rai_gateway.approval.authorization import ApproverContext
from rai_gateway.approval.consumption import ApprovalConsumptionService
from rai_gateway.approval.domain import ActionTarget, ProposedAction
from rai_gateway.approval.errors import (
    ApprovalConflictError,
    ApprovalDeniedError,
    ApprovalError,
)
from rai_gateway.approval.plan import ApprovalPlanService
from rai_gateway.approval.service import ApprovalService
from rai_gateway.core.authorization import (
    TENANT_ROLE_TO_RBAC_ROLE,
    require_permission,
    resolve_acting_membership,
)
from rai_gateway.core.database import get_db
from rai_gateway.core.observability import generate_trace_id
from rai_gateway.core.principal import Principal
from rai_gateway.core.tenant_context import TenantContext
from rai_gateway.identity.errors import AuthorityDeniedError, IdentityError
from rai_gateway.identity.version_resources import (
    enrich_effective_scope,
    load_version_resource_catalog,
)
from rai_gateway.models.governance import OrganizationMembership
from rai_gateway.models.registry import MCPServer, ToolResource

router = APIRouter(
    prefix="/v1",
    tags=["approvals"],
)


def _handle_error(exc: ApprovalError) -> HTTPException:
    detail: dict[str, Any] = {"error": exc.error_code, "message": exc.message}
    if isinstance(exc, ApprovalDeniedError):
        detail["reason"] = exc.reason
    return HTTPException(status_code=exc.status_code, detail=detail)


def _handle_identity_error(exc: IdentityError) -> HTTPException:
    detail: dict[str, Any] = {"error": exc.error_code, "message": exc.message}
    if isinstance(exc, AuthorityDeniedError):
        detail["reason"] = exc.reason
    return HTTPException(status_code=exc.status_code, detail=detail)


def _approval_svc(db: Session = Depends(get_db)) -> ApprovalService:
    return ApprovalService(db)


def _consumption_svc(db: Session = Depends(get_db)) -> ApprovalConsumptionService:
    return ApprovalConsumptionService(db)


class ApprovalRequestCreate(BaseModel):
    runtime_identity_id: UUID
    delegation_id: UUID | None = None
    integration_type: str = "mcp"
    integration_id: UUID | None = None
    tool_id: UUID | None = None
    model_id: UUID | None = None
    data_source_id: UUID | None = None
    target_type: str | None = None
    target_identifier: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    business_reason: str | None = None
    environment: str | None = None
    force: bool = False
    stages: list[dict[str, Any]] | None = None


class DecisionAction(BaseModel):
    acting_membership_id: UUID
    decision_reason: str | None = None
    # Deprecated: ignored. Assurance is server-derived only.
    authentication_assurance: str | None = None


def _approver_role_from_membership(membership: OrganizationMembership) -> str:
    """Map governance membership role to RBAC role id for stage/capability checks."""
    return TENANT_ROLE_TO_RBAC_ROLE.get(membership.role, membership.role)


def _server_approver_context(
    *,
    actor: str,
    role: str,
    principal: Principal | None = None,
    x_step_up_token: str | None = None,
) -> ApproverContext:
    """Build ApproverContext from verified session / server step-up only."""
    from rai_gateway.approval.authorization import STEP_UP_VERIFIED
    from rai_gateway.core.config import settings

    assurance = None
    acr = None
    amr: list[str] = []
    auth_time = None

    if principal is not None:
        assurance = principal.authentication_assurance
        acr = principal.acr
        amr = list(principal.amr or ())
        auth_time = principal.auth_time

    # Shared-secret step-up is a non-prod escape hatch only — never MFA.
    if (
        settings.allow_shared_secret_step_up
        and settings.step_up_token
        and x_step_up_token
        and x_step_up_token == settings.step_up_token
    ):
        assurance = STEP_UP_VERIFIED

    return ApproverContext(
        actor=actor,
        role=role,
        authentication_assurance=assurance,
        acr=acr,
        amr=amr,
        auth_time=auth_time,
    )


class ConsumeActionRequest(BaseModel):
    runtime_identity_id: UUID
    delegation_id: UUID | None = None
    approval_request_id: UUID | None = None
    integration_type: str = "mcp"
    integration_id: UUID | None = None
    tool_id: UUID | None = None
    model_id: UUID | None = None
    data_source_id: UUID | None = None
    target_type: str | None = None
    target_identifier: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    environment: str | None = None


def _serialize_request(
    request,
    db: Session,
    *,
    viewer: TenantContext | None = None,
) -> dict[str, Any]:
    from rai_gateway.approval.presentation import (
        build_human_summary,
        evaluate_viewer_capabilities,
    )

    tool = None
    mcp = None
    if request.tool_id:
        tool = db.query(ToolResource).filter(ToolResource.id == request.tool_id).first()
    if request.integration_id and request.integration_type == "mcp":
        mcp = db.query(MCPServer).filter(MCPServer.id == request.integration_id).first()

    decisions = [
        {
            "id": str(d.id),
            "decision": d.decision,
            "decided_by": d.decided_by,
            "decision_reason": d.decision_reason,
            "authentication_assurance": d.authentication_assurance,
            "decided_at": d.decided_at.isoformat() if d.decided_at else None,
            "correlation_id": d.correlation_id,
        }
        for d in (request.decisions or [])
    ]

    primary_roles = list(viewer.roles) if viewer is not None else []
    viewer_caps = {
        "can_approve": False,
        "can_reject": False,
        "can_cancel": False,
        "can_create_standing_authorization": False,
        "decision_block_reason": "VIEWER_NOT_AUTHENTICATED",
    }
    if viewer is not None:
        if not primary_roles:
            viewer_caps = evaluate_viewer_capabilities(
                request,
                db=db,
                actor=viewer.user_id,
                role=None,
                principal=viewer.principal,
            )
        else:
            for membership_role in primary_roles:
                candidate = evaluate_viewer_capabilities(
                    request,
                    db=db,
                    actor=viewer.user_id,
                    role=_approver_role_from_membership_role(membership_role),
                    principal=viewer.principal,
                )
                viewer_caps["can_approve"] = (
                    viewer_caps["can_approve"] or candidate["can_approve"]
                )
                viewer_caps["can_reject"] = (
                    viewer_caps["can_reject"] or candidate["can_reject"]
                )
                viewer_caps["can_cancel"] = (
                    viewer_caps["can_cancel"] or candidate["can_cancel"]
                )
                if candidate["can_approve"]:
                    viewer_caps["decision_block_reason"] = None
                    break
                viewer_caps["decision_block_reason"] = candidate.get(
                    "decision_block_reason"
                )

    return {
        "id": str(request.id),
        "ai_system_id": str(request.ai_system_id),
        "agent_id": str(request.agent_id),
        "agent_version_id": str(request.agent_version_id),
        "runtime_identity_id": str(request.runtime_identity_id),
        "delegation_id": str(request.delegation_id) if request.delegation_id else None,
        "initiating_principal": request.initiating_principal,
        "action_type": request.action_type,
        "integration_type": request.integration_type,
        "integration_id": str(request.integration_id)
        if request.integration_id
        else None,
        "integration_name": mcp.name if mcp else None,
        "tool_id": str(request.tool_id) if request.tool_id else None,
        "tool_name": tool.name if tool else None,
        "tool_key": tool.tool_key if tool else None,
        "model_id": str(request.model_id) if request.model_id else None,
        "data_source_id": str(request.data_source_id)
        if request.data_source_id
        else None,
        "target_type": request.target_type,
        "target_identifier": request.target_identifier,
        "canonical_action_payload": request.canonical_action_payload,
        "action_digest": request.action_digest,
        "parameters": (request.canonical_action_payload or {}).get("parameters", {}),
        "business_reason": request.business_reason,
        "risk_tier": request.risk_tier,
        "risk_score": request.risk_score,
        "approval_policy_reference": request.approval_policy_reference,
        "requirement_reason": request.requirement_reason,
        "status": request.status,
        "created_at": request.created_at.isoformat() if request.created_at else None,
        "expires_at": request.expires_at.isoformat() if request.expires_at else None,
        "decided_at": request.decided_at.isoformat() if request.decided_at else None,
        "consumed_at": request.consumed_at.isoformat() if request.consumed_at else None,
        "correlation_id": request.correlation_id,
        "created_by": request.created_by,
        "runtime_idempotency_key": getattr(request, "runtime_idempotency_key", None),
        "human_summary": build_human_summary(request, db),
        "viewer_capabilities": viewer_caps,
        "decisions": decisions,
        "plan": (
            lambda plans: plans.serialize_plan(plans.get_plan_for_request(request.id))
        )(ApprovalPlanService(db)),
    }


def _approver_role_from_membership_role(membership_role: str | None) -> str | None:
    if not membership_role:
        return None
    return TENANT_ROLE_TO_RBAC_ROLE.get(membership_role, membership_role)


def _serialize_detail(
    request,
    db: Session,
    consumption: ApprovalConsumptionService,
    *,
    viewer: TenantContext | None = None,
) -> dict[str, Any]:
    data = _serialize_request(request, db, viewer=viewer)
    from rai_gateway.runtime_enforcement.receipt_serializer import (
        serialize_receipt_summary,
    )
    from rai_gateway.runtime_enforcement.repository import RuntimeEnforcementRepository

    related = RuntimeEnforcementRepository(db).list_receipts_for_approval(request.id)
    data["related_enforcement_receipts"] = [
        {
            "id": str(r.id),
            "enforcement_decision": r.enforcement_decision,
            "execution_status": r.execution_status,
            "execution_source": getattr(r, "execution_source", None),
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "href": f"/runtime/enforcement/{r.id}",
        }
        for r in related
    ]
    data["related_enforcement_receipt_details"] = [
        serialize_receipt_summary(r, db) for r in related
    ]
    try:
        authority = consumption.resolve_authority_for_identity(
            request.runtime_identity_id,
            request.delegation_id,
        )
    except IdentityError as exc:
        data["identity_unavailable"] = exc.message
        if isinstance(exc, AuthorityDeniedError):
            data["identity_unavailable_reason"] = exc.reason
        return data

    catalog = load_version_resource_catalog(db, authority.agent_version.id)
    scope_data = authority.effective_scope.to_dict()
    data["identity"] = {
        "ai_system": {
            "id": str(authority.ai_system.id),
            "name": authority.ai_system.name,
            "system_key": authority.ai_system.system_key,
        },
        "agent": {
            "id": str(authority.agent.id),
            "name": authority.agent.name,
            "agent_key": authority.agent.agent_key,
        },
        "agent_version": {
            "id": str(authority.agent_version.id),
            "version_number": authority.agent_version.version_number,
            "risk_tier": authority.agent_version.risk_tier,
        },
        "runtime_identity": {
            "id": str(authority.runtime_identity.id),
            "name": authority.runtime_identity.name,
            "identity_key": authority.runtime_identity.identity_key,
            "environment": authority.runtime_identity.environment,
        },
        "initiating_principal": authority.initiating_principal,
        "delegation_chain": [
            {
                "delegation_id": str(entry.delegation_id),
                "delegator_type": entry.delegator_type,
                "delegator_id": entry.delegator_id,
                "scope": entry.scope,
            }
            for entry in authority.delegation_chain
        ],
    }
    data["effective_scope"] = enrich_effective_scope(catalog, scope_data)
    return data


@router.post("/approval-requests", status_code=201)
def create_approval_request(
    payload: ApprovalRequestCreate,
    db: Session = Depends(get_db),
    svc: ApprovalService = Depends(_approval_svc),
    consumption: ApprovalConsumptionService = Depends(_consumption_svc),
    tenant: TenantContext = Depends(require_permission("approvals:write")),
) -> dict[str, Any]:
    try:
        authority = consumption.resolve_authority_for_identity(
            payload.runtime_identity_id,
            payload.delegation_id,
        )
        request = svc.create_request(
            authority,
            integration_type=payload.integration_type,
            integration_id=payload.integration_id,
            tool_id=payload.tool_id,
            model_id=payload.model_id,
            data_source_id=payload.data_source_id,
            target_type=payload.target_type,
            target_identifier=payload.target_identifier,
            parameters=payload.parameters,
            business_reason=payload.business_reason,
            environment=payload.environment,
            created_by=tenant.user_id,
            correlation_id=generate_trace_id(),
            force=payload.force,
            stages=payload.stages,
        )
        return _serialize_detail(request, db, consumption, viewer=tenant)
    except ApprovalError as exc:
        raise _handle_error(exc) from exc
    except IdentityError as exc:
        raise _handle_identity_error(exc) from exc


@router.get("/approval-requests")
def list_approval_requests(
    status: str | None = None,
    view: str | None = None,
    ai_system_id: UUID | None = None,
    agent_id: UUID | None = None,
    agent_version_id: UUID | None = None,
    runtime_identity_id: UUID | None = None,
    risk_tier: str | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
    svc: ApprovalService = Depends(_approval_svc),
    tenant: TenantContext = Depends(require_permission("approvals:read")),
) -> list[dict[str, Any]]:
    requests = svc.list_requests(
        status=status,
        ai_system_id=ai_system_id,
        agent_id=agent_id,
        agent_version_id=agent_version_id,
        runtime_identity_id=runtime_identity_id,
        risk_tier=risk_tier,
        search=search,
    )
    serialized = [_serialize_request(r, db, viewer=tenant) for r in requests]
    if not view:
        return serialized

    view_key = view.strip().lower()
    if view_key == "needs_my_decision":
        return [
            r
            for r in serialized
            if r["status"] == "PENDING"
            and (r.get("viewer_capabilities") or {}).get("can_approve")
        ]
    if view_key == "waiting":
        return [
            r
            for r in serialized
            if r["status"] == "PENDING"
            and not (r.get("viewer_capabilities") or {}).get("can_approve")
        ]
    if view_key in {"approved_awaiting_execution", "approved-awaiting-execution"}:
        return [r for r in serialized if r["status"] == "APPROVED"]
    if view_key == "resolved":
        return [
            r
            for r in serialized
            if r["status"] in {"CONSUMED", "REJECTED", "EXPIRED", "CANCELLED"}
        ]
    return serialized


@router.get("/approval-requests/{request_id}")
def get_approval_request(
    request_id: UUID,
    db: Session = Depends(get_db),
    svc: ApprovalService = Depends(_approval_svc),
    consumption: ApprovalConsumptionService = Depends(_consumption_svc),
    tenant: TenantContext = Depends(require_permission("approvals:read")),
) -> dict[str, Any]:
    try:
        request = svc.get_request(request_id)
        return _serialize_detail(request, db, consumption, viewer=tenant)
    except ApprovalError as exc:
        raise _handle_error(exc) from exc


@router.post("/approval-requests/{request_id}/approve")
def approve_request(
    request_id: UUID,
    payload: DecisionAction,
    db: Session = Depends(get_db),
    svc: ApprovalService = Depends(_approval_svc),
    tenant: TenantContext = Depends(require_permission("approvals:approve")),
    x_step_up_token: str | None = Header(default=None, alias="X-Step-Up-Token"),
) -> dict[str, Any]:
    membership = resolve_acting_membership(db, tenant, payload.acting_membership_id)
    try:
        request = svc.approve(
            request_id,
            approver=_server_approver_context(
                actor=membership.user_id,
                role=_approver_role_from_membership(membership),
                principal=tenant.principal,
                x_step_up_token=x_step_up_token,
            ),
            decision_reason=payload.decision_reason,
            correlation_id=generate_trace_id(),
        )
        consumption = ApprovalConsumptionService(db)
        return _serialize_detail(request, db, consumption, viewer=tenant)
    except ApprovalConflictError as exc:
        raise HTTPException(status_code=409, detail={"message": exc.message}) from exc
    except ApprovalError as exc:
        raise _handle_error(exc) from exc


@router.post("/approval-requests/{request_id}/reject")
def reject_request(
    request_id: UUID,
    payload: DecisionAction,
    db: Session = Depends(get_db),
    svc: ApprovalService = Depends(_approval_svc),
    tenant: TenantContext = Depends(require_permission("approvals:approve")),
    x_step_up_token: str | None = Header(default=None, alias="X-Step-Up-Token"),
) -> dict[str, Any]:
    membership = resolve_acting_membership(db, tenant, payload.acting_membership_id)
    try:
        request = svc.reject(
            request_id,
            approver=_server_approver_context(
                actor=membership.user_id,
                role=_approver_role_from_membership(membership),
                principal=tenant.principal,
                x_step_up_token=x_step_up_token,
            ),
            decision_reason=payload.decision_reason,
            correlation_id=generate_trace_id(),
        )
        consumption = ApprovalConsumptionService(db)
        return _serialize_detail(request, db, consumption, viewer=tenant)
    except ApprovalConflictError as exc:
        raise HTTPException(status_code=409, detail={"message": exc.message}) from exc
    except ApprovalError as exc:
        raise _handle_error(exc) from exc


@router.post("/approval-requests/{request_id}/cancel")
def cancel_request(
    request_id: UUID,
    db: Session = Depends(get_db),
    svc: ApprovalService = Depends(_approval_svc),
    consumption: ApprovalConsumptionService = Depends(_consumption_svc),
    tenant: TenantContext = Depends(require_permission("approvals:write")),
) -> dict[str, Any]:
    try:
        request = svc.cancel(
            request_id,
            actor=tenant.user_id,
            correlation_id=generate_trace_id(),
        )
        return _serialize_detail(request, db, consumption, viewer=tenant)
    except ApprovalConflictError as exc:
        raise HTTPException(status_code=409, detail={"message": exc.message}) from exc
    except ApprovalError as exc:
        raise _handle_error(exc) from exc


@router.post("/approval-requests/consume")
def consume_approval(
    payload: ConsumeActionRequest,
    consumption: ApprovalConsumptionService = Depends(_consumption_svc),
    tenant: TenantContext = Depends(require_permission("approvals:write")),
) -> dict[str, Any]:
    """Tenant diagnostic consume — core consume() stays runtime/org-agnostic."""
    try:
        authority = consumption.resolve_authority_for_identity(
            payload.runtime_identity_id,
            payload.delegation_id,
        )
    except IdentityError as exc:
        raise _handle_identity_error(exc) from exc

    action = ProposedAction(
        ai_system_id=authority.ai_system.id,
        agent_id=authority.agent.id,
        agent_version_id=authority.agent_version.id,
        runtime_identity_id=payload.runtime_identity_id,
        delegation_id=payload.delegation_id,
        integration_type=payload.integration_type,
        integration_id=payload.integration_id,
        tool_id=payload.tool_id,
        model_id=payload.model_id,
        data_source_id=payload.data_source_id,
        target=ActionTarget(type=payload.target_type, id=payload.target_identifier)
        if payload.target_type
        else None,
        parameters=payload.parameters,
        environment=payload.environment,
    )
    result = consumption.consume(
        authority,
        action,
        approval_request_id=payload.approval_request_id,
        correlation_id=generate_trace_id(),
    )
    return {
        "allowed": result.allowed,
        "reason": result.reason.value if result.reason else None,
        "message": result.message,
        "approval_request_id": str(result.approval_request_id)
        if result.approval_request_id
        else None,
    }
