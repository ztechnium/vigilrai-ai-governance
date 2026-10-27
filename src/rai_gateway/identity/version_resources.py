"""Agent version resource catalog for delegation scope validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from rai_gateway.models.registry import (
    AgentVersionDependency,
    DataSource,
    MCPServer,
    ModelResource,
    ToolResource,
)

# Tools in these states are catalogued but not auto-usable via Agent Versions.
NON_AUTHORITATIVE_TOOL_STATUSES = frozenset(
    {"DISCOVERED", "UNCLASSIFIED", "DISABLED", "DEPRECATED"}
)


def _metadata_dict(row: Any) -> dict[str, Any]:
    meta = getattr(row, "metadata_", None)
    return meta if isinstance(meta, dict) else {}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


@dataclass
class VersionToolResource:
    id: str
    tool_key: str
    name: str
    mcp_server_id: str | None
    native_name: str | None = None
    native_aliases: list[str] = field(default_factory=list)
    status: str | None = None
    capability_type: str | None = None
    side_effect: str | None = None
    default_risk: str | None = None


@dataclass
class VersionMcpResource:
    id: str
    server_key: str
    name: str
    tools: list[VersionToolResource] = field(default_factory=list)
    native_aliases: list[str] = field(default_factory=list)
    source_type: str | None = None
    status: str | None = None
    category: str | None = None
    vendor: str | None = None


@dataclass
class VersionModelResource:
    id: str
    label: str
    provider: str
    model_name: str


@dataclass
class VersionDataSourceResource:
    id: str
    label: str
    data_source_key: str


@dataclass
class VersionResourceCatalog:
    version_id: UUID
    models: list[VersionModelResource] = field(default_factory=list)
    data_sources: list[VersionDataSourceResource] = field(default_factory=list)
    mcp_servers: list[VersionMcpResource] = field(default_factory=list)
    standalone_tools: list[VersionToolResource] = field(default_factory=list)
    declared_tools: list[VersionToolResource] = field(default_factory=list)

    @property
    def model_ids(self) -> set[str]:
        return {m.id for m in self.models}

    @property
    def data_source_ids(self) -> set[str]:
        return {d.id for d in self.data_sources}

    @property
    def mcp_server_ids(self) -> set[str]:
        return {m.id for m in self.mcp_servers}

    @property
    def tool_ids(self) -> set[str]:
        return {t.id for t in self.declared_tools}

    def tool_by_id(self, tool_id: str) -> VersionToolResource | None:
        for tool in self.declared_tools:
            if tool.id == tool_id:
                return tool
        return None

    def to_dict(self) -> dict:
        return {
            "version_id": str(self.version_id),
            "models": [
                {
                    "id": m.id,
                    "label": m.label,
                    "provider": m.provider,
                    "model_name": m.model_name,
                }
                for m in self.models
            ],
            "data_sources": [
                {
                    "id": d.id,
                    "label": d.label,
                    "data_source_key": d.data_source_key,
                }
                for d in self.data_sources
            ],
            "mcp_servers": [
                {
                    "id": m.id,
                    "server_key": m.server_key,
                    "name": m.name,
                    "native_aliases": m.native_aliases,
                    "source_type": m.source_type,
                    "status": m.status,
                    "tools": [
                        {
                            "id": t.id,
                            "tool_key": t.tool_key,
                            "name": t.name,
                            "mcp_server_id": t.mcp_server_id,
                            "native_name": t.native_name,
                            "status": t.status,
                        }
                        for t in m.tools
                    ],
                }
                for m in self.mcp_servers
            ],
            "standalone_tools": [
                {
                    "id": t.id,
                    "tool_key": t.tool_key,
                    "name": t.name,
                    "mcp_server_id": t.mcp_server_id,
                }
                for t in self.standalone_tools
            ],
            "declared_tools": [
                {
                    "id": t.id,
                    "tool_key": t.tool_key,
                    "name": t.name,
                    "mcp_server_id": t.mcp_server_id,
                }
                for t in self.declared_tools
            ],
        }


def _tool_from_row(row: ToolResource) -> VersionToolResource | None:
    status = (row.status or "ACTIVE").upper()
    if status in NON_AUTHORITATIVE_TOOL_STATUSES:
        return None
    meta = _metadata_dict(row)
    native_name = meta.get("native_name")
    if isinstance(native_name, str):
        native_name = native_name.strip() or None
    else:
        native_name = None
    return VersionToolResource(
        id=str(row.id),
        tool_key=row.tool_key,
        name=row.name,
        mcp_server_id=str(row.mcp_server_id) if row.mcp_server_id else None,
        native_name=native_name,
        native_aliases=_string_list(meta.get("native_aliases")),
        status=status,
        capability_type=meta.get("capability_type")
        if isinstance(meta.get("capability_type"), str)
        else None,
        side_effect=meta.get("side_effect")
        if isinstance(meta.get("side_effect"), str)
        else None,
        default_risk=meta.get("default_risk")
        if isinstance(meta.get("default_risk"), str)
        else None,
    )


def _mcp_from_row(row: MCPServer) -> VersionMcpResource:
    meta = _metadata_dict(row)
    return VersionMcpResource(
        id=str(row.id),
        server_key=row.server_key,
        name=row.name,
        native_aliases=_string_list(meta.get("native_aliases")),
        source_type=meta.get("source_type")
        if isinstance(meta.get("source_type"), str)
        else None,
        status=(row.status or "ACTIVE").upper(),
        category=meta.get("category")
        if isinstance(meta.get("category"), str)
        else None,
        vendor=row.provider
        or (meta.get("vendor") if isinstance(meta.get("vendor"), str) else None),
    )


def load_version_resource_catalog(
    db: Session, version_id: UUID
) -> VersionResourceCatalog:
    """Load authoritative resources declared on an exact agent version."""
    deps = (
        db.query(AgentVersionDependency)
        .filter(AgentVersionDependency.agent_version_id == version_id)
        .all()
    )
    model_ids = [d.resource_id for d in deps if d.resource_type == "model"]
    data_source_ids = [d.resource_id for d in deps if d.resource_type == "data_source"]
    mcp_ids = [d.resource_id for d in deps if d.resource_type == "mcp_server"]
    tool_dep_ids = [d.resource_id for d in deps if d.resource_type == "tool"]
    models: list[VersionModelResource] = []
    if model_ids:
        model_q = db.query(ModelResource).filter(ModelResource.id.in_(model_ids))
        for row in model_q.all():
            label = f"{row.provider} {row.model_name}"
            if row.model_version:
                label = f"{label} ({row.model_version})"
            models.append(
                VersionModelResource(
                    id=str(row.id),
                    label=label,
                    provider=row.provider,
                    model_name=row.model_name,
                )
            )
    data_sources: list[VersionDataSourceResource] = []
    if data_source_ids:
        ds_q = db.query(DataSource).filter(DataSource.id.in_(data_source_ids))
        for row in ds_q.all():
            data_sources.append(
                VersionDataSourceResource(
                    id=str(row.id),
                    label=row.name,
                    data_source_key=row.data_source_key,
                )
            )
    mcp_map: dict[str, VersionMcpResource] = {}
    if mcp_ids:
        mcp_q = db.query(MCPServer).filter(MCPServer.id.in_(mcp_ids))
        for row in mcp_q.all():
            mcp_map[str(row.id)] = _mcp_from_row(row)
    declared_mcp_ids = set(mcp_map.keys())
    standalone_tools: list[VersionToolResource] = []
    declared_tools: list[VersionToolResource] = []
    if tool_dep_ids:
        tool_q = db.query(ToolResource).filter(ToolResource.id.in_(tool_dep_ids))
        tool_rows = tool_q.all()
        implied_mcp_ids = {
            row.mcp_server_id
            for row in tool_rows
            if row.mcp_server_id and str(row.mcp_server_id) not in mcp_map
        }
        if implied_mcp_ids:
            implied_q = db.query(MCPServer).filter(MCPServer.id.in_(implied_mcp_ids))
            for row in implied_q.all():
                mcp_map[str(row.id)] = _mcp_from_row(row)
            declared_mcp_ids = set(mcp_map.keys())
        for row in tool_rows:
            tool = _tool_from_row(row)
            if tool is None:
                continue
            declared_tools.append(tool)
            if tool.mcp_server_id and tool.mcp_server_id in declared_mcp_ids:
                mcp_map[tool.mcp_server_id].tools.append(tool)
            elif not tool.mcp_server_id:
                standalone_tools.append(tool)
    for mcp in mcp_map.values():
        mcp.tools.sort(key=lambda t: t.tool_key)
    standalone_tools.sort(key=lambda t: t.tool_key)
    # When an MCP is on the version but no tools were explicitly selected for it,
    # expose all authoritative tools linked to that MCP in the global catalog.
    # If any tool is explicitly declared for the MCP, only those are exposed.
    declared_tool_ids = {t.id for t in declared_tools}
    for mcp_id, mcp in mcp_map.items():
        explicit_for_mcp = [t for t in declared_tools if t.mcp_server_id == mcp_id]
        if explicit_for_mcp:
            mcp.tools = sorted(explicit_for_mcp, key=lambda t: t.tool_key)
            continue
        implicit_tools: list[VersionToolResource] = []
        implicit_q = (
            db.query(ToolResource)
            .filter(ToolResource.mcp_server_id == UUID(mcp_id))
            .order_by(ToolResource.tool_key)
        )
        for row in implicit_q.all():
            tool = _tool_from_row(row)
            if tool is None:
                continue
            implicit_tools.append(tool)
            if tool.id not in declared_tool_ids:
                declared_tools.append(tool)
                declared_tool_ids.add(tool.id)
        mcp.tools = implicit_tools
    declared_tools.sort(key=lambda t: t.tool_key)
    return VersionResourceCatalog(
        version_id=version_id,
        models=sorted(models, key=lambda m: m.label),
        data_sources=sorted(data_sources, key=lambda d: d.label),
        mcp_servers=sorted(mcp_map.values(), key=lambda m: m.name),
        standalone_tools=standalone_tools,
        declared_tools=declared_tools,
    )


def enrich_effective_scope(
    catalog: VersionResourceCatalog, scope_data: dict | None
) -> dict:
    """Resolve scope IDs to structured effective authority for UI/API consumers."""
    from rai_gateway.identity.domain import DelegationScope

    scope = DelegationScope.from_dict(scope_data).resolve_against_catalog(
        model_ids=catalog.model_ids,
        data_source_ids=catalog.data_source_ids,
        mcp_server_ids=catalog.mcp_server_ids,
        tool_ids=catalog.tool_ids,
    )
    model_map = {m.id: m for m in catalog.models}
    ds_map = {d.id: d for d in catalog.data_sources}
    mcp_map = {m.id: m for m in catalog.mcp_servers}
    tool_map = {t.id: t for t in catalog.declared_tools}
    mcp_tools: dict[str, list[dict]] = {}
    for tool_id in scope.tool_ids:
        tool = tool_map.get(tool_id)
        if not tool or not tool.mcp_server_id:
            continue
        mcp_tools.setdefault(tool.mcp_server_id, []).append(
            {
                "id": tool.id,
                "tool_key": tool.tool_key,
                "name": tool.name,
            }
        )
    mcp_entries = []
    for mcp_id in scope.mcp_server_ids:
        mcp = mcp_map.get(mcp_id)
        if not mcp:
            continue
        tools = mcp_tools.get(mcp_id, [])
        mcp_entries.append(
            {
                "id": mcp.id,
                "server_key": mcp.server_key,
                "name": mcp.name,
                "tools": tools,
            }
        )
    # MCPs implied only via selected tools
    for mcp_id, tools in mcp_tools.items():
        if mcp_id in scope.mcp_server_ids:
            continue
        mcp = mcp_map.get(mcp_id)
        if not mcp:
            continue
        mcp_entries.append(
            {
                "id": mcp.id,
                "server_key": mcp.server_key,
                "name": mcp.name,
                "tools": tools,
            }
        )
    return {
        "model_ids": scope.model_ids,
        "data_source_ids": scope.data_source_ids,
        "mcp_server_ids": scope.mcp_server_ids,
        "tool_ids": scope.tool_ids,
        "environment": scope.environment,
        "models": [
            {"id": mid, "label": model_map[mid].label}
            for mid in scope.model_ids
            if mid in model_map
        ],
        "data_sources": [
            {"id": did, "label": ds_map[did].label}
            for did in scope.data_source_ids
            if did in ds_map
        ],
        "mcp_servers": sorted(mcp_entries, key=lambda m: m["name"]),
    }
