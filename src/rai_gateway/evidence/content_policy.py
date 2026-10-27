"""Resolve evidence content-handling modes with org → system → agent → type precedence."""

from __future__ import annotations

from typing import Any, Mapping

from rai_gateway.core.config import settings
from rai_gateway.evidence.domain import (
    DEFAULT_CONTENT_HANDLING,
    ContentHandlingMode,
    ContentKind,
    EvidenceEventType,
    content_kind_for_event,
)

# Prompt and output stay inspectable in production. Secrets are still scrubbed.
# Tool parameters and results stay metadata-only unless demo defaults are on.
_PRODUCTION_RETAINED_KINDS = frozenset(
    {
        ContentKind.PROMPT,
        ContentKind.MODEL_REQUEST,
        ContentKind.MODEL_RESPONSE,
        ContentKind.AGENT_OUTPUT,
    }
)

# Demo/dev defaults: retain inspectable redacted prompt/response/output text.
_DEMO_KIND_DEFAULTS: dict[ContentKind, ContentHandlingMode] = {
    ContentKind.PROMPT: ContentHandlingMode.REDACTED,
    ContentKind.MODEL_REQUEST: ContentHandlingMode.REDACTED,
    ContentKind.MODEL_RESPONSE: ContentHandlingMode.REDACTED,
    ContentKind.AGENT_OUTPUT: ContentHandlingMode.REDACTED,
    ContentKind.TOOL_PARAMETERS: ContentHandlingMode.REDACTED,
    ContentKind.TOOL_RESULT: ContentHandlingMode.REDACTED,
}

_KIND_SETTING_ATTR: dict[ContentKind, str] = {
    ContentKind.PROMPT: "evidence_prompt_handling_mode",
    ContentKind.MODEL_REQUEST: "evidence_model_request_handling_mode",
    ContentKind.MODEL_RESPONSE: "evidence_model_response_handling_mode",
    ContentKind.AGENT_OUTPUT: "evidence_agent_output_handling_mode",
    ContentKind.TOOL_PARAMETERS: "evidence_tool_parameters_handling_mode",
    ContentKind.TOOL_RESULT: "evidence_tool_result_handling_mode",
}


def _parse_mode(value: Any) -> ContentHandlingMode | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    if not text:
        return None
    try:
        return ContentHandlingMode(text)
    except ValueError:
        return None


def _policy_map(raw: Mapping[str, Any] | None) -> dict[str, ContentHandlingMode]:
    if not raw:
        return {}
    out: dict[str, ContentHandlingMode] = {}
    for key, value in raw.items():
        mode = _parse_mode(value)
        if mode is not None:
            out[str(key).strip().lower()] = mode
    return out


def organization_defaults() -> dict[ContentKind, ContentHandlingMode]:
    """Organization-level defaults from settings (demo-friendly when unset)."""
    defaults: dict[ContentKind, ContentHandlingMode] = {}
    use_demo = bool(getattr(settings, "evidence_use_demo_content_defaults", True))
    for kind, attr in _KIND_SETTING_ATTR.items():
        configured = _parse_mode(getattr(settings, attr, None))
        if configured is not None:
            defaults[kind] = configured
        elif use_demo or kind in _PRODUCTION_RETAINED_KINDS:
            defaults[kind] = _DEMO_KIND_DEFAULTS.get(kind, DEFAULT_CONTENT_HANDLING)
        else:
            defaults[kind] = DEFAULT_CONTENT_HANDLING
    return defaults


def resolve_content_handling(
    event_type: str | EvidenceEventType,
    *,
    organization_policy: Mapping[str, Any] | None = None,
    ai_system_policy: Mapping[str, Any] | None = None,
    agent_policy: Mapping[str, Any] | None = None,
    evidence_type_override: str | ContentHandlingMode | None = None,
) -> ContentHandlingMode:
    """
    Resolve handling mode with precedence:

    Organization default
    → AI System override
    → Agent/Version override
    → evidence-type override (caller / explicit)
    """
    kind = content_kind_for_event(event_type)
    mode = organization_defaults().get(kind, DEFAULT_CONTENT_HANDLING)

    for policy in (organization_policy, ai_system_policy, agent_policy):
        mapped = _policy_map(policy)
        if not mapped:
            continue
        # Accept kind keys ("prompt") or event type keys ("PROMPT_OBSERVED").
        event_key = (
            event_type.value
            if isinstance(event_type, EvidenceEventType)
            else str(event_type)
        )
        candidates = (
            kind.value if kind else None,
            event_key.lower() if event_key else None,
            event_key,
        )
        for candidate in candidates:
            if candidate and candidate in mapped:
                mode = mapped[candidate]
                break
            if candidate and candidate.lower() in mapped:
                mode = mapped[candidate.lower()]
                break

    override = _parse_mode(evidence_type_override)
    if override is not None:
        mode = override
    return mode
