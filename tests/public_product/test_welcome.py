"""First-run welcome wizard API."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from rai_gateway.auth.passwords import hash_password
from rai_gateway.core.database import get_db
from rai_gateway.governance.domain import GovernanceRole, MembershipStatus
from rai_gateway.main import app
from rai_gateway.models.database import AdminCredential, UserAccount
from rai_gateway.models.governance import OrganizationMembership
from rai_gateway.models.productization import OrganizationOnboarding
from rai_gateway.models.registry import AISystem, MCPServer, ToolResource
from rai_gateway.services.admin_console import _ensure_default_rbac_seed


@pytest.fixture()
def public_client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def auth_headers(public_client, db_session) -> dict[str, str]:
    _ensure_default_rbac_seed(db_session)
    suffix = uuid.uuid4().hex[:8]
    email = f"welcome-{suffix}@example.com"
    user_id = f"user-{suffix}"
    db_session.add(
        UserAccount(
            user_id=user_id,
            email=email,
            name="Welcome User",
            status="active",
            email_verified_at=datetime.now(timezone.utc),
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
    db_session.add(
        OrganizationMembership(
            user_id=user_id,
            role=GovernanceRole.ORGANIZATION_ADMIN.value,
            status=MembershipStatus.ACTIVE.value,
            created_by=user_id,
        )
    )
    db_session.commit()
    login = public_client.post(
        "/v1/auth/login",
        json={"email": email, "password": "SecurePass123!"},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_welcome_starts_incomplete(public_client, auth_headers):
    welcome = public_client.get("/v1/productization/welcome", headers=auth_headers)
    assert welcome.status_code == 200, welcome.text
    assert welcome.json()["welcome_completed"] is False


def test_welcome_profile_seed_and_complete(public_client, db_session, auth_headers):
    welcome = public_client.get("/v1/productization/welcome", headers=auth_headers)
    assert welcome.status_code == 200, welcome.text
    body = welcome.json()
    assert body["welcome_completed"] is False
    assert any(item["key"] == "support-ai" for item in body["templates"])

    profile = public_client.patch(
        "/v1/productization/welcome/profile",
        json={
            "name": body["organization"]["name"],
            "industry": "Healthcare",
            "logo": "data:image/png;base64,aaaa",
        },
        headers=auth_headers,
    )
    assert profile.status_code == 200, profile.text
    assert profile.json()["organization"]["industry"] == "Healthcare"
    assert profile.json()["organization"]["logo"].startswith("data:image/")

    seeded = public_client.post(
        "/v1/productization/welcome/seed",
        json={"template_key": "support-ai"},
        headers=auth_headers,
    )
    assert seeded.status_code == 200, seeded.text
    payload = seeded.json()
    assert payload["seeded"]["template_key"] == "support-ai"
    assert payload["setup"]["tool_name"] == "create_support_ticket"

    systems = (
        db_session.query(AISystem).filter(AISystem.system_key == "support-ai").all()
    )
    assert [row.system_key for row in systems] == ["support-ai"]
    mcp = (
        db_session.query(MCPServer)
        .filter(MCPServer.server_key == "support-ai-mcp")
        .one()
    )
    tool = (
        db_session.query(ToolResource)
        .filter(ToolResource.tool_key == "create_support_ticket")
        .one()
    )
    assert tool.mcp_server_id == mcp.id

    again = public_client.post(
        "/v1/productization/welcome/seed",
        json={"template_key": "support-ai"},
        headers=auth_headers,
    )
    assert again.status_code == 200, again.text
    assert (
        db_session.query(AISystem).filter(AISystem.system_key == "support-ai").count()
        == 1
    )

    done = public_client.post(
        "/v1/productization/welcome/complete", headers=auth_headers
    )
    assert done.status_code == 200, done.text
    assert done.json()["welcome_completed"] is True


def test_backfilled_welcome_is_complete(public_client, db_session, auth_headers):
    record = (
        db_session.query(OrganizationOnboarding)
        .filter(OrganizationOnboarding.singleton_key == "default")
        .first()
    )
    if record is None:
        record = OrganizationOnboarding(singleton_key="default")
        db_session.add(record)
        db_session.flush()
    record.welcome_completed_at = datetime.now(timezone.utc)
    db_session.commit()

    response = public_client.get("/v1/productization/welcome", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert response.json()["welcome_completed"] is True
