"""Release 1 Option A: Minimal built-in Admin Console.

This intentionally avoids introducing a frontend framework for the first release.
It provides:
- simple HTML pages for operators/admins
- minimal JSON admin APIs for automation

Security note:
- This is gated by a shared ADMIN_TOKEN header (X-Admin-Token).
- In later phases, replace with JWT/SSO + step-up verification.
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
import secrets
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from rai_gateway.core.auth import (
    AdminIdentity,
    create_admin_access_token,
    decode_admin_access_token,
    get_admin_identity_by_email,
    hash_password,
    verify_password,
)
from rai_gateway.core.config import settings
from rai_gateway.core.database import get_db
from rai_gateway.core.observability import generate_trace_id, log_admin_audit
from rai_gateway.models.database import (
    AdminAudit,
    AdminCredential,
    ApiKey,
    Case,
    ExecutionAudit,
    PolicyDocument,
    PolicyObligation,
    Prompt,
    PromptAllowlist,
    PromptRaiRule,
    PromptVersion,
    RagDomain,
    RagSource,
    RaiRule,
    RoleDefinition,
    RolePermission,
    UserAccount,
    UserRole,
)
from rai_gateway.models.registry import AISystem
from rai_gateway.services.provider_settings_store import (
    load_provider_settings_into_runtime,
    persist_provider_settings,
)

router = APIRouter(tags=["admin"], include_in_schema=False)


DEFAULT_RBAC_ROLES: Dict[str, Dict[str, Any]] = {
    "admin": {
        "name": "General Admin",
        "description": "Full system access (legacy platform bootstrap)",
        "permissions": ["*"],
    },
    "platform_admin": {
        "name": "Platform Admin",
        "description": "Internal platform administration across tenants",
        "permissions": ["*"],
    },
    "platform_support": {
        "name": "Platform Support",
        "description": "Internal support access with explicit tenant targeting",
        "permissions": [
            "organization_governance:read",
            "portfolio:read",
            "portfolio:executive",
            "audit:read",
            "evidence:read",
            "evidence_package:read",
            "incident:read",
            "risk:read",
            "registry:read",
            "sdk:read",
        ],
    },
    "organization_admin": {
        "name": "Organization Admin",
        "description": "Full management inside a single organization (not platform admin)",
        "permissions": [
            "rules:read",
            "rules:write",
            "prompts:read",
            "prompts:write",
            "prompts:approve",
            "cases:review",
            "cases:resolve",
            "audit:read",
            "executions:read",
            "policies:read",
            "policies:write",
            "registry:read",
            "registry:write",
            "approvals:read",
            "approvals:write",
            "approvals:approve",
            "evidence:read",
            "evidence:content:read",
            "evidence:export",
            "evidence:content:export",
            "evidence:manage",
            "risk:read",
            "risk:manage",
            "risk:intervene",
            "risk:recommendations",
            "risk:emergency",
            "content_evaluator:manage",
            "evaluation:read",
            "evaluation:manage",
            "evaluation:execute",
            "deployment_gate:read",
            "deployment_gate:manage",
            "waiver:request",
            "waiver:approve",
            "assurance:read",
            "organization_governance:read",
            "organization_governance:manage",
            "organization:members:read",
            "organization:members:manage",
            "control:read",
            "control:assess",
            "control:manage",
            "governance_review:read",
            "governance_review:manage",
            "governance_review:decide",
            "exception:read",
            "exception:request",
            "exception:approve",
            "incident:read",
            "incident:create",
            "incident:manage",
            "incident:close",
            "evidence_package:read",
            "evidence_package:export",
            "pilot:read",
            "pilot:manage",
            "portfolio:read",
            "portfolio:executive",
            "portfolio:report",
            "portfolio:report_schedule",
            "portfolio:decision",
            "sdk:read",
            "sdk:manage",
            "rag:read",
            "rag:write",
            "rag:approve",
            "reports:read",
            "finops:read",
            "finops:export",
            "finops:manage_budgets",
        ],
    },
    "ai_system_owner": {
        "name": "AI System Owner",
        "description": "Owns AI systems and related registry/lifecycle actions",
        "permissions": [
            "registry:read",
            "registry:write",
            "approvals:read",
            "approvals:write",
            "evidence:read",
            "evaluation:read",
            "evaluation:manage",
            "deployment_gate:read",
            "assurance:read",
            "organization_governance:read",
            "control:read",
            "governance_review:read",
            "incident:read",
            "incident:create",
            "portfolio:read",
            "sdk:read",
        ],
    },
    "business_owner": {
        "name": "Business Owner",
        "description": "Business ownership of AI systems and approval participation",
        "permissions": [
            "registry:read",
            "approvals:read",
            "approvals:approve",
            "policies:read",
            "evidence:read",
            "risk:read",
            "assurance:read",
            "evaluation:read",
            "deployment_gate:read",
            "organization_governance:read",
            "control:read",
            "governance_review:read",
            "governance_review:decide",
            "exception:read",
            "incident:read",
            "portfolio:read",
            "sdk:read",
        ],
    },
    "technical_owner": {
        "name": "Technical Owner",
        "description": "Technical ownership of agents, versions, and integrations",
        "permissions": [
            "registry:read",
            "registry:write",
            "approvals:read",
            "approvals:write",
            "evidence:read",
            "evaluation:read",
            "evaluation:execute",
            "deployment_gate:read",
            "organization_governance:read",
            "incident:read",
            "incident:create",
            "portfolio:read",
            "sdk:read",
            "sdk:manage",
        ],
    },
    "prompt_requester": {
        "name": "Prompt Requester",
        "description": "Can view prompts and runtime execution status",
        "permissions": ["prompts:read", "executions:read"],
    },
    "prompt_author": {
        "name": "Prompt Author",
        "description": "Can create and update prompts",
        "permissions": ["prompts:read", "prompts:write"],
    },
    "business_approver": {
        "name": "Business Approver",
        "description": "Can approve prompt versions and consequential actions",
        "permissions": [
            "prompts:read",
            "prompts:approve",
            "cases:review",
            "approvals:read",
            "approvals:approve",
            "policies:read",
            "evidence:read",
            "risk:read",
            "assurance:read",
            "waiver:request",
            "waiver:approve",
            "evaluation:read",
            "deployment_gate:read",
            "organization_governance:read",
            "control:read",
            "governance_review:read",
            "governance_review:decide",
            "exception:read",
            "exception:approve",
            "incident:read",
            "evidence_package:read",
            "pilot:read",
            "portfolio:read",
            "portfolio:executive",
            "portfolio:report",
            "sdk:read",
            "finops:read",
        ],
    },
    "rai_officer": {
        "name": "RAI Officer",
        "description": "Can manage rules and review policy issues",
        "permissions": [
            "rules:read",
            "rules:write",
            "prompts:read",
            "prompts:approve",
            "cases:review",
            "cases:resolve",
            "audit:read",
            "executions:read",
            "policies:read",
            "policies:write",
            "registry:read",
            "registry:write",
            "approvals:read",
            "approvals:write",
            "approvals:approve",
            "evidence:read",
            "evidence:content:read",
            "evidence:export",
            "evidence:content:export",
            "evidence:manage",
            "risk:read",
            "risk:manage",
            "risk:intervene",
            "risk:recommendations",
            "risk:emergency",
            "content_evaluator:manage",
            "evaluation:read",
            "evaluation:manage",
            "evaluation:execute",
            "deployment_gate:read",
            "deployment_gate:manage",
            "waiver:request",
            "waiver:approve",
            "assurance:read",
            "organization_governance:read",
            "organization_governance:manage",
            "control:read",
            "control:assess",
            "control:manage",
            "governance_review:read",
            "governance_review:manage",
            "governance_review:decide",
            "exception:read",
            "exception:request",
            "exception:approve",
            "incident:read",
            "incident:create",
            "incident:manage",
            "incident:close",
            "evidence_package:read",
            "evidence_package:export",
            "pilot:read",
            "pilot:manage",
            "portfolio:read",
            "portfolio:executive",
            "portfolio:report",
            "portfolio:report_schedule",
            "portfolio:decision",
            "sdk:read",
            "sdk:manage",
            "finops:read",
            "finops:manage_budgets",
        ],
    },
    "risk_officer": {
        "name": "Risk Officer",
        "description": "Can review and manage runtime risk findings",
        "permissions": [
            "risk:read",
            "risk:manage",
            "risk:intervene",
            "risk:recommendations",
            "evidence:read",
            "policies:read",
            "approvals:read",
            "audit:read",
            "evaluation:read",
            "assurance:read",
            "deployment_gate:read",
            "organization_governance:read",
            "control:read",
            "control:assess",
            "governance_review:read",
            "exception:read",
            "exception:request",
            "incident:read",
            "incident:create",
            "incident:manage",
            "evidence_package:read",
            "pilot:read",
            "portfolio:read",
            "finops:read",
        ],
    },
    "rag_domain_owner": {
        "name": "RAG Domain Owner",
        "description": "Can manage RAG domains and sources",
        "permissions": ["rag:read", "rag:write"],
    },
    "rag_approver": {
        "name": "RAG Approver",
        "description": "Can approve RAG domains",
        "permissions": ["rag:read", "rag:approve"],
    },
    "auditor": {
        "name": "Auditor",
        "description": "Read-only access to audit and reports",
        "permissions": [
            "audit:read",
            "reports:read",
            "executions:read",
            "policies:read",
            "evidence:read",
            "evidence:export",
            "risk:read",
            "evaluation:read",
            "assurance:read",
            "deployment_gate:read",
            "organization_governance:read",
            "control:read",
            "governance_review:read",
            "exception:read",
            "incident:read",
            "evidence_package:read",
            "evidence_package:export",
            "pilot:read",
            "portfolio:read",
            "portfolio:report",
            "sdk:read",
            "finops:read",
            "finops:export",
        ],
    },
    "incident_manager": {
        "name": "Incident Manager",
        "description": "Can manage AI incidents and corrective actions",
        "permissions": [
            "incident:read",
            "incident:create",
            "incident:manage",
            "incident:close",
            "organization_governance:read",
            "evidence_package:read",
            "risk:read",
            "pilot:read",
            "portfolio:read",
        ],
    },
}


ROLE_ALIAS_MAP: Dict[str, str] = {
    "general admin": "admin",
    "platform admin": "platform_admin",
    "platform support": "platform_support",
    "organization admin": "organization_admin",
    "ai system owner": "ai_system_owner",
    "business owner": "business_owner",
    "technical owner": "technical_owner",
    "prompt requester": "prompt_requester",
    "prompt author": "prompt_author",
    "business approver": "business_approver",
    "rai officer": "rai_officer",
    "risk officer": "risk_officer",
    "rag domain owner": "rag_domain_owner",
    "rag approver": "rag_approver",
    "auditor": "auditor",
    "incident manager": "incident_manager",
    "admin": "admin",
}


_admin_identity_ctx: ContextVar[Optional[AdminIdentity]] = ContextVar(
    "admin_identity_ctx", default=None
)
# FastAPI runs Depends() in a copied context, so ContextVar set inside
# require_admin is invisible to the endpoint body. Bind Request in middleware
# and store identity on request.state for imperative permission checks.
_current_request: ContextVar[Optional[Request]] = ContextVar(
    "admin_current_request", default=None
)
_compliance_report_store: Dict[str, Dict[str, Any]] = {}


def bind_current_request(request: Request):
    """Bind the Starlette request into a ContextVar (call from HTTP middleware)."""
    return _current_request.set(request)


def reset_current_request(token) -> None:
    _current_request.reset(token)


def _store_admin_identity(request: Request, identity: AdminIdentity) -> AdminIdentity:
    request.state.rai_admin_identity = identity
    _admin_identity_ctx.set(identity)
    return identity


def _load_admin_identity() -> Optional[AdminIdentity]:
    identity = _admin_identity_ctx.get()
    if identity is not None:
        return identity
    request = _current_request.get()
    if request is None:
        return None
    return getattr(request.state, "rai_admin_identity", None)


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize_role(raw_role: Optional[str]) -> Optional[str]:
    """Normalize a role slug. Missing/blank values never imply admin."""
    if not raw_role:
        return None

    normalized = raw_role.strip().lower().replace("_", " ")
    normalized = " ".join(normalized.split())
    if not normalized:
        return None
    if normalized in ROLE_ALIAS_MAP:
        return ROLE_ALIAS_MAP[normalized]

    slug = normalized.replace(" ", "_")
    return ROLE_ALIAS_MAP.get(slug.replace("_", " "), slug)


def _ensure_default_rbac_seed(db: Session) -> None:
    for role_id, role_data in DEFAULT_RBAC_ROLES.items():
        role = (
            db.query(RoleDefinition).filter(RoleDefinition.role_id == role_id).first()
        )
        if not role:
            db.add(
                RoleDefinition(
                    role_id=role_id,
                    name=role_data["name"],
                    description=role_data["description"],
                    is_system=True,
                )
            )
    db.commit()

    for role_id, role_data in DEFAULT_RBAC_ROLES.items():
        existing = {
            row.permission
            for row in db.query(RolePermission)
            .filter(RolePermission.role_id == role_id)
            .all()
        }
        for permission in role_data["permissions"]:
            if permission in existing:
                continue
            db.add(RolePermission(role_id=role_id, permission=permission))
    db.commit()


def _resolve_permissions(db: Session, role_id: str) -> List[str]:
    _ensure_default_rbac_seed(db)
    rows = db.query(RolePermission).filter(RolePermission.role_id == role_id).all()
    return sorted({row.permission for row in rows})


def _extract_bearer_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.strip().split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip()


def _ensure_bootstrap_admin(db: Session) -> None:
    """
    Phase 22: Bootstrap Admin Hardening

    Ensures RBAC roles exist and checks for bootstrap admin.

    If RAI_ADMIN_BOOTSTRAP_ENABLED=true:
        - Auto-creates bootstrap admin if missing (dev/test only)

    If RAI_ADMIN_BOOTSTRAP_ENABLED=false:
        - Logs warning if no admin users exist
        - Does NOT auto-create (production mode)
    """
    _ensure_default_rbac_seed(db)

    bootstrap_email = settings.admin_bootstrap_email.strip().lower()
    if not bootstrap_email:
        return

    # Check if bootstrap admin already exists
    credential = (
        db.query(AdminCredential)
        .filter(AdminCredential.email == bootstrap_email)
        .first()
    )
    if credential:
        _ensure_instance_foundation(db, credential.user_id)
        return

    # Phase 22: Respect admin_bootstrap_enabled flag
    if not settings.admin_bootstrap_enabled:
        # Production mode: Do NOT auto-create admin
        # Check if ANY admin exists
        any_admin = db.query(AdminCredential).first()
        if not any_admin:
            from rai_gateway.core.observability import logger

            logger.warning(
                "bootstrap_admin_disabled_no_admins",
                message="Bootstrap admin creation is disabled and no admin users exist. "
                "Use CLI to provision admins: python -m rai_gateway.cli.admin create",
                environment=settings.environment,
                bootstrap_enabled=settings.admin_bootstrap_enabled,
            )
        return

    # Development mode: Auto-create bootstrap admin
    from rai_gateway.core.observability import logger

    logger.info(
        "bootstrap_admin_autocreate",
        message=f"Auto-creating bootstrap admin: {bootstrap_email}",
        environment=settings.environment,
    )

    user_id = "admin"
    user = db.query(UserAccount).filter(UserAccount.user_id == user_id).first()
    if not user:
        db.add(
            UserAccount(
                user_id=user_id,
                email=bootstrap_email,
                name=settings.admin_bootstrap_name,
                status="active",
                email_verified_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
    elif user.email_verified_at is None:
        user.email_verified_at = datetime.now(timezone.utc)
        db.commit()

    role_id = _normalize_role(settings.admin_bootstrap_role) or "admin"
    role = db.query(RoleDefinition).filter(RoleDefinition.role_id == role_id).first()
    if role is None:
        role_id = "admin"

    user_role = (
        db.query(UserRole)
        .filter(UserRole.user_id == user_id, UserRole.role_id == role_id)
        .first()
    )
    if not user_role:
        db.add(UserRole(user_id=user_id, role_id=role_id))
        db.commit()

    db.add(
        AdminCredential(
            email=bootstrap_email,
            user_id=user_id,
            password_hash=hash_password(settings.admin_bootstrap_password),
            is_active=True,
        )
    )
    db.commit()
    _ensure_instance_foundation(db, user_id)

    logger.warning(
        "bootstrap_admin_created",
        message=f"Bootstrap admin created: {bootstrap_email}. "
        "IMPORTANT: Change the default password immediately!",
        email=bootstrap_email,
        environment=settings.environment,
    )


def _ensure_instance_foundation(db: Session, user_id: str) -> None:
    """Ensure the singleton profile, onboarding row, admin memberships, and departments."""
    from rai_gateway.governance.departments import ensure_default_departments
    from rai_gateway.governance.domain import GovernanceRole, MembershipStatus
    from rai_gateway.models.governance import (
        OrganizationGovernanceProfile,
        OrganizationMembership,
    )
    from rai_gateway.models.productization import OrganizationOnboarding

    profile = (
        db.query(OrganizationGovernanceProfile)
        .filter(OrganizationGovernanceProfile.singleton_key == "default")
        .first()
    )
    if profile is None:
        db.add(
            OrganizationGovernanceProfile(
                singleton_key="default",
                name="Organization",
                legal_name="Organization",
                organization_type="PRIVATE_ENTERPRISE",
                pilot_status="PLANNING",
                updated_by=user_id,
            )
        )
    onboarding = (
        db.query(OrganizationOnboarding)
        .filter(OrganizationOnboarding.singleton_key == "default")
        .first()
    )
    if onboarding is None:
        db.add(
            OrganizationOnboarding(
                singleton_key="default",
                current_step="organization_profile",
                completed_steps=[],
                status="NOT_STARTED",
            )
        )
    for role in (
        GovernanceRole.ORGANIZATION_ADMIN.value,
        GovernanceRole.RAI_OFFICER.value,
    ):
        existing = (
            db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.user_id == user_id,
                OrganizationMembership.role == role,
            )
            .first()
        )
        if existing is None:
            db.add(
                OrganizationMembership(
                    user_id=user_id,
                    role=role,
                    status=MembershipStatus.ACTIVE.value,
                    created_by=user_id,
                )
            )
    ensure_default_departments(db, created_by=user_id, commit=False)
    db.commit()


def require_admin_permission(
    db: Session,
    permission: str,
    x_admin_role: Optional[str],
    identity: Optional[AdminIdentity] = None,
) -> str:
    """Legacy platform RBAC gate. **DO NOT USE FOR NEW TENANT-SCOPED ROUTES.**

    Prefer ``require_platform_permission`` / ``require_permission`` from
    ``rai_gateway.core.authorization``.

    Fail-closed rules:
    - No verified identity → 401 UNAUTHENTICATED
    - No verified platform roles → 403 PLATFORM_PERMISSION_REQUIRED
    - Caller-selected ``X-Admin-Role`` not in assigned roles → 403 ROLE_NOT_ASSIGNED
    - Missing role header never defaults to admin
    """
    if identity is None:
        identity = _load_admin_identity()

    # Bridge: routes that authenticated via require_user() may only have Principal.
    if identity is None:
        from rai_gateway.core.authorization import get_current_principal

        principal = get_current_principal()
        if principal is not None:
            if not principal.platform_roles:
                raise HTTPException(
                    status_code=403,
                    detail={
                        "error": "PLATFORM_PERMISSION_REQUIRED",
                        "message": "No verified platform role",
                        "required_permission": permission,
                    },
                )
            identity = AdminIdentity(
                email=principal.email,
                user_id=principal.user_id,
                roles=list(principal.platform_roles),
                authentication_assurance=principal.authentication_assurance,
                acr=principal.acr,
                amr=tuple(principal.amr or ()),
                auth_time=principal.auth_time,
            )
            request = _current_request.get()
            if request is not None:
                _store_admin_identity(request, identity)
            else:
                _admin_identity_ctx.set(identity)

    if identity is None:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "UNAUTHENTICATED",
                "message": "Authentication required",
            },
        )

    assigned_roles = {
        normalized
        for role in identity.roles
        if role
        for normalized in [_normalize_role(role)]
        if normalized
    }

    if not assigned_roles:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "PLATFORM_PERMISSION_REQUIRED",
                "message": "No verified platform role",
                "required_permission": permission,
            },
        )

    if x_admin_role:
        selected_role = _normalize_role(x_admin_role)
        if selected_role is None or selected_role not in assigned_roles:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "ROLE_NOT_ASSIGNED",
                    "message": "Selected role is not assigned to this principal",
                    "requested_role": x_admin_role,
                },
            )
    else:
        selected_role = sorted(assigned_roles)[0]

    permissions = _resolve_permissions(db, selected_role)
    if "*" in permissions or permission in permissions:
        return selected_role
    raise HTTPException(
        status_code=403,
        detail={
            "error": "NOT_ALLOWED",
            "message": "Role does not have required permission",
            "required_permission": permission,
            "role": selected_role,
        },
    )


def require_admin(
    request: Request,
    x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
) -> AdminIdentity:
    """Authenticate an admin/operator principal.

    Accepts:
    - SaaS ``user_session`` JWTs (org registration / ``/v1/auth/login``)
    - Legacy ``admin_session`` JWTs
    - Shared ``X-Admin-Token`` bootstrap (dev / automation)
    """
    _ensure_bootstrap_admin(db)

    bearer_token = _extract_bearer_token(authorization)
    if bearer_token:
        from jose import JWTError, jwt

        from rai_gateway.auth.tokens import USER_SESSION_TYPE, decode_user_access_token
        from rai_gateway.core.errors import RaiException
        from rai_gateway.models.database import UserAccount

        token_type = None
        try:
            unverified = jwt.get_unverified_claims(bearer_token)
            token_type = unverified.get("type")
        except JWTError:
            token_type = None

        if token_type == USER_SESSION_TYPE:
            try:
                token_principal = decode_user_access_token(bearer_token)
            except RaiException as exc:
                raise HTTPException(status_code=401, detail=exc.message) from exc

            user = (
                db.query(UserAccount)
                .filter(UserAccount.user_id == token_principal.user_id)
                .first()
            )
            if not user or user.status != "active":
                raise HTTPException(status_code=401, detail="UNAUTHENTICATED")

            from rai_gateway.auth.service import require_active_session

            try:
                require_active_session(db, token_principal.session_id, user.user_id)
            except RaiException as exc:
                raise HTTPException(status_code=401, detail=exc.message) from exc

            from_db = get_admin_identity_by_email(db, user.email)
            if not from_db:
                # User exists but has no AdminCredential row — still allow as
                # an authenticated operator identity for permission checks.
                identity = AdminIdentity(
                    email=user.email,
                    user_id=user.user_id,
                    roles=list(token_principal.platform_roles or ()),
                    authentication_assurance=token_principal.authentication_assurance,
                    acr=token_principal.acr,
                    amr=tuple(token_principal.amr or ()),
                    auth_time=token_principal.auth_time,
                )
            else:
                identity = AdminIdentity(
                    email=from_db.email,
                    user_id=from_db.user_id,
                    roles=from_db.roles,
                    authentication_assurance=token_principal.authentication_assurance,
                    acr=token_principal.acr,
                    amr=tuple(token_principal.amr or ()),
                    auth_time=token_principal.auth_time,
                )
            return _store_admin_identity(request, identity)

        try:
            token_identity = decode_admin_access_token(bearer_token)
        except RaiException as exc:
            raise HTTPException(status_code=401, detail=exc.message) from exc

        from_db = get_admin_identity_by_email(db, token_identity.email)
        if not from_db:
            raise HTTPException(status_code=401, detail="UNAUTHENTICATED")
        # Preserve server-derived IdP assurance claims from the session JWT.
        identity = AdminIdentity(
            email=from_db.email,
            user_id=from_db.user_id,
            roles=from_db.roles,
            authentication_assurance=token_identity.authentication_assurance,
            acr=token_identity.acr,
            amr=token_identity.amr,
            auth_time=token_identity.auth_time,
        )
        return _store_admin_identity(request, identity)

    if settings.admin_token and x_admin_token and x_admin_token == settings.admin_token:
        identity = AdminIdentity(
            email=settings.admin_bootstrap_email,
            user_id="admin",
            roles=["admin"],
        )
        return _store_admin_identity(request, identity)

    raise HTTPException(status_code=401, detail="UNAUTHENTICATED")


def require_step_up(
    x_step_up_token: Optional[str] = Header(default=None, alias="X-Step-Up-Token"),
) -> None:
    """Gate sensitive admin mutations.

    Prefer IdP MFA embedded in the admin session JWT (ACR/AMR). The shared-secret
    header is allowed only when ``allow_shared_secret_step_up`` is explicitly enabled.
    """
    if not settings.require_step_up:
        return

    identity = _load_admin_identity()
    if identity is not None:
        from rai_gateway.core.admin_oidc import AdminOidcVerifier

        if identity.authentication_assurance == "step_up_verified":
            return
        derived = AdminOidcVerifier.derive_assurance(
            acr=identity.acr, amr=tuple(identity.amr or ())
        )
        if derived == "step_up_verified":
            return
        # Session carries configured ACR/AMR — treat as satisfied for admin gates.
        min_acr = (settings.approval_minimum_acr or "").strip()
        required_amr = {
            p.strip()
            for p in (settings.approval_required_amr or "").split(",")
            if p.strip()
        }
        if min_acr and identity.acr == min_acr:
            if not required_amr or required_amr.issubset(set(identity.amr or ())):
                return
        if required_amr and required_amr.issubset(set(identity.amr or ())):
            return

    if settings.allow_shared_secret_step_up and settings.step_up_token:
        if x_step_up_token and x_step_up_token == settings.step_up_token:
            return
        raise HTTPException(status_code=401, detail="STEP_UP_REQUIRED")

    raise HTTPException(
        status_code=401,
        detail="STEP_UP_REQUIRED",
    )


class CreatePromptRequest(BaseModel):
    prompt_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    domain: Optional[str] = None
    description: Optional[str] = None
    owner_system_id: Optional[str] = None


class CreatePromptVersionRequest(BaseModel):
    prompt_id: str = Field(..., min_length=1)
    version: int = Field(..., ge=1)
    template: str = Field(..., min_length=1)
    required_vars_schema: Dict[str, Any]
    model_policy: Dict[str, Any]
    policy_version: str = Field(..., min_length=1)
    created_by: str = Field(..., min_length=1)
    status: str = Field(default="draft")


class AllowlistUpsertRequest(BaseModel):
    prompt_id: str = Field(..., min_length=1)
    version: int = Field(..., ge=1)
    system_id: str = Field(..., min_length=1)
    module: str = Field(..., min_length=1)
    allowed: bool = True


class IssueApiKeyRequest(BaseModel):
    system_id: str = Field(..., min_length=1)
    scopes: List[str] = Field(default_factory=lambda: ["execute"])


class RevokeApiKeyRequest(BaseModel):
    api_key_id: str = Field(..., min_length=1)


class ApprovePromptVersionRequest(BaseModel):
    prompt_id: str = Field(..., min_length=1)
    version: int = Field(..., ge=1)
    approval_type: str = Field(..., min_length=1)  # biz_approved | rai_approved
    approved_by: str = Field(default="admin", min_length=1)


class ExecutionQueryRequest(BaseModel):
    limit: int = Field(default=50, ge=1, le=500)
    system_id: Optional[str] = None
    prompt_id: Optional[str] = None
    decision: Optional[str] = None


class ProviderSettingsUpdateRequest(BaseModel):
    default_provider: Optional[str] = None
    default_model: Optional[str] = None
    llm_provider_url: Optional[str] = None
    llm_provider_api_key: Optional[str] = None
    azure_openai_api_key: Optional[str] = None
    azure_openai_endpoint: Optional[str] = None
    azure_openai_deployment: Optional[str] = None
    azure_openai_api_version: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    aws_region: Optional[str] = None
    gcp_project_id: Optional[str] = None
    gcp_location: Optional[str] = None
    ollama_endpoint: Optional[str] = None


class ProviderTestRequest(BaseModel):
    provider: str = Field(..., min_length=1)
    model: Optional[str] = None


class AdminLoginRequest(BaseModel):
    email: str = Field(..., min_length=3)
    password: str = Field(..., min_length=1)


class AdminOidcLoginRequest(BaseModel):
    """Exchange a verified enterprise IdP ID token for an admin session."""

    id_token: str = Field(..., min_length=10)


class AdminOidcStepUpRequest(BaseModel):
    """Re-verify MFA with IdP and re-issue the admin session with assurance claims."""

    id_token: str = Field(..., min_length=10)


class CreateUserRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    email: str = Field(..., min_length=3)
    name: str = Field(..., min_length=1)
    status: str = Field(default="active")
    roles: List[str] = Field(default_factory=list)


class UpdateUserRequest(BaseModel):
    email: Optional[str] = None
    name: Optional[str] = None
    status: Optional[str] = None


class AssignRolesRequest(BaseModel):
    roles: List[str] = Field(default_factory=list)


class CreateRoleRequest(BaseModel):
    role_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    description: Optional[str] = None
    permissions: List[str] = Field(default_factory=list)


class UpdateRolePermissionsRequest(BaseModel):
    permissions: List[str] = Field(default_factory=list)


class GenerateComplianceReportRequest(BaseModel):
    doc_id: str = Field(..., min_length=1)
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None


def _coerce_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _serialize_datetime(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    return _coerce_utc(value).isoformat()


def _build_compliance_report(
    db: Session,
    doc_id: str,
    start_at: Optional[datetime],
    end_at: Optional[datetime],
) -> Dict[str, Any]:
    policy = db.query(PolicyDocument).filter(PolicyDocument.doc_id == doc_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    period_end = _coerce_utc(end_at) or datetime.now(timezone.utc)
    period_start = _coerce_utc(start_at) or (period_end - timedelta(days=30))

    obligations = (
        db.query(PolicyObligation)
        .filter(PolicyObligation.doc_id == doc_id)
        .order_by(PolicyObligation.obligation_id.asc())
        .all()
    )

    executions_query = db.query(ExecutionAudit)
    admin_audit_query = db.query(AdminAudit)
    cases_query = db.query(Case)

    if period_start:
        executions_query = executions_query.filter(
            ExecutionAudit.created_at >= period_start
        )
        admin_audit_query = admin_audit_query.filter(
            AdminAudit.created_at >= period_start
        )
        cases_query = cases_query.filter(Case.created_at >= period_start)
    if period_end:
        executions_query = executions_query.filter(
            ExecutionAudit.created_at <= period_end
        )
        admin_audit_query = admin_audit_query.filter(
            AdminAudit.created_at <= period_end
        )
        cases_query = cases_query.filter(Case.created_at <= period_end)

    executions = executions_query.all()
    admin_events = admin_audit_query.all()
    cases = cases_query.all()

    blocked_count = sum(1 for row in executions if row.decision == "block")
    resolved_cases = sum(1 for row in cases if row.status == "resolved")

    evidence_flags = {
        "prompt_governance": any(
            event.action
            in {"prompt.create", "prompt_version.create", "prompt_version.approve"}
            for event in admin_events
        ),
        "allowlist_enforcement": any(
            event.action == "allowlist.upsert" for event in admin_events
        ),
        "runtime_guard": any((row.reason_codes or []) for row in executions),
        "case_management": bool(cases),
        "audit_trail": bool(executions) and bool(admin_events),
        "api_key_governance": any(
            event.action.startswith("api_key.") for event in admin_events
        ),
    }

    keyword_map = {
        "consent": ["prompt_governance", "audit_trail"],
        "retention": ["audit_trail"],
        "deletion": ["audit_trail"],
        "audit": ["audit_trail"],
        "access": ["api_key_governance", "audit_trail"],
        "security": ["runtime_guard", "audit_trail"],
        "breach": ["case_management", "runtime_guard"],
        "incident": ["case_management", "runtime_guard"],
    }

    obligation_results: List[Dict[str, Any]] = []
    score = 0.0
    for obligation in obligations:
        probe = " ".join(
            [
                obligation.topic or "",
                obligation.section_ref or "",
                obligation.constraint_action or "",
            ]
        ).lower()

        matched_controls: List[str] = []
        for keyword, controls in keyword_map.items():
            if keyword in probe:
                matched_controls.extend(controls)
        if not matched_controls:
            matched_controls = ["audit_trail"]

        matched_controls = sorted(set(matched_controls))
        covered = [
            control for control in matched_controls if evidence_flags.get(control)
        ]

        if len(covered) == len(matched_controls):
            status = "PASS"
            score += 1.0
        elif covered:
            status = "PARTIAL"
            score += 0.5
        else:
            status = "FAIL"

        obligation_results.append(
            {
                "obligation_id": obligation.obligation_id,
                "section_ref": obligation.section_ref,
                "topic": obligation.topic,
                "constraint_action": obligation.constraint_action,
                "status": status,
                "controls": matched_controls,
                "covered_controls": covered,
            }
        )

    obligation_total = len(obligation_results)
    compliance_score = (
        round((score / obligation_total) * 100, 1) if obligation_total else 0.0
    )

    report_id = f"cr-{uuid4().hex[:12]}"
    generated_at = datetime.now(timezone.utc)
    status = "ready"

    return {
        "report_id": report_id,
        "doc_id": policy.doc_id,
        "title": f"Compliance Report - {policy.doc_id}",
        "report_type": "policy",
        "status": status,
        "generated_at": _serialize_datetime(generated_at),
        "period": {
            "start_at": _serialize_datetime(period_start),
            "end_at": _serialize_datetime(period_end),
        },
        "framework": {
            "country": policy.country,
            "authority": policy.authority,
            "doc_type": policy.doc_type,
            "version": policy.version,
        },
        "summary": {
            "compliance_score": compliance_score,
            "obligations_total": obligation_total,
            "obligations_pass": sum(
                1 for row in obligation_results if row["status"] == "PASS"
            ),
            "obligations_partial": sum(
                1 for row in obligation_results if row["status"] == "PARTIAL"
            ),
            "obligations_fail": sum(
                1 for row in obligation_results if row["status"] == "FAIL"
            ),
            "evidence": {
                "executions_total": len(executions),
                "executions_blocked": blocked_count,
                "admin_events_total": len(admin_events),
                "cases_total": len(cases),
                "cases_resolved": resolved_cases,
            },
        },
        "obligations": obligation_results,
    }


def _mask_secret(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def _provider_settings_payload() -> Dict[str, Any]:
    return {
        "default_provider": getattr(settings, "llm_provider", "openai"),
        "default_model": settings.llm_provider_model,
        "llm_provider_url": settings.llm_provider_url,
        "llm_provider_api_key": _mask_secret(settings.llm_provider_api_key),
        "azure_openai_api_key": _mask_secret(settings.azure_openai_api_key),
        "azure_openai_endpoint": settings.azure_openai_endpoint,
        "azure_openai_deployment": settings.azure_openai_deployment,
        "azure_openai_api_version": settings.azure_openai_api_version,
        "anthropic_api_key": _mask_secret(settings.anthropic_api_key),
        "aws_region": settings.aws_region,
        "gcp_project_id": settings.gcp_project_id,
        "gcp_location": settings.gcp_location,
        "ollama_endpoint": settings.ollama_endpoint,
    }


@router.post("/admin/api/auth/login")
def admin_login(
    payload: AdminLoginRequest,
    db: Session = Depends(get_db),
):
    """Password login — does not grant MFA / step-up assurance.

    CRITICAL approvals require enterprise OIDC login or an explicit IdP step-up
    via ``/admin/api/auth/oidc`` or ``/admin/api/auth/step-up``.
    """
    _ensure_bootstrap_admin(db)
    email = payload.email.strip().lower()

    credential = (
        db.query(AdminCredential).filter(AdminCredential.email == email).first()
    )
    if not credential or not credential.is_active:
        raise HTTPException(status_code=401, detail="UNAUTHENTICATED")

    if not verify_password(payload.password, credential.password_hash):
        raise HTTPException(status_code=401, detail="UNAUTHENTICATED")

    identity = get_admin_identity_by_email(db, email)
    if not identity:
        raise HTTPException(status_code=401, detail="UNAUTHENTICATED")

    token = create_admin_access_token(
        email=identity.email,
        user_id=identity.user_id,
        roles=identity.roles,
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "email": identity.email,
            "user_id": identity.user_id,
            "roles": identity.roles,
            "authentication_assurance": None,
            "acr": None,
            "amr": [],
            "auth_time": None,
        },
    }


def _issue_admin_session_from_oidc(db: Session, id_token: str) -> dict[str, Any]:
    from rai_gateway.core.admin_oidc import AdminOidcVerifier
    from rai_gateway.core.errors import RaiException

    try:
        claims = AdminOidcVerifier().verify_id_token(id_token)
    except RaiException as exc:
        raise HTTPException(status_code=401, detail=exc.message) from exc

    _ensure_bootstrap_admin(db)
    identity = get_admin_identity_by_email(db, claims.email)
    if not identity:
        raise HTTPException(
            status_code=401,
            detail="UNAUTHENTICATED",
        )

    token = create_admin_access_token(
        email=identity.email,
        user_id=identity.user_id,
        roles=identity.roles,
        authentication_assurance=claims.authentication_assurance,
        acr=claims.acr,
        amr=list(claims.amr),
        auth_time=claims.auth_time,
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "email": identity.email,
            "user_id": identity.user_id,
            "roles": identity.roles,
            "authentication_assurance": claims.authentication_assurance,
            "acr": claims.acr,
            "amr": list(claims.amr),
            "auth_time": claims.auth_time,
            "idp_subject": claims.subject,
            "idp_issuer": claims.issuer,
        },
    }


@router.post("/admin/api/auth/oidc")
def admin_oidc_login(
    payload: AdminOidcLoginRequest,
    db: Session = Depends(get_db),
):
    """Login via enterprise IdP ID token (signature-verified; embeds ACR/AMR)."""
    return _issue_admin_session_from_oidc(db, payload.id_token)


@router.post("/admin/api/auth/step-up")
def admin_oidc_step_up(
    payload: AdminOidcStepUpRequest,
    db: Session = Depends(get_db),
    identity: AdminIdentity = Depends(require_admin),
):
    """Elevate an existing admin session after IdP MFA re-authentication.

    The IdP email must match the current session principal.
    """
    result = _issue_admin_session_from_oidc(db, payload.id_token)
    user = result["user"]
    if str(user["email"]).lower() != identity.email.lower():
        raise HTTPException(
            status_code=403,
            detail="STEP_UP_IDENTITY_MISMATCH",
        )
    if not user.get("authentication_assurance") and not user.get("acr"):
        # Require at least one MFA signal for step-up endpoint
        raise HTTPException(status_code=401, detail="STEP_UP_REQUIRED")
    return result


@router.get("/admin/api/auth/me")
def admin_me(identity: AdminIdentity = Depends(require_admin)):
    return {
        "email": identity.email,
        "user_id": identity.user_id,
        "roles": identity.roles,
        "authentication_assurance": identity.authentication_assurance,
        "acr": identity.acr,
        "amr": list(identity.amr or ()),
        "auth_time": identity.auth_time,
    }


@router.get("/admin/api/rbac/context")
def get_rbac_context(
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
    x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
):
    selected_role = _normalize_role(x_admin_role)
    _ensure_default_rbac_seed(db)
    permissions = _resolve_permissions(db, selected_role)
    available_roles = (
        db.query(RoleDefinition).order_by(RoleDefinition.role_id.asc()).all()
    )
    return {
        "selected_role": selected_role,
        "permissions": permissions,
        "available_roles": [
            {
                "role_id": role.role_id,
                "name": role.name,
                "description": role.description,
            }
            for role in available_roles
        ],
    }


@router.get("/admin/api/users")
def list_users(
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
    x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
):
    require_admin_permission(db, "users:read", x_admin_role)
    users = db.query(UserAccount).order_by(UserAccount.created_at.desc()).all()

    user_role_rows = db.query(UserRole).all()
    roles_by_user: Dict[str, List[str]] = {}
    for row in user_role_rows:
        roles_by_user.setdefault(row.user_id, []).append(row.role_id)

    return [
        {
            "user_id": user.user_id,
            "email": user.email,
            "name": user.name,
            "status": user.status,
            "roles": sorted(roles_by_user.get(user.user_id, [])),
            "created_at": user.created_at,
            "updated_at": user.updated_at,
        }
        for user in users
    ]


@router.post("/admin/api/users")
def create_user(
    payload: CreateUserRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
    x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
    x_admin_user: Optional[str] = Header(default="admin", alias="X-Admin-User"),
):
    actor_role = require_admin_permission(db, "users:write", x_admin_role)
    _ensure_default_rbac_seed(db)

    existing = (
        db.query(UserAccount).filter(UserAccount.user_id == payload.user_id).first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="User already exists")

    if db.query(UserAccount).filter(UserAccount.email == payload.email).first():
        raise HTTPException(status_code=409, detail="Email already exists")

    user = UserAccount(
        user_id=payload.user_id,
        email=payload.email,
        name=payload.name,
        status=payload.status,
    )
    db.add(user)
    db.commit()

    role_ids = sorted({_normalize_role(role) for role in payload.roles})
    for role_id in role_ids:
        role = (
            db.query(RoleDefinition).filter(RoleDefinition.role_id == role_id).first()
        )
        if role is None:
            raise HTTPException(status_code=404, detail=f"Role not found: {role_id}")
        db.add(UserRole(user_id=payload.user_id, role_id=role_id))
    db.commit()

    trace_id = generate_trace_id()
    db.add(
        AdminAudit(
            trace_id=trace_id,
            actor_user_id=x_admin_user or "admin",
            actor_role=actor_role,
            action="user.create",
            target={"user_id": payload.user_id, "roles": role_ids},
            auth_strength="admin_token",
        )
    )
    db.commit()

    return {"ok": True, "user_id": payload.user_id, "roles": role_ids}


@router.put("/admin/api/users/{user_id}")
def update_user(
    user_id: str,
    payload: UpdateUserRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
    x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
):
    require_admin_permission(db, "users:write", x_admin_role)
    user = db.query(UserAccount).filter(UserAccount.user_id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if payload.email is not None:
        user.email = payload.email
    if payload.name is not None:
        user.name = payload.name
    if payload.status is not None:
        user.status = payload.status

    db.commit()
    return {"ok": True, "user_id": user_id}


@router.post("/admin/api/users/{user_id}/roles")
def assign_user_roles(
    user_id: str,
    payload: AssignRolesRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
    x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
):
    require_admin_permission(db, "users:write", x_admin_role)
    _ensure_default_rbac_seed(db)

    user = db.query(UserAccount).filter(UserAccount.user_id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    db.query(UserRole).filter(UserRole.user_id == user_id).delete()
    role_ids = sorted({_normalize_role(role) for role in payload.roles})
    for role_id in role_ids:
        role = (
            db.query(RoleDefinition).filter(RoleDefinition.role_id == role_id).first()
        )
        if role is None:
            raise HTTPException(status_code=404, detail=f"Role not found: {role_id}")
        db.add(UserRole(user_id=user_id, role_id=role_id))

    db.commit()
    return {"ok": True, "user_id": user_id, "roles": role_ids}


@router.delete("/admin/api/users/{user_id}")
def delete_user(
    user_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
    x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
    x_admin_user: Optional[str] = Header(default="admin", alias="X-Admin-User"),
):
    """Delete a user account and related credentials, roles, and memberships."""
    actor_role = require_admin_permission(db, "users:write", x_admin_role)

    user = db.query(UserAccount).filter(UserAccount.user_id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    # Never allow deleting the last platform admin via this path.
    platform_roles = (
        db.query(UserRole)
        .filter(
            UserRole.user_id == user_id,
            UserRole.role_id.in_(["admin", "platform_admin"]),
        )
        .count()
    )
    if platform_roles:
        remaining_admins = (
            db.query(UserRole)
            .filter(
                UserRole.role_id.in_(["admin", "platform_admin"]),
                UserRole.user_id != user_id,
            )
            .count()
        )
        if remaining_admins == 0:
            raise HTTPException(
                status_code=400,
                detail="Cannot delete the last platform admin",
            )

    from rai_gateway.models.auth import (
        AuthSession,
        EmailVerificationToken,
        PasswordResetToken,
    )
    from rai_gateway.models.governance import OrganizationMembership

    db.query(AuthSession).filter(AuthSession.user_id == user_id).delete(
        synchronize_session=False
    )
    db.query(EmailVerificationToken).filter(
        EmailVerificationToken.user_id == user_id
    ).delete(synchronize_session=False)
    db.query(PasswordResetToken).filter(PasswordResetToken.user_id == user_id).delete(
        synchronize_session=False
    )
    from rai_gateway.models.auth import EmailDeliveryAttempt

    db.query(EmailDeliveryAttempt).filter(
        EmailDeliveryAttempt.user_id == user_id
    ).delete(synchronize_session=False)
    db.query(OrganizationMembership).filter(
        OrganizationMembership.user_id == user_id
    ).delete(synchronize_session=False)
    db.query(UserRole).filter(UserRole.user_id == user_id).delete(
        synchronize_session=False
    )
    db.query(AdminCredential).filter(AdminCredential.user_id == user_id).delete(
        synchronize_session=False
    )
    db.delete(user)

    trace_id = generate_trace_id()
    db.add(
        AdminAudit(
            trace_id=trace_id,
            actor_user_id=x_admin_user or "admin",
            actor_role=actor_role,
            action="user.delete",
            target={"user_id": user_id},
            auth_strength="admin_token",
        )
    )
    db.commit()
    return {"ok": True, "user_id": user_id, "deleted": True}


@router.get("/admin/api/roles")
def list_roles(
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
    x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
):
    require_admin_permission(db, "roles:read", x_admin_role)
    _ensure_default_rbac_seed(db)

    roles = db.query(RoleDefinition).order_by(RoleDefinition.role_id.asc()).all()
    permissions = db.query(RolePermission).all()
    perms_by_role: Dict[str, List[str]] = {}
    for row in permissions:
        perms_by_role.setdefault(row.role_id, []).append(row.permission)

    return [
        {
            "role_id": role.role_id,
            "name": role.name,
            "description": role.description,
            "is_system": role.is_system,
            "permissions": sorted(perms_by_role.get(role.role_id, [])),
            "created_at": role.created_at,
        }
        for role in roles
    ]


@router.post("/admin/api/roles")
def create_role(
    payload: CreateRoleRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
    x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
):
    require_admin_permission(db, "roles:write", x_admin_role)

    role_id = _normalize_role(payload.role_id)
    existing = (
        db.query(RoleDefinition).filter(RoleDefinition.role_id == role_id).first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Role already exists")

    db.add(
        RoleDefinition(
            role_id=role_id,
            name=payload.name,
            description=payload.description,
            is_system=False,
        )
    )
    db.commit()

    for permission in sorted(set(payload.permissions)):
        db.add(RolePermission(role_id=role_id, permission=permission))
    db.commit()
    return {"ok": True, "role_id": role_id}


@router.post("/admin/api/roles/{role_id}/permissions")
def update_role_permissions(
    role_id: str,
    payload: UpdateRolePermissionsRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
    x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
):
    require_admin_permission(db, "roles:write", x_admin_role)
    role_id = _normalize_role(role_id)

    role = db.query(RoleDefinition).filter(RoleDefinition.role_id == role_id).first()
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found")

    db.query(RolePermission).filter(RolePermission.role_id == role_id).delete()
    for permission in sorted(set(payload.permissions)):
        db.add(RolePermission(role_id=role_id, permission=permission))
    db.commit()

    return {
        "ok": True,
        "role_id": role_id,
        "permissions": sorted(set(payload.permissions)),
    }


@router.get("/admin", response_class=HTMLResponse)
def admin_home(_: None = Depends(require_admin)) -> str:
    return """<!doctype html>
<html>
  <head><meta charset='utf-8'><title>RAI Gateway Admin</title></head>
  <body>
    <h1>RAI Gateway — Admin Console (Release 1)</h1>
    <ul>
      <li><a href='/admin/prompts'>Prompts</a></li>
      <li><a href='/admin/allowlist'>Allowlist</a></li>
      <li><a href='/admin/api-keys'>API Keys</a></li>
      <li><a href='/admin/executions'>Executions (Audit)</a></li>
      <li><a href='/admin/ops'>Ops</a></li>
    </ul>
    <p>Auth: send <code>X-Admin-Token</code> header.</p>
  </body>
</html>"""


@router.get("/admin/prompts", response_class=HTMLResponse)
def prompts_page(
    db: Session = Depends(get_db), _: None = Depends(require_admin)
) -> str:
    prompts = db.query(Prompt).order_by(Prompt.created_at.desc()).limit(200).all()

    rows = []
    for prompt in prompts:
        rows.append(
            f"<tr><td>{prompt.prompt_id}</td><td>{prompt.name}</td><td>{prompt.domain or ''}</td>"
            f"<td>{prompt.status}</td><td>{prompt.owner_system_id or ''}</td></tr>"
        )

    return (
        """<!doctype html>
<html>
  <head><meta charset='utf-8'><title>Prompts</title></head>
  <body>
    <h1>Prompts</h1>
    <p><a href='/admin'>Back</a></p>

    <h2>Create Prompt</h2>
    <p>POST JSON to <code>/admin/api/prompts</code></p>

    <h2>List</h2>
    <table border='1' cellpadding='6' cellspacing='0'>
      <tr><th>prompt_id</th><th>name</th><th>domain</th><th>status</th><th>owner</th></tr>
      """
        + "\n".join(rows)
        + """
    </table>

    <h2>Create Prompt Version</h2>
    <p>POST JSON to <code>/admin/api/prompt-versions</code></p>
  </body>
</html>"""
    )


@router.get("/admin/allowlist", response_class=HTMLResponse)
def allowlist_page(
    db: Session = Depends(get_db), _: None = Depends(require_admin)
) -> str:
    entries = (
        db.query(PromptAllowlist)
        .order_by(PromptAllowlist.created_at.desc())
        .limit(300)
        .all()
    )

    rows = []
    for e in entries:
        rows.append(
            f"<tr><td>{e.prompt_id}</td><td>{e.version}</td><td>{e.system_id}</td><td>{e.module}</td>"
            f"<td>{'true' if e.allowed else 'false'}</td></tr>"
        )

    return (
        """<!doctype html>
<html>
  <head><meta charset='utf-8'><title>Allowlist</title></head>
  <body>
    <h1>Allowlist</h1>
    <p><a href='/admin'>Back</a></p>

    <h2>Upsert Entry</h2>
    <p>POST JSON to <code>/admin/api/allowlist</code></p>

    <h2>List</h2>
    <table border='1' cellpadding='6' cellspacing='0'>
      <tr><th>prompt_id</th><th>version</th><th>system_id</th><th>module</th><th>allowed</th></tr>
      """
        + "\n".join(rows)
        + """
    </table>
  </body>
</html>"""
    )


@router.get("/admin/api-keys", response_class=HTMLResponse)
def api_keys_page(
    db: Session = Depends(get_db), _: None = Depends(require_admin)
) -> str:
    keys = db.query(ApiKey).order_by(ApiKey.created_at.desc()).limit(200).all()
    rows = []
    for k in keys:
        rows.append(
            f"<tr><td>{k.api_key_id}</td><td>{k.system_id}</td><td>{k.status}</td>"
            f"<td>{','.join(k.scopes or [])}</td></tr>"
        )

    return (
        """<!doctype html>
<html>
  <head><meta charset='utf-8'><title>API Keys</title></head>
  <body>
    <h1>API Keys</h1>
    <p><a href='/admin'>Back</a></p>

    <h2>Issue Key</h2>
    <p>POST JSON to <code>/admin/api/api-keys/issue</code> (plaintext key returned once).</p>

    <h2>List</h2>
    <table border='1' cellpadding='6' cellspacing='0'>
      <tr><th>api_key_id</th><th>system_id</th><th>status</th><th>scopes</th></tr>
      """
        + "\n".join(rows)
        + """
    </table>
  </body>
</html>"""
    )


@router.get("/admin/executions", response_class=HTMLResponse)
def executions_page(
    db: Session = Depends(get_db), _: None = Depends(require_admin)
) -> str:
    executions = (
        db.query(ExecutionAudit)
        .order_by(ExecutionAudit.created_at.desc())
        .limit(200)
        .all()
    )

    rows = []
    for ex in executions:
        rows.append(
            "<tr>"
            f"<td>{ex.created_at}</td>"
            f"<td>{ex.execution_id}</td>"
            f"<td>{ex.trace_id}</td>"
            f"<td>{ex.prompt_id}:{ex.prompt_version}</td>"
            f"<td>{ex.system_id}</td>"
            f"<td>{ex.module or ''}</td>"
            f"<td>{ex.decision}</td>"
            f"<td>{ex.llm_model or ''}</td>"
            f"<td>{'true' if ex.cache_hit else 'false'}</td>"
            "</tr>"
        )

    return (
        """<!doctype html>
<html>
  <head><meta charset='utf-8'><title>Executions</title></head>
  <body>
    <h1>Executions (Metadata-only Audit)</h1>
    <p><a href='/admin'>Back</a></p>

    <table border='1' cellpadding='6' cellspacing='0'>
      <tr>
        <th>time</th><th>execution_id</th><th>trace_id</th><th>prompt</th><th>system</th><th>module</th>
        <th>decision</th><th>model</th><th>cache_hit</th>
      </tr>
      """
        + "\n".join(rows)
        + """
    </table>
  </body>
</html>"""
    )


@router.get("/admin/ops", response_class=HTMLResponse)
def ops_page(db: Session = Depends(get_db), _: None = Depends(require_admin)) -> str:
    # Minimal DB-backed metrics (Release 1 Option A)
    total = db.query(func.count(ExecutionAudit.execution_id)).scalar() or 0
    by_decision = (
        db.query(ExecutionAudit.decision, func.count(ExecutionAudit.execution_id))
        .group_by(ExecutionAudit.decision)
        .all()
    )

    decision_rows = "".join([f"<li>{d}: {c}</li>" for d, c in by_decision])

    return f"""<!doctype html>
<html>
  <head><meta charset='utf-8'><title>Ops</title></head>
  <body>
    <h1>Ops</h1>
    <p><a href='/admin'>Back</a></p>

    <h2>Quick stats</h2>
    <ul>
      <li>Total executions: {total}</li>
    </ul>

    <h2>Executions by decision</h2>
    <ul>
      {decision_rows}
    </ul>

    <p>Note: Grafana/Prometheus dashboards can replace this in Phase P1.</p>
  </body>
</html>"""


@router.post("/admin/api/prompts")
def create_prompt(
    payload: CreatePromptRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
    x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
):
    actor_role = require_admin_permission(db, "prompts:write", x_admin_role)
    trace_id = generate_trace_id()

    existing = db.query(Prompt).filter(Prompt.prompt_id == payload.prompt_id).first()
    if existing:
        raise HTTPException(status_code=409, detail="Prompt already exists")

    prompt = Prompt(
        prompt_id=payload.prompt_id,
        name=payload.name,
        domain=payload.domain,
        description=payload.description,
        status="active",
        owner_system_id=payload.owner_system_id,
    )
    db.add(prompt)
    db.commit()

    db.add(
        AdminAudit(
            trace_id=trace_id,
            actor_user_id="admin",
            actor_role=actor_role,
            action="prompt.create",
            target={"prompt_id": payload.prompt_id},
            auth_strength="admin_token",
        )
    )
    db.commit()

    log_admin_audit(
        trace_id=trace_id,
        actor_user_id="admin",
        actor_role=actor_role,
        action="prompt.create",
        target={"prompt_id": payload.prompt_id},
        auth_strength="admin_token",
    )

    return {"ok": True, "prompt_id": payload.prompt_id}


@router.post("/admin/api/prompt-versions")
def create_prompt_version(
    payload: CreatePromptVersionRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
    x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
):
    actor_role = require_admin_permission(db, "prompts:write", x_admin_role)
    trace_id = generate_trace_id()

    # Ensure prompt exists
    prompt = db.query(Prompt).filter(Prompt.prompt_id == payload.prompt_id).first()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    existing = (
        db.query(PromptVersion)
        .filter(
            PromptVersion.prompt_id == payload.prompt_id,
            PromptVersion.version == payload.version,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Prompt version already exists")

    pv = PromptVersion(
        prompt_id=payload.prompt_id,
        version=payload.version,
        status=payload.status,
        template=payload.template,
        required_vars_schema=payload.required_vars_schema,
        expected_output_schema=None,
        model_policy=payload.model_policy,
        policy_version=payload.policy_version,
        cache_policy={"enabled": False},
        case_policy={"enabled": False},
        rag_policy={"enabled": False},
        judge_policy={"enabled": False},
        xai_policy={"enabled": False},
        review_prompt_template=None,
        created_by=payload.created_by,
    )
    db.add(pv)
    db.commit()

    db.add(
        AdminAudit(
            trace_id=trace_id,
            actor_user_id="admin",
            actor_role=actor_role,
            action="prompt_version.create",
            target={
                "prompt_id": payload.prompt_id,
                "version": payload.version,
                "template_hash": _sha256_hex(payload.template),
            },
            auth_strength="admin_token",
        )
    )
    db.commit()

    log_admin_audit(
        trace_id=trace_id,
        actor_user_id="admin",
        actor_role=actor_role,
        action="prompt_version.create",
        target={"prompt_id": payload.prompt_id, "version": payload.version},
        auth_strength="admin_token",
    )

    return {
        "ok": True,
        "prompt_id": payload.prompt_id,
        "version": payload.version,
        "status": pv.status,
    }


@router.post("/admin/api/allowlist")
def upsert_allowlist(
    payload: AllowlistUpsertRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
    x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
):
    actor_role = require_admin_permission(db, "prompts:write", x_admin_role)
    trace_id = generate_trace_id()

    existing = (
        db.query(PromptAllowlist)
        .filter(
            PromptAllowlist.prompt_id == payload.prompt_id,
            PromptAllowlist.version == payload.version,
            PromptAllowlist.system_id == payload.system_id,
            PromptAllowlist.module == payload.module,
        )
        .first()
    )

    if existing:
        existing.allowed = payload.allowed
    else:
        db.add(
            PromptAllowlist(
                prompt_id=payload.prompt_id,
                version=payload.version,
                system_id=payload.system_id,
                module=payload.module,
                allowed=payload.allowed,
                conditions=None,
            )
        )

    db.commit()

    db.add(
        AdminAudit(
            trace_id=trace_id,
            actor_user_id="admin",
            actor_role=actor_role,
            action="allowlist.upsert",
            target={
                "prompt_id": payload.prompt_id,
                "version": payload.version,
                "system_id": payload.system_id,
                "module": payload.module,
                "allowed": payload.allowed,
            },
            auth_strength="admin_token",
        )
    )
    db.commit()

    log_admin_audit(
        trace_id=trace_id,
        actor_user_id="admin",
        actor_role=actor_role,
        action="allowlist.upsert",
        target={
            "prompt_id": payload.prompt_id,
            "version": payload.version,
            "system_id": payload.system_id,
            "module": payload.module,
        },
        auth_strength="admin_token",
    )

    return {"ok": True}


@router.post("/admin/api/api-keys/issue")
def issue_api_key(
    payload: IssueApiKeyRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
    x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
):
    actor_role = require_admin_permission(db, "api_keys:write", x_admin_role)
    trace_id = generate_trace_id()

    # Return plaintext once; store hash.
    plaintext = secrets.token_urlsafe(32)
    key_hash = _sha256_hex(plaintext)

    record = ApiKey(
        key_hash=key_hash,
        system_id=payload.system_id,
        scopes=payload.scopes,
        status="active",
    )
    db.add(record)
    db.commit()

    db.add(
        AdminAudit(
            trace_id=trace_id,
            actor_user_id="admin",
            actor_role=actor_role,
            action="api_key.issue",
            target={
                "api_key_id": str(record.api_key_id),
                "system_id": payload.system_id,
                "scopes": payload.scopes,
            },
            auth_strength="admin_token",
        )
    )
    db.commit()

    log_admin_audit(
        trace_id=trace_id,
        actor_user_id="admin",
        actor_role=actor_role,
        action="api_key.issue",
        target={"api_key_id": str(record.api_key_id), "system_id": payload.system_id},
        auth_strength="admin_token",
    )

    return {
        "api_key_id": str(record.api_key_id),
        "system_id": payload.system_id,
        "scopes": payload.scopes,
        "api_key": plaintext,
        "note": "Plaintext key is shown only once. Store it securely.",
    }


@router.get("/admin/api/api-keys")
def list_api_keys(
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
    x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
):
    require_admin_permission(db, "api_keys:read", x_admin_role)
    keys = db.query(ApiKey).order_by(ApiKey.created_at.desc()).limit(500).all()
    return [
        {
            "api_key_id": str(k.api_key_id),
            "system_id": k.system_id,
            "status": k.status,
            "scopes": k.scopes or [],
            "created_at": k.created_at.isoformat() if k.created_at else None,
            "revoked_at": k.revoked_at.isoformat() if k.revoked_at else None,
            "expires_at": k.expires_at.isoformat() if k.expires_at else None,
        }
        for k in keys
    ]


@router.post("/admin/api/api-keys/revoke")
def revoke_api_key(
    payload: RevokeApiKeyRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
    x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
):
    actor_role = require_admin_permission(db, "api_keys:write", x_admin_role)
    trace_id = generate_trace_id()

    record = db.query(ApiKey).filter(ApiKey.api_key_id == payload.api_key_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="API key not found")

    record.status = "revoked"
    record.revoked_at = func.now()
    db.commit()

    db.add(
        AdminAudit(
            trace_id=trace_id,
            actor_user_id="admin",
            actor_role=actor_role,
            action="api_key.revoke",
            target={
                "api_key_id": str(record.api_key_id),
                "system_id": record.system_id,
            },
            auth_strength="admin_token",
        )
    )
    db.commit()

    log_admin_audit(
        trace_id=trace_id,
        actor_user_id="admin",
        actor_role=actor_role,
        action="api_key.revoke",
        target={"api_key_id": str(record.api_key_id), "system_id": record.system_id},
        auth_strength="admin_token",
    )

    return {"ok": True, "api_key_id": str(record.api_key_id), "status": record.status}


@router.post("/admin/api/prompt-versions/approve")
def approve_prompt_version(
    payload: ApprovePromptVersionRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
    __: None = Depends(require_step_up),
    x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
):
    actor_role = require_admin_permission(db, "prompts:approve", x_admin_role)
    trace_id = generate_trace_id()

    pv = (
        db.query(PromptVersion)
        .filter(
            PromptVersion.prompt_id == payload.prompt_id,
            PromptVersion.version == payload.version,
        )
        .first()
    )
    if not pv:
        raise HTTPException(status_code=404, detail="Prompt version not found")

    # Minimal lifecycle for Release 1:
    # draft -> biz_approved -> active
    if payload.approval_type == "biz_approved" and pv.status == "draft":
        pv.status = "biz_approved"
    elif payload.approval_type == "rai_approved" and pv.status == "biz_approved":
        pv.status = "active"
    else:
        raise HTTPException(
            status_code=409,
            detail=f"Invalid approval transition: {pv.status} -> {payload.approval_type}",
        )

    pv.approved_by = payload.approved_by
    pv.approved_at = func.now()
    db.commit()

    db.add(
        AdminAudit(
            trace_id=trace_id,
            actor_user_id=payload.approved_by,
            actor_role=actor_role,
            action="prompt_version.approve",
            target={
                "prompt_id": payload.prompt_id,
                "version": payload.version,
                "approval_type": payload.approval_type,
                "new_status": pv.status,
            },
            auth_strength="admin_token",
        )
    )
    db.commit()

    log_admin_audit(
        trace_id=trace_id,
        actor_user_id=payload.approved_by,
        actor_role=actor_role,
        action="prompt_version.approve",
        target={
            "prompt_id": payload.prompt_id,
            "version": payload.version,
            "new_status": pv.status,
        },
        auth_strength="admin_token",
    )

    return {
        "ok": True,
        "prompt_id": payload.prompt_id,
        "version": payload.version,
        "status": pv.status,
    }


@router.post("/admin/api/executions/query")
def query_executions(
    payload: ExecutionQueryRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
    x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
):
    require_admin_permission(db, "executions:read", x_admin_role)
    q = db.query(ExecutionAudit).order_by(ExecutionAudit.created_at.desc())

    if payload.system_id:
        q = q.filter(ExecutionAudit.system_id == payload.system_id)
    if payload.prompt_id:
        q = q.filter(ExecutionAudit.prompt_id == payload.prompt_id)
    if payload.decision:
        q = q.filter(ExecutionAudit.decision == payload.decision)

    rows = q.limit(payload.limit).all()
    return [
        {
            "execution_id": str(r.execution_id),
            "trace_id": r.trace_id,
            "prompt_id": r.prompt_id,
            "prompt_version": r.prompt_version,
            "system_id": r.system_id,
            "module": r.module,
            "decision": r.decision,
            "reason_codes": r.reason_codes or [],
            "rule_ids": r.rule_ids or [],
            "llm_model": r.llm_model,
            "cache_hit": bool(r.cache_hit),
            "latency_ms": r.latency_ms,
            "tokens_in": r.tokens_in,
            "tokens_out": r.tokens_out,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.get("/admin/api/executions/{execution_id}")
def get_execution_detail(
    execution_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
    x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
):
    require_admin_permission(db, "executions:read", x_admin_role)
    if execution_id == "sample":
        record = (
            db.query(ExecutionAudit).order_by(ExecutionAudit.created_at.desc()).first()
        )
        if not record:
            raise HTTPException(status_code=404, detail="No executions available")
    else:
        record = (
            db.query(ExecutionAudit)
            .filter(ExecutionAudit.execution_id == execution_id)
            .first()
        )
    if not record:
        raise HTTPException(status_code=404, detail="Execution not found")

    return {
        "execution_id": str(record.execution_id),
        "trace_id": record.trace_id,
        "prompt_id": record.prompt_id,
        "prompt_version": record.prompt_version,
        "system_id": record.system_id,
        "module": record.module,
        "decision": record.decision,
        "reason_codes": record.reason_codes or [],
        "rule_ids": record.rule_ids or [],
        "policy_version": record.policy_version,
        "guard_version": record.guard_version,
        "llm_model": record.llm_model,
        "cache_hit": bool(record.cache_hit),
        "latency_ms": record.latency_ms,
        "tokens_in": record.tokens_in,
        "tokens_out": record.tokens_out,
        "input_hash": record.input_hash,
        "output_hash": record.output_hash,
        "evidence_ref": record.evidence_ref,
        "citations_refs": record.citations_refs,
        "classification_level": record.classification_level,
        "classification_tags": record.classification_tags or [],
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


@router.get("/admin/api/prompts")
def list_prompts(
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
    x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
):
    require_admin_permission(db, "prompts:read", x_admin_role)
    prompts = db.query(Prompt).order_by(Prompt.created_at.desc()).limit(500).all()
    return [
        {
            "prompt_id": p.prompt_id,
            "name": p.name,
            "domain": p.domain,
            "status": p.status,
            "owner_system_id": p.owner_system_id,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in prompts
    ]


@router.get("/admin/api/prompts/{prompt_id}")
def get_prompt(
    prompt_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
    x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
):
    require_admin_permission(db, "prompts:read", x_admin_role)
    prompt = db.query(Prompt).filter(Prompt.prompt_id == prompt_id).first()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return {
        "prompt_id": prompt.prompt_id,
        "name": prompt.name,
        "domain": prompt.domain,
        "status": prompt.status,
        "owner_system_id": prompt.owner_system_id,
        "created_at": prompt.created_at.isoformat() if prompt.created_at else None,
    }


@router.get("/admin/api/prompts/{prompt_id}/versions")
def list_prompt_versions(
    prompt_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
    x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
):
    require_admin_permission(db, "prompts:read", x_admin_role)
    versions = (
        db.query(PromptVersion)
        .filter(PromptVersion.prompt_id == prompt_id)
        .order_by(PromptVersion.version.desc())
        .all()
    )
    return [
        {
            "version": v.version,
            "status": v.status,
            "approved_by": v.approved_by,
            "approved_at": v.approved_at.isoformat() if v.approved_at else None,
            "created_at": v.created_at.isoformat() if v.created_at else None,
        }
        for v in versions
    ]


@router.get("/admin/api/prompts/{prompt_id}/versions/{version}/allowlist")
def list_prompt_allowlist(
    prompt_id: str,
    version: int,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
    x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
):
    require_admin_permission(db, "prompts:read", x_admin_role)
    entries = (
        db.query(PromptAllowlist)
        .filter(
            PromptAllowlist.prompt_id == prompt_id, PromptAllowlist.version == version
        )
        .order_by(PromptAllowlist.system_id.asc())
        .all()
    )
    return [
        {
            "system_id": e.system_id,
            "module": e.module,
            "allowed": bool(e.allowed),
        }
        for e in entries
    ]


@router.get("/admin/api/prompts/{prompt_id}/versions/{version}/rules")
def list_prompt_rules(
    prompt_id: str,
    version: int,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
    x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
):
    require_admin_permission(db, "prompts:read", x_admin_role)
    rows = (
        db.query(PromptRaiRule, RaiRule)
        .join(RaiRule, RaiRule.rule_id == PromptRaiRule.rule_id)
        .filter(PromptRaiRule.prompt_id == prompt_id, PromptRaiRule.version == version)
        .all()
    )
    return [
        {
            "rule_id": rule.rule_id,
            "name": rule.name,
            "type": rule.type,
            "severity": rule.severity,
            "action": rule.action,
            "enabled": bool(binding.enabled),
        }
        for binding, rule in rows
    ]


@router.get("/admin/api/rai-rules")
def list_rai_rules(
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
    x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
):
    require_admin_permission(db, "rules:read", x_admin_role)
    rules = db.query(RaiRule).order_by(RaiRule.created_at.desc()).limit(500).all()
    return [
        {
            "rule_id": r.rule_id,
            "name": r.name,
            "type": r.type,
            "severity": r.severity,
            "action": r.action,
            "active": bool(r.active),
        }
        for r in rules
    ]


@router.get("/admin/api/audit-logs")
def list_audit_logs(
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
    x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
):
    require_admin_permission(db, "audit:read", x_admin_role)
    logs = db.query(AdminAudit).order_by(AdminAudit.created_at.desc()).limit(500).all()
    return [
        {
            "trace_id": log.trace_id,
            "actor": log.actor_user_id,
            "action": log.action,
            "resource": log.target,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]


@router.get("/admin/api/feature-flags")
def list_feature_flags(_: None = Depends(require_admin)):
    return [
        {"key": "ENABLE_CACHE", "enabled": bool(settings.enable_cache)},
        {"key": "ENABLE_CASES", "enabled": bool(settings.enable_cases)},
        {"key": "ENABLE_RAG", "enabled": bool(settings.enable_rag)},
        {"key": "ENABLE_JUDGE", "enabled": bool(settings.enable_judge)},
        {"key": "ENABLE_XAI", "enabled": bool(settings.enable_xai)},
        {"key": "ENABLE_ETHICS_EVAL", "enabled": bool(settings.enable_ethics_eval)},
    ]


@router.get("/admin/api/compliance-reports")
def list_compliance_reports(
    doc_id: Optional[str] = Query(default=None),
    _: None = Depends(require_admin),
    x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
    db: Session = Depends(get_db),
):
    require_admin_permission(db, "reports:read", x_admin_role)
    reports = list(_compliance_report_store.values())
    if doc_id:
        reports = [report for report in reports if report.get("doc_id") == doc_id]
    reports.sort(key=lambda item: item.get("generated_at", ""), reverse=True)
    return [
        {
            "report_id": report["report_id"],
            "doc_id": report["doc_id"],
            "title": report["title"],
            "report_type": report["report_type"],
            "generated_at": report["generated_at"],
            "period": report["period"],
            "status": report["status"],
            "compliance_score": report["summary"]["compliance_score"],
        }
        for report in reports
    ]


@router.post("/admin/api/compliance-reports/generate")
def generate_compliance_report(
    payload: GenerateComplianceReportRequest,
    _: None = Depends(require_admin),
    x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
    db: Session = Depends(get_db),
):
    require_admin_permission(db, "reports:read", x_admin_role)
    report = _build_compliance_report(
        db, payload.doc_id, payload.start_at, payload.end_at
    )
    _compliance_report_store[report["report_id"]] = report
    return report


@router.get("/admin/api/compliance-reports/{report_id}")
def get_compliance_report(
    report_id: str,
    _: None = Depends(require_admin),
    x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
    db: Session = Depends(get_db),
):
    require_admin_permission(db, "reports:read", x_admin_role)
    report = _compliance_report_store.get(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@router.get("/admin/api/compliance-reports/{report_id}/download")
def download_compliance_report(
    report_id: str,
    format: str = Query(default="json"),
    _: None = Depends(require_admin),
    x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
    db: Session = Depends(get_db),
):
    require_admin_permission(db, "reports:read", x_admin_role)
    report = _compliance_report_store.get(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    if format.lower() == "json":
        return report

    if format.lower() == "csv":
        lines = [
            "obligation_id,section_ref,topic,constraint_action,status,controls,covered_controls",
        ]
        for obligation in report.get("obligations", []):
            controls = "|".join(obligation.get("controls", []))
            covered = "|".join(obligation.get("covered_controls", []))
            row = [
                obligation.get("obligation_id", ""),
                obligation.get("section_ref", ""),
                obligation.get("topic", ""),
                obligation.get("constraint_action", ""),
                obligation.get("status", ""),
                controls,
                covered,
            ]
            escaped = ['"' + str(value).replace('"', '""') + '"' for value in row]
            lines.append(",".join(escaped))

        csv_payload = "\n".join(lines)
        filename = f"{report_id}.csv"
        return Response(
            content=csv_payload,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    raise HTTPException(status_code=400, detail="Unsupported format. Use json or csv.")


@router.get("/admin/api/provider-settings")
def get_provider_settings(
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
    x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
):
    require_admin_permission(db, "settings:read", x_admin_role)
    # Load persisted settings first so UI reflects DB truth.
    load_provider_settings_into_runtime(db, bootstrap_from_runtime=True)
    return _provider_settings_payload()


@router.put("/admin/api/provider-settings")
def update_provider_settings(
    payload: ProviderSettingsUpdateRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
    x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
):
    actor_role = require_admin_permission(db, "settings:write", x_admin_role)
    trace_id = generate_trace_id()

    updates = {k: v for k, v in payload.model_dump().items() if v is not None}

    persist_provider_settings(db, updates)
    db.commit()

    # Keep process environment in sync for providers that read env fallbacks.
    env_key_map = {
        "llm_provider_url": "LLM_PROVIDER_URL",
        "llm_provider_api_key": "LLM_PROVIDER_API_KEY",
        "azure_openai_api_key": "AZURE_OPENAI_API_KEY",
        "azure_openai_endpoint": "AZURE_OPENAI_ENDPOINT",
        "azure_openai_deployment": "AZURE_OPENAI_DEPLOYMENT",
        "azure_openai_api_version": "AZURE_OPENAI_API_VERSION",
        "anthropic_api_key": "ANTHROPIC_API_KEY",
        "aws_region": "AWS_REGION",
        "gcp_project_id": "GCP_PROJECT_ID",
        "gcp_location": "GCP_LOCATION",
        "ollama_endpoint": "OLLAMA_ENDPOINT",
    }
    for key, env_key in env_key_map.items():
        if key in updates:
            os.environ[env_key] = str(updates[key])

    log_admin_audit(
        trace_id=trace_id,
        actor_user_id="admin",
        actor_role=actor_role,
        action="provider_settings.update",
        target={
            "updated_keys": list(updates.keys()),
        },
        auth_strength="admin_token",
    )

    return {"ok": True, "settings": _provider_settings_payload()}


@router.post("/admin/api/provider-settings/seed")
def seed_provider_settings(
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
    x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
):
    require_admin_permission(db, "settings:write", x_admin_role)
    loaded = load_provider_settings_into_runtime(db, bootstrap_from_runtime=True)
    return {
        "ok": True,
        "seeded_keys": sorted(list(loaded.keys())),
        "settings": _provider_settings_payload(),
    }


@router.get("/admin/api/providers/status")
def get_provider_status(
    active_only: bool = Query(False),
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
    x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
):
    require_admin_permission(db, "settings:read", x_admin_role)
    primary_provider = getattr(settings, "llm_provider", "openai")
    providers = [
        {
            "provider": "openai",
            "configured": bool(settings.llm_provider_api_key),
            "default_model": settings.llm_provider_model,
            "notes": "Requires LLM_PROVIDER_API_KEY",
            "is_primary": primary_provider == "openai",
        },
        {
            "provider": "azure_openai",
            "configured": bool(
                settings.azure_openai_api_key
                and settings.azure_openai_endpoint
                and settings.azure_openai_deployment
            ),
            "default_model": settings.azure_openai_deployment,
            "notes": "Requires AZURE_OPENAI_API_KEY/ENDPOINT/DEPLOYMENT",
            "is_primary": primary_provider == "azure_openai",
        },
        {
            "provider": "anthropic",
            "configured": bool(settings.anthropic_api_key),
            "default_model": "claude-3-5-sonnet-20241022",
            "notes": "Requires ANTHROPIC_API_KEY",
            "is_primary": primary_provider == "anthropic",
        },
        {
            "provider": "bedrock",
            "configured": bool(settings.aws_region),
            "default_model": "anthropic.claude-3-sonnet-20240229-v1:0",
            "notes": "Requires AWS creds + boto3",
            "sdk_installed": importlib.util.find_spec("boto3") is not None,
            "is_primary": primary_provider == "bedrock",
        },
        {
            "provider": "vertex",
            "configured": bool(settings.gcp_project_id),
            "default_model": "gemini-1.5-pro-001",
            "notes": "Gemini is available via Vertex provider",
            "sdk_installed": importlib.util.find_spec("google.cloud.aiplatform")
            is not None,
            "is_primary": primary_provider == "vertex",
        },
        {
            "provider": "ollama",
            "configured": bool(settings.ollama_endpoint),
            "default_model": "llama3",
            "notes": "Requires running Ollama server",
            "is_primary": primary_provider == "ollama",
        },
    ]
    if primary_provider == "auto":
        providers = [{**provider, "is_primary": False} for provider in providers]
    if active_only:
        providers = [provider for provider in providers if provider.get("configured")]
    return providers


@router.get("/admin/api/providers/models")
async def get_provider_models(
    provider: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
    x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
):
    require_admin_permission(db, "settings:read", x_admin_role)
    from rai_gateway.services.llm_providers import list_provider_models

    payload = await list_provider_models(provider)
    return {
        "provider": provider,
        "models": payload.get("models", []),
        "source": payload.get("source", "fallback"),
    }


@router.post("/admin/api/providers/test")
async def test_provider(
    payload: ProviderTestRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
    x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
):
    require_admin_permission(db, "settings:write", x_admin_role)
    from rai_gateway.services.llm_providers import get_llm_provider

    model = payload.model or settings.llm_provider_model
    provider = get_llm_provider(payload.provider)
    try:
        result = await provider.generate(
            prompt="Say hello to {name} in one short sentence.",
            variables={"name": "RAI Gateway"},
            model=model,
            max_tokens=60,
            temperature=0.2,
        )
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code if exc.response else 502
        detail = {
            "error": "provider_test_failed",
            "provider": payload.provider,
            "model": model,
            "status_code": status,
            "message": str(exc),
        }
        raise HTTPException(status_code=status, detail=detail) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "error": "provider_test_failed",
                "provider": payload.provider,
                "model": model,
                "message": str(exc),
            },
        ) from exc

    return {
        "ok": True,
        "provider": result.get("provider", payload.provider),
        "model": result.get("model", model),
        "usage": result.get("usage", {}),
        "sample_output": result.get("output", "")[:200],
    }


@router.get("/admin/api/systems", deprecated=True)
def list_systems(
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
    x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
):
    """List governed AI systems from the WP1 registry, enriched with audit activity.

    Deprecated: prefer ``GET /v1/ai-systems`` for authoritative registry access.
    Audit data may include observed-but-unregistered system identifiers separately.
    """
    require_admin_permission(db, "executions:read", x_admin_role)

    registered = db.query(AISystem).order_by(AISystem.name.asc()).all()
    registered_keys = {system.system_key for system in registered}

    execution_counts = dict(
        db.query(ExecutionAudit.system_id, func.count(ExecutionAudit.execution_id))
        .group_by(ExecutionAudit.system_id)
        .all()
    )

    systems: list[dict[str, Any]] = [
        {
            "system_id": system.system_key,
            "name": system.name,
            "owner": system.owner_id or "",
            "status": system.status,
            "registered": True,
            "execution_count": execution_counts.get(system.system_key, 0),
        }
        for system in registered
    ]

    for system_id, count in sorted(execution_counts.items()):
        if not system_id or system_id in registered_keys:
            continue
        systems.append(
            {
                "system_id": system_id,
                "name": f"Observed (Unregistered): {system_id}",
                "owner": "",
                "status": "OBSERVED_UNREGISTERED",
                "registered": False,
                "execution_count": count,
            }
        )

    return systems


# ==================== Policies ====================


@router.get("/admin/api/policies")
def list_policies(
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
    x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
):
    require_admin_permission(db, "policies:read", x_admin_role)
    """List all policy documents"""
    policies = db.query(PolicyDocument).order_by(PolicyDocument.created_at.desc()).all()
    return [
        {
            "doc_id": p.doc_id,
            "country": p.country,
            "authority": p.authority,
            "doc_type": p.doc_type,
            "version": p.version,
            "effective_date": p.effective_date.isoformat()
            if p.effective_date
            else None,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in policies
    ]


@router.get("/admin/api/policies/{doc_id}")
def get_policy_detail(
    doc_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
    x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
):
    require_admin_permission(db, "policies:read", x_admin_role)
    """Get policy document details"""
    policy = db.query(PolicyDocument).filter(PolicyDocument.doc_id == doc_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    return {
        "doc_id": policy.doc_id,
        "country": policy.country,
        "authority": policy.authority,
        "doc_type": policy.doc_type,
        "version": policy.version,
        "effective_date": policy.effective_date.isoformat()
        if policy.effective_date
        else None,
        "content_ref": policy.content_ref,
        "created_at": policy.created_at.isoformat() if policy.created_at else None,
    }


@router.post("/admin/api/policies")
def upload_policy(
    data: dict,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
    x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
):
    require_admin_permission(db, "policies:write", x_admin_role)
    """Upload a new policy document"""
    # Validate required fields
    required_fields = ["doc_id", "country", "authority", "doc_type"]
    for field in required_fields:
        if field not in data:
            raise HTTPException(
                status_code=400, detail=f"Missing required field: {field}"
            )

    # Check if policy already exists
    existing = (
        db.query(PolicyDocument).filter(PolicyDocument.doc_id == data["doc_id"]).first()
    )
    if existing:
        raise HTTPException(
            status_code=400, detail="Policy with this doc_id already exists"
        )

    # Create policy
    policy = PolicyDocument(
        doc_id=data["doc_id"],
        country=data["country"],
        authority=data["authority"],
        doc_type=data["doc_type"],
        version=data.get("version"),
        effective_date=data.get("effective_date"),
        content_ref=data.get("content_ref"),
    )
    db.add(policy)
    db.commit()
    db.refresh(policy)

    return {
        "doc_id": policy.doc_id,
        "country": policy.country,
        "authority": policy.authority,
        "doc_type": policy.doc_type,
        "version": policy.version,
        "effective_date": policy.effective_date.isoformat()
        if policy.effective_date
        else None,
        "content_ref": policy.content_ref,
        "created_at": policy.created_at.isoformat() if policy.created_at else None,
    }


@router.get("/admin/api/policies/{doc_id}/obligations")
def get_policy_obligations(
    doc_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
    x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
):
    require_admin_permission(db, "policies:read", x_admin_role)
    """Get all obligations for a policy document"""
    # Check if policy exists
    policy = db.query(PolicyDocument).filter(PolicyDocument.doc_id == doc_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    obligations = (
        db.query(PolicyObligation)
        .filter(PolicyObligation.doc_id == doc_id)
        .order_by(PolicyObligation.obligation_id.asc())
        .all()
    )

    return [
        {
            "obligation_id": o.obligation_id,
            "doc_id": o.doc_id,
            "section_ref": o.section_ref,
        }
        for o in obligations
    ]


# ==================== RAG Domains ====================


@router.get("/admin/api/rag-domains")
def list_rag_domains(
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
    x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
):
    require_admin_permission(db, "rag:read", x_admin_role)
    """List all RAG domains"""
    domains = db.query(RagDomain).order_by(RagDomain.created_at.desc()).all()
    return [
        {
            "domain_id": d.domain_id,
            "name": d.name,
            "description": d.description,
            "country": d.country,
            "owner_email": d.owner_email,
            "status": d.status,
            "approval_required": d.approval_required,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in domains
    ]


@router.get("/admin/api/rag-domains/{domain_id}")
def get_rag_domain(
    domain_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
    x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
):
    require_admin_permission(db, "rag:read", x_admin_role)
    """Get RAG domain details"""
    domain = db.query(RagDomain).filter(RagDomain.domain_id == domain_id).first()
    if not domain:
        raise HTTPException(status_code=404, detail="RAG domain not found")

    # Get sources for this domain
    sources = db.query(RagSource).filter(RagSource.domain_id == domain_id).all()

    return {
        "domain_id": domain.domain_id,
        "name": domain.name,
        "description": domain.description,
        "country": domain.country,
        "owner_email": domain.owner_email,
        "status": domain.status,
        "approval_required": domain.approval_required,
        "sources": [
            {
                "source_id": s.source_id,
                "source_name": s.source_name,
                "source_type": s.source_type,
                "access_url": s.access_url,
                "leakage_risk_level": s.leakage_risk_level,
                "status": s.status,
            }
            for s in sources
        ],
        "created_at": domain.created_at.isoformat() if domain.created_at else None,
    }


@router.post("/admin/api/rag-domains")
def create_rag_domain(
    data: dict,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
    x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
):
    require_admin_permission(db, "rag:write", x_admin_role)
    """Create a new RAG domain"""
    required_fields = ["domain_id", "name"]
    for field in required_fields:
        if field not in data:
            raise HTTPException(
                status_code=400, detail=f"Missing required field: {field}"
            )

    existing = (
        db.query(RagDomain).filter(RagDomain.domain_id == data["domain_id"]).first()
    )
    if existing:
        raise HTTPException(
            status_code=400, detail="Domain with this ID already exists"
        )

    domain = RagDomain(
        domain_id=data["domain_id"],
        name=data["name"],
        description=data.get("description"),
        country=data.get("country"),
        owner_email=data.get("owner_email"),
        approval_required=data.get("approval_required", True),
    )
    db.add(domain)
    db.commit()
    db.refresh(domain)

    return {
        "domain_id": domain.domain_id,
        "name": domain.name,
        "description": domain.description,
        "country": domain.country,
        "status": domain.status,
        "approval_required": domain.approval_required,
        "created_at": domain.created_at.isoformat() if domain.created_at else None,
    }


@router.post("/admin/api/rag-domains/{domain_id}/sources")
def add_rag_source(
    domain_id: str,
    data: dict,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
    x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
):
    require_admin_permission(db, "rag:write", x_admin_role)
    """Add a source to a RAG domain"""
    domain = db.query(RagDomain).filter(RagDomain.domain_id == domain_id).first()
    if not domain:
        raise HTTPException(status_code=404, detail="RAG domain not found")

    required_fields = ["source_id", "source_name"]
    for field in required_fields:
        if field not in data:
            raise HTTPException(
                status_code=400, detail=f"Missing required field: {field}"
            )

    source = RagSource(
        source_id=data["source_id"],
        domain_id=domain_id,
        source_name=data["source_name"],
        source_type=data.get("source_type"),
        access_url=data.get("access_url"),
        description=data.get("description"),
        leakage_risk_level=data.get("leakage_risk_level", "low"),
        redaction_rules=data.get("redaction_rules"),
    )
    db.add(source)
    db.commit()
    db.refresh(source)

    return {
        "source_id": source.source_id,
        "domain_id": source.domain_id,
        "source_name": source.source_name,
        "source_type": source.source_type,
        "status": source.status,
        "created_at": source.created_at.isoformat() if source.created_at else None,
    }


@router.get("/admin/api/rag-domains/{domain_id}/sources")
def list_rag_sources(
    domain_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
    x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
):
    require_admin_permission(db, "rag:read", x_admin_role)
    """List sources for a RAG domain"""
    domain = db.query(RagDomain).filter(RagDomain.domain_id == domain_id).first()
    if not domain:
        raise HTTPException(status_code=404, detail="RAG domain not found")

    sources = db.query(RagSource).filter(RagSource.domain_id == domain_id).all()

    return [
        {
            "source_id": s.source_id,
            "source_name": s.source_name,
            "source_type": s.source_type,
            "access_url": s.access_url,
            "description": s.description,
            "leakage_risk_level": s.leakage_risk_level,
            "status": s.status,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in sources
    ]


@router.post("/admin/api/rag-domains/{domain_id}/approve")
def approve_rag_domain(
    domain_id: str,
    data: dict,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
    __: None = Depends(require_step_up),
    x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
):
    require_admin_permission(db, "rag:approve", x_admin_role)
    """Approve a RAG domain (requires step-up verification in real scenario)"""
    domain = db.query(RagDomain).filter(RagDomain.domain_id == domain_id).first()
    if not domain:
        raise HTTPException(status_code=404, detail="RAG domain not found")

    domain.status = "active"
    db.commit()

    return {
        "domain_id": domain.domain_id,
        "status": domain.status,
        "message": "Domain approved successfully",
    }


# ==================== Cases (Human Review) ====================


@router.get("/admin/api/cases")
def list_cases(
    status: str | None = None,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
    x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
):
    require_admin_permission(db, "cases:review", x_admin_role)
    """List cases for human review"""
    query = db.query(Case)
    if status:
        query = query.filter(Case.status == status)

    cases = query.order_by(Case.created_at.desc()).limit(100).all()

    return [
        {
            "case_id": str(c.case_id),
            "execution_id": str(c.execution_id),
            "status": c.status,
            "owner": c.owner,
            "reason_codes": c.reason_codes or [],
            "resolution": c.resolution,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        }
        for c in cases
    ]


@router.get("/admin/api/cases/{case_id}")
def get_case(
    case_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
    x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
):
    require_admin_permission(db, "cases:review", x_admin_role)
    """Get case details"""
    try:
        from uuid import UUID

        case_uuid = UUID(case_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid case ID format")

    case = db.query(Case).filter(Case.case_id == case_uuid).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    # Get associated execution
    execution = (
        db.query(ExecutionAudit)
        .filter(ExecutionAudit.execution_id == case.execution_id)
        .first()
    )

    return {
        "case_id": str(case.case_id),
        "execution_id": str(case.execution_id),
        "execution": {
            "system_id": execution.system_id if execution else None,
            "module": execution.module if execution else None,
            "decision": execution.decision if execution else None,
        }
        if execution
        else None,
        "status": case.status,
        "owner": case.owner,
        "reason_codes": case.reason_codes or [],
        "actions": case.actions or {},
        "resolution": case.resolution,
        "created_at": case.created_at.isoformat() if case.created_at else None,
        "updated_at": case.updated_at.isoformat() if case.updated_at else None,
    }


@router.post("/admin/api/cases/{case_id}/resolve")
def resolve_case(
    case_id: str,
    data: dict,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
    __: None = Depends(require_step_up),
    x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
):
    require_admin_permission(db, "cases:resolve", x_admin_role)
    """Resolve a case (requires step-up verification in production)"""
    try:
        from uuid import UUID

        case_uuid = UUID(case_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid case ID format")

    case = db.query(Case).filter(Case.case_id == case_uuid).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    case.status = data.get("status", "resolved")
    case.resolution = data.get("resolution")
    case.owner = data.get("owner")

    db.commit()

    return {
        "case_id": str(case.case_id),
        "status": case.status,
        "resolution": case.resolution,
        "message": "Case resolved successfully",
    }
