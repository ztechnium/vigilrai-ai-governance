"""Shared fixtures for rai-control-plane-sdk unit tests."""

from __future__ import annotations

import httpx
import pytest
from helpers import API_KEY, BASE_URL, INTEGRATION_ID
from rai_sdk import RAIClient


@pytest.fixture()
def client_factory():
    """Build an RAIClient backed by httpx.MockTransport."""

    def _factory(handler: httpx.MockTransport) -> RAIClient:
        client = RAIClient(
            base_url=BASE_URL,
            api_key=API_KEY,
            integration_id=INTEGRATION_ID,
        )
        client._http = httpx.Client(
            base_url=client.base_url,
            timeout=client.timeout,
            headers=dict(client._http.headers),
            transport=handler,
        )
        return client

    return _factory
