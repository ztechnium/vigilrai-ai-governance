"""Security and validation tests for delegation resource scope."""

from __future__ import annotations

import uuid

import pytest

from rai_gateway.identity.domain import DelegationScope
from rai_gateway.identity.errors import ScopeExceededError
from rai_gateway.identity.service import DelegationService, RuntimeIdentityService
from rai_gateway.identity.version_resources import load_version_resource_catalog
from rai_gateway.registry.domain import AgentStatus, AgentVersionStatus, AISystemStatus
from rai_gateway.registry.service import RegistryService


@pytest.fixture()
def registry(db_session) -> RegistryService:
    return RegistryService(db_session)


@pytest.fixture()
def resource_stack(registry: RegistryService, db_session, test_organization) -> dict:
    suffix = uuid.uuid4().hex[:8]
    system = registry.create_ai_system(
        system_key=f"scope-sys-{suffix}",
        name="Scope System",
        created_by="tester",
    )
    for status in (AISystemStatus.UNDER_REVIEW, AISystemStatus.APPROVED):
        registry.transition_ai_system(system.id, status.value, updated_by="tester")

    agent = registry.create_agent(
        system.id,
        agent_key=f"scope-agent-{suffix}",
        name="Scope Agent",
        created_by="tester",
    )
    for status in (AgentStatus.UNDER_REVIEW, AgentStatus.APPROVED):
        registry.transition_agent(agent.id, status.value, updated_by="tester")

    version = registry.create_agent_version(agent.id, created_by="tester")

    model_a = registry.create_model_resource(
        provider="anthropic",
        model_name="claude-sonnet",
    )
    model_b = registry.create_model_resource(
        provider="openai",
        model_name="gpt-5",
    )
    registry.add_version_dependency(
        version.id, resource_type="model", resource_id=model_a.id
    )
    registry.add_version_dependency(
        version.id, resource_type="model", resource_id=model_b.id
    )

    ds_a = registry.create_data_source(
        data_source_key=f"eng-kb-{suffix}",
        name="Engineering KB",
    )
    ds_b = registry.create_data_source(
        data_source_key=f"prod-docs-{suffix}",
        name="Production Documentation",
    )
    registry.add_version_dependency(
        version.id, resource_type="data_source", resource_id=ds_a.id
    )
    registry.add_version_dependency(
        version.id, resource_type="data_source", resource_id=ds_b.id
    )

    mcp_github = registry.create_mcp_server(
        server_key=f"github-{suffix}",
        name="GitHub MCP",
    )
    mcp_frappe = registry.create_mcp_server(
        server_key=f"frappe-{suffix}",
        name="Frappe MCP",
    )
    registry.add_version_dependency(
        version.id, resource_type="mcp_server", resource_id=mcp_github.id
    )
    registry.add_version_dependency(
        version.id, resource_type="mcp_server", resource_id=mcp_frappe.id
    )

    tool_read = registry.create_tool_resource(
        tool_key=f"read_repo_{suffix}",
        name="read_repository",
        mcp_server_id=mcp_github.id,
    )
    tool_delete = registry.create_tool_resource(
        tool_key=f"delete_repo_{suffix}",
        name="delete_repository",
        mcp_server_id=mcp_github.id,
    )
    tool_get_doc = registry.create_tool_resource(
        tool_key=f"get_doc_{suffix}",
        name="get_doc",
        mcp_server_id=mcp_frappe.id,
    )
    registry.add_version_dependency(
        version.id, resource_type="tool", resource_id=tool_read.id
    )
    registry.add_version_dependency(
        version.id, resource_type="tool", resource_id=tool_get_doc.id
    )
    # delete_repository exists globally but NOT on version

    for status in (AgentVersionStatus.UNDER_REVIEW, AgentVersionStatus.APPROVED):
        registry.transition_agent_version(version.id, status.value, updated_by="tester")

    identity_svc = RuntimeIdentityService(db_session)
    identity = identity_svc.create_runtime_identity(
        agent_id=agent.id,
        agent_version_id=version.id,
        name="Scope Runtime",
        created_by="tester",
    )

    return {
        "version": version,
        "identity": identity,
        "model_a": model_a,
        "model_b": model_b,
        "ds_a": ds_a,
        "mcp_github": mcp_github,
        "tool_read": tool_read,
        "tool_delete": tool_delete,
        "tool_get_doc": tool_get_doc,
    }


def test_model_outside_version_denied(db_session, resource_stack) -> None:
    svc = DelegationService(db_session)
    other = RegistryService(db_session).create_model_resource(
        provider="google", model_name="gemini"
    )
    with pytest.raises(ScopeExceededError):
        svc.create_delegation(
            delegator_type="HUMAN",
            delegator_id="user@example.com",
            delegate_runtime_identity_id=resource_stack["identity"].id,
            scope={"model_ids": [str(other.id)]},
            created_by="tester",
        )


def test_tool_globally_exists_but_not_on_version_denied(
    db_session, resource_stack
) -> None:
    svc = DelegationService(db_session)
    with pytest.raises(ScopeExceededError):
        svc.create_delegation(
            delegator_type="HUMAN",
            delegator_id="user@example.com",
            delegate_runtime_identity_id=resource_stack["identity"].id,
            scope={"tool_ids": [str(resource_stack["tool_delete"].id)]},
            created_by="tester",
        )


def test_child_adds_model_outside_parent_denied(db_session, resource_stack) -> None:
    svc = DelegationService(db_session)
    parent = svc.create_delegation(
        delegator_type="HUMAN",
        delegator_id="parent@example.com",
        delegate_runtime_identity_id=resource_stack["identity"].id,
        scope={"model_ids": [str(resource_stack["model_a"].id)]},
        created_by="tester",
    )

    child_identity = RuntimeIdentityService(db_session).create_runtime_identity(
        agent_id=resource_stack["identity"].agent_id,
        agent_version_id=resource_stack["version"].id,
        name="Child",
        created_by="tester",
    )

    with pytest.raises(ScopeExceededError):
        svc.create_delegation(
            delegator_type="HUMAN",
            delegator_id="child@example.com",
            delegate_runtime_identity_id=child_identity.id,
            parent_delegation_id=parent.id,
            scope={
                "model_ids": [
                    str(resource_stack["model_a"].id),
                    str(resource_stack["model_b"].id),
                ]
            },
            created_by="tester",
        )


def test_delegation_scope_subset_validation() -> None:
    parent = DelegationScope.from_dict(
        {
            "model_ids": ["m1"],
            "data_source_ids": ["d1"],
            "mcp_server_ids": ["mcp1"],
            "tool_ids": ["t1"],
        }
    )
    child_ok = DelegationScope.from_dict(
        {
            "model_ids": ["m1"],
            "data_source_ids": ["d1"],
            "mcp_server_ids": ["mcp1"],
            "tool_ids": ["t1"],
        }
    )
    child_bad = DelegationScope.from_dict(
        {
            "model_ids": ["m1", "m2"],
            "data_source_ids": ["d1"],
            "mcp_server_ids": ["mcp1"],
            "tool_ids": ["t1"],
        }
    )
    assert child_ok.is_subset_of(parent)
    assert not child_bad.is_subset_of(parent)


def test_version_resource_catalog_only_declared_tools(
    db_session, resource_stack
) -> None:
    catalog = load_version_resource_catalog(db_session, resource_stack["version"].id)
    tool_ids = catalog.tool_ids
    assert str(resource_stack["tool_read"].id) in tool_ids
    assert str(resource_stack["tool_get_doc"].id) in tool_ids
    assert str(resource_stack["tool_delete"].id) not in tool_ids


def test_mcp_without_explicit_tools_includes_all_linked_tools(
    db_session, registry: RegistryService, test_organization
) -> None:
    suffix = uuid.uuid4().hex[:8]
    system = registry.create_ai_system(
        system_key=f"implicit-sys-{suffix}",
        name="Implicit System",
        created_by="tester",
    )
    agent = registry.create_agent(
        system.id,
        agent_key=f"implicit-agent-{suffix}",
        name="Implicit Agent",
        created_by="tester",
    )
    version = registry.create_agent_version(agent.id, created_by="tester")
    mcp = registry.create_mcp_server(
        server_key=f"office-{suffix}",
        name="Tech Office",
    )
    registry.add_version_dependency(
        version.id, resource_type="mcp_server", resource_id=mcp.id
    )
    tool = registry.create_tool_resource(
        tool_key=f"list-projects-{suffix}",
        name="List projects",
        mcp_server_id=mcp.id,
        consequential_action=True,
    )

    catalog = load_version_resource_catalog(db_session, version.id)
    mcp_entry = next(m for m in catalog.mcp_servers if m.id == str(mcp.id))
    assert len(mcp_entry.tools) == 1
    assert mcp_entry.tools[0].id == str(tool.id)
    assert str(tool.id) in catalog.tool_ids
