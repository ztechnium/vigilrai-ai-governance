"""Deterministic action canonicalization and digest for WP3."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from rai_gateway.approval.domain import ProposedAction


def _normalize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(k): _normalize_value(v)
            for k, v in sorted(value.items(), key=lambda x: x[0])
        }
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    if isinstance(value, float):
        return format(value, ".15g")
    if value is None:
        return None
    return value


def canonicalize_action(action: ProposedAction) -> tuple[dict[str, Any], str]:
    """Return canonical payload and SHA-256 hex digest."""
    payload = _normalize_value(action.to_dict())
    serialized = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return payload, digest
