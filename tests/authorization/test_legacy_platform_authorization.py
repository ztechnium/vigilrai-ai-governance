"""Phase 0 regressions: legacy platform authorization must fail closed."""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from rai_gateway.auth.passwords import hash_password
from rai_gateway.core.auth import AdminIdentity, create_admin_access_token
from rai_gateway.core.config import settings
from rai_gateway.core.database import get_db
from rai_gateway.governance.domain import GovernanceRole, MembershipStatus
from rai_gateway.main import app
from rai_gateway.models.database import AdminCredential, UserAccount, UserRole
from rai_gateway.models.governance import OrganizationMembership
from rai_gateway.services.admin_console import (
    _ensure_default_rbac_seed,
    _normalize_role,
    require_admin_permission,
)


@pytest.fixture()
def auth_client(db_session, db_engine):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


def _seed_saas_tenant_user(db_session, *, email: str | None = None):
    _ensure_default_rbac_seed(db_session)
    suffix = uuid.uuid4().hex[:8]
    email = (email or f"tenant-{suffix}@example.com").lower()
    user_id = f"user-{suffix}"
    user = UserAccount(
        user_id=user_id,
        email=email,
        name="Tenant User",
        status="active",
    )
    db_session.add(user)
    db_session.flush()
    db_session.add(
        AdminCredential(
            email=email,
            user_id=user_id,
            password_hash=hash_password("SecurePass123!"),
            is_active=True,
        )
    )
    db_session.add(
        OrganizationMembership(
            user_id=user_id,
            role=GovernanceRole.ORGANIZATION_ADMIN.value,
            status=MembershipStatus.ACTIVE.value,
            created_by=user_id,
        )
    )
    db_session.commit()
    return {"email": email, "password": "SecurePass123!", "user_id": user_id}


def _seed_platform_admin(db_session, *, role_id: str = "platform_admin"):
    _ensure_default_rbac_seed(db_session)
    suffix = uuid.uuid4().hex[:8]
    email = f"platform-{suffix}@example.com"
    user_id = f"platform-{suffix}"
    db_session.add(
        UserAccount(
            user_id=user_id,
            email=email,
            name="Platform Admin",
            status="active",
        )
    )
    db_session.flush()
    db_session.add(
        AdminCredential(
            email=email,
            user_id=user_id,
            password_hash=hash_password("SecurePass123!"),
            is_active=True,
        )
    )
    db_session.add(UserRole(user_id=user_id, role_id=role_id))
    db_session.commit()
    token = create_admin_access_token(email=email, user_id=user_id, roles=[role_id])
    return {
        "email": email,
        "user_id": user_id,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


def test_normalize_role_never_defaults_to_admin():
    assert _normalize_role(None) is None
    assert _normalize_role("") is None
    assert _normalize_role("   ") is None
    assert _normalize_role("platform_admin") == "platform_admin"
    assert _normalize_role("Platform Admin") == "platform_admin"


def test_require_admin_permission_without_identity_is_401(db_session):
    with pytest.raises(HTTPException) as exc:
        require_admin_permission(db_session, "registry:read", None)
    assert exc.value.status_code == 401
    assert exc.value.detail["error"] == "UNAUTHENTICATED"


def test_tenant_identity_without_platform_roles_is_403(db_session):
    identity = AdminIdentity(
        email="tenant@example.com",
        user_id="tenant-1",
        roles=[],
    )
    with pytest.raises(HTTPException) as exc:
        require_admin_permission(db_session, "registry:read", None, identity=identity)
    assert exc.value.status_code == 403
    assert exc.value.detail["error"] == "PLATFORM_PERMISSION_REQUIRED"


def test_tenant_cannot_spoof_admin_role_header(db_session):
    identity = AdminIdentity(
        email="tenant@example.com",
        user_id="tenant-1",
        roles=[],
    )
    with pytest.raises(HTTPException) as exc:
        require_admin_permission(
            db_session, "registry:read", "admin", identity=identity
        )
    assert exc.value.status_code == 403
    assert exc.value.detail["error"] == "PLATFORM_PERMISSION_REQUIRED"


def test_tenant_cannot_spoof_platform_admin_role_header(db_session):
    identity = AdminIdentity(
        email="tenant@example.com",
        user_id="tenant-1",
        roles=[],
    )
    with pytest.raises(HTTPException) as exc:
        require_admin_permission(
            db_session, "registry:read", "platform_admin", identity=identity
        )
    assert exc.value.status_code == 403
    assert exc.value.detail["error"] == "PLATFORM_PERMISSION_REQUIRED"


def test_platform_admin_allowed_without_role_header(db_session):
    identity = AdminIdentity(
        email="paul@example.com",
        user_id="paul",
        roles=["platform_admin"],
    )
    selected = require_admin_permission(
        db_session, "registry:read", None, identity=identity
    )
    assert selected == "platform_admin"


def test_platform_admin_allowed_with_matching_role_header(db_session):
    identity = AdminIdentity(
        email="paul@example.com",
        user_id="paul",
        roles=["platform_admin"],
    )
    selected = require_admin_permission(
        db_session, "registry:read", "platform_admin", identity=identity
    )
    assert selected == "platform_admin"


def test_platform_admin_denied_for_unassigned_role(db_session):
    identity = AdminIdentity(
        email="paul@example.com",
        user_id="paul",
        roles=["platform_admin"],
    )
    with pytest.raises(HTTPException) as exc:
        require_admin_permission(
            db_session, "registry:read", "auditor", identity=identity
        )
    assert exc.value.status_code == 403
    assert exc.value.detail["error"] == "ROLE_NOT_ASSIGNED"


def test_member_portfolio_access_ignores_admin_role_header(auth_client, db_session):
    """A membership can read the portfolio. X-Admin-Role does not change that."""
    tenant = _seed_saas_tenant_user(db_session)
    login = auth_client.post(
        "/v1/auth/login",
        json={"email": tenant["email"], "password": tenant["password"]},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]

    with_header = auth_client.get(
        "/v1/portfolio/summary",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Admin-Role": "admin",
        },
    )
    without_header = auth_client.get(
        "/v1/portfolio/summary",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert with_header.status_code == 200, with_header.text
    assert without_header.status_code == 200, without_header.text
    assert with_header.json()["freshness"] == without_header.json()["freshness"]


def test_platform_admin_can_access_legacy_platform_route(auth_client, db_session):
    admin = _seed_platform_admin(db_session, role_id="platform_admin")

    response = auth_client.get(
        "/v1/portfolio/summary",
        headers={
            **admin["headers"],
            "X-Admin-Role": "platform_admin",
        },
    )
    assert response.status_code == 200, response.text


def test_revoked_saas_session_is_401(auth_client, db_session):
    tenant = _seed_saas_tenant_user(db_session)
    login = auth_client.post(
        "/v1/auth/login",
        json={"email": tenant["email"], "password": tenant["password"]},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]

    logout = auth_client.post(
        "/v1/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert logout.status_code == 200

    response = auth_client.get(
        "/v1/portfolio/summary",
        params={},
        headers={"Authorization": f"Bearer {token}", "X-Admin-Role": "admin"},
    )
    assert response.status_code == 401


def test_inactive_user_is_401(auth_client, db_session):
    tenant = _seed_saas_tenant_user(db_session)
    login = auth_client.post(
        "/v1/auth/login",
        json={"email": tenant["email"], "password": tenant["password"]},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]

    user = (
        db_session.query(UserAccount)
        .filter(UserAccount.user_id == tenant["user_id"])
        .one()
    )
    user.status = "inactive"
    db_session.commit()

    response = auth_client.get(
        "/v1/portfolio/summary",
        params={},
        headers={"Authorization": f"Bearer {token}", "X-Admin-Role": "admin"},
    )
    assert response.status_code == 401


def test_shared_admin_token_still_works_for_platform_routes(
    auth_client, db_session, monkeypatch
):
    _ensure_default_rbac_seed(db_session)
    token = "phase0-admin-token"
    monkeypatch.setattr(settings, "admin_token", token)

    response = auth_client.get(
        "/v1/portfolio/summary",
        headers={"X-Admin-Token": token, "X-Admin-Role": "admin"},
    )
    assert response.status_code == 200, response.text
