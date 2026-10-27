"""Policy REST API tests."""

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
from rai_gateway.services.admin_console import _ensure_default_rbac_seed


@pytest.fixture()
def tenant_api_client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def tenant_headers(db_session, test_organization, tenant_api_client) -> dict[str, str]:
    _ensure_default_rbac_seed(db_session)
    suffix = uuid.uuid4().hex[:8]
    email = f"policy-api-{suffix}@example.com"
    user_id = f"user-{suffix}"
    db_session.add(
        UserAccount(
            user_id=user_id,
            email=email,
            name="Policy API",
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
    login = tenant_api_client.post(
        "/v1/auth/login",
        json={"email": email, "password": "SecurePass123!"},
    )
    assert login.status_code == 200, login.text
    return {
        "Authorization": f"Bearer {login.json()['access_token']}",
    }


def test_policy_api_flow(
    tenant_api_client: TestClient, policy_stack, tenant_headers
) -> None:
    system_id = str(policy_stack["system"].id)

    res = tenant_api_client.get(
        f"/v1/ai-systems/{system_id}/policies", headers=tenant_headers
    )
    assert res.status_code == 200
    body = res.json()
    assert body["collection"]["ai_system_id"] == system_id
    assert body["content_rules"] == []
    assert body["tool_rules"] == []

    res = tenant_api_client.post(
        f"/v1/ai-systems/{system_id}/policies/content-rules",
        headers=tenant_headers,
        json={
            "title": "Supplier confidentiality",
            "content": "Do not share supplier contracts.",
            "effect": "MONITOR",
        },
    )
    assert res.status_code == 200
    content_rule_id = res.json()["id"]

    res = tenant_api_client.post(
        f"/v1/ai-systems/{system_id}/policies/tool-rules",
        headers=tenant_headers,
        json={
            "title": "High value",
            "mcp_server_id": str(policy_stack["mcp"].id),
            "tool_id": str(policy_stack["tool"].id),
            "effect": "REQUIRE_APPROVAL",
            "required_approver_role": "business_approver",
            "conditions": [
                {
                    "parameter_path": "amount",
                    "operator": "gte",
                    "value_type": "number",
                    "value": 100000,
                }
            ],
        },
    )
    assert res.status_code == 200
    tool_rule_id = res.json()["id"]

    res = tenant_api_client.get(
        f"/v1/policies/tool-rules/{tool_rule_id}", headers=tenant_headers
    )
    assert res.status_code == 200
    assert len(res.json()["conditions"]) == 1

    res = tenant_api_client.patch(
        f"/v1/policies/content-rules/{content_rule_id}",
        headers=tenant_headers,
        json={"enabled": False},
    )
    assert res.status_code == 200
    assert res.json()["enabled"] is False

    res = tenant_api_client.delete(
        f"/v1/policies/tool-rules/{tool_rule_id}", headers=tenant_headers
    )
    assert res.status_code == 204
