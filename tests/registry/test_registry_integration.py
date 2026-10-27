"""PostgreSQL integration tests for WP1 registry."""

from __future__ import annotations

import uuid

import pytest

from rai_gateway.registry.domain import AgentStatus, AgentVersionStatus, AISystemStatus
from rai_gateway.registry.eligibility import EligibilityService
from rai_gateway.registry.service import RegistryService


@pytest.fixture()
def registry(db_session) -> RegistryService:
    return RegistryService(db_session)


def _approve_system(registry: RegistryService, system_id) -> None:
    registry.transition_ai_system(
        system_id, AISystemStatus.UNDER_REVIEW.value, updated_by="tester"
    )
    registry.transition_ai_system(
        system_id, AISystemStatus.APPROVED.value, updated_by="tester"
    )


def _approve_agent(registry: RegistryService, agent_id) -> None:
    registry.transition_agent(
        agent_id, AgentStatus.UNDER_REVIEW.value, updated_by="tester"
    )
    registry.transition_agent(agent_id, AgentStatus.APPROVED.value, updated_by="tester")


def test_create_and_read_ai_system(
    registry: RegistryService, test_organization
) -> None:
    key = f"procurement-ai-{uuid.uuid4().hex[:8]}"
    system = registry.create_ai_system(
        system_key=key,
        name="Procurement AI",
        created_by="tester",
        business_unit="Procurement",
        risk_tier="HIGH",
    )
    assert system.system_key == key
    assert system.status == AISystemStatus.DRAFT.value

    fetched = registry.get_ai_system(system.id)
    assert fetched.name == "Procurement AI"


def test_create_agent_under_system(
    registry: RegistryService, test_organization
) -> None:
    system = registry.create_ai_system(
        system_key=f"sys-1-{uuid.uuid4().hex[:8]}",
        name="Test System",
        created_by="tester",
    )
    agent = registry.create_agent(
        system.id,
        agent_key="po-assistant",
        name="PO Assistant",
        created_by="tester",
    )
    assert agent.ai_system_id == system.id
    agents = registry.list_agents(system.id)
    assert len(agents) == 1


def test_create_multiple_immutable_versions(
    registry: RegistryService, test_organization
) -> None:
    system = registry.create_ai_system(
        system_key=f"sys-v-{uuid.uuid4().hex[:8]}",
        name="Version System",
        created_by="tester",
    )
    _approve_system(registry, system.id)
    agent = registry.create_agent(
        system.id,
        agent_key=f"agent-v-{uuid.uuid4().hex[:8]}",
        name="Agent",
        created_by="tester",
    )
    _approve_agent(registry, agent.id)

    v1 = registry.create_agent_version(agent.id, created_by="tester")
    registry.transition_agent_version(
        v1.id, AgentVersionStatus.UNDER_REVIEW.value, updated_by="tester"
    )
    registry.transition_agent_version(
        v1.id, AgentVersionStatus.APPROVED.value, updated_by="tester"
    )

    v2 = registry.create_agent_version(
        agent.id,
        created_by="tester",
        change_summary="Add payment tool",
    )

    versions = registry.list_agent_versions(agent.id)
    assert len(versions) == 2
    assert v1.lifecycle_status == AgentVersionStatus.APPROVED.value
    assert v2.version_number == 2


def test_procurement_scenario_material_change(
    registry: RegistryService, test_organization
) -> None:
    """Acceptance scenario: v2 adds consequential tool, cannot inherit v1 eligibility."""
    suffix = uuid.uuid4().hex[:8]
    system = registry.create_ai_system(
        system_key=f"procurement-ai-{suffix}",
        name="Procurement AI",
        created_by="tester",
        business_purpose="Assist procurement team",
        business_unit="Procurement",
        risk_tier="HIGH",
    )
    _approve_system(registry, system.id)

    agent = registry.create_agent(
        system.id,
        agent_key=f"po-assistant-{suffix}",
        name="PO Assistant",
        created_by="tester",
        business_purpose="Draft purchase orders",
    )
    _approve_agent(registry, agent.id)

    erp_read = registry.create_tool_resource(
        tool_key=f"ERP.read_supplier-{suffix}",
        name="Read Supplier",
        consequential_action=False,
    )
    erp_draft = registry.create_tool_resource(
        tool_key=f"ERP.create_draft_purchase_order-{suffix}",
        name="Create Draft PO",
        consequential_action=False,
    )
    payment_tool = registry.create_tool_resource(
        tool_key=f"Payments.create_transfer-{suffix}",
        name="Create Transfer",
        consequential_action=True,
    )

    v1 = registry.create_agent_version(
        agent.id,
        created_by="tester",
        risk_tier="HIGH",
    )
    registry.add_version_dependency(
        v1.id,
        resource_type="tool",
        resource_id=erp_read.id,
    )
    registry.add_version_dependency(
        v1.id,
        resource_type="tool",
        resource_id=erp_draft.id,
    )
    registry.transition_agent_version(
        v1.id, AgentVersionStatus.UNDER_REVIEW.value, updated_by="tester"
    )
    registry.transition_agent_version(
        v1.id, AgentVersionStatus.APPROVED.value, updated_by="tester"
    )

    v2 = registry.create_agent_version(
        agent.id,
        created_by="tester",
        change_summary="Add payment capability",
    )
    registry.add_version_dependency(
        v2.id,
        resource_type="tool",
        resource_id=payment_tool.id,
    )

    changes = registry.get_material_changes(v2.id)
    assert any(c.is_material for c in changes)
    assert v2.material_change_status == "MATERIAL"
    assert v2.lifecycle_status == AgentVersionStatus.REASSESSMENT_REQUIRED.value

    eligibility = EligibilityService(registry._db)
    v1_result = eligibility.evaluate(
        system_id=system.id,
        agent_id=agent.id,
        version_id=v1.id,
    )
    assert v1_result.eligible is True

    v2_result = eligibility.evaluate(
        system_id=system.id,
        agent_id=agent.id,
        version_id=v2.id,
    )
    assert v2_result.eligible is False


def test_duplicate_system_key_rejected(
    registry: RegistryService, test_organization
) -> None:
    key = f"dup-key-{uuid.uuid4().hex[:8]}"
    registry.create_ai_system(
        system_key=key,
        name="First",
        created_by="tester",
    )
    from rai_gateway.registry.errors import DuplicateKeyError

    with pytest.raises(DuplicateKeyError):
        registry.create_ai_system(
            system_key=key,
            name="Second",
            created_by="tester",
        )


def test_risk_assessment_persistence(
    registry: RegistryService, test_organization
) -> None:
    system = registry.create_ai_system(
        system_key=f"risk-sys-{uuid.uuid4().hex[:8]}",
        name="Risk System",
        created_by="tester",
    )
    assessment = registry.create_risk_assessment(
        ai_system_id=system.id,
        assessed_by="rai_officer",
        risk_tier="HIGH",
        overall_score=75,
        rationale="High-risk procurement domain",
    )
    finding = registry.create_risk_finding(
        assessment.id,
        category="financial",
        title="Unauthorized payment risk",
        severity="HIGH",
    )
    assert finding.risk_assessment_id == assessment.id
    assert assessment.status == "DRAFT"


def test_risk_assessment_status_transition(
    registry: RegistryService, test_organization
) -> None:
    from rai_gateway.registry.errors import InvalidTransitionError

    system = registry.create_ai_system(
        system_key=f"risk-status-{uuid.uuid4().hex[:8]}",
        name="Risk Status System",
        created_by="tester",
    )
    assessment = registry.create_risk_assessment(
        ai_system_id=system.id,
        assessed_by="rai_officer",
        risk_tier="MEDIUM",
        overall_score=40,
    )
    with pytest.raises(InvalidTransitionError):
        registry.transition_risk_assessment(assessment.id, "APPROVED")

    submitted = registry.transition_risk_assessment(assessment.id, "SUBMITTED")
    approved = registry.transition_risk_assessment(submitted.id, "APPROVED")
    assert approved.status == "APPROVED"


def test_update_model_resource(registry: RegistryService) -> None:
    model = registry.create_model_resource(
        provider="azure_openai",
        model_name="gpt-4o",
        deployment_reference="eastus/gpt-4o",
    )
    updated = registry.update_model_resource(
        model.id,
        provider="azure_openai",
        model_name="gpt-4o-mini",
        deployment_reference="eastus/gpt-4o-mini",
    )
    assert updated.model_name == "gpt-4o-mini"
    assert updated.deployment_reference == "eastus/gpt-4o-mini"


def test_update_mcp_server_and_tools(registry: RegistryService) -> None:
    suffix = uuid.uuid4().hex[:8]
    server = registry.create_mcp_server(
        server_key=f"github-mcp-{suffix}",
        name="GitHub MCP",
        environment="staging",
    )
    tool = registry.create_tool_resource(
        tool_key=f"github.create_issue-{suffix}",
        name="Create Issue",
        mcp_server_id=server.id,
    )
    updated = registry.update_mcp_server(
        server.id,
        name="GitHub MCP (Production)",
        environment="production",
    )
    tools = registry.list_tools_for_mcp(server.id)
    assert updated.name == "GitHub MCP (Production)"
    assert updated.environment == "production"
    assert len(tools) == 1
    assert tools[0].id == tool.id


def test_update_tool_resource(registry: RegistryService) -> None:
    suffix = uuid.uuid4().hex[:8]
    tool = registry.create_tool_resource(
        tool_key=f"github.update_issue-{suffix}",
        name="Update Issue",
        description="Original",
        consequential_action=False,
    )
    updated = registry.update_tool_resource(
        tool.id,
        name="Update Issue (edited)",
        description="Revised",
        consequential_action=True,
        capability_type="UPDATE",
        default_risk="HIGH",
    )
    assert updated.name == "Update Issue (edited)"
    assert updated.description == "Revised"
    assert updated.consequential_action is True
    assert updated.metadata_["capability_type"] == "UPDATE"
    assert updated.metadata_["default_risk"] == "HIGH"


def test_mcp_tool_dependency_requires_associated_mcp(
    registry: RegistryService, test_organization
) -> None:
    suffix = uuid.uuid4().hex[:8]
    system = registry.create_ai_system(
        system_key=f"mcp-dep-sys-{suffix}",
        name="MCP Dependency System",
        created_by="tester",
    )
    agent = registry.create_agent(
        system.id,
        agent_key=f"mcp-dep-agent-{suffix}",
        name="MCP Agent",
        created_by="tester",
    )
    version = registry.create_agent_version(agent.id, created_by="tester")
    server = registry.create_mcp_server(
        server_key=f"frappe-mcp-{suffix}",
        name="Frappe MCP",
    )
    get_doc = registry.create_tool_resource(
        tool_key=f"frappe.get_doc-{suffix}",
        name="get_doc",
        mcp_server_id=server.id,
    )
    registry.create_tool_resource(
        tool_key=f"frappe.insert_doc-{suffix}",
        name="insert_doc",
        mcp_server_id=server.id,
    )

    from rai_gateway.registry.errors import RelationshipError

    with pytest.raises(RelationshipError):
        registry.add_version_dependency(
            version.id,
            resource_type="tool",
            resource_id=get_doc.id,
        )

    registry.add_version_dependency(
        version.id,
        resource_type="mcp_server",
        resource_id=server.id,
    )
    registry.add_version_dependency(
        version.id,
        resource_type="tool",
        resource_id=get_doc.id,
    )

    deps = registry.list_version_dependencies(version.id)
    assert {d.resource_type for d in deps} == {"mcp_server", "tool"}
    assert any(d.resource_id == get_doc.id for d in deps)

    registry.remove_version_dependency(
        version.id, next(d.id for d in deps if d.resource_type == "mcp_server")
    )
    deps_after = registry.list_version_dependencies(version.id)
    assert not any(d.resource_type == "tool" for d in deps_after)
    assert not any(d.resource_id == get_doc.id for d in deps_after)


def test_approved_version_rejects_dependency_mutation(
    registry: RegistryService, test_organization
) -> None:
    suffix = uuid.uuid4().hex[:8]
    system = registry.create_ai_system(
        system_key=f"immutable-sys-{suffix}",
        name="Immutable System",
        created_by="tester",
    )
    _approve_system(registry, system.id)
    agent = registry.create_agent(
        system.id,
        agent_key=f"immutable-agent-{suffix}",
        name="Immutable Agent",
        created_by="tester",
    )
    _approve_agent(registry, agent.id)
    version = registry.create_agent_version(agent.id, created_by="tester")
    registry.transition_agent_version(
        version.id, AgentVersionStatus.UNDER_REVIEW.value, updated_by="tester"
    )
    registry.transition_agent_version(
        version.id, AgentVersionStatus.APPROVED.value, updated_by="tester"
    )
    model = registry.create_model_resource(
        provider="openai",
        model_name="gpt-4o",
    )

    from rai_gateway.registry.errors import ImmutableVersionError

    with pytest.raises(ImmutableVersionError):
        registry.add_version_dependency(
            version.id,
            resource_type="model",
            resource_id=model.id,
        )
