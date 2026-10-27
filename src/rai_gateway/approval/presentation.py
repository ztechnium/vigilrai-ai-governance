"""Server-derived human summaries and viewer capability flags for approvals."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from rai_gateway.approval.authorization import (
    ApproverAuthorizationService,
    ApproverContext,
)
from rai_gateway.approval.domain import ApprovalStatus
from rai_gateway.approval.errors import ApprovalDeniedError
from rai_gateway.approval.plan import ApprovalPlanService
from rai_gateway.core.authorization import TENANT_ROLE_TO_RBAC_ROLE
from rai_gateway.core.principal import Principal
from rai_gateway.models.approval import ApprovalRequest
from rai_gateway.models.registry import Agent, ToolResource
from rai_gateway.services.admin_console import _normalize_role, _resolve_permissions


def build_human_summary(request: ApprovalRequest, db: Session) -> str:
    """One-line business summary for inbox rows."""
    agent = db.query(Agent).filter(Agent.id == request.agent_id).first()
    tool = None
    if request.tool_id:
        tool = db.query(ToolResource).filter(ToolResource.id == request.tool_id).first()

    agent_name = agent.name if agent else "An agent"
    action = None
    if tool:
        action = tool.name or tool.tool_key
    if not action:
        action = request.action_type or "perform an action"

    target = request.target_identifier
    params = (request.canonical_action_payload or {}).get("parameters") or {}
    amount = params.get("amount") or params.get("refund_amount") or params.get("value")

    parts = [f"{agent_name} wants to {action}"]
    if amount is not None:
        currency = params.get("currency") or params.get("currency_code") or ""
        amount_str = f"{currency} {amount}".strip() if currency else str(amount)
        parts.append(f"of {amount_str}")
    if target:
        parts.append(f"for {target}")
    return " ".join(parts)


def _approver_context(
    *,
    actor: str,
    role: str,
    principal: Principal | None = None,
) -> ApproverContext:
    assurance = None
    acr = None
    amr: list[str] = []
    auth_time = None
    if principal is not None:
        assurance = principal.authentication_assurance
        acr = principal.acr
        amr = list(principal.amr or ())
        auth_time = principal.auth_time
    return ApproverContext(
        actor=actor,
        role=role,
        authentication_assurance=assurance,
        acr=acr,
        amr=amr,
        auth_time=auth_time,
    )


def evaluate_viewer_capabilities(
    request: ApprovalRequest,
    *,
    db: Session,
    actor: str | None,
    role: str | None,
    principal: Principal | None = None,
) -> dict[str, Any]:
    """Compute frontend action flags from server-side authorization rules."""
    caps: dict[str, Any] = {
        "can_approve": False,
        "can_reject": False,
        "can_cancel": False,
        "can_create_standing_authorization": False,
        "decision_block_reason": None,
    }
    if request.status != ApprovalStatus.PENDING.value:
        if request.status == ApprovalStatus.APPROVED.value:
            caps["decision_block_reason"] = "APPROVED_AWAITING_EXECUTION"
        else:
            caps["decision_block_reason"] = f"TERMINAL_{request.status}"
        return caps

    if not actor or not role:
        caps["decision_block_reason"] = "VIEWER_NOT_AUTHENTICATED"
        return caps

    approver = _approver_context(actor=actor, role=role, principal=principal)
    auth = ApproverAuthorizationService(db)
    plans = ApprovalPlanService(db)

    try:
        auth.authorize_approve(request, approver)
        plan = plans.get_plan_for_request(request.id)
        if plan is not None:
            stage = plans._active_stage(plan)  # noqa: SLF001 — capability probe
            plans._authorize_stage_role(stage, approver)  # noqa: SLF001
            plans._check_cross_stage_sod(  # noqa: SLF001
                plan, approver.actor, current_stage_id=stage.id
            )
        caps["can_approve"] = True
        caps["can_reject"] = True
    except ApprovalDeniedError as exc:
        caps["decision_block_reason"] = exc.reason
        try:
            auth.authorize_reject(request, approver)
            plan = plans.get_plan_for_request(request.id)
            if plan is not None:
                stage = plans._active_stage(plan)  # noqa: SLF001
                plans._authorize_stage_role(stage, approver)  # noqa: SLF001
            caps["can_reject"] = True
        except ApprovalDeniedError:
            pass

    role_id = _normalize_role(TENANT_ROLE_TO_RBAC_ROLE.get(role, role))
    if role_id:
        perms = _resolve_permissions(db, role_id)
        if "*" in perms or "approvals:write" in perms:
            caps["can_cancel"] = True

    return caps
