"""Content handling, digests, and secret redaction for WP5 evidence."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from rai_gateway.evidence.domain import (
    CONTENT_PAYLOAD_FIELDS,
    ContentHandlingMode,
    RedactionStatus,
)

_SENSITIVE_KEY_FRAGMENTS = (
    "secret",
    "password",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "private_key",
    "rai_agent_key",
    "access_key",
    "session_secret",
)

# Usage / FinOps metrics contain "token" but are not secrets.
_SENSITIVE_KEY_ALLOWLIST = frozenset(
    {
        "token_usage",
        "estimated_input_tokens",
        "estimated_output_tokens",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "prompt_tokens",
        "completion_tokens",
        "cached_input_tokens",
        "cached_tokens",
        "reasoning_tokens",
        "max_tokens",
        "max_output_tokens",
    }
)

_SENSITIVE_EXACT_KEYS = frozenset(
    {
        "authorization",
        "api_key",
        "password",
        "secret",
        "token",
        "rai_agent_key",
        "x-rai-agent-key",
        "access_token",
        "refresh_token",
        "client_secret",
        "private_key",
        "mcp_credentials",
        "transcript_path",
    }
)

_SECRET_PATTERNS = (
    re.compile(r"(?i)bearer\s+[a-z0-9\-._~+/]+=*"),
    re.compile(r"(?i)sk-[a-z0-9]{20,}"),
    re.compile(r"(?i)rai_[a-z0-9_\-]{16,}"),
    re.compile(
        r"(?i)-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?"
        r"-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    ),
)


class RedactionError(RuntimeError):
    """Raised when secret redaction cannot safely complete."""


def canonical_json_bytes(value: Any) -> bytes:
    """Deterministic JSON encoding for digests."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def sha256_digest(value: Any) -> str:
    """SHA-256 hex digest of a JSON-serializable value or raw string/bytes."""
    if isinstance(value, bytes):
        payload = value
    elif isinstance(value, str):
        payload = value.encode("utf-8")
    else:
        payload = canonical_json_bytes(value)
    return hashlib.sha256(payload).hexdigest()


def _key_is_sensitive(key: str) -> bool:
    lowered = key.lower()
    if lowered in _SENSITIVE_KEY_ALLOWLIST:
        return False
    if lowered in _SENSITIVE_EXACT_KEYS:
        return True
    return any(fragment in lowered for fragment in _SENSITIVE_KEY_FRAGMENTS)


def _scrub_string(value: str) -> str:
    scrubbed = value
    for pattern in _SECRET_PATTERNS:
        scrubbed = pattern.sub("[REDACTED]", scrubbed)
    return scrubbed


def redact_secrets(value: Any) -> Any:
    """Recursively redact secrets from nested structures."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if _key_is_sensitive(str(key)):
                out[key] = "[REDACTED]"
            else:
                out[key] = redact_secrets(item)
        return out
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    if isinstance(value, str):
        return _scrub_string(value)
    return value


def _metadata_only(scrubbed: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in scrubbed.items()
        if key not in CONTENT_PAYLOAD_FIELDS
    }


def apply_content_handling(
    payload: dict[str, Any] | None,
    mode: ContentHandlingMode | str,
    *,
    sensitive_fields: frozenset[str] | None = None,
) -> tuple[dict[str, Any] | None, RedactionStatus, str | None]:
    """
    Apply content handling mode and return (stored_payload, redaction_status, digest).

    Digest is always computed over the secret-scrubbed logical payload before
    mode-specific omission, so integrity checks remain meaningful.

    REDACTED stores scrubbed readable content (not blank placeholders).
    On redaction failure, falls back to metadata/digest-only and returns FAILED.
    """
    mode_value = mode.value if isinstance(mode, ContentHandlingMode) else str(mode)
    if payload is None:
        return None, RedactionStatus.NOT_REQUIRED, None

    try:
        scrubbed = redact_secrets(payload)
        if not isinstance(scrubbed, dict):
            raise RedactionError("redact_secrets did not return a dict")
    except Exception as exc:  # noqa: BLE001 — fail closed on any redaction error
        # Never persist raw content when redaction fails.
        digest = sha256_digest({"redaction_failed": True, "error": type(exc).__name__})
        safe_meta = {
            key: ("[REDACTION_FAILED]" if key in CONTENT_PAYLOAD_FIELDS else value)
            for key, value in payload.items()
            if key not in CONTENT_PAYLOAD_FIELDS
        }
        safe_meta["content_status"] = "REDACTION_FAILED"
        return safe_meta, RedactionStatus.FAILED, digest

    digest = sha256_digest(scrubbed)
    content_fields = sensitive_fields or CONTENT_PAYLOAD_FIELDS

    if mode_value == ContentHandlingMode.DO_NOT_STORE.value:
        return None, RedactionStatus.OMITTED, digest

    if mode_value == ContentHandlingMode.HASH_ONLY.value:
        return {"content_digest": digest}, RedactionStatus.HASHED, digest

    if mode_value == ContentHandlingMode.METADATA_ONLY.value:
        return _metadata_only(scrubbed), RedactionStatus.APPLIED, digest

    if mode_value == ContentHandlingMode.REDACTED.value:
        # Keep inspectable text after secret scrubbing; mark policy as applied.
        return scrubbed, RedactionStatus.APPLIED, digest

    # FULL — still scrub secrets.
    changed = scrubbed != payload
    status = RedactionStatus.APPLIED if changed else RedactionStatus.NOT_REQUIRED
    # Ensure content field set is respected for consistency when callers pass overrides.
    if sensitive_fields:
        filtered = {
            key: (scrubbed[key] if key in scrubbed else value)
            for key, value in scrubbed.items()
        }
        return filtered, status, digest
    _ = content_fields  # reserved for callers that narrow fields
    return scrubbed, status, digest


def extract_inline_content(payload: dict[str, Any] | None) -> str | None:
    """Pick the primary inspectable text field from a stored payload."""
    if not payload:
        return None
    for key in ("prompt", "output", "content", "text", "result"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
        if value is not None and not isinstance(value, (dict, list)):
            text = str(value).strip()
            if text:
                return text
    for key in ("parameters", "result_payload"):
        value = payload.get(key)
        if value is None:
            continue
        if isinstance(value, str) and value.strip():
            return value
        try:
            return json.dumps(value, sort_keys=True, default=str)
        except (TypeError, ValueError):
            continue
    return None


def content_preview(
    payload: dict[str, Any] | None, *, max_len: int = 120
) -> str | None:
    """Short safe preview for timeline/evidence lists."""
    text = extract_inline_content(payload)
    if not text:
        return None
    collapsed = " ".join(text.split())
    if len(collapsed) <= max_len:
        return collapsed
    return collapsed[: max_len - 1].rstrip() + "…"


def content_status_for_mode(mode: str | ContentHandlingMode) -> str:
    """UI/API status label when content body is absent."""
    mode_value = mode.value if isinstance(mode, ContentHandlingMode) else str(mode)
    if mode_value == ContentHandlingMode.DO_NOT_STORE.value:
        return "INTENTIONALLY_NOT_RETAINED"
    if mode_value == ContentHandlingMode.METADATA_ONLY.value:
        return "NOT_STORED"
    if mode_value == ContentHandlingMode.HASH_ONLY.value:
        return "DIGEST_ONLY"
    return "NOT_AVAILABLE"
