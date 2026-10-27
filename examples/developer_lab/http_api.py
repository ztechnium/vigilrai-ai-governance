"""Small JSON client for the developer lab scripts."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class ApiError(Exception):
    def __init__(self, status: int, body: Any, method: str, path: str) -> None:
        self.status = status
        self.body = body
        self.method = method
        self.path = path
        super().__init__(f"{method} {path} -> {status}: {body}")


def request_json(
    method: str,
    url: str,
    *,
    token: str | None = None,
    agent_key: str | None = None,
    payload: dict | None = None,
    timeout: float = 30,
) -> Any:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if agent_key:
        headers["X-RAI-Agent-Key"] = agent_key
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            body = raw
        raise ApiError(exc.code, body, method, url) from exc


def items_of(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        items = payload.get("items")
        if isinstance(items, list):
            return items
    return []
