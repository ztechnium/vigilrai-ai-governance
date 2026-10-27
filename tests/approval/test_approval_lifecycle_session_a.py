"""Session A approval lifecycle: resume, outbox, webhooks."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from rai_gateway.approval.authorization import ApproverContext
from rai_gateway.approval.consumption import ApprovalConsumptionService
from rai_gateway.approval.errors import ApprovalConflictError
from rai_gateway.approval.resume import (
    build_approval_resume,
    build_approval_status_response,
)
from rai_gateway.approval.service import ApprovalService
from rai_gateway.models.events import EventOutbox
from rai_gateway.models.productization import WebhookDelivery
from rai_gateway.sdk.errors import SdkError
from rai_gateway.sdk.webhooks import (
    WebhookService,
    sign_webhook_payload,
    validate_webhook_url,
    verify_webhook_signature,
)
from rai_gateway.workers.runtime_events import process_outbox_to_webhooks


def _authority(db_session, stack):
    return ApprovalConsumptionService(db_session).resolve_authority_for_identity(
        stack["identity"].id,
        stack["delegation"].id,
    )


@pytest.fixture(autouse=True)
def _ensure_event_models(db_session):
    import rai_gateway.models.events  # noqa: F401


def test_runtime_idempotency_reuses_pending_request(db_session, approval_stack):
    svc = ApprovalService(db_session)
    authority = _authority(db_session, approval_stack)
    key = f"idem-{uuid4().hex}"
    first = svc.find_or_create_pending_request(
        authority,
        integration_type="mcp",
        integration_id=approval_stack["mcp"].id,
        tool_id=approval_stack["tool"].id,
        target_type="Customer",
        target_identifier="CUST-1",
        parameters={"amount": 100},
        created_by="runtime",
        runtime_idempotency_key=key,
    )
    second = svc.find_or_create_pending_request(
        authority,
        integration_type="mcp",
        integration_id=approval_stack["mcp"].id,
        tool_id=approval_stack["tool"].id,
        target_type="Customer",
        target_identifier="CUST-1",
        parameters={"amount": 100},
        created_by="runtime",
        runtime_idempotency_key=key,
    )
    assert first.id == second.id
    assert first.runtime_idempotency_key == key


def test_runtime_idempotency_conflict_on_digest_mismatch(db_session, approval_stack):
    svc = ApprovalService(db_session)
    authority = _authority(db_session, approval_stack)
    key = f"idem-{uuid4().hex}"
    svc.find_or_create_pending_request(
        authority,
        integration_type="mcp",
        integration_id=approval_stack["mcp"].id,
        tool_id=approval_stack["tool"].id,
        target_type="Customer",
        target_identifier="CUST-1",
        parameters={"amount": 100},
        created_by="runtime",
        runtime_idempotency_key=key,
    )
    with pytest.raises(ApprovalConflictError):
        svc.find_or_create_pending_request(
            authority,
            integration_type="mcp",
            integration_id=approval_stack["mcp"].id,
            tool_id=approval_stack["tool"].id,
            target_type="Customer",
            target_identifier="CUST-1",
            parameters={"amount": 999},
            created_by="runtime",
            runtime_idempotency_key=key,
        )


def test_approval_resume_and_status_payload(db_session, approval_stack):
    svc = ApprovalService(db_session)
    authority = _authority(db_session, approval_stack)
    req = svc.find_or_create_pending_request(
        authority,
        integration_type="mcp",
        integration_id=approval_stack["mcp"].id,
        tool_id=approval_stack["tool"].id,
        created_by="runtime",
    )
    resume = build_approval_resume(req)
    assert resume["resume_mode"] == "RETRY_EXACT_ACTION"
    assert resume["poll_url"].endswith(f"/v1/runtime/approvals/{req.id}/status")
    status = build_approval_status_response(req)
    assert status["can_retry"] is False
    assert status["terminal"] is False

    approved = svc.approve(
        req.id,
        approver=ApproverContext(actor="manager", role="admin"),
    )
    status2 = build_approval_status_response(approved)
    assert status2["can_retry"] is True
    assert status2["status"] == "APPROVED"


def test_outbox_emitted_on_approve(db_session, approval_stack):
    svc = ApprovalService(db_session)
    authority = _authority(db_session, approval_stack)
    req = svc.find_or_create_pending_request(
        authority,
        integration_type="mcp",
        integration_id=approval_stack["mcp"].id,
        tool_id=approval_stack["tool"].id,
        created_by="runtime",
    )
    svc.approve(
        req.id,
        approver=ApproverContext(actor="manager", role="admin"),
    )
    rows = (
        db_session.query(EventOutbox).filter(EventOutbox.aggregate_id == req.id).all()
    )
    types = {r.event_type for r in rows}
    assert "approval.requested" in types
    assert "approval.approved" in types
    for row in rows:
        assert "parameters" not in (row.payload or {})


def test_expire_due_approvals_emits_outbox(db_session, approval_stack):
    svc = ApprovalService(db_session)
    authority = _authority(db_session, approval_stack)
    req = svc.find_or_create_pending_request(
        authority,
        integration_type="mcp",
        integration_id=approval_stack["mcp"].id,
        tool_id=approval_stack["tool"].id,
        created_by="runtime",
        ttl_minutes=15,
    )
    req.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.commit()

    expired = svc.expire_due_approvals(limit=10)
    assert expired >= 1
    db_session.refresh(req)
    assert req.status == "EXPIRED"
    expired_events = (
        db_session.query(EventOutbox)
        .filter(
            EventOutbox.aggregate_id == req.id,
            EventOutbox.event_type == "approval.expired",
        )
        .count()
    )
    assert expired_events >= 1


def test_webhook_signature_roundtrip():
    import time

    secret = "whsec_test_secret"
    body = b'{"id":"1","type":"approval.approved"}'
    ts = str(int(time.time()))
    sig = sign_webhook_payload(secret, timestamp=ts, body=body)
    assert verify_webhook_signature(
        secret, timestamp=ts, body=body, signature=f"v1={sig}"
    )


def test_webhook_rejects_loopback_url(monkeypatch):
    monkeypatch.setattr(
        "rai_gateway.sdk.webhooks.settings.webhook_allow_private_hosts", False
    )
    monkeypatch.setattr("rai_gateway.sdk.webhooks.settings.webhook_allow_http", True)
    with pytest.raises(SdkError):
        validate_webhook_url("http://127.0.0.1:8080/hook")


def test_outbox_bridge_enqueues_webhook_delivery(
    db_session, approval_stack, test_organization, monkeypatch
):
    monkeypatch.setattr(
        "rai_gateway.sdk.webhooks.settings.webhook_allow_private_hosts", True
    )
    monkeypatch.setattr("rai_gateway.sdk.webhooks.settings.webhook_allow_http", True)
    monkeypatch.setattr(
        "rai_gateway.core.config.settings.approval_webhooks_enabled", True
    )

    wh = WebhookService(db_session)
    endpoint, _secret = wh.create_endpoint(
        name="test",
        url="http://127.0.0.1:9/hook",
        event_types=["approval.approved", "*"],
        created_by="tester",
    )
    db_session.commit()
    endpoint_id = UUID(endpoint["id"])

    svc = ApprovalService(db_session)
    authority = _authority(db_session, approval_stack)
    req = svc.find_or_create_pending_request(
        authority,
        integration_type="mcp",
        integration_id=approval_stack["mcp"].id,
        tool_id=approval_stack["tool"].id,
        created_by="runtime",
    )
    svc.approve(
        req.id,
        approver=ApproverContext(actor="manager", role="admin"),
    )

    processed = process_outbox_to_webhooks(db_session, limit=20)
    assert processed >= 1

    deliveries = (
        db_session.query(WebhookDelivery)
        .filter(WebhookDelivery.endpoint_id == endpoint_id)
        .all()
    )
    assert any(d.event_type == "approval.approved" for d in deliveries)
