"""Registry application service — CRUD and lifecycle operations."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from rai_gateway.models.registry import (
    Agent,
    AgentVersion,
    AgentVersionDependency,
    AISystem,
    DataSource,
    EnterpriseRiskReference,
    ExternalService,
    MaterialChangeRecord,
    MCPServer,
    ModelResource,
    RiskAssessment,
    RiskFinding,
    RiskFindingEnterpriseRiskLink,
    ToolResource,
)
from rai_gateway.registry.domain import (
    AGENT_TRANSITIONS,
    AGENT_VERSION_TRANSITIONS,
    AI_SYSTEM_TRANSITIONS,
    ASSESSMENT_TRANSITIONS,
    AgentStatus,
    AgentVersionStatus,
    AISystemStatus,
    AssessmentStatus,
    CatalogScope,
    validate_lifecycle_transition,
    validate_score,
)
from rai_gateway.registry.errors import (
    CatalogPermissionError,
    DuplicateKeyError,
    ImmutableVersionError,
    InvalidTransitionError,
    NotFoundError,
    RelationshipError,
)
from rai_gateway.registry.material_change import (
    apply_material_change_analysis,
    compute_configuration_digest,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RegistryService:
    """Authoritative registry operations."""

    def __init__(self, db: Session) -> None:
        self._db = db

    # --- AI Systems ---
    def create_ai_system(
        self,
        *,
        system_key: str,
        name: str,
        created_by: str,
        description: str | None = None,
        business_purpose: str | None = None,
        business_unit: str | None = None,
        owner_id: str | None = None,
        technical_owner_id: str | None = None,
        criticality: str | None = None,
        risk_tier: str | None = None,
        data_classification: str | None = None,
    ) -> AISystem:
        existing = (
            self._db.query(AISystem).filter(AISystem.system_key == system_key).first()
        )
        if existing:
            raise DuplicateKeyError("system_key", system_key)
        system = AISystem(
            system_key=system_key,
            name=name,
            description=description,
            business_purpose=business_purpose,
            business_unit=business_unit,
            owner_id=owner_id,
            technical_owner_id=technical_owner_id,
            criticality=criticality,
            risk_tier=risk_tier,
            data_classification=data_classification,
            status=AISystemStatus.DRAFT.value,
            created_by=created_by,
            updated_by=created_by,
        )
        self._db.add(system)
        self._db.commit()
        self._db.refresh(system)
        return system

    def list_ai_systems(
        self,
        *,
        status: str | None = None,
        search: str | None = None,
    ) -> list[AISystem]:
        query = self._db.query(AISystem)
        if status:
            query = query.filter(AISystem.status == status)
        if search:
            pattern = f"%{search}%"
            query = query.filter(
                (AISystem.name.ilike(pattern))
                | (AISystem.system_key.ilike(pattern))
                | (AISystem.business_unit.ilike(pattern))
            )
        return query.order_by(AISystem.updated_at.desc()).all()

    def get_ai_system(self, system_id: UUID) -> AISystem:
        query = self._db.query(AISystem).filter(AISystem.id == system_id)
        system = query.first()
        if not system:
            raise NotFoundError("AI system", str(system_id))
        return system

    def update_ai_system(
        self,
        system_id: UUID,
        *,
        updated_by: str,
        **fields: Any,
    ) -> AISystem:
        system = self.get_ai_system(system_id)
        mutable = {
            "name",
            "description",
            "business_purpose",
            "business_unit",
            "owner_id",
            "technical_owner_id",
            "criticality",
            "risk_tier",
            "data_classification",
        }
        for key, value in fields.items():
            if key in mutable and value is not None:
                setattr(system, key, value)
        system.updated_by = updated_by
        self._db.commit()
        self._db.refresh(system)
        return system

    def transition_ai_system(
        self,
        system_id: UUID,
        target_status: str,
        *,
        updated_by: str,
    ) -> AISystem:
        system = self.get_ai_system(system_id)
        try:
            validate_lifecycle_transition(
                system.status,
                target_status,
                AI_SYSTEM_TRANSITIONS,
                AISystemStatus,
            )
        except ValueError as exc:
            raise InvalidTransitionError(str(exc)) from exc
        system.status = target_status
        system.updated_by = updated_by
        if target_status == AISystemStatus.RETIRED.value:
            system.retired_at = _utcnow()
        self._db.commit()
        self._db.refresh(system)
        return system

    def count_agents_for_system(self, system_id: UUID) -> int:
        return (
            self._db.query(func.count(Agent.id))
            .filter(Agent.ai_system_id == system_id)
            .scalar()
            or 0
        )

    # --- Agents ---
    def create_agent(
        self,
        system_id: UUID,
        *,
        agent_key: str,
        name: str,
        created_by: str,
        description: str | None = None,
        business_purpose: str | None = None,
        owner_id: str | None = None,
        avatar: str | None = None,
    ) -> Agent:
        self.get_ai_system(system_id)
        existing = self._db.query(Agent).filter(Agent.agent_key == agent_key).first()
        if existing:
            raise DuplicateKeyError("agent_key", agent_key)
        agent = Agent(
            agent_key=agent_key,
            ai_system_id=system_id,
            name=name,
            description=description,
            business_purpose=business_purpose,
            owner_id=owner_id,
            avatar=avatar.strip()
            if isinstance(avatar, str) and avatar.strip()
            else None,
            status=AgentStatus.DRAFT.value,
            created_by=created_by,
            updated_by=created_by,
        )
        self._db.add(agent)
        self._db.commit()
        self._db.refresh(agent)
        return agent

    def list_agents(self, system_id: UUID) -> list[Agent]:
        self.get_ai_system(system_id)
        return (
            self._db.query(Agent)
            .filter(Agent.ai_system_id == system_id)
            .order_by(Agent.updated_at.desc())
            .all()
        )

    def get_agent(self, agent_id: UUID) -> Agent:
        query = self._db.query(Agent).filter(Agent.id == agent_id)
        agent = query.first()
        if not agent:
            raise NotFoundError("Agent", str(agent_id))
        return agent

    def update_agent(
        self,
        agent_id: UUID,
        *,
        updated_by: str,
        **fields: Any,
    ) -> Agent:
        agent = self.get_agent(agent_id)
        mutable = {"name", "description", "business_purpose", "owner_id", "avatar"}
        for key, value in fields.items():
            if key not in mutable:
                continue
            if key == "avatar":
                setattr(
                    agent,
                    key,
                    value.strip() if isinstance(value, str) and value.strip() else None,
                )
            elif value is not None:
                setattr(agent, key, value)
        agent.updated_by = updated_by
        self._db.commit()
        self._db.refresh(agent)
        return agent

    def transition_agent(
        self,
        agent_id: UUID,
        target_status: str,
        *,
        updated_by: str,
    ) -> Agent:
        agent = self.get_agent(agent_id)
        try:
            validate_lifecycle_transition(
                agent.status,
                target_status,
                AGENT_TRANSITIONS,
                AgentStatus,
            )
        except ValueError as exc:
            raise InvalidTransitionError(str(exc)) from exc
        agent.status = target_status
        agent.updated_by = updated_by
        if target_status == AgentStatus.RETIRED.value:
            agent.retired_at = _utcnow()
        self._db.commit()
        self._db.refresh(agent)
        return agent

    # --- Agent Versions ---
    def create_agent_version(
        self,
        agent_id: UUID,
        *,
        created_by: str,
        change_summary: str | None = None,
        configuration_snapshot: dict[str, Any] | None = None,
        risk_tier: str | None = None,
        evaluation_endpoint_url: str | None = None,
    ) -> AgentVersion:
        self.get_agent(agent_id)
        max_version = (
            self._db.query(func.max(AgentVersion.version_number))
            .filter(AgentVersion.agent_id == agent_id)
            .scalar()
        )
        next_number = (max_version or 0) + 1
        digest = compute_configuration_digest(configuration_snapshot)
        version = AgentVersion(
            agent_id=agent_id,
            version_number=next_number,
            change_summary=change_summary,
            configuration_snapshot=configuration_snapshot,
            configuration_digest=digest,
            evaluation_endpoint_url=evaluation_endpoint_url,
            risk_tier=risk_tier,
            lifecycle_status=AgentVersionStatus.DRAFT.value,
            created_by=created_by,
        )
        self._db.add(version)
        self._db.commit()
        self._db.refresh(version)
        # Compare with previous approved version if any
        prev = self._previous_version(agent_id, next_number)
        apply_material_change_analysis(self._db, version, prev)
        self._db.commit()
        self._db.refresh(version)
        return version

    def _previous_version(
        self, agent_id: UUID, current_number: int
    ) -> AgentVersion | None:
        return (
            self._db.query(AgentVersion)
            .filter(
                AgentVersion.agent_id == agent_id,
                AgentVersion.version_number < current_number,
            )
            .order_by(AgentVersion.version_number.desc())
            .first()
        )

    def list_agent_versions(self, agent_id: UUID) -> list[AgentVersion]:
        self.get_agent(agent_id)
        return (
            self._db.query(AgentVersion)
            .filter(AgentVersion.agent_id == agent_id)
            .order_by(AgentVersion.version_number.desc())
            .all()
        )

    def get_agent_version(self, version_id: UUID) -> AgentVersion:
        query = self._db.query(AgentVersion).filter(AgentVersion.id == version_id)
        version = query.first()
        if not version:
            raise NotFoundError("Agent version", str(version_id))
        return version

    def transition_agent_version(
        self,
        version_id: UUID,
        target_status: str,
        *,
        updated_by: str,
    ) -> AgentVersion:
        version = self.get_agent_version(version_id)
        try:
            validate_lifecycle_transition(
                version.lifecycle_status,
                target_status,
                AGENT_VERSION_TRANSITIONS,
                AgentVersionStatus,
            )
        except ValueError as exc:
            raise InvalidTransitionError(str(exc)) from exc
        if target_status == AgentVersionStatus.APPROVED.value:
            if version.material_change_status == "MATERIAL" and (
                version.lifecycle_status
                != AgentVersionStatus.REASSESSMENT_REQUIRED.value
                and version.lifecycle_status != AgentVersionStatus.UNDER_REVIEW.value
            ):
                raise InvalidTransitionError(
                    "Material change requires reassessment before approval"
                )
        version.lifecycle_status = target_status
        now = _utcnow()
        if target_status == AgentVersionStatus.UNDER_REVIEW.value:
            version.submitted_at = now
        if target_status == AgentVersionStatus.APPROVED.value:
            version.approved_at = now
            agent = self.get_agent(version.agent_id)
            agent.current_version_id = version.id
        if target_status == AgentVersionStatus.RETIRED.value:
            version.retired_at = now
        self._db.commit()
        self._db.refresh(version)
        return version

    def update_draft_version(
        self,
        version_id: UUID,
        *,
        change_summary: str | None = None,
        configuration_snapshot: dict[str, Any] | None = None,
        risk_tier: str | None = None,
        evaluation_endpoint_url: str | None = None,
    ) -> AgentVersion:
        version = self.get_agent_version(version_id)
        # evaluation_endpoint_url is operational binding for live eval — not config.
        endpoint_only = (
            evaluation_endpoint_url is not None
            and change_summary is None
            and configuration_snapshot is None
            and risk_tier is None
        )
        if version.lifecycle_status not in (
            AgentVersionStatus.DRAFT.value,
            AgentVersionStatus.REASSESSMENT_REQUIRED.value,
        ):
            if not endpoint_only:
                raise ImmutableVersionError(
                    "Approved or governed versions cannot be mutated in place"
                )
            version.evaluation_endpoint_url = evaluation_endpoint_url
            self._db.commit()
            self._db.refresh(version)
            return version
        if change_summary is not None:
            version.change_summary = change_summary
        if configuration_snapshot is not None:
            version.configuration_snapshot = configuration_snapshot
            version.configuration_digest = compute_configuration_digest(
                configuration_snapshot
            )
        if risk_tier is not None:
            version.risk_tier = risk_tier
        if evaluation_endpoint_url is not None:
            version.evaluation_endpoint_url = evaluation_endpoint_url
        prev = self._previous_version(version.agent_id, version.version_number)
        apply_material_change_analysis(self._db, version, prev)
        self._db.commit()
        self._db.refresh(version)
        return version

    def get_material_changes(self, version_id: UUID) -> list[MaterialChangeRecord]:
        self.get_agent_version(version_id)
        return (
            self._db.query(MaterialChangeRecord)
            .filter(MaterialChangeRecord.to_version_id == version_id)
            .all()
        )

    # --- Dependency resources (catalog scope is a label) ---
    def _resolve_catalog_scope(self, scope: str | None) -> str:
        resolved = (scope or CatalogScope.ORGANIZATION.value).upper()
        if resolved not in {
            CatalogScope.PLATFORM.value,
            CatalogScope.ORGANIZATION.value,
        }:
            raise RelationshipError(f"Unknown catalog scope: {resolved}")
        return resolved

    def _assert_catalog_mutable(
        self,
        resource: Any,
        *,
        allow_platform_mutation: bool = False,
    ) -> None:
        if (
            resource.scope == CatalogScope.PLATFORM.value
            and not allow_platform_mutation
        ):
            raise CatalogPermissionError(
                "Built-in PLATFORM catalog resources cannot be modified"
            )

    def _find_keyed_duplicate(
        self,
        model: Any,
        key_attr: str,
        key_value: str,
        *,
        scope: str,
    ) -> Any | None:
        return (
            self._db.query(model)
            .filter(
                getattr(model, key_attr) == key_value,
                model.scope == scope,
            )
            .first()
        )

    def create_model_resource(
        self,
        *,
        scope: str | None = None,
        allow_platform: bool = False,
        **fields: Any,
    ) -> ModelResource:
        resolved_scope = self._resolve_catalog_scope(scope)
        if resolved_scope == CatalogScope.PLATFORM.value and not allow_platform:
            raise CatalogPermissionError(
                "Only platform operators can create PLATFORM catalog resources"
            )
        if "metadata" in fields:
            fields["metadata_"] = fields.pop("metadata")
        resource = ModelResource(
            scope=resolved_scope,
            **fields,
        )
        self._db.add(resource)
        self._db.commit()
        self._db.refresh(resource)
        return resource

    def list_model_resources(self, *, scope: str | None = None) -> list[ModelResource]:
        query = self._db.query(ModelResource)
        if scope:
            query = query.filter(ModelResource.scope == scope.upper())
        return query.order_by(ModelResource.created_at.desc()).all()

    def get_model_resource(self, model_id: UUID) -> ModelResource:
        query = self._db.query(ModelResource).filter(ModelResource.id == model_id)
        resource = query.first()
        if not resource:
            raise NotFoundError("model", str(model_id))
        return resource

    def update_model_resource(
        self,
        model_id: UUID,
        *,
        allow_platform_mutation: bool = False,
        **fields: Any,
    ) -> ModelResource:
        resource = self.get_model_resource(model_id)
        self._assert_catalog_mutable(
            resource,
            allow_platform_mutation=allow_platform_mutation,
        )
        mutable = {
            "provider",
            "model_name",
            "model_version",
            "deployment_reference",
            "hosting_type",
        }
        if "metadata" in fields:
            fields["metadata_"] = fields.pop("metadata")
        for key, value in fields.items():
            if key in mutable and value is not None:
                setattr(resource, key, value)
        self._db.commit()
        self._db.refresh(resource)
        return resource

    def create_tool_resource(
        self,
        *,
        scope: str | None = None,
        allow_platform: bool = False,
        **fields: Any,
    ) -> ToolResource:
        resolved_scope = self._resolve_catalog_scope(scope)
        if resolved_scope == CatalogScope.PLATFORM.value and not allow_platform:
            raise CatalogPermissionError(
                "Only platform operators can create PLATFORM catalog resources"
            )
        tool_key = fields.get("tool_key")
        if tool_key and self._find_keyed_duplicate(
            ToolResource,
            "tool_key",
            tool_key,
            scope=resolved_scope,
        ):
            raise DuplicateKeyError("tool_key", tool_key)
        if "metadata" in fields:
            fields["metadata_"] = fields.pop("metadata")
        mcp_server_id = fields.get("mcp_server_id")
        if mcp_server_id:
            self._validate_resource_exists(
                "mcp_server",
                mcp_server_id,
            )
        resource = ToolResource(
            scope=resolved_scope,
            **fields,
        )
        self._db.add(resource)
        self._db.commit()
        self._db.refresh(resource)
        return resource

    def list_tool_resources(self, *, scope: str | None = None) -> list[ToolResource]:
        query = self._db.query(ToolResource)
        if scope:
            query = query.filter(ToolResource.scope == scope.upper())
        return query.order_by(ToolResource.created_at.desc()).all()

    def list_tools_for_mcp(self, mcp_server_id: UUID) -> list[ToolResource]:
        self.get_mcp_server(mcp_server_id)
        query = self._db.query(ToolResource).filter(
            ToolResource.mcp_server_id == mcp_server_id
        )
        return query.order_by(ToolResource.tool_key).all()

    def get_tool_resource(self, tool_id: UUID) -> ToolResource:
        query = self._db.query(ToolResource).filter(ToolResource.id == tool_id)
        resource = query.first()
        if not resource:
            raise NotFoundError("tool", str(tool_id))
        return resource

    def update_tool_resource(
        self,
        tool_id: UUID,
        *,
        allow_platform_mutation: bool = False,
        **fields: Any,
    ) -> ToolResource:
        resource = self.get_tool_resource(tool_id)
        self._assert_catalog_mutable(
            resource,
            allow_platform_mutation=allow_platform_mutation,
        )
        metadata_keys = {
            "capability_type",
            "side_effect",
            "default_risk",
            "default_requires_approval",
        }
        metadata = dict(resource.metadata_ or {})
        metadata_changed = False
        for key in metadata_keys:
            if key in fields:
                metadata[key] = fields.pop(key)
                metadata_changed = True
        if metadata_changed:
            resource.metadata_ = metadata
        mutable = {
            "name",
            "description",
            "category",
            "provider",
            "sensitivity",
            "consequential_action",
            "status",
        }
        for key, value in fields.items():
            if key in mutable and value is not None:
                setattr(resource, key, value)
        self._db.commit()
        self._db.refresh(resource)
        return resource

    def create_mcp_server(
        self,
        *,
        scope: str | None = None,
        allow_platform: bool = False,
        **fields: Any,
    ) -> MCPServer:
        resolved_scope = self._resolve_catalog_scope(scope)
        if resolved_scope == CatalogScope.PLATFORM.value and not allow_platform:
            raise CatalogPermissionError(
                "Only platform operators can create PLATFORM catalog resources"
            )
        server_key = fields.get("server_key")
        if server_key and self._find_keyed_duplicate(
            MCPServer,
            "server_key",
            server_key,
            scope=resolved_scope,
        ):
            raise DuplicateKeyError("server_key", server_key)
        if "metadata" in fields:
            fields["metadata_"] = fields.pop("metadata")
        resource = MCPServer(
            scope=resolved_scope,
            **fields,
        )
        self._db.add(resource)
        self._db.commit()
        self._db.refresh(resource)
        return resource

    def list_mcp_servers(self, *, scope: str | None = None) -> list[MCPServer]:
        query = self._db.query(MCPServer)
        if scope:
            query = query.filter(MCPServer.scope == scope.upper())
        return query.order_by(MCPServer.created_at.desc()).all()

    def get_mcp_server(self, mcp_server_id: UUID) -> MCPServer:
        query = self._db.query(MCPServer).filter(MCPServer.id == mcp_server_id)
        server = query.first()
        if not server:
            raise NotFoundError("MCP server", str(mcp_server_id))
        return server

    def update_mcp_server(
        self,
        mcp_server_id: UUID,
        *,
        allow_platform_mutation: bool = False,
        **fields: Any,
    ) -> MCPServer:
        server = self.get_mcp_server(mcp_server_id)
        self._assert_catalog_mutable(
            server,
            allow_platform_mutation=allow_platform_mutation,
        )
        mutable = {
            "name",
            "description",
            "provider",
            "environment",
            "endpoint_reference",
            "trust_classification",
        }
        if "metadata" in fields:
            fields["metadata_"] = fields.pop("metadata")
        for key, value in fields.items():
            if key in mutable and value is not None:
                setattr(server, key, value)
        self._db.commit()
        self._db.refresh(server)
        return server

    def create_external_service(
        self,
        *,
        scope: str | None = None,
        allow_platform: bool = False,
        **fields: Any,
    ) -> ExternalService:
        resolved_scope = self._resolve_catalog_scope(scope)
        if resolved_scope == CatalogScope.PLATFORM.value and not allow_platform:
            raise CatalogPermissionError(
                "Only platform operators can create PLATFORM catalog resources"
            )
        service_key = fields.get("service_key")
        if service_key and self._find_keyed_duplicate(
            ExternalService,
            "service_key",
            service_key,
            scope=resolved_scope,
        ):
            raise DuplicateKeyError("service_key", service_key)
        if "metadata" in fields:
            fields["metadata_"] = fields.pop("metadata")
        resource = ExternalService(
            scope=resolved_scope,
            **fields,
        )
        self._db.add(resource)
        self._db.commit()
        self._db.refresh(resource)
        return resource

    def list_external_services(
        self, *, scope: str | None = None
    ) -> list[ExternalService]:
        query = self._db.query(ExternalService)
        if scope:
            query = query.filter(ExternalService.scope == scope.upper())
        return query.order_by(ExternalService.created_at.desc()).all()

    def create_data_source(
        self,
        *,
        scope: str | None = None,
        allow_platform: bool = False,
        **fields: Any,
    ) -> DataSource:
        resolved_scope = self._resolve_catalog_scope(scope)
        if resolved_scope == CatalogScope.PLATFORM.value and not allow_platform:
            raise CatalogPermissionError(
                "Only platform operators can create PLATFORM catalog resources"
            )
        data_source_key = fields.get("data_source_key")
        if data_source_key and self._find_keyed_duplicate(
            DataSource,
            "data_source_key",
            data_source_key,
            scope=resolved_scope,
        ):
            raise DuplicateKeyError("data_source_key", data_source_key)
        if "metadata" in fields:
            fields["metadata_"] = fields.pop("metadata")
        resource = DataSource(
            scope=resolved_scope,
            **fields,
        )
        self._db.add(resource)
        self._db.commit()
        self._db.refresh(resource)
        return resource

    def list_data_sources(self, *, scope: str | None = None) -> list[DataSource]:
        query = self._db.query(DataSource)
        if scope:
            query = query.filter(DataSource.scope == scope.upper())
        return query.order_by(DataSource.created_at.desc()).all()

    def get_system_hierarchy(self, system_id: UUID) -> dict[str, Any]:
        """Return AI System → Agents → Versions → Model/dependencies tree."""
        system = self.get_ai_system(system_id)
        agents = self.list_agents(system_id)
        dep_type_keys = {
            "model": "models",
            "tool": "tools",
            "mcp_server": "mcp_servers",
            "data_source": "data_sources",
            "external_service": "external_services",
        }
        agent_nodes: list[dict[str, Any]] = []
        for agent in agents:
            versions = self.list_agent_versions(agent.id)
            version_nodes: list[dict[str, Any]] = []
            for version in versions:
                deps = self.list_version_dependencies(version.id)
                dep_counts = {v: 0 for v in dep_type_keys.values()}
                model_info: dict[str, Any] | None = None
                for dep in deps:
                    key = dep_type_keys.get(dep.resource_type)
                    if key:
                        dep_counts[key] += 1
                    if dep.resource_type == "model" and model_info is None:
                        model = (
                            self._db.query(ModelResource)
                            .filter(ModelResource.id == dep.resource_id)
                            .first()
                        )
                        if model:
                            model_info = {
                                "id": str(model.id),
                                "provider": model.provider,
                                "model_name": model.model_name,
                                "label": f"{model.provider}/{model.model_name}",
                            }
                version_nodes.append(
                    {
                        "id": str(version.id),
                        "version_number": version.version_number,
                        "lifecycle_status": version.lifecycle_status,
                        "risk_tier": version.risk_tier,
                        "material_change_status": version.material_change_status,
                        "change_summary": version.change_summary,
                        "approved_at": (
                            version.approved_at.isoformat()
                            if version.approved_at
                            else None
                        ),
                        "is_current": str(version.id) == str(agent.current_version_id)
                        if agent.current_version_id
                        else False,
                        "model": model_info,
                        "dependency_counts": dep_counts,
                    }
                )
            agent_nodes.append(
                {
                    "id": str(agent.id),
                    "agent_key": agent.agent_key,
                    "name": agent.name,
                    "status": agent.status,
                    "current_version_id": (
                        str(agent.current_version_id)
                        if agent.current_version_id
                        else None
                    ),
                    "versions": version_nodes,
                }
            )
        return {
            "system": {
                "id": str(system.id),
                "system_key": system.system_key,
                "name": system.name,
                "status": system.status,
                "risk_tier": system.risk_tier,
                "business_unit": system.business_unit,
            },
            "agents": agent_nodes,
        }

    def _ensure_version_mutable(self, version: AgentVersion) -> None:
        if version.lifecycle_status not in (
            AgentVersionStatus.DRAFT.value,
            AgentVersionStatus.REASSESSMENT_REQUIRED.value,
        ):
            raise ImmutableVersionError(
                "Dependencies can only be modified on draft versions"
            )

    def _version_mcp_server_ids(self, version_id: UUID) -> set[UUID]:
        rows = (
            self._db.query(AgentVersionDependency.resource_id)
            .filter(
                AgentVersionDependency.agent_version_id == version_id,
                AgentVersionDependency.resource_type == "mcp_server",
            )
            .all()
        )
        return {row[0] for row in rows}

    def _validate_tool_dependency(self, version_id: UUID, tool_id: UUID) -> None:
        tool = self._db.query(ToolResource).filter(ToolResource.id == tool_id).first()
        if not tool:
            raise NotFoundError("tool", str(tool_id))
        if not tool.mcp_server_id:
            return
        associated_mcps = self._version_mcp_server_ids(version_id)
        if tool.mcp_server_id not in associated_mcps:
            raise RelationshipError(
                "Tool can only be selected for MCP servers already associated with this version"
            )

    def add_version_dependency(
        self,
        version_id: UUID,
        *,
        resource_type: str,
        resource_id: UUID,
        usage_purpose: str | None = None,
        access_mode: str | None = None,
        capability_declaration: str | None = None,
        required: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> AgentVersionDependency:
        version = self.get_agent_version(version_id)
        self._ensure_version_mutable(version)
        self._validate_resource_exists(resource_type, resource_id)
        existing = (
            self._db.query(AgentVersionDependency)
            .filter(
                AgentVersionDependency.agent_version_id == version_id,
                AgentVersionDependency.resource_type == resource_type,
                AgentVersionDependency.resource_id == resource_id,
            )
            .first()
        )
        if existing:
            raise DuplicateKeyError(
                "version_dependency",
                f"{resource_type}:{resource_id}",
            )
        if resource_type == "tool":
            self._validate_tool_dependency(version_id, resource_id)
        dep = AgentVersionDependency(
            agent_version_id=version_id,
            resource_type=resource_type,
            resource_id=resource_id,
            usage_purpose=usage_purpose,
            access_mode=access_mode,
            capability_declaration=capability_declaration,
            required=required,
            metadata_=metadata,
        )
        self._db.add(dep)
        self._db.commit()
        prev = self._previous_version(version.agent_id, version.version_number)
        apply_material_change_analysis(self._db, version, prev)
        self._db.commit()
        self._db.refresh(dep)
        return dep

    def remove_version_dependency(self, version_id: UUID, dependency_id: UUID) -> None:
        version = self.get_agent_version(version_id)
        self._ensure_version_mutable(version)
        dep = (
            self._db.query(AgentVersionDependency)
            .filter(
                AgentVersionDependency.id == dependency_id,
                AgentVersionDependency.agent_version_id == version_id,
            )
            .first()
        )
        if not dep:
            raise NotFoundError("version dependency", str(dependency_id))
        to_remove = [dep]
        if dep.resource_type == "mcp_server":
            tool_ids = {
                row.id
                for row in self._db.query(ToolResource.id)
                .filter(ToolResource.mcp_server_id == dep.resource_id)
                .all()
            }
            if tool_ids:
                tool_deps = (
                    self._db.query(AgentVersionDependency)
                    .filter(
                        AgentVersionDependency.agent_version_id == version_id,
                        AgentVersionDependency.resource_type == "tool",
                        AgentVersionDependency.resource_id.in_(tool_ids),
                    )
                    .all()
                )
                to_remove.extend(tool_deps)
        for row in to_remove:
            self._db.delete(row)
        self._db.commit()
        prev = self._previous_version(version.agent_id, version.version_number)
        apply_material_change_analysis(self._db, version, prev)
        self._db.commit()

    def list_version_dependencies(
        self, version_id: UUID
    ) -> list[AgentVersionDependency]:
        self.get_agent_version(version_id)
        return (
            self._db.query(AgentVersionDependency)
            .filter(AgentVersionDependency.agent_version_id == version_id)
            .all()
        )

    def _validate_resource_exists(self, resource_type: str, resource_id: UUID) -> None:
        model_map = {
            "model": ModelResource,
            "tool": ToolResource,
            "mcp_server": MCPServer,
            "external_service": ExternalService,
            "data_source": DataSource,
        }
        model_cls = model_map.get(resource_type)
        if not model_cls:
            raise RelationshipError(f"Unknown resource type: {resource_type}")
        query = self._db.query(model_cls).filter(model_cls.id == resource_id)
        row = query.first()
        if not row:
            raise NotFoundError(resource_type, str(resource_id))

    # --- Risk ---
    def create_risk_assessment(
        self,
        *,
        ai_system_id: UUID,
        agent_version_id: UUID | None = None,
        assessed_by: str,
        **fields: Any,
    ) -> RiskAssessment:
        self.get_ai_system(ai_system_id)
        if agent_version_id:
            version = self.get_agent_version(agent_version_id)
            agent = self.get_agent(version.agent_id)
            if agent.ai_system_id != ai_system_id:
                raise RelationshipError(
                    "Agent version does not belong to the specified AI system"
                )
        for score_field in (
            "overall_score",
            "impact_score",
            "likelihood_score",
            "exposure_score",
            "confidence_score",
        ):
            if score_field in fields:
                validate_score(fields[score_field], score_field)
        assessment = RiskAssessment(
            ai_system_id=ai_system_id,
            agent_version_id=agent_version_id,
            status=AssessmentStatus.DRAFT.value,
            assessed_by=assessed_by,
            assessed_at=_utcnow(),
            **fields,
        )
        self._db.add(assessment)
        self._db.commit()
        self._db.refresh(assessment)
        return assessment

    def transition_risk_assessment(
        self, assessment_id: UUID, target_status: str
    ) -> RiskAssessment:
        assessment = self.get_risk_assessment(assessment_id)
        try:
            validate_lifecycle_transition(
                assessment.status,
                target_status,
                ASSESSMENT_TRANSITIONS,
                AssessmentStatus,
            )
        except ValueError as exc:
            raise InvalidTransitionError(str(exc)) from exc
        assessment.status = target_status
        self._db.commit()
        self._db.refresh(assessment)
        return assessment

    def get_risk_assessment(self, assessment_id: UUID) -> RiskAssessment:
        query = self._db.query(RiskAssessment).filter(
            RiskAssessment.id == assessment_id
        )
        row = query.first()
        if not row:
            raise NotFoundError("Risk assessment", str(assessment_id))
        return row

    def create_risk_finding(
        self,
        assessment_id: UUID,
        *,
        category: str,
        title: str,
        severity: str,
        **fields: Any,
    ) -> RiskFinding:
        self.get_risk_assessment(assessment_id)
        for score_field in ("likelihood", "impact", "score"):
            if score_field in fields:
                validate_score(fields[score_field], score_field)
        finding = RiskFinding(
            risk_assessment_id=assessment_id,
            category=category,
            title=title,
            severity=severity,
            **fields,
        )
        self._db.add(finding)
        self._db.commit()
        self._db.refresh(finding)
        return finding

    def create_enterprise_risk_reference(
        self, **fields: Any
    ) -> EnterpriseRiskReference:
        existing = (
            self._db.query(EnterpriseRiskReference)
            .filter(EnterpriseRiskReference.external_key == fields.get("external_key"))
            .first()
        )
        if existing:
            raise DuplicateKeyError("external_key", fields["external_key"])
        if "metadata" in fields:
            fields["metadata_"] = fields.pop("metadata")
        ref = EnterpriseRiskReference(**fields)
        self._db.add(ref)
        self._db.commit()
        self._db.refresh(ref)
        return ref

    def get_risk_finding(self, finding_id: UUID) -> RiskFinding:
        query = self._db.query(RiskFinding).filter(RiskFinding.id == finding_id)
        finding = query.first()
        if not finding:
            raise NotFoundError("Risk finding", str(finding_id))
        return finding

    def link_finding_to_enterprise_risk(
        self, finding_id: UUID, enterprise_risk_id: UUID
    ) -> RiskFindingEnterpriseRiskLink:
        finding = self.get_risk_finding(finding_id)
        ref = (
            self._db.query(EnterpriseRiskReference)
            .filter(EnterpriseRiskReference.id == enterprise_risk_id)
            .first()
        )
        if not ref:
            raise NotFoundError("Enterprise risk reference", str(enterprise_risk_id))
        link = RiskFindingEnterpriseRiskLink(
            risk_finding_id=finding.id,
            enterprise_risk_reference_id=enterprise_risk_id,
        )
        self._db.add(link)
        self._db.commit()
        self._db.refresh(link)
        return link

    def list_assessments_for_version(self, version_id: UUID) -> list[RiskAssessment]:
        self.get_agent_version(version_id)
        return (
            self._db.query(RiskAssessment)
            .filter(RiskAssessment.agent_version_id == version_id)
            .order_by(RiskAssessment.created_at.desc())
            .all()
        )
