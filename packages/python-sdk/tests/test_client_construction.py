"""RAIClient construction and secret-safe repr tests."""

from __future__ import annotations

import httpx
from helpers import API_KEY, BASE_URL, INTEGRATION_ID, json_response
from rai_sdk import RAIClient, __version__


def test_public_import():
    from rai_sdk import RAIClient as ImportedClient

    assert ImportedClient is RAIClient


def test_construction_strips_trailing_slash():
    client = RAIClient(
        base_url="https://rai.example.com/",
        api_key=API_KEY,
        integration_id=INTEGRATION_ID,
    )
    assert client.base_url == BASE_URL
    client.close()


def test_default_options():
    client = RAIClient(
        base_url=BASE_URL,
        api_key=API_KEY,
        integration_id=INTEGRATION_ID,
    )
    assert client.timeout == 30.0
    assert client.fail_closed is True
    assert client.sdk_version == __version__
    client.close()


def test_repr_never_includes_api_key():
    client = RAIClient(
        base_url=BASE_URL,
        api_key=API_KEY,
        integration_id=INTEGRATION_ID,
    )
    text = repr(client)
    assert "RAIClient" in text
    assert API_KEY not in text
    assert "api_key" not in text
    assert INTEGRATION_ID in text
    client.close()


def test_context_manager_closes_client():
    with RAIClient(
        base_url=BASE_URL,
        api_key=API_KEY,
        integration_id=INTEGRATION_ID,
    ) as client:
        assert not client._http.is_closed
    assert client._http.is_closed


def test_auth_header_set(client_factory):
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["agent_key"] = request.headers.get("X-RAI-Agent-Key", "")
        seen["sdk_version"] = request.headers.get("X-RAI-SDK-Version", "")
        return json_response(200, {"api_version": "v1", "ok": True})

    client = client_factory(httpx.MockTransport(handler))
    client.health()
    assert seen["agent_key"] == API_KEY
    assert seen["sdk_version"] == __version__
    client.close()
