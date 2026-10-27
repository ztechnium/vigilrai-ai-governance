"""MCP live discovery / sync seam.
Discovery never auto-authorizes tools. Unknown tools land as DISCOVERED /
UNCLASSIFIED and require admin review before becoming ACTIVE.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from rai_gateway.models.registry import MCPServer, ToolResource
from rai_gateway.registry.domain import CatalogScope


@dataclass
class DiscoveredTool:
    native_name: str
    description: str | None = None
    input_schema: dict[str, Any] | None = None


@dataclass
class DiscoverySyncResult:
    mcp_server_id: str
    matched: list[str] = field(default_factory=list)
    discovered: list[str] = field(default_factory=list)
    deprecated: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mcp_server_id": self.mcp_server_id,
            "matched": self.matched,
            "discovered": self.discovered,
            "deprecated": self.deprecated,
        }


class MCPToolDiscoveryClient(ABC):
    """Interface for listing tools from a connected MCP server."""

    @abstractmethod
    def list_tools(self, mcp_server: MCPServer) -> list[DiscoveredTool]:
        """Return native tools currently advertised by the live MCP."""


class NoOpMCPToolDiscoveryClient(MCPToolDiscoveryClient):
    def list_tools(self, mcp_server: MCPServer) -> list[DiscoveredTool]:
        return []


class MCPDiscoveryService:
    """Compare live MCP tools against the catalog without granting authority."""

    def __init__(
        self,
        db: Session,
        discovery_client: MCPToolDiscoveryClient | None = None,
    ) -> None:
        self._db = db
        self._client = discovery_client or NoOpMCPToolDiscoveryClient()

    def discover_tools(self, mcp_server_id: UUID) -> list[DiscoveredTool]:
        mcp = self._db.query(MCPServer).filter(MCPServer.id == mcp_server_id).first()
        if not mcp:
            raise ValueError(f"MCP server not found: {mcp_server_id}")
        return self._client.list_tools(mcp)

    def sync_tools(self, mcp_server_id: UUID) -> DiscoverySyncResult:
        """Upsert discovered tools as DISCOVERED/UNCLASSIFIED; never auto-activate.
        Historical tool rows used by old Agent Versions are retained (deprecated
        rather than deleted).
        """
        mcp = self._db.query(MCPServer).filter(MCPServer.id == mcp_server_id).first()
        if not mcp:
            raise ValueError(f"MCP server not found: {mcp_server_id}")
        discovered = self._client.list_tools(mcp)
        existing = (
            self._db.query(ToolResource)
            .filter(ToolResource.mcp_server_id == mcp.id)
            .all()
        )
        by_native: dict[str, ToolResource] = {}
        for tool in existing:
            meta = tool.metadata_ if isinstance(tool.metadata_, dict) else {}
            native = meta.get("native_name") or tool.name
            by_native[str(native).strip().lower()] = tool
            # Also index trailing segment of stable key.
            if "." in tool.tool_key:
                by_native[tool.tool_key.rsplit(".", 1)[-1].lower()] = tool
        result = DiscoverySyncResult(mcp_server_id=str(mcp.id))
        seen: set[str] = set()
        for item in discovered:
            native = item.native_name.strip()
            key = native.lower()
            seen.add(key)
            existing_tool = by_native.get(key)
            if existing_tool:
                meta = dict(existing_tool.metadata_ or {})
                meta["native_name"] = native
                if item.description:
                    existing_tool.description = item.description
                if item.input_schema is not None:
                    meta["input_schema"] = item.input_schema
                existing_tool.metadata_ = meta
                result.matched.append(native)
                continue
            tool_key = f"{mcp.server_key}.{native}"
            tool = ToolResource(
                tool_key=tool_key,
                name=native,
                description=item.description,
                provider=mcp.provider,
                mcp_server_id=mcp.id,
                consequential_action=False,
                status="DISCOVERED",
                scope=mcp.scope or CatalogScope.PLATFORM.value,
                metadata_={
                    "native_name": native,
                    "native_aliases": [native],
                    "source_type": "DISCOVERED",
                    "lifecycle": "UNCLASSIFIED",
                    "input_schema": item.input_schema,
                    "capability_type": None,
                    "side_effect": None,
                    "default_risk": None,
                    "default_requires_approval": False,
                },
            )
            self._db.add(tool)
            result.discovered.append(native)
        for tool in existing:
            meta = tool.metadata_ if isinstance(tool.metadata_, dict) else {}
            native = str(meta.get("native_name") or tool.name).strip().lower()
            if native in seen:
                continue
            if (tool.status or "").upper() in {
                "DISCOVERED",
                "UNCLASSIFIED",
                "SEEDED",
                "ACTIVE",
            }:
                # Soft-deprecate; do not destroy historical references.
                if (tool.status or "").upper() != "DEPRECATED":
                    tool.status = "DEPRECATED"
                    result.deprecated.append(meta.get("native_name") or tool.name)
        self._db.commit()
        return result
