"""Tests for enterprise MCP seed catalog."""

from __future__ import annotations

from pathlib import Path

import pytest

from rai_gateway.identity.version_resources import load_version_resource_catalog
from rai_gateway.models.registry import MCPServer, ToolResource
from rai_gateway.registry.mcp_discovery import (
    DiscoveredTool,
    MCPDiscoveryService,
    MCPToolDiscoveryClient,
)
from rai_gateway.registry.seed_mcp_catalog import (
    DEFAULT_SEED_PATH,
    MCPSeedCatalogService,
    load_seed_catalog,
)
from rai_gateway.registry.service import RegistryService


def test_seed_catalog_file_exists_and_has_required_mcps() -> None:
    catalog = load_seed_catalog(DEFAULT_SEED_PATH)
    keys = {m["canonical_key"] for m in catalog["mcps"]}
    required = {
        "atlassian",
        "github",
        "azure_devops",
        "slack",
        "google_workspace",
        "salesforce",
        "aws",
        "postgresql",
        "filesystem",
        "sentry",
        "frappe",
        "strapi",
    }
    assert required.issubset(keys)
    atlassian = next(m for m in catalog["mcps"] if m["canonical_key"] == "atlassian")
    assert "atlassian" in atlassian["native_aliases"]
    tool_names = {t["native_name"] for t in atlassian["tools"]}
    assert "getAccessibleAtlassianResources" in tool_names
    assert "search" in tool_names
    assert "searchJiraIssuesUsingJql" in tool_names
    assert "getVisibleJiraProjects" in tool_names
    assert len(tool_names) >= 30
    cursor_local = next(
        m for m in catalog["mcps"] if m["canonical_key"] == "cursor_local"
    )
    assert "shell" in {t["native_name"] for t in cursor_local["tools"]}
    families = {model["family"] for model in catalog["models"]}
    assert {"gemini", "claude", "gpt"}.issubset(families)


def test_seed_rejects_credentials(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(
        '{"mcps":[{"canonical_key":"x","display_name":"X","credentials":{"token":"no"}}]}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="secrets"):
        load_seed_catalog(bad)


def test_seed_idempotent(db_session) -> None:
    svc = MCPSeedCatalogService(db_session)
    first = svc.seed(DEFAULT_SEED_PATH)
    second = svc.seed(DEFAULT_SEED_PATH)
    assert first.mcps_created >= 12
    assert second.mcps_created == 0
    assert second.mcps_updated >= 12

    atlassian = (
        db_session.query(MCPServer).filter(MCPServer.server_key == "atlassian").one()
    )
    assert atlassian.metadata_["native_aliases"]
    assert "atlassian" in atlassian.metadata_["native_aliases"]
    assert atlassian.metadata_["source_type"] == "SEEDED_TEMPLATE"

    tool = (
        db_session.query(ToolResource)
        .filter(ToolResource.tool_key == "atlassian.getAccessibleAtlassianResources")
        .one()
    )
    assert tool.metadata_["native_name"] == "getAccessibleAtlassianResources"
    assert tool.metadata_["default_risk"] == "LOW"
    assert tool.status == "SEEDED"

    frappe = db_session.query(MCPServer).filter(MCPServer.server_key == "frappe").one()
    strapi = db_session.query(MCPServer).filter(MCPServer.server_key == "strapi").one()
    assert frappe is not None
    assert strapi is not None


def test_discovered_tools_not_in_version_catalog(db_session, test_organization) -> None:
    registry = RegistryService(db_session)
    MCPSeedCatalogService(db_session).seed(DEFAULT_SEED_PATH)
    atlassian = (
        db_session.query(MCPServer).filter(MCPServer.server_key == "atlassian").one()
    )

    class _Client(MCPToolDiscoveryClient):
        def list_tools(self, mcp_server):
            # Preserve seeded tools as matched; only the unknown name is DISCOVERED.
            return [
                DiscoveredTool(
                    native_name="getAccessibleAtlassianResources",
                    description="seeded",
                ),
                DiscoveredTool(native_name="brandNewAtlassianTool", description="new"),
            ]

    sync = MCPDiscoveryService(db_session, _Client()).sync_tools(atlassian.id)
    assert "brandNewAtlassianTool" in sync.discovered

    discovered = (
        db_session.query(ToolResource)
        .filter(ToolResource.tool_key == "atlassian.brandNewAtlassianTool")
        .one()
    )
    assert discovered.status == "DISCOVERED"

    system = registry.create_ai_system(
        system_key="seed-sys",
        name="Seed Sys",
        created_by="tester",
    )
    agent = registry.create_agent(
        system.id, agent_key="seed-agent", name="Seed Agent", created_by="tester"
    )
    version = registry.create_agent_version(agent.id, created_by="tester")
    registry.add_version_dependency(
        version.id, resource_type="mcp_server", resource_id=atlassian.id
    )

    catalog = load_version_resource_catalog(db_session, version.id)
    mcp = next(m for m in catalog.mcp_servers if m.server_key == "atlassian")
    native_names = {(t.native_name or t.name) for t in mcp.tools}
    assert "getAccessibleAtlassianResources" in native_names
    assert "brandNewAtlassianTool" not in native_names
