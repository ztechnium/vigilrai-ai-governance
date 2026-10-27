"""Unified Resource Catalog read model — server-side filter + pagination."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from rai_gateway.models.registry import (
    Agent,
    AgentVersion,
    AgentVersionDependency,
    AISystem,
    DataSource,
    ExternalService,
    MCPServer,
    ModelResource,
    ToolResource,
)
from rai_gateway.registry.domain import CatalogScope, ResourceType

# API-facing type labels (plan §4.2) ↔ dependency resource_type values
_API_TYPE_TO_DB: dict[str, str] = {
    "MODEL": ResourceType.MODEL.value,
    "MCP": ResourceType.MCP_SERVER.value,
    "DATA_SOURCE": ResourceType.DATA_SOURCE.value,
    "SERVICE": ResourceType.EXTERNAL_SERVICE.value,
}
_DB_TYPE_TO_API: dict[str, str] = {v: k for k, v in _API_TYPE_TO_DB.items()}
_DEFAULT_LIMIT = 50
_MAX_LIMIT = 200


@dataclass(frozen=True)
class _CatalogRow:
    id: UUID
    resource_type: str  # API type
    key: str
    name: str
    provider: str | None
    environment: str | None
    status: str
    scope: str
    details: str | None
    tool_count: int | None
    created_at: Any


def _clamp_limit(limit: int | None) -> int:
    if limit is None:
        return _DEFAULT_LIMIT
    return max(1, min(int(limit), _MAX_LIMIT))


class ResourceCatalogQueryService:
    """Paginated union read across catalog resource tables."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def query(
        self,
        *,
        search: str | None = None,
        ai_system_id: UUID | None = None,
        resource_type: str | None = None,
        status: str | None = None,
        environment: str | None = None,
        provider: str | None = None,
        scope: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
        sort: str | None = None,
    ) -> dict[str, Any]:
        page_limit = _clamp_limit(limit)
        page_offset = max(0, int(offset or 0))
        search_term = (search or "").strip().lower() or None
        api_type = (resource_type or "").strip().upper() or None
        if api_type in ("", "ALL"):
            api_type = None
        if api_type and api_type not in _API_TYPE_TO_DB:
            raise ValueError(f"Invalid resource_type: {resource_type}")
        allowed_ids: set[tuple[str, UUID]] | None = None
        if ai_system_id is not None:
            allowed_ids = self._resource_ids_for_ai_system(ai_system_id=ai_system_id)
            if not allowed_ids:
                return {
                    "items": [],
                    "total": 0,
                    "limit": page_limit,
                    "offset": page_offset,
                }
        rows: list[_CatalogRow] = []
        types_to_load = [api_type] if api_type else list(_API_TYPE_TO_DB.keys())
        for api_t in types_to_load:
            rows.extend(
                self._load_type(
                    api_type=api_t,
                    search_term=search_term,
                    status=status,
                    environment=environment,
                    provider=provider,
                    scope=scope,
                    allowed_ids=allowed_ids,
                )
            )
        reverse = False
        sort_key = (sort or "name").strip().lower()
        if sort_key.startswith("-"):
            reverse = True
            sort_key = sort_key[1:]

        def _sort_value(row: _CatalogRow):
            if sort_key == "created_at":
                return row.created_at or ""
            if sort_key == "type":
                return row.resource_type
            if sort_key == "status":
                return row.status
            if sort_key == "key":
                return (row.key or "").lower()
            return (row.name or "").lower()

        rows.sort(key=_sort_value, reverse=reverse)
        total = len(rows)
        page = rows[page_offset : page_offset + page_limit]
        usage = self._usage_for_resources(
            resources=[(r.resource_type, r.id) for r in page],
        )
        items = []
        for row in page:
            systems = usage.get((row.resource_type, row.id), [])
            items.append(
                {
                    "id": str(row.id),
                    "resource_type": row.resource_type,
                    "key": row.key,
                    "name": row.name,
                    "provider": row.provider,
                    "environment": row.environment,
                    "status": row.status,
                    "scope": row.scope,
                    "details": row.details,
                    "tool_count": row.tool_count,
                    "used_by_ai_systems": systems,
                    "dependency_count": len(systems),
                }
            )
        return {
            "items": items,
            "total": total,
            "limit": page_limit,
            "offset": page_offset,
        }

    def _resource_ids_for_ai_system(
        self, *, ai_system_id: UUID
    ) -> set[tuple[str, UUID]]:
        """Return (api_type, resource_id) used by any agent version under the AI System."""
        system = self._db.query(AISystem).filter(AISystem.id == ai_system_id).first()
        if not system:
            return set()
        rows = (
            self._db.query(
                AgentVersionDependency.resource_type,
                AgentVersionDependency.resource_id,
            )
            .join(
                AgentVersion,
                AgentVersion.id == AgentVersionDependency.agent_version_id,
            )
            .join(Agent, Agent.id == AgentVersion.agent_id)
            .filter(Agent.ai_system_id == ai_system_id)
            .distinct()
            .all()
        )
        result: set[tuple[str, UUID]] = set()
        for db_type, resource_id in rows:
            api_type = _DB_TYPE_TO_API.get(db_type)
            if api_type:
                result.add((api_type, resource_id))
        return result

    def _usage_for_resources(
        self,
        *,
        resources: list[tuple[str, UUID]],
    ) -> dict[tuple[str, UUID], list[dict[str, str]]]:
        if not resources:
            return {}
        db_pairs: list[tuple[str, UUID]] = []
        for api_type, rid in resources:
            db_type = _API_TYPE_TO_DB.get(api_type)
            if db_type:
                db_pairs.append((db_type, rid))
        if not db_pairs:
            return {}
        q = (
            self._db.query(
                AgentVersionDependency.resource_type,
                AgentVersionDependency.resource_id,
                AISystem.id,
                AISystem.name,
            )
            .join(
                AgentVersion,
                AgentVersion.id == AgentVersionDependency.agent_version_id,
            )
            .join(Agent, Agent.id == AgentVersion.agent_id)
            .join(AISystem, AISystem.id == Agent.ai_system_id)
            .filter(
                or_(
                    *[
                        and_(
                            AgentVersionDependency.resource_type == db_type,
                            AgentVersionDependency.resource_id == rid,
                        )
                        for db_type, rid in db_pairs
                    ]
                )
            )
            .distinct()
        )
        out: dict[tuple[str, UUID], list[dict[str, str]]] = {}
        seen: set[tuple[str, UUID, UUID]] = set()
        for db_type, rid, system_id, system_name in q.all():
            api_type = _DB_TYPE_TO_API.get(db_type)
            if not api_type:
                continue
            key = (api_type, rid)
            dedupe = (api_type, rid, system_id)
            if dedupe in seen:
                continue
            seen.add(dedupe)
            out.setdefault(key, []).append({"id": str(system_id), "name": system_name})
        for systems in out.values():
            systems.sort(key=lambda s: s["name"].lower())
        return out

    def _load_type(
        self,
        *,
        api_type: str,
        search_term: str | None,
        status: str | None,
        environment: str | None,
        provider: str | None,
        scope: str | None,
        allowed_ids: set[tuple[str, UUID]] | None,
    ) -> list[_CatalogRow]:
        if api_type == "MODEL":
            return self._load_models(
                search_term=search_term,
                status=status,
                provider=provider,
                scope=scope,
                allowed_ids=allowed_ids,
            )
        if api_type == "MCP":
            return self._load_mcps(
                search_term=search_term,
                status=status,
                environment=environment,
                provider=provider,
                scope=scope,
                allowed_ids=allowed_ids,
            )
        if api_type == "DATA_SOURCE":
            return self._load_data_sources(
                search_term=search_term,
                status=status,
                scope=scope,
                allowed_ids=allowed_ids,
            )
        if api_type == "SERVICE":
            return self._load_services(
                search_term=search_term,
                status=status,
                environment=environment,
                provider=provider,
                scope=scope,
                allowed_ids=allowed_ids,
            )
        return []

    def _filter_allowed(
        self,
        rows: list[_CatalogRow],
        *,
        api_type: str,
        allowed_ids: set[tuple[str, UUID]] | None,
    ) -> list[_CatalogRow]:
        if allowed_ids is None:
            return rows
        return [r for r in rows if (api_type, r.id) in allowed_ids]

    def _load_models(self, **kwargs) -> list[_CatalogRow]:
        q = self._db.query(ModelResource)
        if kwargs.get("status"):
            q = q.filter(ModelResource.status == kwargs["status"])
        if kwargs.get("provider"):
            q = q.filter(ModelResource.provider.ilike(kwargs["provider"]))
        if kwargs.get("scope"):
            q = q.filter(ModelResource.scope == kwargs["scope"].upper())
        search = kwargs.get("search_term")
        if search:
            like = f"%{search}%"
            q = q.filter(
                or_(
                    ModelResource.model_name.ilike(like),
                    ModelResource.provider.ilike(like),
                    ModelResource.deployment_reference.ilike(like),
                )
            )
        rows = [
            _CatalogRow(
                id=m.id,
                resource_type="MODEL",
                key=m.model_name,
                name=m.model_name,
                provider=m.provider,
                environment=None,
                status=m.status or "ACTIVE",
                scope=m.scope or CatalogScope.PLATFORM.value,
                details=m.provider,
                tool_count=None,
                created_at=m.created_at,
            )
            for m in q.all()
        ]
        return self._filter_allowed(
            rows, api_type="MODEL", allowed_ids=kwargs.get("allowed_ids")
        )

    def _load_mcps(self, **kwargs) -> list[_CatalogRow]:
        q = self._db.query(MCPServer)
        if kwargs.get("status"):
            q = q.filter(MCPServer.status == kwargs["status"])
        if kwargs.get("environment"):
            q = q.filter(MCPServer.environment.ilike(kwargs["environment"]))
        if kwargs.get("provider"):
            q = q.filter(MCPServer.provider.ilike(kwargs["provider"]))
        if kwargs.get("scope"):
            q = q.filter(MCPServer.scope == kwargs["scope"].upper())
        search = kwargs.get("search_term")
        if search:
            like = f"%{search}%"
            q = q.filter(
                or_(
                    MCPServer.name.ilike(like),
                    MCPServer.server_key.ilike(like),
                    MCPServer.provider.ilike(like),
                )
            )
        servers = q.all()
        tool_counts: dict[UUID, int] = {}
        if servers:
            ids = [s.id for s in servers]
            count_rows = (
                self._db.query(ToolResource.mcp_server_id, func.count(ToolResource.id))
                .filter(ToolResource.mcp_server_id.in_(ids))
                .group_by(ToolResource.mcp_server_id)
                .all()
            )
            tool_counts = {sid: int(c) for sid, c in count_rows if sid}
        rows = [
            _CatalogRow(
                id=s.id,
                resource_type="MCP",
                key=s.server_key,
                name=s.name,
                provider=s.provider,
                environment=s.environment,
                status=s.status or "ACTIVE",
                scope=s.scope or CatalogScope.PLATFORM.value,
                details=f"{tool_counts.get(s.id, 0)} tools",
                tool_count=tool_counts.get(s.id, 0),
                created_at=s.created_at,
            )
            for s in servers
        ]
        return self._filter_allowed(
            rows, api_type="MCP", allowed_ids=kwargs.get("allowed_ids")
        )

    def _load_data_sources(self, **kwargs) -> list[_CatalogRow]:
        q = self._db.query(DataSource)
        if kwargs.get("status"):
            q = q.filter(DataSource.status == kwargs["status"])
        if kwargs.get("scope"):
            q = q.filter(DataSource.scope == kwargs["scope"].upper())
        search = kwargs.get("search_term")
        if search:
            like = f"%{search}%"
            q = q.filter(
                or_(
                    DataSource.name.ilike(like),
                    DataSource.data_source_key.ilike(like),
                    DataSource.classification.ilike(like),
                )
            )
        rows = [
            _CatalogRow(
                id=d.id,
                resource_type="DATA_SOURCE",
                key=d.data_source_key,
                name=d.name,
                provider=d.owner,
                environment=None,
                status=d.status or "ACTIVE",
                scope=d.scope or CatalogScope.PLATFORM.value,
                details=d.classification,
                tool_count=None,
                created_at=d.created_at,
            )
            for d in q.all()
        ]
        return self._filter_allowed(
            rows, api_type="DATA_SOURCE", allowed_ids=kwargs.get("allowed_ids")
        )

    def _load_services(self, **kwargs) -> list[_CatalogRow]:
        q = self._db.query(ExternalService)
        if kwargs.get("status"):
            q = q.filter(ExternalService.status == kwargs["status"])
        if kwargs.get("environment"):
            q = q.filter(ExternalService.environment.ilike(kwargs["environment"]))
        if kwargs.get("provider"):
            q = q.filter(ExternalService.provider.ilike(kwargs["provider"]))
        if kwargs.get("scope"):
            q = q.filter(ExternalService.scope == kwargs["scope"].upper())
        search = kwargs.get("search_term")
        if search:
            like = f"%{search}%"
            q = q.filter(
                or_(
                    ExternalService.name.ilike(like),
                    ExternalService.service_key.ilike(like),
                    ExternalService.provider.ilike(like),
                )
            )
        rows = [
            _CatalogRow(
                id=s.id,
                resource_type="SERVICE",
                key=s.service_key,
                name=s.name,
                provider=s.provider,
                environment=s.environment,
                status=s.status or "ACTIVE",
                scope=s.scope or CatalogScope.PLATFORM.value,
                details=s.endpoint_reference or s.provider,
                tool_count=None,
                created_at=s.created_at,
            )
            for s in q.all()
        ]
        return self._filter_allowed(
            rows, api_type="SERVICE", allowed_ids=kwargs.get("allowed_ids")
        )
