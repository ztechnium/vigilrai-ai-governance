"""Native client hook payload normalization helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

CONTEXT_METADATA_KEYS = frozenset(
    {
        "conversation_id",
        "generation_id",
        "session_id",
        "model",
        "cursor_version",
        "workspace_roots",
        "user_email",
        "transcript_path",
        "hook_event_name",
    }
)


@dataclass
class ParsedHookPayload:
    native_mcp_name: str | None
    native_tool_name: str | None
    parameters: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None

    @property
    def ok(self) -> bool:
        return self.error_code is None


def extract_context_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    """Preserve observational client fields; never treat as authority."""
    return {key: payload[key] for key in CONTEXT_METADATA_KEYS if key in payload}


def parse_tool_input(raw: Any) -> tuple[dict[str, Any] | None, str | None]:
    """Parse tool input with fail-closed semantics for malformed JSON strings."""
    if raw is None or raw == "":
        return {}, None
    if isinstance(raw, dict):
        return dict(raw), None
    if isinstance(raw, str):
        stripped = raw.strip()
        if not stripped:
            return {}, None
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return None, "Malformed tool_input JSON"
        if parsed is None:
            return {}, None
        if isinstance(parsed, dict):
            return parsed, None
        return {"value": parsed}, None
    if isinstance(raw, (list, int, float, bool)):
        return {"value": raw}, None
    return None, "Unsupported tool_input type"


def extract_cursor_mcp_fields(payload: dict[str, Any]) -> ParsedHookPayload:
    """Normalize Cursor beforeMCPExecution fields from the observed payload shape.

    Source of truth for MCP identity:
      1. command
      2. mcp_server_name / mcpServerName
      3. server_name
    """
    native_mcp = (
        payload.get("command")
        or payload.get("mcp_server_name")
        or payload.get("mcpServerName")
        or payload.get("server_name")
        or payload.get("mcp")
    )
    if isinstance(native_mcp, str):
        native_mcp = native_mcp.strip() or None
    else:
        native_mcp = None

    native_tool = (
        payload.get("tool_name") or payload.get("toolName") or payload.get("name")
    )
    if isinstance(native_tool, str):
        native_tool = native_tool.strip() or None
    else:
        native_tool = None

    raw_input = (
        payload.get("tool_input")
        if "tool_input" in payload
        else payload.get("toolInput")
        if "toolInput" in payload
        else payload.get("arguments")
        if "arguments" in payload
        else payload.get("input")
        if "input" in payload
        else payload.get("args")
    )
    parameters, parse_error = parse_tool_input(raw_input)
    if parse_error:
        return ParsedHookPayload(
            native_mcp_name=native_mcp,
            native_tool_name=native_tool,
            parameters={},
            context=extract_context_metadata(payload),
            error_code="INVALID_HOOK_PAYLOAD",
            error_message=parse_error,
        )

    return ParsedHookPayload(
        native_mcp_name=native_mcp,
        native_tool_name=native_tool,
        parameters=parameters or {},
        context=extract_context_metadata(payload),
    )


def extract_generic_tool_fields(payload: dict[str, Any]) -> ParsedHookPayload:
    """Normalize Claude/Gemini-style tool payloads."""
    native_mcp = payload.get("mcp_server_name") or payload.get("mcp")
    if isinstance(native_mcp, str):
        native_mcp = native_mcp.strip() or None
    else:
        native_mcp = None

    native_tool = payload.get("tool_name") or payload.get("name")
    if isinstance(native_tool, str):
        native_tool = native_tool.strip() or None
    else:
        native_tool = None

    raw_input = (
        payload.get("tool_input")
        if "tool_input" in payload
        else payload.get("input")
        if "input" in payload
        else payload.get("args")
    )
    parameters, parse_error = parse_tool_input(raw_input)
    if parse_error:
        return ParsedHookPayload(
            native_mcp_name=native_mcp,
            native_tool_name=native_tool,
            parameters={},
            context={},
            error_code="INVALID_HOOK_PAYLOAD",
            error_message=parse_error,
        )

    return ParsedHookPayload(
        native_mcp_name=native_mcp,
        native_tool_name=native_tool,
        parameters=parameters or {},
    )
