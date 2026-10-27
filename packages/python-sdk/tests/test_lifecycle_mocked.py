"""Full /sdk/v1 lifecycle tests with mocked HTTP transport."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from helpers import INTEGRATION_ID, json_response
from rai_sdk import RAIError

SESSION_ID = "rai-sess-001"
TRAJECTORY_ID = "traj-001"
DECISION_ALLOW = "dec-allow-001"
DECISION_DENY = "dec-deny-001"
DECISION_APPROVAL = "dec-approval-001"


def _authorize_payload(
    decision: str,
    decision_id: str,
    *,
    approval_request_id: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "decision": decision,
        "decision_id": decision_id,
        "reason_code": "POLICY",
        "human_message": f"Decision: {decision}",
    }
    if approval_request_id:
        payload["approval_request_id"] = approval_request_id
    return payload


def test_full_lifecycle_allow(client_factory):
    idempotency_calls: list[str | None] = []
    execution_calls: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/sdk/v1/health":
            return json_response(200, {"api_version": "v1", "ok": True})
        if path == "/sdk/v1/heartbeat":
            body = json.loads(request.content)
            assert body["integration_id"] == INTEGRATION_ID
            return json_response(200, {"ok": True})
        if path == "/sdk/v1/sessions" and request.method == "POST":
            return json_response(
                201,
                {
                    "rai_session_id": SESSION_ID,
                    "trajectory_id": TRAJECTORY_ID,
                    "status": "ACTIVE",
                },
            )
        if path == f"/sdk/v1/sessions/{SESSION_ID}/input":
            return json_response(200, {"decision": "ALLOW", "ok": True})
        if path == f"/sdk/v1/sessions/{SESSION_ID}/actions/authorize":
            idempotency_calls.append(request.headers.get("Idempotency-Key"))
            return json_response(200, _authorize_payload("ALLOW", DECISION_ALLOW))
        if path == f"/sdk/v1/actions/{DECISION_ALLOW}/execution":
            execution_calls.append(json.loads(request.content))
            return json_response(200, {"recorded": True})
        if path == f"/sdk/v1/sessions/{SESSION_ID}/output":
            return json_response(200, {"ok": True})
        if path == f"/sdk/v1/sessions/{SESSION_ID}/end":
            return json_response(200, {"status": "ENDED"})
        return json_response(404, {"detail": {"error": "NOT_FOUND", "message": path}})

    client = client_factory(httpx.MockTransport(handler))

    assert client.health()["api_version"] == "v1"
    assert client.heartbeat()["ok"] is True

    session = client.start_session(external_session_id="ext-1", channel="sales-ai")
    assert session.rai_session_id == SESSION_ID
    assert session.trajectory_id == TRAJECTORY_ID

    session.observe_input("Create an order")
    decision = session.authorize_action(tool="create_order", parameters={"amount": 100})
    assert decision.allowed is True
    assert decision.decision_id == DECISION_ALLOW
    assert idempotency_calls == [None]

    decision.report_execution(client, status="SUCCEEDED")
    assert execution_calls[0]["status"] == "SUCCEEDED"

    session.observe_output("Order created")
    assert session.end()["status"] == "ENDED"
    client.close()


def test_authorize_deny(client_factory):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/actions/authorize"):
            return json_response(200, _authorize_payload("DENY", DECISION_DENY))
        return json_response(
            201,
            {"rai_session_id": SESSION_ID, "trajectory_id": TRAJECTORY_ID},
        )

    client = client_factory(httpx.MockTransport(handler))
    session = client.start_session()
    decision = session.authorize_action(tool="delete_all")
    assert decision.allowed is False
    assert decision.decision == "DENY"
    client.close()


def test_authorize_require_approval(client_factory):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/actions/authorize"):
            return json_response(
                200,
                _authorize_payload(
                    "REQUIRE_APPROVAL",
                    DECISION_APPROVAL,
                    approval_request_id="appr-001",
                ),
            )
        return json_response(
            201,
            {"rai_session_id": SESSION_ID, "trajectory_id": TRAJECTORY_ID},
        )

    client = client_factory(httpx.MockTransport(handler))
    session = client.start_session()
    decision = session.authorize_action(tool="wire_transfer", amount=50000)
    assert decision.allowed is False
    assert decision.decision == "REQUIRE_APPROVAL"
    assert decision.approval_request_id == "appr-001"
    client.close()


def test_idempotency_header_sent(client_factory):
    captured: dict[str, str | None] = {"header": None, "body_key": None}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/actions/authorize"):
            captured["header"] = request.headers.get("Idempotency-Key")
            captured["body_key"] = json.loads(request.content).get("idempotency_key")
            return json_response(200, _authorize_payload("ALLOW", DECISION_ALLOW))
        return json_response(
            201,
            {"rai_session_id": SESSION_ID, "trajectory_id": TRAJECTORY_ID},
        )

    client = client_factory(httpx.MockTransport(handler))
    session = client.start_session()
    key = "stable-idem-key-123"
    session.authorize_action(tool="create_order", idempotency_key=key)
    assert captured["header"] == key
    assert captured["body_key"] == key
    client.close()


def test_unavailable_fail_closed(client_factory):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out")

    client = client_factory(httpx.MockTransport(handler))
    with pytest.raises(RAIError) as exc:
        client.health()
    assert exc.value.code == "RAI_UNAVAILABLE"
    assert exc.value.retryable is True
    client.close()


def test_health_calls_sdk_v1_endpoint(client_factory):
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        return json_response(200, {"api_version": "v1"})

    client = client_factory(httpx.MockTransport(handler))
    result = client.health()
    assert seen == {"method": "GET", "path": "/sdk/v1/health"}
    assert result["api_version"] == "v1"
    client.close()


def test_report_execution_via_client(client_factory):
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == f"/sdk/v1/actions/{DECISION_ALLOW}/execution":
            seen.update(json.loads(request.content))
            return json_response(200, {"ok": True})
        return json_response(404, {"detail": {"error": "NOT_FOUND"}})

    client = client_factory(httpx.MockTransport(handler))
    result = client.report_execution(
        DECISION_ALLOW,
        status="FAILED",
        error_metadata={"code": "TIMEOUT"},
    )
    assert result["ok"] is True
    assert seen["status"] == "FAILED"
    assert seen["error_metadata"] == {"code": "TIMEOUT"}
    client.close()


def test_start_session_delegation_flags(client_factory):
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/sdk/v1/sessions":
            seen.update(json.loads(request.content))
            return json_response(201, {"rai_session_id": SESSION_ID})
        return json_response(404, {"detail": {"error": "NOT_FOUND"}})

    client = client_factory(httpx.MockTransport(handler))
    client.start_session(
        delegation_id="del-1",
        allow_ended_session_reuse=True,
    )
    assert seen["delegation_id"] == "del-1"
    assert seen["allow_ended_session_reuse"] is True
    client.close()


def test_record_usage_and_complete_span(client_factory):
    calls: list[tuple[str, str, dict[str, Any]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        calls.append((request.method, request.url.path, body))
        if request.url.path == "/sdk/v1/sessions":
            return json_response(201, {"rai_session_id": SESSION_ID})
        if request.url.path.endswith("/metering/spans"):
            return json_response(200, {"span_id": "span-1"})
        if "/metering/spans/span-1" in request.url.path:
            return json_response(200, {"completed": True})
        return json_response(404, {"detail": {"error": "NOT_FOUND"}})

    client = client_factory(httpx.MockTransport(handler))
    session = client.start_session()
    session.record_model_call(
        provider="openai",
        model="gpt-4o",
        input_tokens=10,
        output_tokens=5,
        provider_cost=0.01,
    )
    session.complete_metering_span("span-1", output_tokens=8)
    assert calls[1][0] == "POST"
    assert calls[1][2]["usage"]["input_tokens"] == 10
    assert calls[1][2]["cost"]["source"] == "PROVIDER_RESPONSE"
    assert calls[2][0] == "PATCH"
    client.close()


def test_authorize_data_access(client_factory):
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/sdk/v1/sessions":
            return json_response(201, {"rai_session_id": SESSION_ID})
        if request.url.path.endswith("/data-access/authorize"):
            seen.update(json.loads(request.content))
            return json_response(200, {"decision": "ALLOW"})
        return json_response(404, {"detail": {"error": "NOT_FOUND"}})

    client = client_factory(httpx.MockTransport(handler))
    session = client.start_session()
    result = session.authorize_data_access(
        resource="customer.profile",
        fields=["email"],
    )
    assert result["decision"] == "ALLOW"
    assert seen["resource"] == "customer.profile"
    assert seen["access_mode"] == "READ"
    client.close()


def test_get_decision_and_approval_status(client_factory):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/sdk/v1/decisions/dec-1":
            return json_response(
                200,
                {
                    "decision": "REQUIRE_APPROVAL",
                    "decision_id": "dec-1",
                    "approval": {"approval_request_id": "apr-1"},
                },
            )
        if request.url.path == "/sdk/v1/approvals/apr-1":
            return json_response(200, {"status": "PENDING"})
        return json_response(404, {"detail": {"error": "NOT_FOUND"}})

    client = client_factory(httpx.MockTransport(handler))
    decision = client.get_decision("dec-1")
    assert decision.decision == "REQUIRE_APPROVAL"
    assert decision.approval_request_id == "apr-1"
    assert client.get_approval_status("apr-1")["status"] == "PENDING"
    client.close()
