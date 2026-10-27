"""RAIError and fail-closed behavior tests."""

from __future__ import annotations

import httpx
import pytest
from helpers import API_KEY, BASE_URL, INTEGRATION_ID, json_response
from rai_sdk import RAIClient, RAIError


def test_rai_error_attributes():
    err = RAIError(
        "TENANT_SUSPENDED",
        "Organization suspended",
        retryable=False,
        details={"org_id": "1"},
        status_code=403,
    )
    assert err.code == "TENANT_SUSPENDED"
    assert err.message == "Organization suspended"
    assert err.retryable is False
    assert err.details == {"org_id": "1"}
    assert err.status_code == 403
    assert "TENANT_SUSPENDED" in str(err)


def test_api_error_from_structured_response(client_factory):
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(
            403,
            {
                "detail": {
                    "error": "TENANT_SUSPENDED",
                    "message": "Organization is suspended",
                    "retryable": False,
                }
            },
        )

    client = client_factory(httpx.MockTransport(handler))
    with pytest.raises(RAIError) as exc:
        client.heartbeat()
    assert exc.value.code == "TENANT_SUSPENDED"
    assert exc.value.status_code == 403
    assert exc.value.retryable is False
    client.close()


def test_api_error_redacts_api_key_in_message(client_factory):
    secret = API_KEY

    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(
            400,
            {
                "detail": {
                    "error": "INVALID_REQUEST",
                    "message": f"Invalid key {secret}",
                }
            },
        )

    client = client_factory(httpx.MockTransport(handler))
    with pytest.raises(RAIError) as exc:
        client.heartbeat()
    assert secret not in exc.value.message
    assert "***" in exc.value.message
    client.close()


def test_fail_closed_on_network_error(client_factory):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = client_factory(httpx.MockTransport(handler))
    with pytest.raises(RAIError) as exc:
        client.heartbeat()
    assert exc.value.code == "RAI_UNAVAILABLE"
    assert exc.value.retryable is True
    client.close()


def test_fail_closed_on_timeout(client_factory):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("read timed out")

    client = client_factory(httpx.MockTransport(handler))
    with pytest.raises(RAIError) as exc:
        client.heartbeat()
    assert exc.value.code == "RAI_UNAVAILABLE"
    client.close()


def test_fail_closed_disabled_propagates_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = RAIClient(
        base_url=BASE_URL,
        api_key=API_KEY,
        integration_id=INTEGRATION_ID,
        fail_closed=False,
    )
    client._http = httpx.Client(
        base_url=client.base_url,
        timeout=client.timeout,
        headers=dict(client._http.headers),
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(httpx.ConnectError):
        client.heartbeat()
    client.close()


def test_network_error_redacts_api_key(client_factory):
    secret = API_KEY

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"auth header was {secret}")

    client = client_factory(httpx.MockTransport(handler))
    with pytest.raises(RAIError) as exc:
        client.heartbeat()
    assert secret not in exc.value.message
    assert "***" in exc.value.message
    client.close()


def test_decision_report_execution_requires_decision_id():
    from rai_sdk import Decision

    decision = Decision(decision="ALLOW", decision_id=None)
    client = RAIClient(
        base_url=BASE_URL,
        api_key=API_KEY,
        integration_id=INTEGRATION_ID,
    )
    with pytest.raises(RAIError) as exc:
        decision.report_execution(client, status="SUCCEEDED")
    assert exc.value.code == "INVALID_REQUEST"
    client.close()
