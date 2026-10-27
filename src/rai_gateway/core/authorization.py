"""Membership authorization for the single-organization community edition.

Permissions come from ACTIVE OrganizationMembership records, never from a
browser-selected role header or an organization id.

Standard dependencies (prefer these for all new routes):

- ``require_user`` — authenticate a human Principal
- ``require_tenant`` — resolve TenantContext from the caller's memberships
- ``require_organization_member`` — same membership resolution
- ``require_permission(permission)`` — membership permission gate
- ``require_any_permission(*permissions)`` — any-of permission gate
- ``require_tenant_role(*roles)`` — governance role gate
- ``require_platform_permission(permission)`` — platform UserRole gate

Rules:

- Product API → require_tenant / require_permission
- Admin console API → require_platform_permission
- Runtime API → runtime credential/OIDC authority

Legacy ``require_admin_permission`` in admin_console is fail-closed platform RBAC
only. Do not use it for new product routes.
"""

from __future__ import annotations

from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Callable, Optional
from uuid import UUID

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from rai_gateway.core.database import get_db
from rai_gateway.core.errors import ErrorCode, RaiException
from rai_gateway.core.principal import Principal
from rai_gateway.core.tenant_context import TenantContext
from rai_gateway.governance.domain import MembershipStatus
from rai_gateway.models.database import RolePermission, UserRole
from rai_gateway.models.governance import OrganizationMembership

# Governance membership roles → RBAC RoleDefinition.role_id
TENANT_ROLE_TO_RBAC_ROLE: dict[str, str] = {
    "ORGANIZATION_ADMIN": "organization_admin",
    "RAI_OFFICER": "rai_officer",
    "RISK_COMPLIANCE_REVIEWER": "risk_officer",
    "BUSINESS_APPROVER": "business_approver",
    "AUDITOR": "auditor",
    "INCIDENT_MANAGER": "incident_manager",
    "AI_SYSTEM_OWNER": "ai_system_owner",
    "BUSINESS_OWNER": "business_owner",
    "TECHNICAL_OWNER": "technical_owner",
}

PLATFORM_ROLES: frozenset[str] = frozenset(
    {"platform_admin", "platform_support", "admin"}
)

_tenant_context_ctx: ContextVar[Optional[TenantContext]] = ContextVar(
    "tenant_context_ctx", default=None
)
_principal_ctx: ContextVar[Optional[Principal]] = ContextVar(
    "principal_ctx", default=None
)


def get_current_tenant() -> Optional[TenantContext]:
    tenant = _tenant_context_ctx.get()
    if tenant is not None:
        return tenant
    from rai_gateway.services.admin_console import _current_request

    request = _current_request.get()
    if request is None:
        return None
    return getattr(request.state, "rai_tenant_context", None)


def get_current_principal() -> Optional[Principal]:
    principal = _principal_ctx.get()
    if principal is not None:
        return principal
    from rai_gateway.services.admin_console import _current_request

    request = _current_request.get()
    if request is None:
        return None
    return getattr(request.state, "rai_principal", None)


def _store_principal(request: Request | None, principal: Principal) -> Principal:
    _principal_ctx.set(principal)
    if request is not None:
        request.state.rai_principal = principal
    return principal


def _store_tenant(request: Request | None, tenant: TenantContext) -> TenantContext:
    _tenant_context_ctx.set(tenant)
    if request is not None:
        request.state.rai_tenant_context = tenant
    return tenant


def map_tenant_roles_to_rbac(tenant_roles: list[str] | tuple[str, ...]) -> list[str]:
    """Map governance role names to RBAC role IDs (deduplicated, ordered)."""
    seen: set[str] = set()
    mapped: list[str] = []
    for role in tenant_roles:
        rbac_role = TENANT_ROLE_TO_RBAC_ROLE.get(role)
        if rbac_role and rbac_role not in seen:
            seen.add(rbac_role)
            mapped.append(rbac_role)
    return mapped


def load_permissions_for_roles(db: Session, role_ids: list[str]) -> frozenset[str]:
    """Load the union of RolePermission rows for the given RBAC role IDs."""
    if not role_ids:
        return frozenset()

    # Ensure catalog roles exist (idempotent seed).
    from rai_gateway.services.admin_console import _ensure_default_rbac_seed

    _ensure_default_rbac_seed(db)

    rows = db.query(RolePermission).filter(RolePermission.role_id.in_(role_ids)).all()
    return frozenset(row.permission for row in rows)


def load_platform_roles(db: Session, user_id: str) -> tuple[str, ...]:
    rows = db.query(UserRole).filter(UserRole.user_id == user_id).all()
    return tuple(sorted({row.role_id for row in rows}))


def resolve_tenant_context(db: Session, principal: Principal) -> TenantContext:
    """Resolve access from the caller's active memberships.

    Platform roles do not invent product permissions. The bootstrap admin
    receives memberships at startup.

    Raises RaiException when the user has no active membership.
    """
    now = datetime.now(timezone.utc)
    memberships = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.user_id == principal.user_id,
            OrganizationMembership.status == MembershipStatus.ACTIVE.value,
        )
        .all()
    )

    active: list[OrganizationMembership] = []
    for membership in memberships:
        if _membership_currently_valid(membership, now=now):
            active.append(membership)

    if not active:
        raise RaiException(
            error_code=ErrorCode.NOT_ALLOWED,
            message="No active membership",
        )

    tenant_roles = tuple(sorted({m.role for m in active}))
    membership_ids = tuple(m.id for m in active)
    rbac_roles = map_tenant_roles_to_rbac(tenant_roles)
    permissions = load_permissions_for_roles(db, rbac_roles)

    return TenantContext(
        principal=principal,
        membership_ids=membership_ids,
        roles=tenant_roles,
        permissions=permissions,
    )


def require_user(
    request: Request,
    x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
) -> Principal:
    """Authenticate a human principal (no organization context yet).

    Accepts SaaS ``user_session`` JWTs and legacy ``admin_session`` JWTs.
    Platform roles are always reloaded from ``UserRole`` (never trusted from JWT).

    Authentication sources (in priority order):
    1. Cookie: rai_access (when auth_set_cookies=true)
    2. Header: Authorization: Bearer <token>
    3. Header: X-Admin-Token (legacy, production-unsafe)
    """
    from jose import JWTError, jwt

    from rai_gateway.auth.tokens import USER_SESSION_TYPE, decode_user_access_token
    from rai_gateway.core.auth import decode_admin_access_token
    from rai_gateway.core.config import settings
    from rai_gateway.models.database import UserAccount
    from rai_gateway.services.admin_console import (
        _ensure_bootstrap_admin,
        _extract_bearer_token,
    )

    _ensure_bootstrap_admin(db)

    # Phase 20: Extract access token from cookie if cookie auth is enabled
    bearer_token = None
    if settings.auth_set_cookies:
        cookie_token = request.cookies.get(settings.auth_access_cookie_name)
        if cookie_token:
            bearer_token = cookie_token

    # Fallback to Authorization header if no cookie or cookie auth disabled
    if not bearer_token:
        bearer_token = _extract_bearer_token(authorization)

    if bearer_token:
        # Peek at token type without fully trusting claims yet.
        token_type = None
        try:
            unverified = jwt.get_unverified_claims(bearer_token)
            token_type = unverified.get("type")
        except JWTError:
            token_type = None

        if token_type == USER_SESSION_TYPE:
            token_principal = decode_user_access_token(bearer_token)
            user = (
                db.query(UserAccount)
                .filter(UserAccount.user_id == token_principal.user_id)
                .first()
            )
            if not user or user.status != "active":
                raise RaiException(
                    error_code=ErrorCode.UNAUTHENTICATED,
                    message="User is not active",
                )
            from rai_gateway.auth.service import require_active_session

            require_active_session(db, token_principal.session_id, user.user_id)
            platform_roles = load_platform_roles(db, user.user_id)
            principal = Principal(
                user_id=user.user_id,
                email=user.email,
                session_id=token_principal.session_id,
                platform_roles=platform_roles,
                authentication_assurance=token_principal.authentication_assurance,
                acr=token_principal.acr,
                amr=token_principal.amr,
                auth_time=token_principal.auth_time,
            )
            return _store_principal(request, principal)

        # Legacy admin_session path (compat during migration).
        token_identity = decode_admin_access_token(bearer_token)
        from rai_gateway.core.auth import get_admin_identity_by_email

        from_db = get_admin_identity_by_email(db, token_identity.email)
        if not from_db:
            raise RaiException(
                error_code=ErrorCode.UNAUTHENTICATED,
                message="Invalid admin session token",
            )
        platform_roles = load_platform_roles(db, from_db.user_id)
        principal = Principal(
            user_id=from_db.user_id,
            email=from_db.email,
            session_id=None,
            platform_roles=platform_roles,
            authentication_assurance=token_identity.authentication_assurance,
            acr=token_identity.acr,
            amr=tuple(token_identity.amr or ()),
            auth_time=token_identity.auth_time,
        )
        return _store_principal(request, principal)

    if settings.admin_token and x_admin_token and x_admin_token == settings.admin_token:
        principal = Principal(
            user_id="admin",
            email=settings.admin_bootstrap_email,
            session_id=None,
            platform_roles=("admin",),
        )
        return _store_principal(request, principal)

    raise RaiException(
        error_code=ErrorCode.UNAUTHENTICATED,
        message="Authentication required",
    )


def require_tenant(
    request: Request,
    principal: Principal = Depends(require_user),
    db: Session = Depends(get_db),
) -> TenantContext:
    """Resolve the caller's memberships into a TenantContext."""
    tenant = resolve_tenant_context(db, principal)
    return _store_tenant(request, tenant)


def require_organization_member(
    request: Request,
    principal: Principal = Depends(require_user),
    db: Session = Depends(get_db),
) -> TenantContext:
    """Resolve product access from a real membership.

    Platform roles do not grant product access by themselves.
    """
    tenant = resolve_tenant_context(db, principal)
    return _store_tenant(request, tenant)


def require_permission(permission: str) -> Callable[..., TenantContext]:
    """FastAPI dependency factory: require a tenant permission."""

    def _dependency(
        tenant: TenantContext = Depends(require_tenant),
        db: Session = Depends(get_db),
    ) -> TenantContext:
        _enforce_email_verified_for_mutation(db, tenant.principal, permission)
        if not tenant.has_permission(permission):
            raise RaiException(
                error_code=ErrorCode.NOT_ALLOWED,
                message="Missing required permission",
                details={"required_permission": permission},
            )
        return tenant

    return _dependency


def require_any_permission(*permissions: str) -> Callable[..., TenantContext]:
    """FastAPI dependency factory: require any of the given permissions."""

    def _dependency(
        tenant: TenantContext = Depends(require_tenant),
        db: Session = Depends(get_db),
    ) -> TenantContext:
        for permission in permissions:
            _enforce_email_verified_for_mutation(db, tenant.principal, permission)
        if not tenant.has_any_permission(*permissions):
            raise RaiException(
                error_code=ErrorCode.NOT_ALLOWED,
                message="Missing required permission",
                details={"required_permissions": list(permissions)},
            )
        return tenant

    return _dependency


def _is_mutating_permission(permission: str) -> bool:
    if permission.endswith(":read") or permission in {
        "audit:read",
        "reports:read",
        "finops:export",
    }:
        return False
    return True


def _enforce_email_verified_for_mutation(
    db: Session, principal: Principal, permission: str
) -> None:
    """Privileged tenant mutations require a verified email (login still allowed)."""
    if not _is_mutating_permission(permission):
        return
    # Platform operators are not gated by customer email verification.
    if principal.has_platform_role("admin") or principal.has_platform_role(
        "platform_admin"
    ):
        return
    from rai_gateway.models.database import UserAccount

    user = (
        db.query(UserAccount).filter(UserAccount.user_id == principal.user_id).first()
    )
    if user is None or user.email_verified_at is None:
        raise RaiException(
            error_code=ErrorCode.NOT_ALLOWED,
            message="Email verification required for this action",
            details={"required_permission": permission},
        )


def require_tenant_role(*roles: str) -> Callable[..., TenantContext]:
    """FastAPI dependency factory: require one of the given governance roles."""

    def _dependency(
        tenant: TenantContext = Depends(require_tenant),
    ) -> TenantContext:
        if not tenant.has_any_role(*roles):
            raise RaiException(
                error_code=ErrorCode.NOT_ALLOWED,
                message="Missing required tenant role",
                details={"required_roles": list(roles)},
            )
        return tenant

    return _dependency


def require_platform_permission(permission: str) -> Callable[..., Principal]:
    """FastAPI dependency factory: require a platform-level permission.

    Platform authority comes only from global UserRole assignments
    (platform_admin / platform_support / legacy admin), never from
    OrganizationMembership.
    """

    def _dependency(
        principal: Principal = Depends(require_user),
        db: Session = Depends(get_db),
    ) -> Principal:
        if not principal.platform_roles:
            raise RaiException(
                error_code=ErrorCode.NOT_ALLOWED,
                message="Platform permission required",
                details={"required_permission": permission},
            )
        permissions = load_permissions_for_roles(db, list(principal.platform_roles))
        if "*" not in permissions and permission not in permissions:
            raise RaiException(
                error_code=ErrorCode.NOT_ALLOWED,
                message="Platform permission required",
                details={"required_permission": permission},
            )
        return principal

    return _dependency


def _membership_currently_valid(
    membership: OrganizationMembership, *, now: datetime | None = None
) -> bool:
    """Return True when membership is inside its valid_from / valid_until window."""
    now = now or datetime.now(timezone.utc)
    valid_from = membership.valid_from
    if valid_from is not None:
        if valid_from.tzinfo is None:
            valid_from = valid_from.replace(tzinfo=timezone.utc)
        if valid_from > now:
            return False
    valid_until = membership.valid_until
    if valid_until is not None:
        if valid_until.tzinfo is None:
            valid_until = valid_until.replace(tzinfo=timezone.utc)
        if valid_until <= now:
            return False
    return True


def resolve_acting_membership(
    db: Session,
    tenant: TenantContext,
    acting_membership_id: UUID,
    *,
    allowed_roles: tuple[str, ...] | None = None,
) -> OrganizationMembership:
    """Validate an acting membership for SoD / approval workflows."""
    membership = (
        db.query(OrganizationMembership)
        .filter(OrganizationMembership.id == acting_membership_id)
        .first()
    )
    if (
        membership is None
        or membership.user_id != tenant.user_id
        or membership.status != MembershipStatus.ACTIVE.value
        or membership.id not in tenant.membership_ids
        or not _membership_currently_valid(membership)
    ):
        raise RaiException(
            error_code=ErrorCode.NOT_ALLOWED,
            message="Acting membership is not valid for this action",
            details={"acting_membership_id": str(acting_membership_id)},
        )

    if allowed_roles is not None and membership.role not in allowed_roles:
        raise RaiException(
            error_code=ErrorCode.NOT_ALLOWED,
            message="Acting membership role is not allowed for this action",
            details={
                "acting_membership_id": str(acting_membership_id),
                "role": membership.role,
                "allowed_roles": list(allowed_roles),
            },
        )

    return membership
