"""API integration tests for WP2 runtime identity endpoints."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from rai_gateway.core.config import settings
from rai_gateway.registry.domain import AgentStatus, AgentVersionStatus, AISystemStatus
from rai_gateway.registry.service import RegistryService


@pytest.fixture()
def admin_headers(monkeypatch: pytest.MonkeyPatch, test_organization) -> dict[str, str]:
    token = "test-admin-token"
    monkeypatch.setattr(settings, "admin_token", token)
    return {
        "X-Admin-Token": token,
        "X-Admin-Role": "admin",
    }


@pytest.fixture()
def approved_stack(db_session, test_organization) -> dict:
    registry = RegistryService(db_session)
    suffix = uuid.uuid4().hex[:8]
    system = registry.create_ai_system(
        system_key=f"api-sys-{suffix}",
        name="API System",
        created_by="tester",
    )
    for status in (AISystemStatus.UNDER_REVIEW, AISystemStatus.APPROVED):
        registry.transition_ai_system(system.id, status.value, updated_by="tester")

    agent = registry.create_agent(
        system.id,
        agent_key=f"api-agent-{suffix}",
        name="API Agent",
        created_by="tester",
    )
    for status in (AgentStatus.UNDER_REVIEW, AgentStatus.APPROVED):
        registry.transition_agent(agent.id, status.value, updated_by="tester")

    version = registry.create_agent_version(agent.id, created_by="tester")
    for status in (AgentVersionStatus.UNDER_REVIEW, AgentVersionStatus.APPROVED):
        registry.transition_agent_version(version.id, status.value, updated_by="tester")

    return {"agent": agent, "version": version}


def test_create_runtime_identity_api(
    test_client: TestClient,
    admin_headers: dict[str, str],
    approved_stack: dict,
) -> None:
    response = test_client.post(
        "/v1/runtime-identities",
        headers=admin_headers,
        json={
            "agent_id": str(approved_stack["agent"].id),
            "agent_version_id": str(approved_stack["version"].id),
            "name": "support-runtime",
            "identity_type": "RAI_API_CREDENTIAL",
            "environment": "production",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "support-runtime"
    assert body["environment"] == "production"
    assert body["status"] == "ACTIVE"


def test_list_runtime_identities_returns_array(
    test_client: TestClient,
    admin_headers: dict[str, str],
    approved_stack: dict,
) -> None:
    test_client.post(
        "/v1/runtime-identities",
        headers=admin_headers,
        json={
            "agent_id": str(approved_stack["agent"].id),
            "agent_version_id": str(approved_stack["version"].id),
            "name": "list-test-runtime",
        },
    )
    response = test_client.get(
        f"/v1/runtime-identities?agent_version_id={approved_stack['version'].id}",
        headers=admin_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)


def test_update_delegation_api(
    test_client: TestClient,
    admin_headers: dict[str, str],
    approved_stack: dict,
) -> None:
    create_res = test_client.post(
        "/v1/runtime-identities",
        headers=admin_headers,
        json={
            "agent_id": str(approved_stack["agent"].id),
            "agent_version_id": str(approved_stack["version"].id),
            "name": "delegation-update-runtime",
        },
    )
    identity_id = create_res.json()["id"]

    delegation_res = test_client.post(
        "/v1/delegations",
        headers=admin_headers,
        json={
            "delegator_type": "HUMAN",
            "delegator_id": "before@example.com",
            "delegate_runtime_identity_id": identity_id,
            "scope": {"tool_keys": []},
        },
    )
    delegation_id = delegation_res.json()["id"]

    update_res = test_client.patch(
        f"/v1/delegations/{delegation_id}",
        headers=admin_headers,
        json={"scope": {"tool_keys": []}, "change_reason": "noop scope refresh"},
    )
    assert update_res.status_code == 200, update_res.text
    body = update_res.json()
    assert body["delegator_id"] == "before@example.com"
    assert body["revision_number"] == 2
    assert body["scope_v2"]["scope_version"] == 2
