"""WP2 Runtime Identity and Delegation REST API."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import rai_gateway.models.identity  # noqa: F401
from rai_gateway.core.authorization import require_permission
from rai_gateway.core.database import get_db
from rai_gateway.core.observability import generate_trace_id, log_admin_audit
from rai_gateway.core.tenant_context import TenantContext
from rai_gateway.identity.errors import AuthorityDeniedError, IdentityError
from rai_gateway.identity.resolver import RuntimeAuthorityResolver
from rai_gateway.identity.service import (
    CredentialService,
    DelegationService,
    RuntimeIdentityService,
)
from rai_gateway.identity.version_resources import (
    enrich_effective_scope,
    load_version_resource_catalog,
)

router = APIRouter(prefix="/v1", tags=["runtime-identity"])


def _handle_error(exc: IdentityError) -> HTTPException:
    detail: dict[str, Any] = {"error": exc.error_code, "message": exc.message}
    if isinstance(exc, AuthorityDeniedError):
        detail["reason"] = exc.reason
    return HTTPException(status_code=exc.status_code, detail=detail)


def _identity_svc(db: Session = Depends(get_db)) -> RuntimeIdentityService:
    return RuntimeIdentityService(db)


def _credential_svc(db: Session = Depends(get_db)) -> CredentialService:
    return CredentialService(db)


def _delegation_svc(db: Session = Depends(get_db)) -> DelegationService:
    return DelegationService(db)


def _audit_role(tenant: TenantContext) -> str:
    return ",".join(tenant.roles) if tenant.roles else "member"


# --- Schemas ---
class RuntimeIdentityCreate(BaseModel):
    agent_id: UUID
    agent_version_id: UUID
    name: str = Field(..., min_length=1)
    identity_type: str = "RAI_API_CREDENTIAL"
    auth_provider: str | None = None
    external_subject: str | None = None
    environment: str | None = None
    expires_at: datetime | None = None


class RuntimeIdentityUpdate(BaseModel):
    name: str | None = None
    environment: str | None = None
    auth_provider: str | None = None
    external_subject: str | None = None
    expires_at: datetime | None = None


class LifecycleAction(BaseModel):
    reason: str | None = None


class CredentialCreate(BaseModel):
    expires_at: datetime | None = None


class CredentialIssuedResponse(BaseModel):
    id: UUID
    credential_key: str
    credential_type: str
    status: str
    issued_at: datetime | None
    expires_at: datetime | None
    plaintext_secret: str


class CredentialResponse(BaseModel):
    id: UUID
    credential_key: str
    credential_type: str
    status: str
    issued_at: datetime | None
    expires_at: datetime | None
    last_used_at: datetime | None
    revoked_at: datetime | None


class DelegationCreate(BaseModel):
    delegator_type: str
    delegator_id: str
    delegate_runtime_identity_id: UUID
    parent_delegation_id: UUID | None = None
    scope: dict[str, Any] = Field(default_factory=dict)
    expires_at: datetime | None = None


class DelegationUpdate(BaseModel):
    scope: dict[str, Any] | None = None
    expires_at: datetime | None = None
    clear_expires_at: bool = False
    valid_from: datetime | None = None
    change_reason: str | None = None


class DelegationLifecycleAction(BaseModel):
    reason: str = Field(..., min_length=1)


def _serialize_identity(identity) -> dict[str, Any]:
    return {
        "id": str(identity.id),
        "identity_key": identity.identity_key,
        "agent_id": str(identity.agent_id),
        "agent_version_id": str(identity.agent_version_id),
        "name": identity.name,
        "identity_type": identity.identity_type,
        "auth_provider": identity.auth_provider,
        "external_subject": identity.external_subject,
        "environment": identity.environment,
        "status": identity.status,
        "created_at": identity.created_at.isoformat() if identity.created_at else None,
        "created_by": identity.created_by,
        "updated_at": identity.updated_at.isoformat() if identity.updated_at else None,
        "expires_at": identity.expires_at.isoformat() if identity.expires_at else None,
        "last_authenticated_at": (
            identity.last_authenticated_at.isoformat()
            if identity.last_authenticated_at
            else None
        ),
        "revoked_at": identity.revoked_at.isoformat() if identity.revoked_at else None,
        "revocation_reason": identity.revocation_reason,
    }


def _serialize_credential(cred, *, include_secret: str | None = None) -> dict[str, Any]:
    data = {
        "id": str(cred.id),
        "credential_key": cred.credential_key,
        "credential_type": cred.credential_type,
        "status": cred.status,
        "issued_at": cred.issued_at.isoformat() if cred.issued_at else None,
        "expires_at": cred.expires_at.isoformat() if cred.expires_at else None,
        "last_used_at": cred.last_used_at.isoformat() if cred.last_used_at else None,
        "revoked_at": cred.revoked_at.isoformat() if cred.revoked_at else None,
    }
    if include_secret:
        data["plaintext_secret"] = include_secret
    return data


def _serialize_delegation(
    grant, *, effective_status: str | None = None
) -> dict[str, Any]:
    scope = grant.scope or {}
    from rai_gateway.identity.domain import DelegationScope

    parsed = DelegationScope.from_dict(scope)
    return {
        "id": str(grant.id),
        "delegator_type": grant.delegator_type,
        "delegator_id": grant.delegator_id,
        "delegate_runtime_identity_id": str(grant.delegate_runtime_identity_id),
        "parent_delegation_id": (
            str(grant.parent_delegation_id) if grant.parent_delegation_id else None
        ),
        "status": grant.status,
        "effective_status": effective_status,
        "scope": parsed.to_legacy_dict(),
        "scope_v2": parsed.to_dict(),
        "scope_version": getattr(grant, "scope_version", None) or parsed.scope_version,
        "revision_number": getattr(grant, "revision_number", None),
        "scope_digest": getattr(grant, "scope_digest", None),
        "valid_from": grant.valid_from.isoformat() if grant.valid_from else None,
        "expires_at": grant.expires_at.isoformat() if grant.expires_at else None,
        "created_by": grant.created_by,
        "created_at": grant.created_at.isoformat() if grant.created_at else None,
        "revoked_at": grant.revoked_at.isoformat() if grant.revoked_at else None,
        "revocation_reason": grant.revocation_reason,
    }


# --- Runtime Identities ---
@router.get("/runtime-identities")
def list_runtime_identities(
    agent_id: UUID | None = None,
    agent_version_id: UUID | None = None,
    status: str | None = None,
    environment: str | None = None,
    search: str | None = None,
    tenant: TenantContext = Depends(require_permission("registry:read")),
    svc: RuntimeIdentityService = Depends(_identity_svc),
):
    identities = svc.list_runtime_identities(
        agent_id=agent_id,
        agent_version_id=agent_version_id,
        status=status,
        environment=environment,
        search=search,
    )
    return [_serialize_identity(i) for i in identities]


@router.post("/runtime-identities", status_code=201)
def create_runtime_identity(
    body: RuntimeIdentityCreate,
    tenant: TenantContext = Depends(require_permission("registry:write")),
    svc: RuntimeIdentityService = Depends(_identity_svc),
):
    try:
        identity = svc.create_runtime_identity(
            agent_id=body.agent_id,
            agent_version_id=body.agent_version_id,
            name=body.name,
            created_by=tenant.user_id,
            identity_type=body.identity_type,
            auth_provider=body.auth_provider,
            external_subject=body.external_subject,
            environment=body.environment,
            expires_at=body.expires_at,
        )
    except IdentityError as exc:
        raise _handle_error(exc) from exc
    log_admin_audit(
        trace_id=generate_trace_id(),
        actor_user_id=tenant.user_id,
        actor_role=_audit_role(tenant),
        action="runtime_identity.created",
        target={
            "runtime_identity_id": str(identity.id),
            "agent_id": str(body.agent_id),
            "agent_version_id": str(body.agent_version_id),
        },
    )
    return _serialize_identity(identity)


@router.get("/runtime-identities/{identity_id}")
def get_runtime_identity(
    identity_id: UUID,
    tenant: TenantContext = Depends(require_permission("registry:read")),
    svc: RuntimeIdentityService = Depends(_identity_svc),
):
    try:
        identity = svc.get_runtime_identity(identity_id)
    except IdentityError as exc:
        raise _handle_error(exc) from exc
    return _serialize_identity(identity)


@router.patch("/runtime-identities/{identity_id}")
def update_runtime_identity(
    identity_id: UUID,
    body: RuntimeIdentityUpdate,
    tenant: TenantContext = Depends(require_permission("registry:write")),
    svc: RuntimeIdentityService = Depends(_identity_svc),
):
    try:
        identity = svc.update_runtime_identity(
            identity_id,
            updated_by=tenant.user_id,
            name=body.name,
            environment=body.environment,
            auth_provider=body.auth_provider,
            external_subject=body.external_subject,
            expires_at=body.expires_at,
        )
    except IdentityError as exc:
        raise _handle_error(exc) from exc
    return _serialize_identity(identity)


@router.post("/runtime-identities/{identity_id}/suspend")
def suspend_runtime_identity(
    identity_id: UUID,
    body: LifecycleAction,
    tenant: TenantContext = Depends(require_permission("registry:write")),
    svc: RuntimeIdentityService = Depends(_identity_svc),
):
    try:
        identity = svc.suspend_runtime_identity(
            identity_id,
            updated_by=tenant.user_id,
            reason=body.reason,
        )
    except IdentityError as exc:
        raise _handle_error(exc) from exc
    log_admin_audit(
        trace_id=generate_trace_id(),
        actor_user_id=tenant.user_id,
        actor_role=_audit_role(tenant),
        action="runtime_identity.suspended",
        target={
            "runtime_identity_id": str(identity_id),
        },
    )
    return _serialize_identity(identity)


@router.post("/runtime-identities/{identity_id}/activate")
def activate_runtime_identity(
    identity_id: UUID,
    body: LifecycleAction = Body(default_factory=LifecycleAction),
    tenant: TenantContext = Depends(require_permission("registry:write")),
    svc: RuntimeIdentityService = Depends(_identity_svc),
):
    reason = body.reason
    try:
        identity = svc.activate_runtime_identity(
            identity_id,
            updated_by=tenant.user_id,
            reason=reason,
        )
    except IdentityError as exc:
        raise _handle_error(exc) from exc
    log_admin_audit(
        trace_id=generate_trace_id(),
        actor_user_id=tenant.user_id,
        actor_role=_audit_role(tenant),
        action="runtime_identity.activated",
        target={
            "runtime_identity_id": str(identity_id),
            "reason": reason,
            "previous_status": "SUSPENDED",
            "new_status": identity.status,
        },
    )
    return _serialize_identity(identity)


@router.post("/runtime-identities/{identity_id}/reactivate")
def reactivate_runtime_identity(
    identity_id: UUID,
    body: LifecycleAction,
    tenant: TenantContext = Depends(require_permission("registry:write")),
    svc: RuntimeIdentityService = Depends(_identity_svc),
):
    """Alias for activate with required reason (WP6 kill-switch reactivation)."""
    try:
        identity = svc.activate_runtime_identity(
            identity_id,
            updated_by=tenant.user_id,
            reason=body.reason,
        )
    except IdentityError as exc:
        raise _handle_error(exc) from exc
    log_admin_audit(
        trace_id=generate_trace_id(),
        actor_user_id=tenant.user_id,
        actor_role=_audit_role(tenant),
        action="runtime_identity.reactivated",
        target={
            "runtime_identity_id": str(identity_id),
            "reason": body.reason,
            "previous_status": "SUSPENDED",
            "new_status": identity.status,
        },
    )
    return _serialize_identity(identity)


@router.post("/runtime-identities/{identity_id}/revoke")
def revoke_runtime_identity(
    identity_id: UUID,
    body: LifecycleAction,
    tenant: TenantContext = Depends(require_permission("registry:write")),
    svc: RuntimeIdentityService = Depends(_identity_svc),
):
    try:
        identity = svc.revoke_runtime_identity(
            identity_id,
            updated_by=tenant.user_id,
            reason=body.reason,
        )
    except IdentityError as exc:
        raise _handle_error(exc) from exc
    log_admin_audit(
        trace_id=generate_trace_id(),
        actor_user_id=tenant.user_id,
        actor_role=_audit_role(tenant),
        action="runtime_identity.revoked",
        target={
            "runtime_identity_id": str(identity_id),
        },
    )
    return _serialize_identity(identity)


# --- Credentials ---
@router.get("/runtime-identities/{identity_id}/credentials")
def list_credentials(
    identity_id: UUID,
    tenant: TenantContext = Depends(require_permission("registry:read")),
    svc: CredentialService = Depends(_credential_svc),
):
    try:
        creds = svc.list_credentials(identity_id)
    except IdentityError as exc:
        raise _handle_error(exc) from exc
    return [_serialize_credential(c) for c in creds]


@router.post("/runtime-identities/{identity_id}/credentials", status_code=201)
def issue_credential(
    identity_id: UUID,
    body: CredentialCreate,
    tenant: TenantContext = Depends(require_permission("registry:write")),
    svc: CredentialService = Depends(_credential_svc),
):
    try:
        issued = svc.issue_credential(
            identity_id,
            created_by=tenant.user_id,
            expires_at=body.expires_at,
        )
    except IdentityError as exc:
        raise _handle_error(exc) from exc
    log_admin_audit(
        trace_id=generate_trace_id(),
        actor_user_id=tenant.user_id,
        actor_role=_audit_role(tenant),
        action="credential.issued",
        target={
            "credential_id": str(issued.credential.id),
            "runtime_identity_id": str(identity_id),
        },
    )
    return _serialize_credential(
        issued.credential, include_secret=issued.plaintext_secret
    )


@router.post("/runtime-identities/{identity_id}/credentials/{credential_id}/rotate")
def rotate_credential(
    identity_id: UUID,
    credential_id: UUID,
    body: CredentialCreate,
    tenant: TenantContext = Depends(require_permission("registry:write")),
    svc: CredentialService = Depends(_credential_svc),
):
    try:
        issued = svc.rotate_credential(
            identity_id,
            credential_id,
            rotated_by=tenant.user_id,
            expires_at=body.expires_at,
        )
    except IdentityError as exc:
        raise _handle_error(exc) from exc
    log_admin_audit(
        trace_id=generate_trace_id(),
        actor_user_id=tenant.user_id,
        actor_role=_audit_role(tenant),
        action="credential.rotated",
        target={
            "credential_id": str(issued.credential.id),
            "replaced_credential_id": str(credential_id),
        },
    )
    return _serialize_credential(
        issued.credential, include_secret=issued.plaintext_secret
    )


@router.post("/runtime-identities/{identity_id}/credentials/{credential_id}/revoke")
def revoke_credential(
    identity_id: UUID,
    credential_id: UUID,
    tenant: TenantContext = Depends(require_permission("registry:write")),
    svc: CredentialService = Depends(_credential_svc),
):
    try:
        cred = svc.revoke_credential(
            identity_id,
            credential_id,
            revoked_by=tenant.user_id,
        )
    except IdentityError as exc:
        raise _handle_error(exc) from exc
    log_admin_audit(
        trace_id=generate_trace_id(),
        actor_user_id=tenant.user_id,
        actor_role=_audit_role(tenant),
        action="credential.revoked",
        target={
            "credential_id": str(credential_id),
        },
    )
    return _serialize_credential(cred)


# --- Delegations ---
@router.get("/delegations")
def list_delegations(
    delegate_runtime_identity_id: UUID | None = None,
    delegator_id: str | None = None,
    status: str | None = None,
    tenant: TenantContext = Depends(require_permission("registry:read")),
    svc: DelegationService = Depends(_delegation_svc),
):
    try:
        grants = svc.list_delegations(
            delegate_runtime_identity_id=delegate_runtime_identity_id,
            delegator_id=delegator_id,
            status=status,
        )
    except IdentityError as exc:
        raise _handle_error(exc) from exc
    return [_serialize_delegation(g) for g in grants]


@router.post("/delegations", status_code=201)
def create_delegation(
    body: DelegationCreate,
    tenant: TenantContext = Depends(require_permission("registry:write")),
    svc: DelegationService = Depends(_delegation_svc),
):
    try:
        grant = svc.create_delegation(
            delegator_type=body.delegator_type,
            delegator_id=body.delegator_id,
            delegate_runtime_identity_id=body.delegate_runtime_identity_id,
            scope=body.scope,
            created_by=tenant.user_id,
            parent_delegation_id=body.parent_delegation_id,
            expires_at=body.expires_at,
        )
    except IdentityError as exc:
        raise _handle_error(exc) from exc
    log_admin_audit(
        trace_id=generate_trace_id(),
        actor_user_id=tenant.user_id,
        actor_role=_audit_role(tenant),
        action="delegation.created",
        target={
            "delegation_id": str(grant.id),
        },
    )
    return _serialize_delegation(grant)


@router.get("/delegations/{delegation_id}")
def get_delegation(
    delegation_id: UUID,
    tenant: TenantContext = Depends(require_permission("registry:read")),
    svc: DelegationService = Depends(_delegation_svc),
):
    try:
        grant = svc.get_delegation(delegation_id)
    except IdentityError as exc:
        raise _handle_error(exc) from exc
    return _serialize_delegation(grant)


@router.patch("/delegations/{delegation_id}")
def update_delegation(
    delegation_id: UUID,
    body: DelegationUpdate,
    tenant: TenantContext = Depends(require_permission("registry:write")),
    svc: DelegationService = Depends(_delegation_svc),
):
    try:
        grant = svc.update_delegation(
            delegation_id,
            updated_by=tenant.user_id,
            scope=body.scope,
            expires_at=body.expires_at,
            clear_expires_at=body.clear_expires_at,
            valid_from=body.valid_from,
            change_reason=body.change_reason,
        )
    except IdentityError as exc:
        raise _handle_error(exc) from exc
    log_admin_audit(
        trace_id=generate_trace_id(),
        actor_user_id=tenant.user_id,
        actor_role=_audit_role(tenant),
        action="delegation.updated",
        target={
            "delegation_id": str(delegation_id),
        },
    )
    return _serialize_delegation(grant)


@router.post("/delegations/{delegation_id}/suspend")
def suspend_delegation(
    delegation_id: UUID,
    body: DelegationLifecycleAction,
    tenant: TenantContext = Depends(require_permission("registry:write")),
    svc: DelegationService = Depends(_delegation_svc),
):
    try:
        grant = svc.suspend_delegation(
            delegation_id,
            updated_by=tenant.user_id,
            reason=body.reason,
        )
    except IdentityError as exc:
        raise _handle_error(exc) from exc
    return _serialize_delegation(
        grant,
        effective_status=svc.compute_effective_status(grant),
    )


@router.post("/delegations/{delegation_id}/activate")
def activate_delegation(
    delegation_id: UUID,
    body: DelegationLifecycleAction,
    tenant: TenantContext = Depends(require_permission("registry:write")),
    svc: DelegationService = Depends(_delegation_svc),
):
    try:
        grant = svc.activate_delegation(
            delegation_id,
            updated_by=tenant.user_id,
            reason=body.reason,
        )
    except IdentityError as exc:
        raise _handle_error(exc) from exc
    return _serialize_delegation(
        grant,
        effective_status=svc.compute_effective_status(grant),
    )


@router.post("/delegations/{delegation_id}/revoke")
def revoke_delegation(
    delegation_id: UUID,
    body: DelegationLifecycleAction,
    tenant: TenantContext = Depends(require_permission("registry:write")),
    svc: DelegationService = Depends(_delegation_svc),
):
    try:
        grant = svc.revoke_delegation(
            delegation_id,
            revoked_by=tenant.user_id,
            reason=body.reason,
        )
    except IdentityError as exc:
        raise _handle_error(exc) from exc
    log_admin_audit(
        trace_id=generate_trace_id(),
        actor_user_id=tenant.user_id,
        actor_role=_audit_role(tenant),
        action="delegation.revoked",
        target={
            "delegation_id": str(delegation_id),
        },
    )
    return _serialize_delegation(grant)


@router.get("/delegations/{delegation_id}/history")
def get_delegation_history(
    delegation_id: UUID,
    tenant: TenantContext = Depends(require_permission("registry:read")),
    svc: DelegationService = Depends(_delegation_svc),
):
    try:
        revisions = svc.list_revisions(delegation_id)
    except IdentityError as exc:
        raise _handle_error(exc) from exc
    return [
        {
            "id": str(rev.id),
            "delegation_id": str(rev.delegation_id),
            "revision_number": rev.revision_number,
            "scope_version": rev.scope_version,
            "scope_snapshot": rev.scope_snapshot,
            "scope_digest": rev.scope_digest,
            "valid_from": rev.valid_from.isoformat() if rev.valid_from else None,
            "expires_at": rev.expires_at.isoformat() if rev.expires_at else None,
            "change_type": rev.change_type,
            "change_reason": rev.change_reason,
            "changed_by": rev.changed_by,
            "created_at": rev.created_at.isoformat() if rev.created_at else None,
        }
        for rev in revisions
    ]


@router.get("/delegations/{delegation_id}/effective-authority")
def get_delegation_effective_authority(
    delegation_id: UUID,
    tenant: TenantContext = Depends(require_permission("registry:read")),
    svc: DelegationService = Depends(_delegation_svc),
    db: Session = Depends(get_db),
):
    try:
        grant = svc.get_delegation(delegation_id)
        effective_scope = svc.compute_effective_scope(grant)
        effective_status = svc.compute_effective_status(grant)
        catalog = load_version_resource_catalog(
            db,
            RuntimeIdentityService(db)
            .get_runtime_identity(
                grant.delegate_runtime_identity_id,
            )
            .agent_version_id,
        )
    except IdentityError as exc:
        raise _handle_error(exc) from exc
    return {
        "delegation": _serialize_delegation(grant, effective_status=effective_status),
        "effective_status": effective_status,
        "effective_scope": effective_scope.to_dict(),
        "effective_scope_legacy": effective_scope.to_legacy_dict(),
        "resources": enrich_effective_scope(catalog, effective_scope.to_legacy_dict()),
    }


@router.get("/agent-versions/{version_id}/delegation-resources")
def get_delegation_resources(
    version_id: UUID,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("registry:read")),
):
    """Authoritative agent-version resources for delegation scope selection."""
    try:
        catalog = load_version_resource_catalog(db, version_id)
    except IdentityError as exc:
        raise _handle_error(exc) from exc
    return catalog.to_dict()


# --- Runtime authority resolution (internal contract surface) ---
class AuthorityResolveRequest(BaseModel):
    agent_id: UUID | None = None
    agent_version_id: UUID | None = None
    delegation_id: UUID | None = None


@router.post("/runtime-authority/resolve")
def resolve_runtime_authority(
    body: AuthorityResolveRequest,
    db: Session = Depends(get_db),
    x_rai_agent_key: str | None = Header(default=None, alias="X-RAI-Agent-Key"),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    """Resolve trusted runtime authority from presented credential."""
    secret = x_rai_agent_key
    if not secret and authorization and authorization.lower().startswith("bearer "):
        secret = authorization[7:].strip()
    if not secret:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "UNAUTHENTICATED",
                "message": "Missing runtime agent credential",
            },
        )
    resolver = RuntimeAuthorityResolver(db)
    try:
        ctx = resolver.resolve_from_credential(
            secret,
            claimed_agent_id=body.agent_id,
            claimed_version_id=body.agent_version_id,
            delegation_id=body.delegation_id,
        )
    except AuthorityDeniedError as exc:
        raise _handle_error(exc) from exc
    catalog = load_version_resource_catalog(db, ctx.agent_version.id)
    return {
        "runtime_identity_id": str(ctx.runtime_identity.id),
        "ai_system_id": str(ctx.ai_system.id),
        "agent_id": str(ctx.agent.id),
        "agent_version_id": str(ctx.agent_version.id),
        "initiating_principal": ctx.initiating_principal,
        "effective_scope": enrich_effective_scope(
            catalog, ctx.effective_scope.to_dict()
        ),
        "eligibility": {
            "eligible": ctx.eligibility.eligible if ctx.eligibility else False,
            "reason": ctx.eligibility.reason if ctx.eligibility else None,
        },
        "delegation_chain": [
            {
                "delegation_id": str(e.delegation_id),
                "delegator_type": e.delegator_type,
                "delegator_id": e.delegator_id,
                "scope": e.scope,
            }
            for e in ctx.delegation_chain
        ],
    }
