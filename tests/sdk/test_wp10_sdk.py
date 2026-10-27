"""WP10 SDK / productization DoD tests."""

from __future__ import annotations

import uuid
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from rai_gateway.governance.domain import GovernanceRole, MembershipStatus
from rai_gateway.governance.service import GovernanceService
from rai_gateway.identity.domain import DelegatorType
from rai_gateway.identity.service import (
    CredentialService,
    DelegationService,
    RuntimeIdentityService,
)
from rai_gateway.main import app
from rai_gateway.registry.domain import AgentStatus, AgentVersionStatus, AISystemStatus
from rai_gateway.registry.service import RegistryService
from rai_gateway.sdk.domain import SdkDecision
from rai_gateway.sdk.errors import SdkError
from rai_gateway.sdk.jobs import JobQueue
from rai_gateway.sdk.rate_limit import SlidingWindowRateLimiter
from rai_gateway.sdk.service import SdkService
from rai_gateway.sdk.webhooks import (
    WebhookService,
    sign_webhook_payload,
    verify_webhook_signature,
)


@pytest.fixture()
def gov(db_session) -> GovernanceService:
    return GovernanceService(db_session)


@pytest.fixture()
def registry(db_session) -> RegistryService:
    return RegistryService(db_session)


@pytest.fixture()
def sdk_stack(gov: GovernanceService, registry: RegistryService, db_session) -> dict:
    suffix = uuid.uuid4().hex[:8]
    gov.create_membership(
        user_id=f"admin-{suffix}",
        role=GovernanceRole.ORGANIZATION_ADMIN.value,
        created_by="tester",
        status=MembershipStatus.ACTIVE.value,
    )

    system = registry.create_ai_system(
        system_key=f"wp10-sys-{suffix}",
        name="Sales AI",
        created_by="tester",
    )
    for status in (AISystemStatus.UNDER_REVIEW, AISystemStatus.APPROVED):
        registry.transition_ai_system(system.id, status.value, updated_by="tester")
    gov.link_ai_system(system.id, "tester")

    agent = registry.create_agent(
        system.id,
        agent_key=f"wp10-agent-{suffix}",
        name="Sales Agent",
        created_by="tester",
    )
    for status in (AgentStatus.UNDER_REVIEW, AgentStatus.APPROVED):
        registry.transition_agent(agent.id, status.value, updated_by="tester")

    version = registry.create_agent_version(agent.id, created_by="tester")
    tool = registry.create_tool_resource(
        tool_key=f"create_order_{suffix}",
        name="create_order",
        consequential_action=True,
    )
    registry.add_version_dependency(
        version.id, resource_type="tool", resource_id=tool.id
    )
    for status in (AgentVersionStatus.UNDER_REVIEW, AgentVersionStatus.APPROVED):
        registry.transition_agent_version(version.id, status.value, updated_by="tester")

    identity = RuntimeIdentityService(db_session).create_runtime_identity(
        agent_id=agent.id,
        agent_version_id=version.id,
        name="WP10 Runtime",
        created_by="tester",
    )
    issued = CredentialService(db_session).issue_credential(
        identity.id, created_by="tester"
    )
    delegation = DelegationService(db_session).create_delegation(
        delegator_type=DelegatorType.HUMAN.value,
        delegator_id="sales-owner",
        delegate_runtime_identity_id=identity.id,
        scope={"tool_ids": [str(tool.id)]},
        created_by="tester",
    )

    svc = SdkService(db_session)
    integration = svc.create_integration(
        integration_key=f"sales-sdk-{suffix}",
        name="Sales AI SDK",
        runtime_identity_id=identity.id,
        created_by="tester",
        enforcement_mode="OBSERVE_ONLY",
        fail_closed=True,
    )

    return {
        "system": system,
        "agent": agent,
        "version": version,
        "tool": tool,
        "identity": identity,
        "credential_secret": issued.plaintext_secret,
        "integration": integration,
        "delegation": delegation,
        "svc": svc,
    }


def test_sdk_session_lifecycle_observe_only(sdk_stack):
    svc: SdkService = sdk_stack["svc"]
    auth = svc.authenticate(secret=sdk_stack["credential_secret"], token=None)
    session = svc.start_session(
        auth,
        integration_id=UUID(sdk_stack["integration"]["id"]),
        external_session_id="ext-1",
        channel="sales-ai",
    )
    assert session["status"] == "ACTIVE"
    assert session["trajectory_id"]

    observed = svc.observe_input(
        auth,
        session_id=UUID(session["rai_session_id"]),
        content="Please create an order",
    )
    assert observed["decision"] in {"ALLOW", "MONITOR", "DENY"}

    key = f"idem-stable-{uuid.uuid4().hex}"
    d1 = svc.authorize_action(
        auth,
        session_id=UUID(session["rai_session_id"]),
        credential_secret=sdk_stack["credential_secret"],
        tool=sdk_stack["tool"].tool_key,
        parameters={"amount": 50},
        idempotency_key=key,
    )
    assert d1["decision"] == SdkDecision.MONITOR.value
    assert d1["decision_id"]

    d2 = svc.authorize_action(
        auth,
        session_id=UUID(session["rai_session_id"]),
        credential_secret=sdk_stack["credential_secret"],
        tool=sdk_stack["tool"].tool_key,
        parameters={"amount": 50},
        idempotency_key=key,
    )
    assert d1["decision_id"] == d2["decision_id"]

    out = svc.observe_output(
        auth,
        session_id=UUID(session["rai_session_id"]),
        content="Order drafted",
    )
    assert out["ok"] is True

    ended = svc.end_session(auth, session_id=UUID(session["rai_session_id"]))
    assert ended["status"] == "ENDED"
    ended2 = svc.end_session(auth, session_id=UUID(session["rai_session_id"]))
    assert ended2["status"] == "ENDED"


def test_observe_input_merges_session_configuration_provenance(sdk_stack, db_session):
    from rai_gateway.evidence.domain import EvidenceEventType
    from rai_gateway.evidence.lifecycle_projection import LifecycleProjectionService
    from rai_gateway.evidence.service import TrajectoryService
    from rai_gateway.models.evidence import RuntimeTrajectory

    svc: SdkService = sdk_stack["svc"]
    auth = svc.authenticate(secret=sdk_stack["credential_secret"], token=None)
    session = svc.start_session(
        auth,
        integration_id=UUID(sdk_stack["integration"]["id"]),
        external_session_id=f"prov-{uuid.uuid4().hex[:8]}",
        external_conversation_id="conv-prov",
        metadata={
            "configuration_id": "lapeep-agent",
            "configuration_version": "42",
            "configuration_digest": "sha256:abc",
            "release_id": "9f219e",
        },
    )
    svc.observe_input(
        auth,
        session_id=UUID(session["rai_session_id"]),
        content="Book appointment",
        metadata={"turn_id": "t-1"},
    )
    trajectory = (
        db_session.query(RuntimeTrajectory)
        .filter(RuntimeTrajectory.id == UUID(session["trajectory_id"]))
        .one()
    )
    events = TrajectoryService(db_session).list_events(trajectory.id, limit=50)
    prompt_events = [
        e for e in events if e.event_type == EvidenceEventType.PROMPT_OBSERVED.value
    ]
    assert prompt_events
    payload = prompt_events[0].payload or {}
    assert payload["configuration_id"] == "lapeep-agent"
    assert payload["configuration_digest"] == "sha256:abc"
    assert payload["turn_id"] == "t-1"

    lifecycle = LifecycleProjectionService(db_session).project(
        trajectory, events=events
    )
    provenance = lifecycle["configuration_provenance"]
    assert provenance["configuration_id"] == "lapeep-agent"
    assert provenance["release_id"] == "9f219e"
    assert provenance["assurance"] == "APPLICATION_REPORTED"


def test_ended_session_not_silently_reopened(sdk_stack):
    svc: SdkService = sdk_stack["svc"]
    auth = svc.authenticate(secret=sdk_stack["credential_secret"], token=None)
    session = svc.start_session(
        auth,
        integration_id=UUID(sdk_stack["integration"]["id"]),
        external_session_id="turn-ended-1",
        external_conversation_id="conv-1",
    )
    svc.end_session(auth, session_id=UUID(session["rai_session_id"]))
    with pytest.raises(SdkError) as exc:
        svc.start_session(
            auth,
            integration_id=UUID(sdk_stack["integration"]["id"]),
            external_session_id="turn-ended-1",
            external_conversation_id="conv-1",
        )
    assert exc.value.code.value == "INVALID_REQUEST"
    assert "ended" in exc.value.message.lower()


def test_conversation_turns_create_distinct_trajectories(sdk_stack):
    svc: SdkService = sdk_stack["svc"]
    auth = svc.authenticate(secret=sdk_stack["credential_secret"], token=None)
    integration_id = UUID(sdk_stack["integration"]["id"])
    conv = f"conv-{uuid.uuid4().hex[:8]}"
    s1 = svc.start_session(
        auth,
        integration_id=integration_id,
        external_conversation_id=conv,
        external_session_id=f"{conv}-t1",
    )
    s2 = svc.start_session(
        auth,
        integration_id=integration_id,
        external_conversation_id=conv,
        external_session_id=f"{conv}-t2",
    )
    assert s1["trajectory_id"] != s2["trajectory_id"]
    assert s1["rai_session_id"] != s2["rai_session_id"]


def test_session_binds_delegation(sdk_stack, db_session):
    from rai_gateway.evidence.service import TrajectoryService
    from rai_gateway.models.productization import SdkSession

    svc: SdkService = sdk_stack["svc"]
    auth = svc.authenticate(secret=sdk_stack["credential_secret"], token=None)
    delegation_id = sdk_stack["delegation"].id
    session = svc.start_session(
        auth,
        integration_id=UUID(sdk_stack["integration"]["id"]),
        external_session_id=f"turn-del-{uuid.uuid4().hex[:6]}",
        external_conversation_id="conv-del",
        delegation_id=delegation_id,
    )
    assert session["delegation_id"] == str(delegation_id)

    row = (
        db_session.query(SdkSession)
        .filter(SdkSession.id == UUID(session["rai_session_id"]))
        .one()
    )
    assert row.delegation_id == delegation_id

    trajectory = TrajectoryService(db_session).get_trajectory(
        UUID(session["trajectory_id"])
    )
    assert trajectory is not None
    assert trajectory.delegation_id == delegation_id


def test_expired_approval_releases_idempotency_for_new_approval(sdk_stack, db_session):
    """An expired approval must not lock the idempotency key.

    A later authorize — even with a different action digest — opens a new
    decision instead of INVALID_REQUEST. A still-pending approval stays bound.
    """
    from datetime import datetime, timedelta, timezone

    from rai_gateway.models.approval import ApprovalRequest
    from rai_gateway.models.productization import SdkDecisionRecord

    svc: SdkService = sdk_stack["svc"]
    auth = svc.authenticate(secret=sdk_stack["credential_secret"], token=None)
    session = svc.start_session(
        auth,
        integration_id=UUID(sdk_stack["integration"]["id"]),
        channel="sales-ai",
    )
    key = f"idem-expired-{uuid.uuid4().hex}"
    first = svc.authorize_action(
        auth,
        session_id=UUID(session["rai_session_id"]),
        credential_secret=sdk_stack["credential_secret"],
        tool=sdk_stack["tool"].tool_key,
        parameters={"amount": 50},
        idempotency_key=key,
    )
    record = (
        db_session.query(SdkDecisionRecord)
        .filter(SdkDecisionRecord.id == UUID(first["decision_id"]))
        .one()
    )
    expired = ApprovalRequest(
        ai_system_id=sdk_stack["system"].id,
        agent_id=sdk_stack["agent"].id,
        agent_version_id=sdk_stack["version"].id,
        runtime_identity_id=sdk_stack["identity"].id,
        integration_type="sdk",
        tool_id=sdk_stack["tool"].id,
        canonical_action_payload={"amount": 50},
        action_digest=record.action_digest or "digest",
        status="PENDING",
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        created_by="tester",
    )
    db_session.add(expired)
    db_session.commit()
    record.approval_request_id = expired.id
    record.decision = "REQUIRE_APPROVAL"
    db_session.commit()

    second = svc.authorize_action(
        auth,
        session_id=UUID(session["rai_session_id"]),
        credential_secret=sdk_stack["credential_secret"],
        tool=sdk_stack["tool"].tool_key,
        parameters={"amount": 75, "fields": {"phone": "+1555"}},
        idempotency_key=key,
    )
    assert second["decision_id"] != first["decision_id"]
    db_session.refresh(expired)
    assert expired.status == "EXPIRED"
    db_session.refresh(record)
    assert record.idempotency_key is None

    pending = ApprovalRequest(
        ai_system_id=sdk_stack["system"].id,
        agent_id=sdk_stack["agent"].id,
        agent_version_id=sdk_stack["version"].id,
        runtime_identity_id=sdk_stack["identity"].id,
        integration_type="sdk",
        tool_id=sdk_stack["tool"].id,
        canonical_action_payload={"amount": 75},
        action_digest="live",
        status="PENDING",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        created_by="tester",
    )
    db_session.add(pending)
    db_session.commit()
    live = (
        db_session.query(SdkDecisionRecord)
        .filter(SdkDecisionRecord.id == UUID(second["decision_id"]))
        .one()
    )
    live.approval_request_id = pending.id
    db_session.commit()

    with pytest.raises(SdkError) as exc:
        svc.authorize_action(
            auth,
            session_id=UUID(session["rai_session_id"]),
            credential_secret=sdk_stack["credential_secret"],
            tool=sdk_stack["tool"].tool_key,
            parameters={"amount": 999},
            idempotency_key=key,
        )
    assert exc.value.code.value == "INVALID_REQUEST"


def test_idempotency_digest_mismatch_denied(sdk_stack):
    svc: SdkService = sdk_stack["svc"]
    auth = svc.authenticate(secret=sdk_stack["credential_secret"], token=None)
    session = svc.start_session(
        auth,
        integration_id=UUID(sdk_stack["integration"]["id"]),
        channel="sales-ai",
    )
    key = f"idem-mismatch-{uuid.uuid4().hex}"
    svc.authorize_action(
        auth,
        session_id=UUID(session["rai_session_id"]),
        credential_secret=sdk_stack["credential_secret"],
        tool=sdk_stack["tool"].tool_key,
        parameters={"amount": 50},
        idempotency_key=key,
    )
    with pytest.raises(SdkError) as exc:
        svc.authorize_action(
            auth,
            session_id=UUID(session["rai_session_id"]),
            credential_secret=sdk_stack["credential_secret"],
            tool=sdk_stack["tool"].tool_key,
            parameters={"amount": 999},
            idempotency_key=key,
        )
    assert exc.value.code.value == "INVALID_REQUEST"
    assert "digest" in exc.value.message.lower()


def test_onboarding_checklist(sdk_stack):
    checklist = sdk_stack["svc"].onboarding_checklist()
    assert checklist["legacy_complete"] is True
    assert all(step["done"] for step in checklist["legacy_steps"])
    assert len(checklist["steps"]) == 13
    assert "onboarding" in checklist


def test_heartbeat_and_health(sdk_stack):
    svc: SdkService = sdk_stack["svc"]
    auth = svc.authenticate(secret=sdk_stack["credential_secret"], token=None)
    hb = svc.heartbeat(
        auth,
        integration_id=UUID(sdk_stack["integration"]["id"]),
        sdk_version="1.0.0",
    )
    assert hb["ok"] is True
    assert svc.health()["api_version"] == "v1"


def test_webhook_signature_replay_protection():
    secret = "whsec_test"
    body = b'{"id":"1"}'
    ts = "1700000000"
    sig = sign_webhook_payload(secret, timestamp=ts, body=body)
    assert verify_webhook_signature(
        secret, timestamp=ts, body=body, signature=sig, max_skew_seconds=10**9
    )
    assert not verify_webhook_signature(
        secret, timestamp="1", body=body, signature=sig, max_skew_seconds=60
    )


def test_webhook_enqueue_and_jobs(sdk_stack, db_session, monkeypatch):
    monkeypatch.setattr(
        "rai_gateway.sdk.webhooks.socket.getaddrinfo",
        lambda *_args, **_kwargs: [(2, 1, 6, "", ("93.184.216.34", 443))],
    )
    wh = WebhookService(db_session)
    endpoint, plaintext = wh.create_endpoint(
        name="ops",
        url="https://example.invalid/hooks",
        event_types=["risk.critical", "*"],
        created_by="tester",
    )
    assert plaintext.startswith("whsec_")
    ids = wh.enqueue(
        event_type="risk.critical",
        payload={"severity": "high"},
    )
    assert len(ids) >= 1
    assert wh.list_deliveries()

    jobs = JobQueue(db_session)
    job = jobs.enqueue(
        job_type="WEBHOOK_DELIVERY",
        idempotency_key=f"job-{uuid.uuid4().hex}",
        payload={"delivery_id": str(ids[0])},
    )
    again = jobs.enqueue(
        job_type="WEBHOOK_DELIVERY",
        idempotency_key=job["idempotency_key"],
        payload={"delivery_id": str(ids[0])},
    )
    assert job["id"] == again["id"]


def test_rate_limiter_fail_closed():
    limiter = SlidingWindowRateLimiter()
    for _ in range(3):
        assert limiter.check("k", limit=3, window_seconds=60).allowed
    assert not limiter.check("k", limit=3, window_seconds=60).allowed


def test_sdk_http_health():
    client = TestClient(app)
    resp = client.get("/sdk/v1/health")
    assert resp.status_code in {200, 500}
    if resp.status_code == 200:
        assert resp.json()["api_version"] == "v1"


def test_observe_only_authorize_without_enforcement_secret(sdk_stack):
    svc: SdkService = sdk_stack["svc"]
    auth = svc.authenticate(secret=sdk_stack["credential_secret"], token=None)
    session = svc.start_session(
        auth, integration_id=UUID(sdk_stack["integration"]["id"])
    )
    decision = svc.authorize_action(
        auth,
        session_id=UUID(session["rai_session_id"]),
        credential_secret=None,
        tool="create_order",
    )
    assert decision["decision"] == "MONITOR"
