"""Fail-closed architecture tests for WP1 registry eligibility."""

from __future__ import annotations

import uuid

import pytest

from rai_gateway.registry.domain import AgentStatus, AgentVersionStatus, AISystemStatus
from rai_gateway.registry.eligibility import EligibilityService
from rai_gateway.registry.service import RegistryService


@pytest.fixture()
def registry(db_session) -> RegistryService:
    return RegistryService(db_session)


@pytest.fixture()
def approved_stack(registry: RegistryService, test_organization) -> dict:
    """Create a fully approved system/agent/version stack."""
    suffix = uuid.uuid4().hex[:8]
    system = registry.create_ai_system(
        system_key=f"stack-sys-{suffix}",
        name="Stack System",
        created_by="tester",
    )
    for status in (
        AISystemStatus.UNDER_REVIEW,
        AISystemStatus.APPROVED,
    ):
        registry.transition_ai_system(system.id, status.value, updated_by="tester")

    agent = registry.create_agent(
        system.id,
        agent_key=f"stack-agent-{suffix}",
        name="Stack Agent",
        created_by="tester",
    )
    for status in (AgentStatus.UNDER_REVIEW, AgentStatus.APPROVED):
        registry.transition_agent(agent.id, status.value, updated_by="tester")

    version = registry.create_agent_version(agent.id, created_by="tester")
    for status in (
        AgentVersionStatus.UNDER_REVIEW,
        AgentVersionStatus.APPROVED,
    ):
        registry.transition_agent_version(version.id, status.value, updated_by="tester")

    return {"system": system, "agent": agent, "version": version}


def test_unknown_agent_not_eligible(db_session, approved_stack) -> None:
    result = EligibilityService(db_session).evaluate(
        system_id=approved_stack["system"].id,
        agent_id=uuid.uuid4(),
        version_id=approved_stack["version"].id,
    )
    assert result.eligible is False


def test_wrong_system_denied(db_session, approved_stack, test_organization) -> None:
    other = RegistryService(db_session).create_ai_system(
        system_key=f"other-sys-{uuid.uuid4().hex[:8]}",
        name="Other",
        created_by="tester",
    )
    result = EligibilityService(db_session).evaluate(
        system_id=other.id,
        agent_id=approved_stack["agent"].id,
        version_id=approved_stack["version"].id,
    )
    assert result.eligible is False


def test_unknown_version_not_eligible(db_session, approved_stack) -> None:
    result = EligibilityService(db_session).evaluate(
        system_id=approved_stack["system"].id,
        agent_id=approved_stack["agent"].id,
        version_id=uuid.uuid4(),
    )
    assert result.eligible is False


def test_suspended_system_not_eligible(
    db_session, registry: RegistryService, approved_stack
) -> None:
    registry.transition_ai_system(
        approved_stack["system"].id,
        AISystemStatus.SUSPENDED.value,
        updated_by="tester",
    )
    result = EligibilityService(db_session).evaluate(
        system_id=approved_stack["system"].id,
        agent_id=approved_stack["agent"].id,
        version_id=approved_stack["version"].id,
    )
    assert result.eligible is False


def test_suspended_agent_not_eligible(
    db_session, registry: RegistryService, approved_stack
) -> None:
    registry.transition_agent(
        approved_stack["agent"].id,
        AgentStatus.SUSPENDED.value,
        updated_by="tester",
    )
    result = EligibilityService(db_session).evaluate(
        system_id=approved_stack["system"].id,
        agent_id=approved_stack["agent"].id,
        version_id=approved_stack["version"].id,
    )
    assert result.eligible is False


def test_materially_changed_draft_not_eligible(
    db_session, registry: RegistryService, approved_stack
) -> None:
    tool = registry.create_tool_resource(
        tool_key=f"Payments.create_transfer-{uuid.uuid4().hex[:8]}",
        name="Transfer",
        consequential_action=True,
    )
    v2 = registry.create_agent_version(
        approved_stack["agent"].id,
        created_by="tester",
    )
    registry.add_version_dependency(v2.id, resource_type="tool", resource_id=tool.id)
    result = EligibilityService(db_session).evaluate(
        system_id=approved_stack["system"].id,
        agent_id=approved_stack["agent"].id,
        version_id=v2.id,
    )
    assert result.eligible is False


def test_caller_cannot_widen_tool_authority(
    db_session, registry: RegistryService, approved_stack
) -> None:
    result = EligibilityService(db_session).evaluate(
        system_id=approved_stack["system"].id,
        agent_id=approved_stack["agent"].id,
        version_id=approved_stack["version"].id,
        caller_tools=["Undeclared.tool"],
    )
    assert result.eligible is False
    assert "not in approved" in result.reason.lower()
