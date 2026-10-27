"""Shared fixtures for WP3 approval tests."""

from __future__ import annotations

import uuid

import pytest

from rai_gateway.identity.domain import DelegatorType
from rai_gateway.identity.service import (
    DelegationService,
    RuntimeIdentityService,
)
from rai_gateway.registry.domain import AgentStatus, AgentVersionStatus, AISystemStatus
from rai_gateway.registry.service import RegistryService


@pytest.fixture()
def registry(db_session) -> RegistryService:
    return RegistryService(db_session)


@pytest.fixture()
def approval_stack(registry: RegistryService, db_session, test_organization) -> dict:
    suffix = uuid.uuid4().hex[:8]
    system = registry.create_ai_system(
        system_key=f"wp3-sys-{suffix}",
        name="WP3 System",
        created_by="tester",
    )
    for status in (AISystemStatus.UNDER_REVIEW, AISystemStatus.APPROVED):
        registry.transition_ai_system(system.id, status.value, updated_by="tester")

    agent = registry.create_agent(
        system.id,
        agent_key=f"wp3-agent-{suffix}",
        name="WP3 Agent",
        created_by="tester",
    )
    for status in (AgentStatus.UNDER_REVIEW, AgentStatus.APPROVED):
        registry.transition_agent(agent.id, status.value, updated_by="tester")

    version = registry.create_agent_version(agent.id, created_by="tester")

    mcp = registry.create_mcp_server(
        server_key=f"frappe-{suffix}",
        name="Frappe MCP",
    )
    tool = registry.create_tool_resource(
        tool_key=f"update_doc_{suffix}",
        name="Update Doc",
        mcp_server_id=mcp.id,
        consequential_action=True,
    )
    extra_tool = registry.create_tool_resource(
        tool_key=f"delete_doc_{suffix}",
        name="Delete Doc",
        mcp_server_id=mcp.id,
        consequential_action=True,
    )
    registry.add_version_dependency(
        version.id, resource_type="mcp_server", resource_id=mcp.id
    )
    registry.add_version_dependency(
        version.id, resource_type="tool", resource_id=tool.id
    )
    registry.add_version_dependency(
        version.id, resource_type="tool", resource_id=extra_tool.id
    )

    for status in (AgentVersionStatus.UNDER_REVIEW, AgentVersionStatus.APPROVED):
        registry.transition_agent_version(version.id, status.value, updated_by="tester")

    identity_service = RuntimeIdentityService(db_session)
    identity = identity_service.create_runtime_identity(
        agent_id=agent.id,
        agent_version_id=version.id,
        name="WP3 Runtime",
        created_by="tester",
    )

    delegation_service = DelegationService(db_session)
    delegation = delegation_service.create_delegation(
        delegator_type=DelegatorType.HUMAN.value,
        delegator_id="ahmed",
        delegate_runtime_identity_id=identity.id,
        scope={
            "mcp_server_ids": [str(mcp.id)],
            "tool_ids": [str(tool.id)],
        },
        created_by="tester",
    )

    return {
        "system": system,
        "agent": agent,
        "version": version,
        "mcp": mcp,
        "tool": tool,
        "extra_tool": extra_tool,
        "identity": identity,
        "delegation": delegation,
    }
