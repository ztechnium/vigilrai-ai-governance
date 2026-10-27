"""HTTP-level smoke tests for unified catalog and rules endpoints."""

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
from rai_gateway.registry.domain import AISystemStatus
from rai_gateway.registry.service import RegistryService
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
    email = f"unified-api-{suffix}@example.com"
    user_id = f"user-{suffix}"
    db_session.add(
        UserAccount(
            user_id=user_id,
            email=email,
            name="Unified API",
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


def test_resource_catalog_endpoint(
    tenant_api_client: TestClient, db_session, test_organization, tenant_headers
):
    registry = RegistryService(db_session)
    suffix = uuid.uuid4().hex[:6]
    registry.create_mcp_server(
        server_key=f"mcp-{suffix}",
        name=f"MCP {suffix}",
    )
    res = tenant_api_client.get(
        "/v1/resource-catalog", params={"limit": 50}, headers=tenant_headers
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert "items" in body and "total" in body
    assert any(i["resource_type"] == "MCP" for i in body["items"])


def test_rai_rules_and_policy_library_endpoints(
    tenant_api_client: TestClient, db_session, test_organization, tenant_headers
):
    registry = RegistryService(db_session)
    suffix = uuid.uuid4().hex[:6]
    system = registry.create_ai_system(
        system_key=f"sys-{suffix}",
        name=f"System {suffix}",
        created_by="tester",
    )
    for status in (AISystemStatus.UNDER_REVIEW, AISystemStatus.APPROVED):
        registry.transition_ai_system(system.id, status.value, updated_by="tester")

    create = tenant_api_client.post(
        f"/v1/ai-systems/{system.id}/policies/content-rules",
        headers=tenant_headers,
        json={
            "title": "No PII",
            "content": "Do not leak PII",
            "effect": "MONITOR",
            "applies_to": "BOTH",
            "severity": "HIGH",
            "category": "PRIVACY",
        },
    )
    assert create.status_code == 200, create.text

    rules = tenant_api_client.get(
        "/v1/rai-rules",
        params={"ai_system_id": str(system.id)},
        headers=tenant_headers,
    )
    assert rules.status_code == 200, rules.text
    assert rules.json()["total"] >= 1

    source = tenant_api_client.post(
        "/v1/policy-library",
        headers=tenant_headers,
        json={
            "title": "Privacy Policy",
            "source_type": "MANUAL_TEXT",
            "content_text": "Protect personal data.",
            "jurisdiction": "EU",
        },
    )
    assert source.status_code == 200, source.text
    source_id = source.json()["id"]

    listed = tenant_api_client.get("/v1/policy-library", headers=tenant_headers)
    assert listed.status_code == 200
    assert any(i["id"] == source_id for i in listed.json()["items"])

    detail = tenant_api_client.get(
        f"/v1/policy-library/{source_id}", headers=tenant_headers
    )
    assert detail.status_code == 200
    assert detail.json()["title"] == "Privacy Policy"
