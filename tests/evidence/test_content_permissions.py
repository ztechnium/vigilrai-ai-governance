"""Content permission gating and conversation/audit tenant isolation."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from rai_gateway.auth.passwords import hash_password
from rai_gateway.core.database import get_db
from rai_gateway.evidence.content_access import (
    apply_content_permission,
    apply_export_content_permission,
    strip_event_content,
)
from rai_gateway.evidence.domain import EvidenceEventType, EvidenceSourceType
from rai_gateway.evidence.service import TrajectoryService
from rai_gateway.governance.domain import GovernanceRole, MembershipStatus
from rai_gateway.identity.service import RuntimeIdentityService
from rai_gateway.main import app
from rai_gateway.models.database import AdminCredential, UserAccount
from rai_gateway.models.governance import OrganizationMembership
from rai_gateway.registry.domain import AgentStatus, AgentVersionStatus, AISystemStatus
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


def _stack(db_session, suffix: str) -> dict:
    registry = RegistryService(db_session)
    system = registry.create_ai_system(
        system_key=f"sys-{suffix}",
        name=f"System {suffix}",
        created_by="tester",
    )
    for status in (AISystemStatus.UNDER_REVIEW, AISystemStatus.APPROVED):
        registry.transition_ai_system(system.id, status.value, updated_by="tester")
    agent = registry.create_agent(
        system.id,
        agent_key=f"agent-{suffix}",
        name=f"Agent {suffix}",
        created_by="tester",
    )
    for status in (AgentStatus.UNDER_REVIEW, AgentStatus.APPROVED):
        registry.transition_agent(agent.id, status.value, updated_by="tester")
    version = registry.create_agent_version(agent.id, created_by="tester")
    for status in (AgentVersionStatus.UNDER_REVIEW, AgentVersionStatus.APPROVED):
        registry.transition_agent_version(version.id, status.value, updated_by="tester")
    identity = RuntimeIdentityService(db_session).create_runtime_identity(
        agent_id=agent.id,
        agent_version_id=version.id,
        name=f"rt-{suffix}",
        created_by="tester",
    )
    return {
        "system": system,
        "agent": agent,
        "version": version,
        "identity": identity,
    }


def _seed_member(db_session, *, role: str | None = None):
    _ensure_default_rbac_seed(db_session)
    suffix = uuid.uuid4().hex[:8]
    email = f"ev-{suffix}@example.com"
    user_id = f"user-{suffix}"
    membership_role = role or GovernanceRole.ORGANIZATION_ADMIN.value
    db_session.add(
        UserAccount(
            user_id=user_id,
            email=email,
            name="Member",
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
            role=membership_role,
            status=MembershipStatus.ACTIVE.value,
            created_by=user_id,
        )
    )
    db_session.commit()
    return {"email": email, "password": "SecurePass123!", "user_id": user_id}


def _login_headers(client: TestClient, member: dict) -> dict[str, str]:
    login = client.post(
        "/v1/auth/login",
        json={"email": member["email"], "password": member["password"]},
    )
    assert login.status_code == 200, login.text
    return {
        "Authorization": f"Bearer {login.json()['access_token']}",
    }


def test_strip_event_content_removes_payload_fields():
    event = {
        "id": "1",
        "payload": {"prompt": "secret", "model": "gpt", "token_count": 3},
        "content_preview": "secret…",
        "artifacts": [{"id": "a", "inline_content": "raw"}],
    }
    stripped = strip_event_content(event)
    assert "prompt" not in stripped["payload"]
    assert stripped["payload"]["model"] == "gpt"
    assert stripped["content_preview"] is None
    assert stripped["content_access"] == "DENIED"
    assert stripped["artifacts"][0]["inline_content"] is None


def test_apply_content_permission_allows_when_permitted():
    event = {"payload": {"prompt": "hello"}, "content_preview": "hello"}
    allowed = apply_content_permission(event, allowed=True)
    assert allowed["payload"]["prompt"] == "hello"
    assert allowed["content_access"] == "ALLOWED"


def test_export_strips_without_content_export_permission():
    export = {
        "trajectory": {
            "events": [{"payload": {"prompt": "x"}, "content_preview": "x"}],
            "artifacts": [{"inline_content": "y"}],
        }
    }
    result = apply_export_content_permission(export, allowed=False)
    assert result["content_access"] == "DENIED"
    assert result["trajectory"]["events"][0]["content_preview"] is None
    assert "prompt" not in result["trajectory"]["events"][0]["payload"]


def _trajectory_with_prompt(db_session, stack, *, suffix: str):
    svc = TrajectoryService(db_session)
    trajectory = svc.get_or_create_trajectory(
        ai_system_id=stack["system"].id,
        agent_id=stack["agent"].id,
        agent_version_id=stack["version"].id,
        runtime_identity_id=stack["identity"].id,
        conversation_id=f"conv-{suffix}",
        client_session_id=f"turn-{suffix}",
        correlation_id=f"corr-{suffix}",
    )
    svc.append_event(
        trajectory,
        event_type=EvidenceEventType.PROMPT_OBSERVED.value,
        source_type=EvidenceSourceType.CLIENT_OBSERVED.value,
        source_reference=f"prompt:{suffix}",
        payload={"prompt": f"secret-prompt-{suffix}", "model": "demo"},
        content_handling_mode="FULL",
    )
    db_session.commit()
    db_session.refresh(trajectory)
    return trajectory


def test_api_strips_content_without_content_read_permission(
    tenant_api_client, db_session
):
    stack = _stack(db_session, uuid.uuid4().hex[:8])
    trajectory = _trajectory_with_prompt(db_session, stack, suffix=uuid.uuid4().hex[:8])
    # risk_officer has evidence:read but not evidence:content:read
    member = _seed_member(
        db_session,
        role="RISK_COMPLIANCE_REVIEWER",
    )

    headers = _login_headers(tenant_api_client, member)
    detail = tenant_api_client.get(f"/v1/trajectories/{trajectory.id}", headers=headers)
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["content_access"] == "DENIED"
    prompt_events = [
        e
        for e in body["events"]
        if e["event_type"] == EvidenceEventType.PROMPT_OBSERVED.value
    ]
    assert prompt_events
    assert prompt_events[0]["content_preview"] is None
    assert "prompt" not in (prompt_events[0].get("payload") or {})

    lifecycle = tenant_api_client.get(
        f"/v1/trajectories/{trajectory.id}/lifecycle", headers=headers
    )
    assert lifecycle.status_code == 200
    assert lifecycle.json()["content_access"] == "DENIED"
    for stage in lifecycle.json()["stages"]:
        content = stage.get("content") or {}
        assert content.get("preview") is None


def test_api_allows_content_with_content_read_permission(tenant_api_client, db_session):
    stack = _stack(db_session, uuid.uuid4().hex[:8])
    trajectory = _trajectory_with_prompt(db_session, stack, suffix=uuid.uuid4().hex[:8])
    member = _seed_member(db_session)
    headers = _login_headers(tenant_api_client, member)
    detail = tenant_api_client.get(f"/v1/trajectories/{trajectory.id}", headers=headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body["content_access"] == "ALLOWED"
    prompt_events = [
        e
        for e in body["events"]
        if e["event_type"] == EvidenceEventType.PROMPT_OBSERVED.value
    ]
    assert prompt_events
    assert prompt_events[0]["payload"].get("prompt", "").startswith("secret-prompt-")
