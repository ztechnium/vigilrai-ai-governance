"""SaaS auth session API tests."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from rai_gateway.auth.passwords import hash_password
from rai_gateway.core.database import get_db
from rai_gateway.governance.domain import GovernanceRole, MembershipStatus
from rai_gateway.main import app
from rai_gateway.models.database import AdminCredential, UserAccount
from rai_gateway.models.governance import OrganizationMembership
from rai_gateway.services.admin_console import _ensure_default_rbac_seed


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


@pytest.fixture()
def registered_user(db_session):
    _ensure_default_rbac_seed(db_session)
    suffix = uuid.uuid4().hex[:8]
    email = f"owner-{suffix}@example.com"
    user_id = f"user-{suffix}"
    user = UserAccount(
        user_id=user_id,
        email=email,
        name="Owner",
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
    for role in (
        GovernanceRole.ORGANIZATION_ADMIN.value,
        GovernanceRole.RAI_OFFICER.value,
    ):
        db_session.add(
            OrganizationMembership(
                user_id=user_id,
                role=role,
                status=MembershipStatus.ACTIVE.value,
                created_by=user_id,
            )
        )
    db_session.commit()
    return {
        "email": email,
        "password": "SecurePass123!",
        "user_id": user_id,
    }


def test_login_me_context_logout(auth_client, registered_user, db_session):
    login = auth_client.post(
        "/v1/auth/login",
        json={
            "email": registered_user["email"],
            "password": registered_user["password"],
        },
    )
    assert login.status_code == 200, login.text
    body = login.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["user"]["email"] == registered_user["email"]
    assert body["platform_roles"] == []
    assert "ORGANIZATION_ADMIN" in body["roles"]

    headers = {"Authorization": f"Bearer {body['access_token']}"}
    me = auth_client.get("/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert "ORGANIZATION_ADMIN" in me.json()["roles"]

    ctx = auth_client.get("/v1/auth/context", headers=headers)
    assert ctx.status_code == 200, ctx.text
    assert "registry:write" in ctx.json()["permissions"]
    assert "ORGANIZATION_ADMIN" in ctx.json()["roles"]

    missing = auth_client.post("/v1/public/register", json={})
    assert missing.status_code == 404

    logout = auth_client.post("/v1/auth/logout", headers=headers)
    assert logout.status_code == 200

    # Access token rejected after logout (session revoked)
    after = auth_client.get("/v1/auth/me", headers=headers)
    assert after.status_code == 401


def test_refresh_rotates_and_detects_reuse(auth_client, registered_user):
    login = auth_client.post(
        "/v1/auth/login",
        json={
            "email": registered_user["email"],
            "password": registered_user["password"],
        },
    ).json()
    old_refresh = login["refresh_token"]

    refreshed = auth_client.post(
        "/v1/auth/refresh", json={"refresh_token": old_refresh}
    )
    assert refreshed.status_code == 200
    new_refresh = refreshed.json()["refresh_token"]
    assert new_refresh != old_refresh

    reuse = auth_client.post("/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert reuse.status_code == 401
