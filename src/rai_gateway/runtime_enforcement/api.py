"""WP4 Mandatory Runtime Enforcement Gateway REST API."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import rai_gateway.models.runtime_enforcement  # noqa: F401
from rai_gateway.core.authorization import require_permission
from rai_gateway.core.database import get_db
from rai_gateway.core.observability import generate_trace_id
from rai_gateway.core.tenant_context import TenantContext
from rai_gateway.runtime_enforcement.domain import (
    RuntimeActionRequest,
    RuntimeActionTarget,
)
from rai_gateway.runtime_enforcement.receipt_serializer import (
    serialize_receipt_detail,
    serialize_receipt_summary,
)
from rai_gateway.runtime_enforcement.repository import RuntimeEnforcementRepository
from rai_gateway.runtime_enforcement.service import RuntimeEnforcementService

router = APIRouter(prefix="/v1", tags=["runtime-enforcement"])


class RuntimeActionBody(BaseModel):
    integration_type: str = "mcp"
    integration_id: UUID | None = None
    tool_id: UUID | None = None
    target: dict[str, Any] | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    environment: str | None = None
    approval_request_id: UUID | None = None
    idempotency_key: str | None = None
    delegation_id: UUID | None = None
    correlation_id: str | None = None
    trace_id: str | None = None
    client_context: dict[str, Any] | None = None


def _extract_runtime_secret(
    x_rai_agent_key: str | None,
    authorization: str | None,
) -> str | None:
    if x_rai_agent_key:
        return x_rai_agent_key
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def _to_request(body: RuntimeActionBody) -> RuntimeActionRequest:
    target = None
    if body.target:
        target = RuntimeActionTarget(
            type=str(body.target.get("type", "")),
            id=body.target.get("id"),
        )
    return RuntimeActionRequest(
        integration_type=body.integration_type,
        integration_id=body.integration_id,
        tool_id=body.tool_id,
        target=target,
        parameters=body.parameters,
        environment=body.environment,
        approval_request_id=body.approval_request_id,
        idempotency_key=body.idempotency_key,
        delegation_id=body.delegation_id,
        correlation_id=body.correlation_id,
        trace_id=body.trace_id,
        client_context=body.client_context,
    )


@router.post("/runtime/actions/execute")
def execute_runtime_action(
    body: RuntimeActionBody,
    db: Session = Depends(get_db),
    x_rai_agent_key: str | None = Header(default=None, alias="X-RAI-Agent-Key"),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    """Mandatory proxy enforcement: govern then execute when allowed."""
    secret = _extract_runtime_secret(x_rai_agent_key, authorization)
    if not secret:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "UNAUTHENTICATED",
                "message": "Missing runtime agent credential",
            },
        )

    request = _to_request(body)
    if not request.correlation_id:
        request.correlation_id = generate_trace_id()

    result = RuntimeEnforcementService(db).enforce_and_execute(
        request,
        credential_secret=secret,
    )
    status_code = 200 if result.allowed else 403
    return JSONResponse(status_code=status_code, content=result.to_dict())


@router.post("/runtime/actions/authorize")
def authorize_runtime_action(
    body: RuntimeActionBody,
    db: Session = Depends(get_db),
    x_rai_agent_key: str | None = Header(default=None, alias="X-RAI-Agent-Key"),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    """Decision-only enforcement without downstream execution (hook mode)."""
    secret = _extract_runtime_secret(x_rai_agent_key, authorization)
    if not secret:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "UNAUTHENTICATED",
                "message": "Missing runtime agent credential",
            },
        )

    request = _to_request(body)
    if not request.correlation_id:
        request.correlation_id = generate_trace_id()

    result = RuntimeEnforcementService(db).authorize(
        request,
        credential_secret=secret,
    )
    status_code = 200 if result.allowed else 403
    return JSONResponse(status_code=status_code, content=result.to_dict())


@router.get("/runtime/approvals/{approval_request_id}/status")
def get_runtime_approval_status(
    approval_request_id: UUID,
    db: Session = Depends(get_db),
    x_rai_agent_key: str | None = Header(default=None, alias="X-RAI-Agent-Key"),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    """Minimal runtime-scoped approval poll for resume/retry flows."""
    from rai_gateway.approval.resume import build_approval_status_response
    from rai_gateway.approval.service import ApprovalService
    from rai_gateway.identity.errors import AuthorityDeniedError
    from rai_gateway.identity.resolver import RuntimeAuthorityResolver
    from rai_gateway.models.approval import ApprovalRequest

    secret = _extract_runtime_secret(x_rai_agent_key, authorization)
    if not secret:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "UNAUTHENTICATED",
                "message": "Missing runtime agent credential",
            },
        )
    try:
        authority = RuntimeAuthorityResolver(db).resolve_from_credential(secret)
    except AuthorityDeniedError as exc:
        raise HTTPException(
            status_code=401,
            detail={"error": "UNAUTHENTICATED", "message": str(exc)},
        ) from exc

    row = (
        db.query(ApprovalRequest)
        .filter(ApprovalRequest.id == approval_request_id)
        .first()
    )
    if not row or row.runtime_identity_id != authority.runtime_identity.id:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND"})

    ApprovalService(db)._expire_if_needed(row)  # noqa: SLF001
    db.refresh(row)
    return build_approval_status_response(row)


@router.get("/runtime/enforcement/receipts")
def list_enforcement_receipts(
    db: Session = Depends(get_db),
    _tenant: TenantContext = Depends(require_permission("registry:read")),
    ai_system_id: UUID | None = None,
    agent_id: UUID | None = None,
    runtime_identity_id: UUID | None = None,
    tool_id: UUID | None = None,
    enforcement_decision: str | None = None,
    execution_status: str | None = None,
    enforcement_mode: str | None = None,
    approval_request_id: UUID | None = None,
    client_type: str | None = None,
    started_after: datetime | None = None,
    started_before: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """List runtime enforcement receipts for operational visibility."""
    repo = RuntimeEnforcementRepository(db)
    receipts = repo.list_receipts(
        ai_system_id=ai_system_id,
        agent_id=agent_id,
        runtime_identity_id=runtime_identity_id,
        tool_id=tool_id,
        enforcement_decision=enforcement_decision,
        execution_status=execution_status,
        enforcement_mode=enforcement_mode,
        approval_request_id=approval_request_id,
        client_type=client_type,
        started_after=started_after,
        started_before=started_before,
        limit=limit,
        offset=offset,
    )
    return [serialize_receipt_summary(r, db) for r in receipts]


@router.get("/runtime/enforcement/receipts/{receipt_id}")
def get_enforcement_receipt(
    receipt_id: UUID,
    db: Session = Depends(get_db),
    _tenant: TenantContext = Depends(require_permission("registry:read")),
):
    """Get a single runtime enforcement receipt with structured sections."""
    repo = RuntimeEnforcementRepository(db)
    receipt = repo.get_receipt(receipt_id)
    if not receipt:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND"})
    return serialize_receipt_detail(receipt, db)


@router.get("/runtime/executions")
def list_runtime_executions(
    db: Session = Depends(get_db),
    _tenant: TenantContext = Depends(require_permission("registry:read")),
    execution_status: str | None = None,
    enforcement_mode: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """WP4 execution index spanning proxy (RAI_EXECUTED) and hook (CLIENT_REPORTED)."""
    repo = RuntimeEnforcementRepository(db)
    receipts = repo.list_receipts(
        execution_status=execution_status,
        enforcement_mode=enforcement_mode,
        limit=limit,
        offset=offset,
    )
    rows = []
    for receipt in receipts:
        summary = serialize_receipt_summary(receipt, db)
        rows.append(
            {
                "receipt_id": summary["id"],
                "tool_name": summary.get("tool_name"),
                "tool_id": summary.get("tool_id"),
                "integration_name": summary.get("integration_name"),
                "action_digest": summary.get("action_digest"),
                "execution_source": summary.get("execution_source"),
                "execution_status": summary.get("execution_status"),
                "enforcement_decision": summary.get("enforcement_decision"),
                "enforcement_mode": summary.get("enforcement_mode"),
                "started_at": summary.get("started_at"),
                "completed_at": summary.get("completed_at"),
                "reported_at": summary.get("reported_at"),
                "duration_ms": summary.get("duration_ms"),
                "safe_result_metadata": (summary.get("execution") or {}).get("report"),
                "runtime_identity_name": summary.get("runtime_identity_name"),
                "ai_system_name": summary.get("ai_system_name"),
                "agent_name": summary.get("agent_name"),
            }
        )
    return rows
