"""Deterministic trajectory correlation / session-key rules."""

from __future__ import annotations

from typing import Any
from uuid import UUID


def build_session_key(
    *,
    runtime_identity_id: UUID,
    client_integration_id: UUID | None = None,
    conversation_id: str | None = None,
    client_session_id: str | None = None,
    correlation_id: str | None = None,
    generation_id: str | None = None,
) -> str:
    """
    Build a deterministic trajectory session key.

    Conversation ID is a grouping key only — never a trajectory identity.

    Preferred turn / request identifiers (in order):
        client_session_id (SDK external_session_id / turn id)
        generation_id (Cursor-style turn / generation)
        correlation_id
        runtime_identity fallback (single-shot)

    When client_session_id is present but equals conversation_id (common Cursor
    aliasing), prefer generation_id so one chat thread does not collapse every
    generation into a single trajectory.
    """
    rid = str(runtime_identity_id)
    cid = str(client_integration_id) if client_integration_id else "_"

    turn_session = client_session_id
    if (
        turn_session
        and conversation_id
        and turn_session == conversation_id
        and generation_id
    ):
        turn_session = None

    if turn_session:
        return f"sess:{turn_session}|ri:{rid}|ci:{cid}"
    if generation_id:
        return f"gen:{generation_id}|ri:{rid}"
    if correlation_id:
        return f"corr:{correlation_id}|ri:{rid}"
    return f"ri:{rid}|ci:{cid}"


def extract_client_session_fields(
    client_context: dict[str, Any] | None,
) -> dict[str, str | None]:
    """Pull stable session identifiers from WP4 receipt client_context."""
    ctx = client_context or {}
    return {
        "conversation_id": _as_optional_str(ctx.get("conversation_id")),
        "client_session_id": _as_optional_str(ctx.get("session_id")),
        "generation_id": _as_optional_str(ctx.get("generation_id")),
        "observed_model": _as_optional_str(ctx.get("observed_model")),
        "client_type": _as_optional_str(ctx.get("client_type")),
        "hook_event": _as_optional_str(ctx.get("hook_event")),
        "client_version": _as_optional_str(ctx.get("client_version")),
    }


def _as_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
