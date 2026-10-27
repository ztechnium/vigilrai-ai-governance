"""Unified Resource Catalog query tests."""

from __future__ import annotations

import uuid

import pytest

from rai_gateway.registry.catalog_query import ResourceCatalogQueryService
from rai_gateway.registry.domain import AgentStatus, AISystemStatus
from rai_gateway.registry.service import RegistryService


@pytest.fixture()
def catalog_stack(db_session, test_organization):
    registry = RegistryService(db_session)
    suffix = uuid.uuid4().hex[:8]

    model = registry.create_model_resource(
        provider="google",
        model_name=f"gemini-{suffix}",
    )
    mcp = registry.create_mcp_server(
        server_key=f"booking-{suffix}",
        name=f"Booking MCP {suffix}",
        environment="production",
    )
    ds = registry.create_data_source(
        data_source_key=f"lapeep-db-{suffix}",
        name=f"Lapeep DB {suffix}",
        classification="Confidential",
    )
    svc = registry.create_external_service(
        service_key=f"shopify-{suffix}",
        name=f"Shopify {suffix}",
    )

    system = registry.create_ai_system(
        system_key=f"sys-{suffix}",
        name=f"Lapeep AI {suffix}",
        created_by="tester",
    )
    for status in (AISystemStatus.UNDER_REVIEW, AISystemStatus.APPROVED):
        registry.transition_ai_system(system.id, status.value, updated_by="tester")
    agent = registry.create_agent(
        system.id,
        agent_key=f"agent-{suffix}",
        name="Agent",
        created_by="tester",
    )
    for status in (AgentStatus.UNDER_REVIEW, AgentStatus.APPROVED):
        registry.transition_agent(agent.id, status.value, updated_by="tester")
    version = registry.create_agent_version(agent.id, created_by="tester")
    registry.add_version_dependency(
        version.id, resource_type="model", resource_id=model.id
    )
    registry.add_version_dependency(
        version.id, resource_type="mcp_server", resource_id=mcp.id
    )
    registry.add_version_dependency(
        version.id, resource_type="data_source", resource_id=ds.id
    )

    return {
        "org": test_organization,
        "registry": registry,
        "model": model,
        "mcp": mcp,
        "ds": ds,
        "service": svc,
        "system": system,
        "query": ResourceCatalogQueryService(db_session),
        "suffix": suffix,
    }


def test_unified_catalog_lists_mixed_types(catalog_stack):
    result = catalog_stack["query"].query(limit=200)
    types = {item["resource_type"] for item in result["items"]}
    assert "MODEL" in types
    assert "MCP" in types
    assert "DATA_SOURCE" in types
    assert "SERVICE" in types
    assert result["total"] >= 4


def test_catalog_filter_by_type(catalog_stack):
    result = catalog_stack["query"].query(
        resource_type="MCP",
        limit=200,
    )
    assert result["total"] >= 1
    assert all(i["resource_type"] == "MCP" for i in result["items"])


def test_catalog_ai_system_usage_filter(catalog_stack):
    result = catalog_stack["query"].query(
        ai_system_id=catalog_stack["system"].id,
        limit=200,
    )
    keys = {i["key"] for i in result["items"]}
    assert catalog_stack["model"].model_name in keys
    assert catalog_stack["mcp"].server_key in keys
    assert catalog_stack["ds"].data_source_key in keys
    assert catalog_stack["service"].service_key not in keys


def test_catalog_used_by_ai_systems_column(catalog_stack):
    result = catalog_stack["query"].query(
        resource_type="MODEL",
        search=catalog_stack["suffix"],
        limit=50,
    )
    assert result["items"]
    item = next(i for i in result["items"] if i["id"] == str(catalog_stack["model"].id))
    names = [s["name"] for s in item["used_by_ai_systems"]]
    assert catalog_stack["system"].name in names


def test_catalog_pagination(catalog_stack):
    page1 = catalog_stack["query"].query(limit=2, offset=0)
    page2 = catalog_stack["query"].query(limit=2, offset=2)
    assert page1["limit"] == 2
    assert len(page1["items"]) <= 2
    ids1 = {i["id"] for i in page1["items"]}
    ids2 = {i["id"] for i in page2["items"]}
    assert ids1.isdisjoint(ids2) or page1["total"] <= 2
