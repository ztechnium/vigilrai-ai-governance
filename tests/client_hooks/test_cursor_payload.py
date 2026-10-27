"""Tests for Cursor payload normalization."""

from __future__ import annotations

from uuid import uuid4

import pytest

from rai_gateway.client_hooks.adapters import CursorHookAdapter
from rai_gateway.client_hooks.domain import NativeHookEvent, ResourceMappingResult
from rai_gateway.client_hooks.payload import extract_cursor_mcp_fields, parse_tool_input

OBSERVED_CURSOR_PAYLOAD = {
    "conversation_id": "6fae5e1f-29d9-407f-acef-4945ae3ac21b",
    "generation_id": "e25157df-fc79-486e-b914-b73ec8469241",
    "model": "gpt-5.4-mini",
    "tool_name": "getAccessibleAtlassianResources",
    "tool_input": "{}",
    "command": "atlassian",
    "session_id": "6fae5e1f-29d9-407f-acef-4945ae3ac21b",
    "hook_event_name": "beforeMCPExecution",
    "cursor_version": "3.2.21",
    "workspace_roots": ["/tmp/rai-workspace"],
    "user_email": "developer@example.com",
    "transcript_path": "/tmp/rai-hook-transcript.jsonl",
}


def _mapping(**kwargs) -> ResourceMappingResult:
    defaults = {
        "integration_type": "mcp",
        "integration_id": uuid4(),
        "tool_id": uuid4(),
        "parameters": {},
    }
    defaults.update(kwargs)
    return ResourceMappingResult(**defaults)


def test_parse_tool_input_variants() -> None:
    assert parse_tool_input("{}") == ({}, None)
    assert parse_tool_input({"a": 1}) == ({"a": 1}, None)
    assert parse_tool_input(None) == ({}, None)
    assert parse_tool_input("") == ({}, None)
    params, err = parse_tool_input("{not-json")
    assert params is None
    assert err is not None


def test_extract_observed_cursor_payload() -> None:
    parsed = extract_cursor_mcp_fields(OBSERVED_CURSOR_PAYLOAD)
    assert parsed.ok
    assert parsed.native_mcp_name == "atlassian"
    assert parsed.native_tool_name == "getAccessibleAtlassianResources"
    assert parsed.parameters == {}
    assert parsed.context["model"] == "gpt-5.4-mini"
    assert parsed.context["user_email"] == "developer@example.com"


def test_cursor_command_preferred_over_mcp_server_name() -> None:
    parsed = extract_cursor_mcp_fields(
        {
            "command": "atlassian",
            "mcp_server_name": "other",
            "tool_name": "search",
            "tool_input": {"q": "x"},
        }
    )
    assert parsed.native_mcp_name == "atlassian"
    assert parsed.parameters == {"q": "x"}


def test_cursor_fallback_mcp_server_name() -> None:
    parsed = extract_cursor_mcp_fields(
        {
            "mcp_server_name": "frappe",
            "tool_name": "get_doc",
            "tool_input": {},
        }
    )
    assert parsed.native_mcp_name == "frappe"


def test_cursor_malformed_tool_input_fails_closed() -> None:
    parsed = extract_cursor_mcp_fields(
        {
            "command": "atlassian",
            "tool_name": "search",
            "tool_input": "{bad",
        }
    )
    assert not parsed.ok
    assert parsed.error_code == "INVALID_HOOK_PAYLOAD"


def test_cursor_adapter_normalize_observed_payload() -> None:
    adapter = CursorHookAdapter()
    event = NativeHookEvent(
        client_type="cursor",
        hook_event="beforeMCPExecution",
        payload=OBSERVED_CURSOR_PAYLOAD,
    )
    normalized = adapter.normalize_event(
        event,
        _mapping(parameters={}),
        runtime_identity_id=uuid4(),
        delegation_id=None,
    )
    assert normalized.native_mcp_name == "atlassian"
    assert normalized.native_tool_name == "getAccessibleAtlassianResources"
    assert normalized.request.parameters == {}


def test_cursor_adapter_object_tool_input() -> None:
    adapter = CursorHookAdapter()
    event = NativeHookEvent(
        client_type="cursor",
        hook_event="beforeMCPExecution",
        payload={
            "command": "atlassian",
            "tool_name": "search",
            "tool_input": {"query": "hello"},
        },
    )
    normalized = adapter.normalize_event(
        event,
        _mapping(parameters={}),
        runtime_identity_id=uuid4(),
        delegation_id=None,
    )
    assert normalized.request.parameters == {"query": "hello"}


def test_cursor_adapter_malformed_raises() -> None:
    adapter = CursorHookAdapter()
    event = NativeHookEvent(
        client_type="cursor",
        hook_event="beforeMCPExecution",
        payload={
            "command": "atlassian",
            "tool_name": "search",
            "tool_input": "{bad",
        },
    )
    with pytest.raises(ValueError):
        adapter.normalize_event(
            event,
            _mapping(parameters={}),
            runtime_identity_id=uuid4(),
            delegation_id=None,
        )
