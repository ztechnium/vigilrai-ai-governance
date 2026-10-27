"""Cursor + Atlassian regression for WP4 payload mapping."""

from __future__ import annotations

from uuid import uuid4

from rai_gateway.client_hooks.domain import NativeHookEvent
from rai_gateway.client_hooks.service import ClientHookService
from rai_gateway.identity.domain import DelegatorType
from rai_gateway.identity.service import (
    CredentialService,
    DelegationService,
    RuntimeIdentityService,
)
from rai_gateway.models.registry import MCPServer, ToolResource
from rai_gateway.registry.domain import AgentStatus, AgentVersionStatus, AISystemStatus
from rai_gateway.registry.seed_mcp_catalog import (
    DEFAULT_SEED_PATH,
    MCPSeedCatalogService,
)
from rai_gateway.registry.service import RegistryService
from rai_gateway.runtime_enforcement.domain import RuntimeEnforcementReasonCode


def _atlassian_runtime_stack(db_session) -> dict:
    MCPSeedCatalogService(db_session).seed(DEFAULT_SEED_PATH)
    registry = RegistryService(db_session)

    mcp = db_session.query(MCPServer).filter(MCPServer.server_key == "atlassian").one()
    tool = (
        db_session.query(ToolResource)
        .filter(ToolResource.tool_key == "atlassian.getAccessibleAtlassianResources")
        .one()
    )
    search_tool = (
        db_session.query(ToolResource)
        .filter(ToolResource.tool_key == "atlassian.search")
        .one()
    )
    jql_tool = (
        db_session.query(ToolResource)
        .filter(ToolResource.tool_key == "atlassian.searchJiraIssuesUsingJql")
        .one()
    )
    for row in (tool, search_tool, jql_tool):
        row.status = "ACTIVE"
    mcp.status = "ACTIVE"
    db_session.commit()

    suffix = uuid4().hex[:8]
    system = registry.create_ai_system(
        system_key=f"cursor-atlassian-sys-{suffix}",
        name="Cursor Atlassian Sys",
        created_by="tester",
    )
    for status in (AISystemStatus.UNDER_REVIEW, AISystemStatus.APPROVED):
        registry.transition_ai_system(system.id, status.value, updated_by="tester")

    agent = registry.create_agent(
        system.id,
        agent_key=f"cursor-atlassian-agent-{suffix}",
        name="Atlassian Agent",
        created_by="tester",
    )
    for status in (AgentStatus.UNDER_REVIEW, AgentStatus.APPROVED):
        registry.transition_agent(agent.id, status.value, updated_by="tester")

    version = registry.create_agent_version(agent.id, created_by="tester")
    # MCP-only dependency exposes all authoritative tools on the MCP.
    registry.add_version_dependency(
        version.id, resource_type="mcp_server", resource_id=mcp.id
    )
    for status in (AgentVersionStatus.UNDER_REVIEW, AgentVersionStatus.APPROVED):
        registry.transition_agent_version(version.id, status.value, updated_by="tester")

    identity = RuntimeIdentityService(db_session).create_runtime_identity(
        agent_id=agent.id,
        agent_version_id=version.id,
        name="Cursor Atlassian Runtime",
        created_by="tester",
    )
    issued = CredentialService(db_session).issue_credential(
        identity.id, created_by="tester"
    )
    delegation = DelegationService(db_session).create_delegation(
        delegator_type=DelegatorType.HUMAN.value,
        delegator_id="tester",
        delegate_runtime_identity_id=identity.id,
        scope={
            "mcp_server_ids": [str(mcp.id)],
            "tool_ids": [str(tool.id), str(search_tool.id), str(jql_tool.id)],
        },
        created_by="tester",
    )
    return {
        "mcp": mcp,
        "tool": tool,
        "search_tool": search_tool,
        "jql_tool": jql_tool,
        "identity": identity,
        "delegation": delegation,
        "credential_secret": issued.plaintext_secret,
        "version": version,
        "registry": registry,
    }


OBSERVED_PAYLOAD = {
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


def test_cursor_atlassian_observed_payload_allows(
    db_session, monkeypatch, test_organization
) -> None:
    monkeypatch.setenv("RAI_HOOK_DEBUG", "1")
    stack = _atlassian_runtime_stack(db_session)
    svc = ClientHookService(db_session)
    result = svc.authorize_hook(
        NativeHookEvent(
            client_type="cursor",
            hook_event="beforeMCPExecution",
            payload=OBSERVED_PAYLOAD,
            delegation_id=stack["delegation"].id,
        ),
        credential_secret=stack["credential_secret"],
    )
    assert result.allowed is True
    assert result.client_response["permission"] == "allow"
    assert result.debug is not None
    assert result.debug["native_mcp"] == "atlassian"
    assert result.debug["native_tool"] == "getAccessibleAtlassianResources"
    assert result.debug["tool_input"] == {}
    assert result.debug["mapped_mcp_id"] == str(stack["mcp"].id)
    assert result.debug["mapped_tool_id"] == str(stack["tool"].id)


def test_cursor_atlassian_malformed_tool_input_blocks(
    db_session, test_organization
) -> None:
    stack = _atlassian_runtime_stack(db_session)
    svc = ClientHookService(db_session)
    payload = dict(OBSERVED_PAYLOAD)
    payload["tool_input"] = "{bad"
    result = svc.authorize_hook(
        NativeHookEvent(
            client_type="cursor",
            hook_event="beforeMCPExecution",
            payload=payload,
            delegation_id=stack["delegation"].id,
        ),
        credential_secret=stack["credential_secret"],
    )
    assert result.allowed is False
    assert result.reason_code == "INVALID_HOOK_PAYLOAD"


def test_cursor_atlassian_unknown_tool_blocks(db_session, test_organization) -> None:
    stack = _atlassian_runtime_stack(db_session)
    svc = ClientHookService(db_session)
    payload = dict(OBSERVED_PAYLOAD)
    payload["tool_name"] = "totallyUnknownTool"
    result = svc.authorize_hook(
        NativeHookEvent(
            client_type="cursor",
            hook_event="beforeMCPExecution",
            payload=payload,
            delegation_id=stack["delegation"].id,
        ),
        credential_secret=stack["credential_secret"],
    )
    assert result.allowed is False
    assert result.reason_code == "RESOURCE_NOT_REGISTERED"


def test_cursor_atlassian_seeded_jql_tool_allows(
    db_session, monkeypatch, test_organization
) -> None:
    monkeypatch.setenv("RAI_HOOK_DEBUG", "1")
    stack = _atlassian_runtime_stack(db_session)
    payload = dict(OBSERVED_PAYLOAD)
    payload["tool_name"] = "searchJiraIssuesUsingJql"
    payload["tool_input"] = (
        '{"cloudId":"example.atlassian.net","jql":"sprint in openSprints()","maxResults":50}'
    )
    result = ClientHookService(db_session).authorize_hook(
        NativeHookEvent(
            client_type="cursor",
            hook_event="beforeMCPExecution",
            payload=payload,
            delegation_id=stack["delegation"].id,
        ),
        credential_secret=stack["credential_secret"],
    )
    assert result.allowed is True
    assert result.debug is not None
    assert result.debug["native_tool"] == "searchJiraIssuesUsingJql"
    assert result.debug["mapped_tool_id"] == str(stack["jql_tool"].id)


def test_cursor_atlassian_remove_from_delegation(db_session, test_organization) -> None:
    stack = _atlassian_runtime_stack(db_session)
    # Only search is delegated — getAccessible... must fail closed.
    narrow = DelegationService(db_session).create_delegation(
        delegator_type=DelegatorType.HUMAN.value,
        delegator_id="tester",
        delegate_runtime_identity_id=stack["identity"].id,
        scope={
            "mcp_server_ids": [str(stack["mcp"].id)],
            "tool_ids": [str(stack["search_tool"].id)],
        },
        created_by="tester",
    )
    svc = ClientHookService(db_session)
    result = svc.authorize_hook(
        NativeHookEvent(
            client_type="cursor",
            hook_event="beforeMCPExecution",
            payload=OBSERVED_PAYLOAD,
            delegation_id=narrow.id,
        ),
        credential_secret=stack["credential_secret"],
    )
    assert result.allowed is False
    assert (
        result.reason_code
        == RuntimeEnforcementReasonCode.AUTHORITY_SCOPE_EXCEEDED.value
    )


def test_cursor_atlassian_remove_from_catalog(db_session, test_organization) -> None:
    stack = _atlassian_runtime_stack(db_session)
    db_session.delete(stack["tool"])
    db_session.commit()
    svc = ClientHookService(db_session)
    result = svc.authorize_hook(
        NativeHookEvent(
            client_type="cursor",
            hook_event="beforeMCPExecution",
            payload=OBSERVED_PAYLOAD,
            delegation_id=stack["delegation"].id,
        ),
        credential_secret=stack["credential_secret"],
    )
    assert result.allowed is False
    assert result.reason_code == "RESOURCE_NOT_REGISTERED"
