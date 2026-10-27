"""Shared test utilities (no live server required)."""

from __future__ import annotations

import json
from typing import Any

import httpx

BASE_URL = "https://rai.example.com"
API_KEY = "rai_test_secret_key_abc123"
INTEGRATION_ID = "int-test-001"


def json_response(status: int, payload: dict[str, Any] | None = None) -> httpx.Response:
    body = b"" if payload is None else json.dumps(payload).encode()
    return httpx.Response(status, json=payload, content=body)
