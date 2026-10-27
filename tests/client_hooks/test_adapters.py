"""Tests for client hook adapters."""

from __future__ import annotations

from uuid import uuid4

from rai_gateway.client_hooks.adapters import (
    ClaudeCodeHookAdapter,
    CursorHookAdapter,
    GeminiCLIHookAdapter,
    get_adapter,
)
from rai_gateway.client_hooks.domain import NativeHookEvent, ResourceMappingResult


def _mapping(**kwargs) -> ResourceMappingResult:
    defaults = {
        "integration_type": "mcp",
        "integration_id": uuid4(),
        "tool_id": uuid4(),
        "parameters": {"amount": 150000},
    }
    defaults.update(kwargs)
    return ResourceMappingResult(**defaults)


def test_cursor_allow_response() -> None:
    adapter = CursorHookAdapter()
    resp = adapter.translate_allow({"effect": "ALLOW"})
    assert resp == {"permission": "allow"}


def test_cursor_deny_with_approval_message() -> None:
    adapter = CursorHookAdapter()
    resp = adapter.translate_deny(
        {
            "effect": "REQUIRE_APPROVAL",
            "approval_request_id": "apr-104",
            "human_explanation": "Needs approval",
        }
    )
    assert resp["permission"] == "deny"
    assert "APR-104" in resp["user_message"] or "apr-104" in resp["user_message"]


def test_claude_deny_response() -> None:
    adapter = ClaudeCodeHookAdapter()
    resp = adapter.translate_deny({"effect": "DENY", "human_explanation": "Blocked"})
    assert resp["decision"] == "deny"


def test_gemini_critical_failure_exit_code() -> None:
    adapter = GeminiCLIHookAdapter()
    assert adapter.critical_failure_exit_code == 2


def test_cursor_normalize_mcp_event() -> None:
    adapter = CursorHookAdapter()
    event = NativeHookEvent(
        client_type="cursor",
        hook_event="beforeMCPExecution",
        payload={
            "mcp_server_name": "frappe",
            "tool_name": "submit_po",
            "tool_input": {"amount": 150000},
        },
    )
    normalized = adapter.normalize_event(
        event,
        _mapping(parameters={}),
        runtime_identity_id=uuid4(),
        delegation_id=None,
    )
    assert normalized.request.integration_type == "mcp"
    assert normalized.request.parameters == {"amount": 150000}
    assert normalized.native_mcp_name == "frappe"
    assert normalized.native_tool_name == "submit_po"


def test_cursor_normalize_command_field() -> None:
    adapter = CursorHookAdapter()
    event = NativeHookEvent(
        client_type="cursor",
        hook_event="beforeMCPExecution",
        payload={
            "command": "atlassian",
            "tool_name": "search",
            "tool_input": "{}",
        },
    )
    normalized = adapter.normalize_event(
        event,
        _mapping(parameters={}),
        runtime_identity_id=uuid4(),
        delegation_id=None,
    )
    assert normalized.native_mcp_name == "atlassian"
    assert normalized.native_tool_name == "search"
    assert normalized.request.parameters == {}


def test_get_adapter_unknown_raises() -> None:
    try:
        get_adapter("unknown")
        raised = False
    except ValueError:
        raised = True
    assert raised
