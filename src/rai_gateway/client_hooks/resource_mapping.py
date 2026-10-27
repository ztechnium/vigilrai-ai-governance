"""Authoritative WP1 resource mapping for native client hook events."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from rai_gateway.client_hooks.domain import ResourceMappingResult
from rai_gateway.identity.version_resources import (
    VersionMcpResource,
    VersionToolResource,
    load_version_resource_catalog,
)
from rai_gateway.models.identity import AgentRuntimeIdentity


def _norm(value: str | None) -> str:
    return (value or "").strip().lower()


def _mcp_aliases(mcp: VersionMcpResource) -> set[str]:
    aliases = {_norm(mcp.server_key), _norm(mcp.name)}
    for alias in mcp.native_aliases:
        aliases.add(_norm(alias))
    return {a for a in aliases if a}


def _tool_aliases(tool: VersionToolResource) -> set[str]:
    aliases = {_norm(tool.tool_key), _norm(tool.name)}
    if tool.native_name:
        aliases.add(_norm(tool.native_name))
    # Stable key form: "{mcp}.{native_tool}" → also match trailing native segment.
    if "." in tool.tool_key:
        aliases.add(_norm(tool.tool_key.rsplit(".", 1)[-1]))
    for alias in tool.native_aliases:
        aliases.add(_norm(alias))
    return {a for a in aliases if a}


def _mcp_matches(mcp: VersionMcpResource, mcp_norm: str) -> bool:
    if not mcp_norm:
        return True
    return mcp_norm in _mcp_aliases(mcp)


def _tool_matches(tool: VersionToolResource, tool_norm: str) -> bool:
    return bool(tool_norm) and tool_norm in _tool_aliases(tool)


class HookResourceMapper:
    """Map native MCP/tool names to authoritative WP1 UUIDs for a runtime identity."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def resolve_mcp_tool(
        self,
        *,
        runtime_identity_id: UUID,
        native_mcp_name: str | None,
        native_tool_name: str,
        parameters: dict | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
    ) -> ResourceMappingResult:
        identity = (
            self._db.query(AgentRuntimeIdentity)
            .filter(AgentRuntimeIdentity.id == runtime_identity_id)
            .first()
        )
        if not identity:
            return ResourceMappingResult(
                integration_type="mcp",
                integration_id=None,
                tool_id=None,
                error_code="RESOURCE_NOT_REGISTERED",
                error_message="Runtime identity not found",
            )

        catalog = load_version_resource_catalog(self._db, identity.agent_version_id)
        tool_norm = _norm(native_tool_name)
        mcp_norm = _norm(native_mcp_name)

        matched_tools: list[tuple[VersionMcpResource | None, VersionToolResource]] = []

        for mcp in catalog.mcp_servers:
            if not _mcp_matches(mcp, mcp_norm):
                continue
            for tool in mcp.tools:
                if _tool_matches(tool, tool_norm):
                    matched_tools.append((mcp, tool))

        if not matched_tools:
            for tool in catalog.standalone_tools + catalog.declared_tools:
                if _tool_matches(tool, tool_norm):
                    matched_tools.append((None, tool))

        if not matched_tools:
            mcp_keys = sorted({m.server_key for m in catalog.mcp_servers})
            tool_names = sorted(
                {
                    (t.native_name or t.tool_key)
                    for m in catalog.mcp_servers
                    for t in m.tools
                }
                | {(t.native_name or t.tool_key) for t in catalog.declared_tools}
            )
            matched_mcps = [
                m.server_key for m in catalog.mcp_servers if _mcp_matches(m, mcp_norm)
            ]
            if mcp_norm and not matched_mcps:
                detail = (
                    f"MCP '{native_mcp_name}' is not on agent version "
                    f"(version mcps={mcp_keys or ['<none>']})"
                )
            elif matched_mcps:
                detail = (
                    f"tool '{native_tool_name}' not declared for MCP(s) {matched_mcps} "
                    f"(available={tool_names or ['<none>']})"
                )
            else:
                detail = (
                    f"tool '{native_tool_name}' not on agent version "
                    f"(version mcps={mcp_keys or ['<none>']}, "
                    f"tools={tool_names or ['<none>']})"
                )
            return ResourceMappingResult(
                integration_type="mcp",
                integration_id=None,
                tool_id=None,
                error_code="RESOURCE_NOT_REGISTERED",
                error_message=(
                    f"Unknown tool '{native_tool_name}' for runtime identity: {detail}"
                ),
            )

        if len(matched_tools) > 1 and not mcp_norm:
            return ResourceMappingResult(
                integration_type="mcp",
                integration_id=None,
                tool_id=None,
                error_code="RESOURCE_NOT_REGISTERED",
                error_message=f"Ambiguous tool mapping for '{native_tool_name}'",
            )

        if len(matched_tools) > 1 and mcp_norm:
            exact = [
                (mcp, tool)
                for mcp, tool in matched_tools
                if mcp is not None and _mcp_matches(mcp, mcp_norm)
            ]
            if len(exact) == 1:
                matched_tools = exact
            elif len(exact) > 1:
                return ResourceMappingResult(
                    integration_type="mcp",
                    integration_id=None,
                    tool_id=None,
                    error_code="RESOURCE_NOT_REGISTERED",
                    error_message=f"Ambiguous tool mapping for '{native_tool_name}'",
                )

        mcp, tool = matched_tools[0]
        integration_id = UUID(mcp.id) if mcp else None
        if mcp and tool.mcp_server_id and tool.mcp_server_id != mcp.id:
            return ResourceMappingResult(
                integration_type="mcp",
                integration_id=integration_id,
                tool_id=UUID(tool.id),
                error_code="RESOURCE_RELATIONSHIP_INVALID",
                error_message="Tool does not belong to the specified MCP server",
            )

        return ResourceMappingResult(
            integration_type="mcp",
            integration_id=integration_id,
            tool_id=UUID(tool.id),
            target_type=target_type,
            target_id=target_id,
            parameters=dict(parameters or {}),
        )

    def resolve_standalone_tool(
        self,
        *,
        runtime_identity_id: UUID,
        native_tool_name: str,
        parameters: dict | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
    ) -> ResourceMappingResult:
        return self.resolve_mcp_tool(
            runtime_identity_id=runtime_identity_id,
            native_mcp_name=None,
            native_tool_name=native_tool_name,
            parameters=parameters,
            target_type=target_type,
            target_id=target_id,
        )
