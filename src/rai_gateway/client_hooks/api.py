"""WP4 client hook REST API."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import rai_gateway.models.client_hooks  # noqa: F401
from rai_gateway.client_hooks.domain import (
    BRIDGE_VERSION,
    COVERAGE_DISCLAIMER,
    DEFAULT_COVERAGE,
    PROTOCOL_VERSION,
    NativeHookEvent,
)
from rai_gateway.client_hooks.service import (
    ClientHookService,
    ClientIntegrationRepository,
)
from rai_gateway.core.authorization import Principal, require_user
from rai_gateway.core.database import get_db
from rai_gateway.identity.resolver import RuntimeAuthorityResolver
from rai_gateway.runtime_enforcement.domain import (
    ClientExecutionReport,
    DeploymentControl,
    VerificationStatus,
)
from rai_gateway.runtime_enforcement.service import RuntimeEnforcementService

router = APIRouter(prefix="/v1", tags=["client-hooks"])


def _extract_runtime_secret(
    x_rai_agent_key: str | None,
    authorization: str | None,
) -> str | None:
    if x_rai_agent_key:
        return x_rai_agent_key
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


class HookAuthorizeBody(BaseModel):
    client_type: str
    hook_event: str
    native_payload: dict[str, Any] = Field(default_factory=dict)
    delegation_id: UUID | None = None
    correlation_id: str | None = None


class ExecutionResultBody(BaseModel):
    enforcement_receipt_id: UUID | None = None
    correlation_id: str | None = None
    client_type: str | None = None
    hook_event: str | None = None
    status: str
    duration_ms: int | None = None
    safe_result_metadata: dict[str, Any] = Field(default_factory=dict)
    client_event_id: str | None = None


class HeartbeatBody(BaseModel):
    client_type: str
    client_version: str | None = None
    bridge_version: str | None = None
    protocol_version: int | None = None
    coverage: dict[str, str] | None = None
    deployment_control: str | None = None
    verification_status: str | None = None
    # Observed install hash for managed-profile attestation (server compares).
    observed_bridge_hash: str | None = None


class ManagedProfileBody(BaseModel):
    deployment_control: str
    expected_bridge_hash: str = Field(..., min_length=8)
    expected_bridge_version: str | None = None
    managed_profile_key: str | None = None


class TestConnectionBody(BaseModel):
    credential_secret: str


def _serialize_integration(row) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "runtime_identity_id": str(row.runtime_identity_id),
        "client_type": row.client_type,
        "enforcement_mode": row.enforcement_mode,
        "deployment_control": row.deployment_control
        or DeploymentControl.LOCAL_HOOK.value,
        "verification_status": row.verification_status
        or VerificationStatus.DECLARED.value,
        "status": row.status,
        "client_version": row.client_version,
        "bridge_version": row.bridge_version,
        "protocol_version": row.protocol_version,
        "configuration_status": row.configuration_status,
        "coverage": row.coverage or DEFAULT_COVERAGE.get(row.client_type, {}),
        "coverage_disclaimer": COVERAGE_DISCLAIMER,
        "expected_bridge_hash": row.expected_bridge_hash,
        "expected_bridge_version": row.expected_bridge_version,
        "observed_bridge_hash": row.observed_bridge_hash,
        "managed_profile_key": row.managed_profile_key,
        "last_attested_at": row.last_attested_at.isoformat()
        if getattr(row, "last_attested_at", None)
        else None,
        "last_seen_at": row.last_seen_at.isoformat() if row.last_seen_at else None,
        "last_decision_at": row.last_decision_at.isoformat()
        if row.last_decision_at
        else None,
        "last_decision_effect": row.last_decision_effect,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.post("/runtime/client-hooks/authorize")
def authorize_client_hook(
    body: HookAuthorizeBody,
    db: Session = Depends(get_db),
    x_rai_agent_key: str | None = Header(default=None, alias="X-RAI-Agent-Key"),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    """Authorize a native client hook event via WP4."""
    secret = _extract_runtime_secret(x_rai_agent_key, authorization)
    if not secret:
        raise HTTPException(status_code=401, detail={"error": "UNAUTHENTICATED"})
    svc = ClientHookService(db)
    result = svc.authorize_hook(
        NativeHookEvent(
            client_type=body.client_type,
            hook_event=body.hook_event,
            payload=body.native_payload,
            delegation_id=body.delegation_id,
            correlation_id=body.correlation_id,
        ),
        credential_secret=secret,
    )
    return result.to_dict()


@router.post("/runtime/client-hooks/execution-result")
def report_client_execution_result(
    body: ExecutionResultBody,
    db: Session = Depends(get_db),
    x_rai_agent_key: str | None = Header(default=None, alias="X-RAI-Agent-Key"),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    """Provider-neutral post-execution reporting for hook mode."""
    secret = _extract_runtime_secret(x_rai_agent_key, authorization)
    if not secret:
        raise HTTPException(status_code=401, detail={"error": "UNAUTHENTICATED"})
    authority = RuntimeAuthorityResolver(db).resolve_from_credential(secret)
    result = RuntimeEnforcementService(db).report_execution_result(
        ClientExecutionReport(
            enforcement_receipt_id=body.enforcement_receipt_id,
            correlation_id=body.correlation_id,
            client_type=body.client_type,
            hook_event=body.hook_event,
            status=body.status,
            duration_ms=body.duration_ms,
            safe_result_metadata=body.safe_result_metadata,
            client_event_id=body.client_event_id,
        ),
        runtime_identity_id=authority.runtime_identity.id,
    )
    if result.reason_code in {
        "EXECUTION_REPORT_UNKNOWN_RECEIPT",
        "EXECUTION_REPORT_IDENTITY_MISMATCH",
        "EXECUTION_REPORT_DENIED_RECEIPT",
        "EXECUTION_REPORT_INVALID",
    }:
        raise HTTPException(
            status_code=400,
            detail={
                "error": result.reason_code,
                "message": result.human_explanation,
                "receipt_id": str(result.receipt_id) if result.receipt_id else None,
            },
        )
    return result.to_dict()


@router.post("/runtime/client-hooks/heartbeat")
def client_hook_heartbeat(
    body: HeartbeatBody,
    db: Session = Depends(get_db),
    x_rai_agent_key: str | None = Header(default=None, alias="X-RAI-Agent-Key"),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    secret = _extract_runtime_secret(x_rai_agent_key, authorization)
    if not secret:
        raise HTTPException(status_code=401, detail={"error": "UNAUTHENTICATED"})
    authority = RuntimeAuthorityResolver(db).resolve_from_credential(secret)
    if body.protocol_version and body.protocol_version != PROTOCOL_VERSION:
        raise HTTPException(
            status_code=400,
            detail={"error": "UNSUPPORTED_PROTOCOL", "expected": PROTOCOL_VERSION},
        )
    # Never auto-promote local claims to VERIFIED.
    verification = body.verification_status or VerificationStatus.DECLARED.value
    if verification == VerificationStatus.VERIFIED.value:
        verification = VerificationStatus.DECLARED.value
    row = ClientIntegrationRepository(db).record_heartbeat(
        authority.runtime_identity.id,
        body.client_type,
        client_version=body.client_version,
        bridge_version=body.bridge_version or BRIDGE_VERSION,
        protocol_version=str(body.protocol_version or PROTOCOL_VERSION),
        coverage=body.coverage,
        deployment_control=body.deployment_control
        or DeploymentControl.LOCAL_HOOK.value,
        verification_status=verification,
        observed_bridge_hash=body.observed_bridge_hash,
    )
    return _serialize_integration(row)


@router.get("/runtime-identities/{identity_id}/client-integrations")
def list_client_integrations(
    identity_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
):
    rows = ClientIntegrationRepository(db).list_for_identity(identity_id)
    known = {row.client_type: row for row in rows}
    result = []
    for client_type in ("cursor", "claude_code", "gemini_cli"):
        if client_type in known:
            result.append(_serialize_integration(known[client_type]))
        else:
            result.append(
                {
                    "id": None,
                    "runtime_identity_id": str(identity_id),
                    "client_type": client_type,
                    "enforcement_mode": "HOOK_ENFORCED",
                    "deployment_control": DeploymentControl.LOCAL_HOOK.value,
                    "verification_status": VerificationStatus.UNKNOWN.value,
                    "status": "NOT_CONFIGURED",
                    "coverage": DEFAULT_COVERAGE.get(client_type, {}),
                    "coverage_disclaimer": COVERAGE_DISCLAIMER,
                    "client_version": None,
                    "bridge_version": None,
                    "protocol_version": None,
                    "configuration_status": None,
                    "last_seen_at": None,
                    "last_decision_at": None,
                    "last_decision_effect": None,
                }
            )
    return result


@router.post(
    "/runtime-identities/{identity_id}/client-integrations/{client_type}/setup"
)
def setup_client_integration(
    identity_id: UUID,
    client_type: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
):
    return ClientHookService(db).generate_setup_config(identity_id, client_type)


@router.post(
    "/runtime-identities/{identity_id}/client-integrations/{client_type}/managed-profile"
)
def register_managed_profile(
    identity_id: UUID,
    client_type: str,
    body: ManagedProfileBody,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
):
    """Admin-register managed hook expectations (required before VERIFIED)."""
    try:
        row = ClientIntegrationRepository(db).register_managed_profile(
            identity_id,
            client_type,
            deployment_control=body.deployment_control,
            expected_bridge_hash=body.expected_bridge_hash,
            expected_bridge_version=body.expected_bridge_version,
            managed_profile_key=body.managed_profile_key,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail={"error": "INVALID_REQUEST", "message": str(exc)}
        ) from exc
    return _serialize_integration(row)


@router.post("/runtime-identities/{identity_id}/client-integrations/{client_type}/test")
def test_client_integration(
    identity_id: UUID,
    client_type: str,
    body: TestConnectionBody,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
):
    return ClientHookService(db).test_connection(
        identity_id=identity_id,
        client_type=client_type,
        credential_secret=body.credential_secret,
    )


@router.post(
    "/runtime-identities/{identity_id}/client-integrations/{client_type}/disconnect"
)
def disconnect_client_integration(
    identity_id: UUID,
    client_type: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
):
    row = ClientIntegrationRepository(db).disconnect(identity_id, client_type)
    if not row:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND"})
    return _serialize_integration(row)
