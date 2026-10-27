"""GitHub and Frappe MCP mapping regressions for WP4 closure."""

from __future__ import annotations

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


def _seeded_runtime(
    db_session, *, server_key: str, tool_key: str, system_key: str
) -> dict:
    MCPSeedCatalogService(db_session).seed(DEFAULT_SEED_PATH)
    registry = RegistryService(db_session)
    mcp = db_session.query(MCPServer).filter(MCPServer.server_key == server_key).one()
    tool = (
        db_session.query(ToolResource).filter(ToolResource.tool_key == tool_key).one()
    )
    tool.status = "ACTIVE"
    mcp.status = "ACTIVE"
    db_session.commit()

    system = registry.create_ai_system(
        system_key=system_key,
        name=f"{server_key} Sys",
        created_by="tester",
    )
    for status in (AISystemStatus.UNDER_REVIEW, AISystemStatus.APPROVED):
        registry.transition_ai_system(system.id, status.value, updated_by="tester")
    agent = registry.create_agent(
        system.id,
        agent_key=f"{system_key}-agent",
        name=f"{server_key} Agent",
        created_by="tester",
    )
    for status in (AgentStatus.UNDER_REVIEW, AgentStatus.APPROVED):
        registry.transition_agent(agent.id, status.value, updated_by="tester")
    version = registry.create_agent_version(agent.id, created_by="tester")
    registry.add_version_dependency(
        version.id, resource_type="mcp_server", resource_id=mcp.id
    )
    for status in (AgentVersionStatus.UNDER_REVIEW, AgentVersionStatus.APPROVED):
        registry.transition_agent_version(version.id, status.value, updated_by="tester")
    identity = RuntimeIdentityService(db_session).create_runtime_identity(
        agent_id=agent.id,
        agent_version_id=version.id,
        name=f"{server_key} Runtime",
        created_by="tester",
    )
    issued = CredentialService(db_session).issue_credential(
        identity.id, created_by="tester"
    )
    DelegationService(db_session).create_delegation(
        delegator_type=DelegatorType.HUMAN.value,
        delegator_id="tester@example.com",
        delegate_runtime_identity_id=identity.id,
        scope={
            "mcp_server_ids": [str(mcp.id)],
            "tool_ids": [str(tool.id)],
        },
        created_by="tester",
    )
    return {
        "credential": issued.plaintext_secret,
        "mcp": mcp,
        "tool": tool,
        "identity": identity,
    }


def _native_name(tool: ToolResource) -> str:
    meta = tool.metadata_ or {}
    return str(meta.get("native_name") or tool.name)


def test_github_read_tool_maps_and_authorizes(db_session, test_organization):
    stack = _seeded_runtime(
        db_session,
        server_key="github",
        tool_key="github.read_repository",
        system_key="github-map",
    )
    result = ClientHookService(db_session).authorize_hook(
        NativeHookEvent(
            client_type="cursor",
            hook_event="beforeMCPExecution",
            payload={
                "command": "github",
                "tool_name": _native_name(stack["tool"]),
                "tool_input": "{}",
            },
        ),
        credential_secret=stack["credential"],
    )
    assert result.allowed is True
    assert result.receipt_id is not None
    assert result.enforcement_result.get("effect") in {"ALLOW", "MONITOR"}


def test_github_side_effect_tool_maps(db_session, test_organization):
    stack = _seeded_runtime(
        db_session,
        server_key="github",
        tool_key="github.create_issue",
        system_key="github-write",
    )
    result = ClientHookService(db_session).authorize_hook(
        NativeHookEvent(
            client_type="cursor",
            hook_event="beforeMCPExecution",
            payload={
                "command": "github",
                "tool_name": _native_name(stack["tool"]),
                "tool_input": '{"title":"test","body":"hello"}',
            },
        ),
        credential_secret=stack["credential"],
    )
    # Mapping succeeded; platform/policy may REQUIRE_APPROVAL for side-effect tools.
    assert result.reason_code not in {
        "RESOURCE_NOT_REGISTERED",
        "RESOURCE_RELATIONSHIP_INVALID",
        "INVALID_HOOK_PAYLOAD",
    }
    assert result.receipt_id is not None
    assert result.effect in {"ALLOW", "MONITOR", "REQUIRE_APPROVAL"}
    if result.effect == "REQUIRE_APPROVAL":
        assert result.approval_request_id is not None
        assert result.allowed is False
    else:
        assert result.allowed is True


def test_github_unknown_tool_fails_closed(db_session, test_organization):
    stack = _seeded_runtime(
        db_session,
        server_key="github",
        tool_key="github.read_repository",
        system_key="github-unknown",
    )
    result = ClientHookService(db_session).authorize_hook(
        NativeHookEvent(
            client_type="cursor",
            hook_event="beforeMCPExecution",
            payload={
                "command": "github",
                "tool_name": "definitely_not_a_real_github_tool",
                "tool_input": "{}",
            },
        ),
        credential_secret=stack["credential"],
    )
    assert result.allowed is False


def test_frappe_get_doc_maps_and_authorizes(db_session, test_organization):
    stack = _seeded_runtime(
        db_session,
        server_key="frappe",
        tool_key="frappe.get_doc",
        system_key="frappe-map",
    )
    result = ClientHookService(db_session).authorize_hook(
        NativeHookEvent(
            client_type="cursor",
            hook_event="beforeMCPExecution",
            payload={
                "command": "frappe",
                "tool_name": "get_doc",
                "tool_input": '{"doctype":"User","name":"Administrator"}',
            },
        ),
        credential_secret=stack["credential"],
    )
    assert result.allowed is True
    assert result.receipt_id is not None


def test_frappe_update_doc_maps(db_session, test_organization):
    stack = _seeded_runtime(
        db_session,
        server_key="frappe",
        tool_key="frappe.update_doc",
        system_key="frappe-update",
    )
    result = ClientHookService(db_session).authorize_hook(
        NativeHookEvent(
            client_type="cursor",
            hook_event="beforeMCPExecution",
            payload={
                "command": "erpnext",
                "tool_name": "update_doc",
                "tool_input": '{"doctype":"User","name":"Administrator","data":{}}',
            },
        ),
        credential_secret=stack["credential"],
    )
    # Mapping + authority succeeded; HIGH-risk update may require approval.
    assert result.reason_code not in {
        "RESOURCE_NOT_REGISTERED",
        "RESOURCE_RELATIONSHIP_INVALID",
        "INVALID_HOOK_PAYLOAD",
    }
    assert result.receipt_id is not None
    assert result.effect in {"ALLOW", "MONITOR", "REQUIRE_APPROVAL"}
    if result.effect == "REQUIRE_APPROVAL":
        assert result.approval_request_id is not None
        assert result.allowed is False
    else:
        assert result.allowed is True


def test_frappe_unknown_tool_fails_closed(db_session, test_organization):
    stack = _seeded_runtime(
        db_session,
        server_key="frappe",
        tool_key="frappe.get_doc",
        system_key="frappe-unknown",
    )
    result = ClientHookService(db_session).authorize_hook(
        NativeHookEvent(
            client_type="cursor",
            hook_event="beforeMCPExecution",
            payload={
                "command": "frappe",
                "tool_name": "totally_unknown_frappe_tool",
                "tool_input": "{}",
            },
        ),
        credential_secret=stack["credential"],
    )
    assert result.allowed is False
