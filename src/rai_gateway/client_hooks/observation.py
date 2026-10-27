"""Extract safe observation payloads from native client hook events."""

from __future__ import annotations

from typing import Any

from rai_gateway.client_hooks.domain import ClientType


def extract_observation_payload(
    client_type: str,
    hook_event: str,
    payload: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Build a metadata-first observation payload.

    Raw prompt/output text is included only under controlled keys so WP5
    content-handling modes can redact/hash/omit it. Secrets must still be
    scrubbed by evidence redaction before persistence.
    """
    raw = payload or {}
    base: dict[str, Any] = {
        "client_type": client_type,
        "hook_event": hook_event,
        "observed_model": _first(raw, "model", "model_name", "modelId"),
    }

    if client_type == ClientType.CURSOR.value:
        if hook_event == "beforeSubmitPrompt":
            base["prompt"] = _first(raw, "prompt", "content", "text", "message")
            base["generation_id"] = raw.get("generation_id")
        elif hook_event in {"afterAgentResponse", "afterAgentThought"}:
            base["output"] = _first(
                raw, "text", "output", "response", "content", "message"
            )
            base["generation_id"] = raw.get("generation_id")
    elif client_type == ClientType.CLAUDE_CODE.value:
        if hook_event == "UserPromptSubmit":
            base["prompt"] = _first(raw, "prompt", "content", "text")
        elif hook_event == "Stop":
            base["output"] = _first(raw, "output", "response", "text", "content")
    elif client_type == ClientType.GEMINI_CLI.value:
        if hook_event in {"BeforeAgent", "BeforeModel"}:
            base["prompt"] = _first(raw, "prompt", "content", "text", "input")
        elif hook_event in {"AfterModel", "AfterAgent"}:
            base["output"] = _first(raw, "output", "response", "text", "content")

    # Drop empty values; keep structure stable for digests.
    return {k: v for k, v in base.items() if v is not None and v != ""}


def _first(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None
