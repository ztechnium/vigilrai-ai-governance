"""Delegation Scope V2 narrowing, intersection, and lifecycle tests."""

from __future__ import annotations

import uuid

import pytest

from rai_gateway.identity.domain import (
    DelegationScope,
    EffectiveDelegationStatus,
    ResourceScope,
    ResourceScopeMode,
)
from rai_gateway.identity.errors import InvalidTransitionError, ScopeExceededError
from rai_gateway.identity.service import DelegationService, RuntimeIdentityService
from rai_gateway.registry.domain import AgentStatus, AgentVersionStatus, AISystemStatus
from rai_gateway.registry.service import RegistryService


def test_v1_empty_list_normalizes_to_all_declared():
    scope = DelegationScope.from_dict({"tool_ids": [], "model_ids": []})
    assert scope.tools.mode == ResourceScopeMode.ALL_DECLARED
    assert scope.models.mode == ResourceScopeMode.ALL_DECLARED


def test_v1_nonempty_normalizes_to_explicit():
    scope = DelegationScope.from_dict({"tool_ids": ["t1", "t2"]})
    assert scope.tools.mode == ResourceScopeMode.EXPLICIT
    assert scope.tool_ids == ["t1", "t2"]


def test_narrowing_parent_all_child_explicit_allowed():
    parent = DelegationScope(tools=ResourceScope.all_declared())
    child = DelegationScope(tools=ResourceScope.explicit(["a", "b"]))
    assert child.is_subset_of(parent)


def test_narrowing_parent_explicit_child_all_denied():
    parent = DelegationScope(tools=ResourceScope.explicit(["a", "b"]))
    child = DelegationScope(tools=ResourceScope.all_declared())
    assert not child.is_subset_of(parent)


def test_narrowing_parent_explicit_child_subset_allowed():
    parent = DelegationScope(tools=ResourceScope.explicit(["a", "b", "c"]))
    child = DelegationScope(tools=ResourceScope.explicit(["a", "b"]))
    assert child.is_subset_of(parent)


def test_narrowing_parent_explicit_child_wider_denied():
    parent = DelegationScope(tools=ResourceScope.explicit(["a", "b"]))
    child = DelegationScope(tools=ResourceScope.explicit(["a", "b", "c"]))
    assert not child.is_subset_of(parent)


def test_intersect_chain_modes():
    root = DelegationScope(tools=ResourceScope.all_declared())
    child = DelegationScope(tools=ResourceScope.explicit(["a", "b"]))
    effective = root.intersect(child)
    assert effective.tools.mode == ResourceScopeMode.EXPLICIT
    assert set(effective.tools.ids) == {"a", "b"}


@pytest.fixture()
def scope_stack(db_session, test_organization):
    registry = RegistryService(db_session)
    suffix = uuid.uuid4().hex[:8]
    system = registry.create_ai_system(
        system_key=f"v2-sys-{suffix}",
        name="V2 System",
        created_by="tester",
    )
    for status in (AISystemStatus.UNDER_REVIEW, AISystemStatus.APPROVED):
        registry.transition_ai_system(system.id, status.value, updated_by="tester")
    agent = registry.create_agent(
        system.id, agent_key=f"v2-agent-{suffix}", name="V2", created_by="tester"
    )
    for status in (AgentStatus.UNDER_REVIEW, AgentStatus.APPROVED):
        registry.transition_agent(agent.id, status.value, updated_by="tester")
    version = registry.create_agent_version(agent.id, created_by="tester")
    mcp = registry.create_mcp_server(
        server_key=f"mcp-{suffix}",
        name="MCP",
    )
    tool_a = registry.create_tool_resource(
        tool_key=f"tool_a_{suffix}",
        name="A",
        mcp_server_id=mcp.id,
    )
    tool_b = registry.create_tool_resource(
        tool_key=f"tool_b_{suffix}",
        name="B",
        mcp_server_id=mcp.id,
    )
    registry.add_version_dependency(
        version.id, resource_type="mcp_server", resource_id=mcp.id
    )
    registry.add_version_dependency(
        version.id, resource_type="tool", resource_id=tool_a.id
    )
    registry.add_version_dependency(
        version.id, resource_type="tool", resource_id=tool_b.id
    )
    for status in (AgentVersionStatus.UNDER_REVIEW, AgentVersionStatus.APPROVED):
        registry.transition_agent_version(version.id, status.value, updated_by="tester")
    identity = RuntimeIdentityService(db_session).create_runtime_identity(
        agent_id=agent.id,
        agent_version_id=version.id,
        name="rt",
        created_by="tester",
    )
    return {
        "org": test_organization,
        "identity": identity,
        "tool_a": tool_a,
        "tool_b": tool_b,
        "mcp": mcp,
    }


def test_parent_all_child_explicit_create(scope_stack, db_session):
    svc = DelegationService(db_session)
    identity_svc = RuntimeIdentityService(db_session)
    parent_identity = scope_stack["identity"]
    child_identity = identity_svc.create_runtime_identity(
        agent_id=parent_identity.agent_id,
        agent_version_id=parent_identity.agent_version_id,
        name="child-rt",
        created_by="tester",
    )
    parent = svc.create_delegation(
        delegator_type="HUMAN",
        delegator_id="p",
        delegate_runtime_identity_id=parent_identity.id,
        scope={
            "scope_version": 2,
            "tools": {"mode": "ALL_DECLARED", "ids": []},
            "mcp_servers": {"mode": "ALL_DECLARED", "ids": []},
            "models": {"mode": "ALL_DECLARED", "ids": []},
            "data_sources": {"mode": "ALL_DECLARED", "ids": []},
            "environments": {"mode": "ALL_DECLARED", "values": []},
        },
        created_by="tester",
    )
    child = svc.create_delegation(
        delegator_type="HUMAN",
        delegator_id="c",
        delegate_runtime_identity_id=child_identity.id,
        parent_delegation_id=parent.id,
        scope={
            "scope_version": 2,
            "tools": {
                "mode": "EXPLICIT",
                "ids": [str(scope_stack["tool_a"].id)],
            },
            "mcp_servers": {"mode": "ALL_DECLARED", "ids": []},
            "models": {"mode": "ALL_DECLARED", "ids": []},
            "data_sources": {"mode": "ALL_DECLARED", "ids": []},
            "environments": {"mode": "ALL_DECLARED", "values": []},
        },
        created_by="tester",
    )
    effective = svc.compute_effective_scope(child)
    assert str(scope_stack["tool_a"].id) in effective.tool_ids
    assert str(scope_stack["tool_b"].id) not in effective.tool_ids


def test_parent_explicit_child_all_create_denied(scope_stack, db_session):
    svc = DelegationService(db_session)
    identity_svc = RuntimeIdentityService(db_session)
    parent_identity = scope_stack["identity"]
    child_identity = identity_svc.create_runtime_identity(
        agent_id=parent_identity.agent_id,
        agent_version_id=parent_identity.agent_version_id,
        name="child-rt-2",
        created_by="tester",
    )
    parent = svc.create_delegation(
        delegator_type="HUMAN",
        delegator_id="p",
        delegate_runtime_identity_id=parent_identity.id,
        scope={"tool_ids": [str(scope_stack["tool_a"].id)]},
        created_by="tester",
    )
    with pytest.raises(ScopeExceededError):
        svc.create_delegation(
            delegator_type="HUMAN",
            delegator_id="c",
            delegate_runtime_identity_id=child_identity.id,
            parent_delegation_id=parent.id,
            scope={
                "scope_version": 2,
                "tools": {"mode": "ALL_DECLARED", "ids": []},
                "mcp_servers": {"mode": "ALL_DECLARED", "ids": []},
                "models": {"mode": "ALL_DECLARED", "ids": []},
                "data_sources": {"mode": "ALL_DECLARED", "ids": []},
                "environments": {"mode": "ALL_DECLARED", "values": []},
            },
            created_by="tester",
        )


def test_suspend_and_effective_status(scope_stack, db_session):
    svc = DelegationService(db_session)
    identity_svc = RuntimeIdentityService(db_session)
    parent_identity = scope_stack["identity"]
    child_identity = identity_svc.create_runtime_identity(
        agent_id=parent_identity.agent_id,
        agent_version_id=parent_identity.agent_version_id,
        name="child-rt-3",
        created_by="tester",
    )
    parent = svc.create_delegation(
        delegator_type="HUMAN",
        delegator_id="p",
        delegate_runtime_identity_id=parent_identity.id,
        scope={"tool_ids": [str(scope_stack["tool_a"].id)]},
        created_by="tester",
    )
    child = svc.create_delegation(
        delegator_type="HUMAN",
        delegator_id="c",
        delegate_runtime_identity_id=child_identity.id,
        parent_delegation_id=parent.id,
        scope={"tool_ids": [str(scope_stack["tool_a"].id)]},
        created_by="tester",
    )
    svc.suspend_delegation(parent.id, updated_by="tester", reason="pause")
    assert (
        svc.compute_effective_status(child)
        == EffectiveDelegationStatus.BLOCKED_BY_PARENT.value
    )
    with pytest.raises(InvalidTransitionError):
        svc.activate_delegation(parent.id, updated_by="tester", reason="")
    svc.activate_delegation(parent.id, updated_by="tester", reason="resume")
    assert svc.compute_effective_status(child) == EffectiveDelegationStatus.ACTIVE.value
    revisions = svc.list_revisions(parent.id)
    assert any(r.change_type == "SUSPEND" for r in revisions)
    assert any(r.change_type == "REACTIVATE" for r in revisions)
