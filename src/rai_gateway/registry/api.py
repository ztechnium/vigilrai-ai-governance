"""WP1 Registry REST API."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import rai_gateway.models.registry  # noqa: F401 — register models with Base.metadata
from rai_gateway.core.authorization import (
    require_permission,
    require_platform_permission,
    require_user,
)
from rai_gateway.core.database import get_db
from rai_gateway.core.observability import generate_trace_id, log_admin_audit
from rai_gateway.core.principal import Principal
from rai_gateway.core.tenant_context import TenantContext
from rai_gateway.registry.catalog_query import ResourceCatalogQueryService
from rai_gateway.registry.eligibility import EligibilityService
from rai_gateway.registry.errors import RegistryError
from rai_gateway.registry.mcp_discovery import MCPDiscoveryService
from rai_gateway.registry.seed_mcp_catalog import MCPSeedCatalogService
from rai_gateway.registry.service import RegistryService

router = APIRouter(prefix="/v1", tags=["registry"])


def _handle_registry_error(exc: RegistryError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={"error": exc.error_code, "message": exc.message},
    )


def _svc(db: Session = Depends(get_db)) -> RegistryService:
    return RegistryService(db)


def _catalog_query(db: Session = Depends(get_db)) -> ResourceCatalogQueryService:
    return ResourceCatalogQueryService(db)


# --- Pydantic schemas ---
class AISystemCreate(BaseModel):
    system_key: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    description: str | None = None
    business_purpose: str | None = None
    business_unit: str | None = None
    owner_id: str | None = None
    technical_owner_id: str | None = None
    criticality: str | None = None
    risk_tier: str | None = None
    data_classification: str | None = None


class AISystemUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    business_purpose: str | None = None
    business_unit: str | None = None
    owner_id: str | None = None
    technical_owner_id: str | None = None
    criticality: str | None = None
    risk_tier: str | None = None
    data_classification: str | None = None


class LifecycleTransition(BaseModel):
    status: str


class AgentCreate(BaseModel):
    agent_key: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    description: str | None = None
    business_purpose: str | None = None
    owner_id: str | None = None
    avatar: str | None = None


class AgentUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    business_purpose: str | None = None
    owner_id: str | None = None
    avatar: str | None = None


class AgentVersionCreate(BaseModel):
    change_summary: str | None = None
    configuration_snapshot: dict[str, Any] | None = None
    risk_tier: str | None = None
    evaluation_endpoint_url: str | None = None


class AgentVersionUpdate(BaseModel):
    change_summary: str | None = None
    configuration_snapshot: dict[str, Any] | None = None
    risk_tier: str | None = None
    evaluation_endpoint_url: str | None = None


class ToolResourceCreate(BaseModel):
    tool_key: str
    name: str
    description: str | None = None
    category: str | None = None
    provider: str | None = None
    mcp_server_id: UUID | None = None
    sensitivity: str | None = None
    consequential_action: bool = False
    metadata: dict[str, Any] | None = None


class ToolResourceUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    category: str | None = None
    consequential_action: bool | None = None
    status: str | None = None
    capability_type: str | None = None
    side_effect: str | None = None
    default_risk: str | None = None
    default_requires_approval: bool | None = None


class ModelResourceCreate(BaseModel):
    provider: str
    model_name: str
    model_version: str | None = None
    deployment_reference: str | None = None
    hosting_type: str | None = None
    metadata: dict[str, Any] | None = None


class ModelResourceUpdate(BaseModel):
    provider: str | None = None
    model_name: str | None = None
    model_version: str | None = None
    deployment_reference: str | None = None
    hosting_type: str | None = None
    metadata: dict[str, Any] | None = None


class MCPServerCreate(BaseModel):
    server_key: str
    name: str
    description: str | None = None
    provider: str | None = None
    environment: str | None = None
    endpoint_reference: str | None = None
    trust_classification: str | None = None
    metadata: dict[str, Any] | None = None


class MCPServerUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    provider: str | None = None
    environment: str | None = None
    endpoint_reference: str | None = None
    trust_classification: str | None = None
    metadata: dict[str, Any] | None = None


class ExternalServiceCreate(BaseModel):
    service_key: str
    name: str
    description: str | None = None
    provider: str | None = None
    environment: str | None = None
    endpoint_reference: str | None = None
    sensitivity: str | None = None
    trust_classification: str | None = None
    metadata: dict[str, Any] | None = None


class DataSourceCreate(BaseModel):
    data_source_key: str
    name: str
    description: str | None = None
    owner: str | None = None
    classification: str | None = None
    contains_personal_data: bool = False
    contains_sensitive_data: bool = False
    jurisdiction: str | None = None
    metadata: dict[str, Any] | None = None


class VersionDependencyCreate(BaseModel):
    resource_type: str
    resource_id: UUID
    usage_purpose: str | None = None
    access_mode: str | None = None
    capability_declaration: str | None = None
    required: bool = True
    metadata: dict[str, Any] | None = None


class RiskAssessmentCreate(BaseModel):
    ai_system_id: UUID
    agent_version_id: UUID | None = None
    risk_tier: str | None = None
    overall_score: int | None = None
    impact_score: int | None = None
    likelihood_score: int | None = None
    exposure_score: int | None = None
    confidence_score: int | None = None
    rationale: str | None = None
    next_review_at: str | None = None


class RiskFindingCreate(BaseModel):
    category: str
    title: str
    severity: str
    description: str | None = None
    likelihood: int | None = None
    impact: int | None = None
    score: int | None = None
    source: str | None = None
    rationale: str | None = None
    owner: str | None = None


class EnterpriseRiskCreate(BaseModel):
    external_key: str
    source_system: str
    name: str
    description: str | None = None
    category: str | None = None
    metadata: dict[str, Any] | None = None


class EnterpriseRiskLinkCreate(BaseModel):
    enterprise_risk_reference_id: UUID


class EligibilityCheckRequest(BaseModel):
    system_id: UUID | None = None
    system_key: str | None = None
    agent_id: UUID | None = None
    agent_key: str | None = None
    version_id: UUID | None = None
    version_number: int | None = None
    caller_system_id: str | None = None
    caller_tools: list[str] | None = None


def _serialize_system(svc: RegistryService, system) -> dict[str, Any]:
    return {
        "id": str(system.id),
        "system_key": system.system_key,
        "name": system.name,
        "description": system.description,
        "business_purpose": system.business_purpose,
        "business_unit": system.business_unit,
        "owner_id": system.owner_id,
        "technical_owner_id": system.technical_owner_id,
        "status": system.status,
        "criticality": system.criticality,
        "risk_tier": system.risk_tier,
        "data_classification": system.data_classification,
        "agent_count": svc.count_agents_for_system(system.id),
        "created_at": system.created_at.isoformat() if system.created_at else None,
        "created_by": system.created_by,
        "updated_at": system.updated_at.isoformat() if system.updated_at else None,
        "updated_by": system.updated_by,
        "retired_at": system.retired_at.isoformat() if system.retired_at else None,
    }


def _serialize_agent(agent) -> dict[str, Any]:
    return {
        "id": str(agent.id),
        "agent_key": agent.agent_key,
        "ai_system_id": str(agent.ai_system_id),
        "name": agent.name,
        "description": agent.description,
        "business_purpose": agent.business_purpose,
        "owner_id": agent.owner_id,
        "avatar": agent.avatar,
        "status": agent.status,
        "current_version_id": (
            str(agent.current_version_id) if agent.current_version_id else None
        ),
        "created_at": agent.created_at.isoformat() if agent.created_at else None,
        "created_by": agent.created_by,
        "updated_at": agent.updated_at.isoformat() if agent.updated_at else None,
        "updated_by": agent.updated_by,
        "retired_at": agent.retired_at.isoformat() if agent.retired_at else None,
    }


def _serialize_version(version) -> dict[str, Any]:
    return {
        "id": str(version.id),
        "agent_id": str(version.agent_id),
        "version_number": version.version_number,
        "change_summary": version.change_summary,
        "lifecycle_status": version.lifecycle_status,
        "configuration_snapshot": version.configuration_snapshot,
        "configuration_digest": version.configuration_digest,
        "evaluation_endpoint_url": version.evaluation_endpoint_url,
        "risk_tier": version.risk_tier,
        "material_change_status": version.material_change_status,
        "created_at": version.created_at.isoformat() if version.created_at else None,
        "created_by": version.created_by,
        "submitted_at": (
            version.submitted_at.isoformat() if version.submitted_at else None
        ),
        "approved_at": version.approved_at.isoformat() if version.approved_at else None,
        "retired_at": version.retired_at.isoformat() if version.retired_at else None,
    }


# --- AI Systems ---
@router.post("/ai-systems")
def create_ai_system(
    body: AISystemCreate,
    svc: RegistryService = Depends(_svc),
    tenant: TenantContext = Depends(require_permission("registry:write")),
):
    try:
        system = svc.create_ai_system(
            created_by=tenant.user_id,
            **body.model_dump(),
        )
    except RegistryError as exc:
        raise _handle_registry_error(exc) from exc
    trace_id = generate_trace_id()
    log_admin_audit(
        trace_id=trace_id,
        actor_user_id=tenant.user_id,
        actor_role=",".join(tenant.roles),
        action="ai_system.created",
        target={
            "system_id": str(system.id),
            "system_key": system.system_key,
        },
    )
    return _serialize_system(svc, system)


@router.get("/ai-systems")
def list_ai_systems(
    status: str | None = Query(default=None),
    search: str | None = Query(default=None),
    svc: RegistryService = Depends(_svc),
    tenant: TenantContext = Depends(require_permission("registry:read")),
):
    systems = svc.list_ai_systems(status=status, search=search)
    return [_serialize_system(svc, s) for s in systems]


@router.get("/ai-systems/{system_id}")
def get_ai_system(
    system_id: UUID,
    svc: RegistryService = Depends(_svc),
    tenant: TenantContext = Depends(require_permission("registry:read")),
):
    try:
        system = svc.get_ai_system(system_id)
    except RegistryError as exc:
        raise _handle_registry_error(exc) from exc
    return _serialize_system(svc, system)


@router.get("/ai-systems/{system_id}/hierarchy")
def get_ai_system_hierarchy(
    system_id: UUID,
    svc: RegistryService = Depends(_svc),
    tenant: TenantContext = Depends(require_permission("registry:read")),
):
    try:
        svc.get_ai_system(system_id)
        return svc.get_system_hierarchy(system_id)
    except RegistryError as exc:
        raise _handle_registry_error(exc) from exc


@router.patch("/ai-systems/{system_id}")
def update_ai_system(
    system_id: UUID,
    body: AISystemUpdate,
    svc: RegistryService = Depends(_svc),
    tenant: TenantContext = Depends(require_permission("registry:write")),
):
    try:
        svc.get_ai_system(system_id)
        system = svc.update_ai_system(
            system_id,
            updated_by=tenant.user_id,
            **body.model_dump(exclude_unset=True),
        )
    except RegistryError as exc:
        raise _handle_registry_error(exc) from exc
    return _serialize_system(svc, system)


@router.post("/ai-systems/{system_id}/lifecycle")
def transition_ai_system(
    system_id: UUID,
    body: LifecycleTransition,
    svc: RegistryService = Depends(_svc),
    tenant: TenantContext = Depends(require_permission("registry:write")),
):
    try:
        svc.get_ai_system(system_id)
        system = svc.transition_ai_system(
            system_id, body.status, updated_by=tenant.user_id
        )
    except RegistryError as exc:
        raise _handle_registry_error(exc) from exc
    trace_id = generate_trace_id()
    log_admin_audit(
        trace_id=trace_id,
        actor_user_id=tenant.user_id,
        actor_role=",".join(tenant.roles),
        action="ai_system.lifecycle_changed",
        target={
            "system_id": str(system_id),
            "status": body.status,
        },
    )
    return _serialize_system(svc, system)


# --- Agents ---
@router.post("/ai-systems/{system_id}/agents")
def create_agent(
    system_id: UUID,
    body: AgentCreate,
    svc: RegistryService = Depends(_svc),
    tenant: TenantContext = Depends(require_permission("registry:write")),
):
    try:
        agent = svc.create_agent(
            system_id,
            created_by=tenant.user_id,
            **body.model_dump(),
        )
    except RegistryError as exc:
        raise _handle_registry_error(exc) from exc
    trace_id = generate_trace_id()
    log_admin_audit(
        trace_id=trace_id,
        actor_user_id=tenant.user_id,
        actor_role=",".join(tenant.roles),
        action="agent.created",
        target={
            "agent_id": str(agent.id),
            "system_id": str(system_id),
        },
    )
    return _serialize_agent(agent)


@router.get("/ai-systems/{system_id}/agents")
def list_agents(
    system_id: UUID,
    svc: RegistryService = Depends(_svc),
    tenant: TenantContext = Depends(require_permission("registry:read")),
):
    try:
        agents = svc.list_agents(system_id)
    except RegistryError as exc:
        raise _handle_registry_error(exc) from exc
    return [_serialize_agent(a) for a in agents]


@router.get("/agents/{agent_id}")
def get_agent(
    agent_id: UUID,
    svc: RegistryService = Depends(_svc),
    tenant: TenantContext = Depends(require_permission("registry:read")),
):
    try:
        agent = svc.get_agent(agent_id)
    except RegistryError as exc:
        raise _handle_registry_error(exc) from exc
    return _serialize_agent(agent)


@router.patch("/agents/{agent_id}")
def update_agent(
    agent_id: UUID,
    body: AgentUpdate,
    svc: RegistryService = Depends(_svc),
    tenant: TenantContext = Depends(require_permission("registry:write")),
):
    try:
        agent = svc.update_agent(
            agent_id,
            updated_by=tenant.user_id,
            **body.model_dump(exclude_unset=True),
        )
    except RegistryError as exc:
        raise _handle_registry_error(exc) from exc
    return _serialize_agent(agent)


@router.post("/agents/{agent_id}/lifecycle")
def transition_agent(
    agent_id: UUID,
    body: LifecycleTransition,
    svc: RegistryService = Depends(_svc),
    tenant: TenantContext = Depends(require_permission("registry:write")),
):
    try:
        agent = svc.transition_agent(
            agent_id,
            body.status,
            updated_by=tenant.user_id,
        )
    except RegistryError as exc:
        raise _handle_registry_error(exc) from exc
    trace_id = generate_trace_id()
    log_admin_audit(
        trace_id=trace_id,
        actor_user_id=tenant.user_id,
        actor_role=",".join(tenant.roles),
        action="agent.lifecycle_changed",
        target={
            "agent_id": str(agent_id),
            "status": body.status,
        },
    )
    return _serialize_agent(agent)


# --- Agent Versions ---
@router.post("/agents/{agent_id}/versions")
def create_agent_version(
    agent_id: UUID,
    body: AgentVersionCreate,
    svc: RegistryService = Depends(_svc),
    tenant: TenantContext = Depends(require_permission("registry:write")),
):
    try:
        version = svc.create_agent_version(
            agent_id,
            created_by=tenant.user_id,
            **body.model_dump(),
        )
    except RegistryError as exc:
        raise _handle_registry_error(exc) from exc
    trace_id = generate_trace_id()
    log_admin_audit(
        trace_id=trace_id,
        actor_user_id=tenant.user_id,
        actor_role=",".join(tenant.roles),
        action="agent_version.created",
        target={
            "version_id": str(version.id),
            "agent_id": str(agent_id),
        },
    )
    return _serialize_version(version)


@router.get("/agents/{agent_id}/versions")
def list_agent_versions(
    agent_id: UUID,
    svc: RegistryService = Depends(_svc),
    tenant: TenantContext = Depends(require_permission("registry:read")),
):
    try:
        versions = svc.list_agent_versions(agent_id)
    except RegistryError as exc:
        raise _handle_registry_error(exc) from exc
    return [_serialize_version(v) for v in versions]


@router.get("/agent-versions/{version_id}")
def get_agent_version(
    version_id: UUID,
    svc: RegistryService = Depends(_svc),
    tenant: TenantContext = Depends(require_permission("registry:read")),
):
    try:
        version = svc.get_agent_version(version_id)
    except RegistryError as exc:
        raise _handle_registry_error(exc) from exc
    return _serialize_version(version)


@router.patch("/agent-versions/{version_id}")
def update_agent_version(
    version_id: UUID,
    body: AgentVersionUpdate,
    svc: RegistryService = Depends(_svc),
    tenant: TenantContext = Depends(require_permission("registry:write")),
):
    try:
        version = svc.update_draft_version(
            version_id,
            **body.model_dump(exclude_unset=True),
        )
    except RegistryError as exc:
        raise _handle_registry_error(exc) from exc
    return _serialize_version(version)


@router.post("/agent-versions/{version_id}/lifecycle")
def transition_agent_version(
    version_id: UUID,
    body: LifecycleTransition,
    svc: RegistryService = Depends(_svc),
    tenant: TenantContext = Depends(require_permission("registry:write")),
):
    try:
        version = svc.transition_agent_version(
            version_id,
            body.status,
            updated_by=tenant.user_id,
        )
    except RegistryError as exc:
        raise _handle_registry_error(exc) from exc
    trace_id = generate_trace_id()
    log_admin_audit(
        trace_id=trace_id,
        actor_user_id=tenant.user_id,
        actor_role=",".join(tenant.roles),
        action="agent_version.lifecycle_changed",
        target={
            "version_id": str(version_id),
            "status": body.status,
        },
    )
    return _serialize_version(version)


@router.get("/agent-versions/{version_id}/dependencies")
def list_version_dependencies(
    version_id: UUID,
    svc: RegistryService = Depends(_svc),
    tenant: TenantContext = Depends(require_permission("registry:read")),
):
    try:
        deps = svc.list_version_dependencies(version_id)
    except RegistryError as exc:
        raise _handle_registry_error(exc) from exc
    return [
        {
            "id": str(d.id),
            "resource_type": d.resource_type,
            "resource_id": str(d.resource_id),
            "usage_purpose": d.usage_purpose,
            "access_mode": d.access_mode,
            "capability_declaration": d.capability_declaration,
            "required": d.required,
            "metadata": d.metadata_,
        }
        for d in deps
    ]


@router.post("/agent-versions/{version_id}/dependencies")
def add_version_dependency(
    version_id: UUID,
    body: VersionDependencyCreate,
    svc: RegistryService = Depends(_svc),
    tenant: TenantContext = Depends(require_permission("registry:write")),
):
    try:
        dep = svc.add_version_dependency(
            version_id,
            **body.model_dump(),
        )
    except RegistryError as exc:
        raise _handle_registry_error(exc) from exc
    return {
        "id": str(dep.id),
        "resource_type": dep.resource_type,
        "resource_id": str(dep.resource_id),
    }


@router.delete("/agent-versions/{version_id}/dependencies/{dependency_id}")
def remove_version_dependency(
    version_id: UUID,
    dependency_id: UUID,
    svc: RegistryService = Depends(_svc),
    tenant: TenantContext = Depends(require_permission("registry:write")),
):
    try:
        svc.remove_version_dependency(
            version_id,
            dependency_id,
        )
    except RegistryError as exc:
        raise _handle_registry_error(exc) from exc
    return {"ok": True}


@router.get("/agent-versions/{version_id}/material-changes")
def get_material_changes(
    version_id: UUID,
    svc: RegistryService = Depends(_svc),
    tenant: TenantContext = Depends(require_permission("registry:read")),
):
    try:
        changes = svc.get_material_changes(version_id)
    except RegistryError as exc:
        raise _handle_registry_error(exc) from exc
    return [
        {
            "change_category": c.change_category,
            "change_description": c.change_description,
            "is_material": c.is_material,
            "reason": c.reason,
            "previous_value": c.previous_value,
            "current_value": c.current_value,
        }
        for c in changes
    ]


# --- Dependency registries (tenant-aware catalog) ---
def _serialize_model(resource) -> dict[str, Any]:
    return {
        "id": str(resource.id),
        "scope": resource.scope,
        "provider": resource.provider,
        "model_name": resource.model_name,
        "model_version": resource.model_version,
        "deployment_reference": resource.deployment_reference,
        "hosting_type": resource.hosting_type,
        "status": resource.status,
    }


@router.post("/registry/models")
def create_model(
    body: ModelResourceCreate,
    svc: RegistryService = Depends(_svc),
    tenant: TenantContext = Depends(require_permission("registry:write")),
):
    try:
        resource = svc.create_model_resource(
            **body.model_dump(),
        )
    except RegistryError as exc:
        raise _handle_registry_error(exc) from exc
    return _serialize_model(resource)


@router.get("/registry/models")
def list_models(
    svc: RegistryService = Depends(_svc),
    tenant: TenantContext = Depends(require_permission("registry:read")),
):
    return [_serialize_model(r) for r in svc.list_model_resources()]


@router.get("/registry/models/{model_id}")
def get_model(
    model_id: UUID,
    svc: RegistryService = Depends(_svc),
    tenant: TenantContext = Depends(require_permission("registry:read")),
):
    try:
        resource = svc.get_model_resource(model_id)
    except RegistryError as exc:
        raise _handle_registry_error(exc) from exc
    return _serialize_model(resource)


@router.patch("/registry/models/{model_id}")
def update_model(
    model_id: UUID,
    body: ModelResourceUpdate,
    svc: RegistryService = Depends(_svc),
    tenant: TenantContext = Depends(require_permission("registry:write")),
):
    try:
        resource = svc.update_model_resource(
            model_id,
            **body.model_dump(exclude_unset=True),
        )
    except RegistryError as exc:
        raise _handle_registry_error(exc) from exc
    return _serialize_model(resource)


@router.post("/registry/tools")
def create_tool(
    body: ToolResourceCreate,
    svc: RegistryService = Depends(_svc),
    tenant: TenantContext = Depends(require_permission("registry:write")),
):
    try:
        resource = svc.create_tool_resource(
            **body.model_dump(),
        )
    except RegistryError as exc:
        raise _handle_registry_error(exc) from exc
    return {
        "id": str(resource.id),
        "scope": resource.scope,
        "tool_key": resource.tool_key,
        "name": resource.name,
    }


@router.patch("/registry/tools/{tool_id}")
def update_tool(
    tool_id: UUID,
    body: ToolResourceUpdate,
    svc: RegistryService = Depends(_svc),
    tenant: TenantContext = Depends(require_permission("registry:write")),
):
    try:
        resource = svc.update_tool_resource(
            tool_id,
            **body.model_dump(exclude_unset=True),
        )
    except RegistryError as exc:
        raise _handle_registry_error(exc) from exc
    meta = resource.metadata_ if isinstance(resource.metadata_, dict) else {}
    return {
        "id": str(resource.id),
        "tool_key": resource.tool_key,
        "name": resource.name,
        "description": resource.description,
        "category": resource.category,
        "consequential_action": resource.consequential_action,
        "status": resource.status,
        "capability_type": meta.get("capability_type"),
        "side_effect": meta.get("side_effect"),
        "default_risk": meta.get("default_risk"),
        "default_requires_approval": meta.get("default_requires_approval"),
    }


@router.get("/registry/tools")
def list_tools(
    svc: RegistryService = Depends(_svc),
    tenant: TenantContext = Depends(require_permission("registry:read")),
):
    tools = svc.list_tool_resources()
    mcp_map = {str(m.id): m for m in svc.list_mcp_servers()}
    return [
        {
            "id": str(r.id),
            "scope": r.scope,
            "tool_key": r.tool_key,
            "name": r.name,
            "consequential_action": r.consequential_action,
            "status": r.status,
            "mcp_server_id": str(r.mcp_server_id) if r.mcp_server_id else None,
            "mcp_server_key": (
                mcp_map[str(r.mcp_server_id)].server_key
                if r.mcp_server_id and str(r.mcp_server_id) in mcp_map
                else None
            ),
        }
        for r in tools
    ]


@router.get("/registry/mcp-servers/{mcp_server_id}/tools")
def list_mcp_tools(
    mcp_server_id: UUID,
    svc: RegistryService = Depends(_svc),
    tenant: TenantContext = Depends(require_permission("registry:read")),
):
    try:
        tools = svc.list_tools_for_mcp(mcp_server_id)
    except RegistryError as exc:
        raise _handle_registry_error(exc) from exc
    return [
        {
            "id": str(t.id),
            "scope": t.scope,
            "tool_key": t.tool_key,
            "name": t.name,
        }
        for t in tools
    ]


@router.post("/registry/mcp-servers")
def create_mcp(
    body: MCPServerCreate,
    svc: RegistryService = Depends(_svc),
    tenant: TenantContext = Depends(require_permission("registry:write")),
):
    try:
        resource = svc.create_mcp_server(
            **body.model_dump(),
        )
    except RegistryError as exc:
        raise _handle_registry_error(exc) from exc
    return {
        "id": str(resource.id),
        "scope": resource.scope,
        "server_key": resource.server_key,
    }


def _serialize_mcp_server(svc: RegistryService, server) -> dict[str, Any]:
    tools = svc.list_tools_for_mcp(server.id)
    meta = server.metadata_ if isinstance(server.metadata_, dict) else {}
    serialized_tools = []
    for t in tools:
        t_meta = t.metadata_ if isinstance(t.metadata_, dict) else {}
        serialized_tools.append(
            {
                "id": str(t.id),
                "scope": t.scope,
                "tool_key": t.tool_key,
                "name": t.name,
                "description": t.description,
                "category": t.category,
                "consequential_action": t.consequential_action,
                "status": t.status,
                "native_name": t_meta.get("native_name"),
                "capability_type": t_meta.get("capability_type"),
                "side_effect": t_meta.get("side_effect"),
                "default_risk": t_meta.get("default_risk"),
                "default_requires_approval": t_meta.get("default_requires_approval"),
            }
        )
    return {
        "id": str(server.id),
        "scope": server.scope,
        "server_key": server.server_key,
        "name": server.name,
        "description": server.description,
        "provider": server.provider,
        "vendor": server.provider or meta.get("vendor"),
        "environment": server.environment,
        "endpoint_reference": server.endpoint_reference,
        "trust_classification": server.trust_classification,
        "status": server.status,
        "source_type": meta.get("source_type"),
        "native_aliases": meta.get("native_aliases") or [],
        "category": meta.get("category"),
        "tool_count": len(tools),
        "tools": serialized_tools,
    }


@router.get("/registry/mcp-servers")
def list_mcp(
    svc: RegistryService = Depends(_svc),
    tenant: TenantContext = Depends(require_permission("registry:read")),
):
    return [_serialize_mcp_server(svc, s) for s in svc.list_mcp_servers()]


@router.get("/resource-catalog")
def list_resource_catalog(
    tenant: TenantContext = Depends(require_permission("registry:read")),
    catalog: ResourceCatalogQueryService = Depends(_catalog_query),
    search: str | None = Query(default=None),
    ai_system_id: UUID | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    environment: str | None = Query(default=None),
    provider: str | None = Query(default=None),
    scope: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    sort: str | None = Query(default=None),
):
    try:
        return catalog.query(
            search=search,
            ai_system_id=ai_system_id,
            resource_type=resource_type,
            status=status,
            environment=environment,
            provider=provider,
            scope=scope,
            limit=limit,
            offset=offset,
            sort=sort,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "INVALID_FILTER", "message": str(exc)},
        ) from exc


@router.get("/registry/mcp-servers/{mcp_server_id}")
def get_mcp(
    mcp_server_id: UUID,
    svc: RegistryService = Depends(_svc),
    tenant: TenantContext = Depends(require_permission("registry:read")),
):
    try:
        server = svc.get_mcp_server(mcp_server_id)
    except RegistryError as exc:
        raise _handle_registry_error(exc) from exc
    return _serialize_mcp_server(svc, server)


@router.patch("/registry/mcp-servers/{mcp_server_id}")
def update_mcp(
    mcp_server_id: UUID,
    body: MCPServerUpdate,
    svc: RegistryService = Depends(_svc),
    tenant: TenantContext = Depends(require_permission("registry:write")),
):
    try:
        server = svc.update_mcp_server(
            mcp_server_id,
            **body.model_dump(exclude_unset=True),
        )
    except RegistryError as exc:
        raise _handle_registry_error(exc) from exc
    return _serialize_mcp_server(svc, server)


@router.post("/registry/mcp-servers/seed-catalog")
def seed_mcp_catalog(
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("registry:write")),
    scope: str | None = Query(default=None),
):
    """Upsert the built-in MCP catalog.

    Scope defaults to PLATFORM (built-in templates). Pass scope to seed
    PLATFORM or ORGANIZATION rows.
    """
    try:
        result = MCPSeedCatalogService(db).seed(scope=scope)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "INVALID_REQUEST", "message": str(exc)},
        ) from exc
    trace_id = generate_trace_id()
    log_admin_audit(
        trace_id=trace_id,
        actor_user_id=tenant.user_id,
        actor_role=",".join(tenant.roles),
        action="mcp_catalog.seeded",
        target=result.to_dict(),
    )
    return result.to_dict()


@router.post("/registry/mcp-servers/{mcp_server_id}/discover-tools")
def discover_mcp_tools(
    mcp_server_id: UUID,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("registry:read")),
):
    try:
        RegistryService(db).get_mcp_server(mcp_server_id)
        tools = MCPDiscoveryService(db).discover_tools(mcp_server_id)
    except RegistryError as exc:
        raise _handle_registry_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": "MCP_NOT_FOUND", "message": str(exc)},
        ) from exc
    return [
        {
            "native_name": t.native_name,
            "description": t.description,
            "input_schema": t.input_schema,
        }
        for t in tools
    ]


@router.post("/registry/mcp-servers/{mcp_server_id}/sync-tools")
def sync_mcp_tools(
    mcp_server_id: UUID,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("registry:write")),
):
    try:
        RegistryService(db).get_mcp_server(mcp_server_id)
        result = MCPDiscoveryService(db).sync_tools(mcp_server_id)
    except RegistryError as exc:
        raise _handle_registry_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": "MCP_NOT_FOUND", "message": str(exc)},
        ) from exc
    payload = result.to_dict()
    trace_id = generate_trace_id()
    log_admin_audit(
        trace_id=trace_id,
        actor_user_id=tenant.user_id,
        actor_role=",".join(tenant.roles),
        action="mcp_tools.synced",
        target={**payload},
    )
    return payload


@router.post("/registry/external-services")
def create_external(
    body: ExternalServiceCreate,
    svc: RegistryService = Depends(_svc),
    tenant: TenantContext = Depends(require_permission("registry:write")),
):
    try:
        resource = svc.create_external_service(
            **body.model_dump(),
        )
    except RegistryError as exc:
        raise _handle_registry_error(exc) from exc
    return {
        "id": str(resource.id),
        "scope": resource.scope,
        "service_key": resource.service_key,
    }


@router.get("/registry/external-services")
def list_external(
    svc: RegistryService = Depends(_svc),
    tenant: TenantContext = Depends(require_permission("registry:read")),
):
    return [
        {
            "id": str(r.id),
            "scope": r.scope,
            "service_key": r.service_key,
            "name": r.name,
            "provider": r.provider,
            "environment": r.environment,
            "sensitivity": r.sensitivity,
            "trust_classification": r.trust_classification,
            "status": r.status,
        }
        for r in svc.list_external_services()
    ]


@router.post("/registry/data-sources")
def create_data_source(
    body: DataSourceCreate,
    svc: RegistryService = Depends(_svc),
    tenant: TenantContext = Depends(require_permission("registry:write")),
):
    try:
        resource = svc.create_data_source(
            **body.model_dump(),
        )
    except RegistryError as exc:
        raise _handle_registry_error(exc) from exc
    return {
        "id": str(resource.id),
        "scope": resource.scope,
        "data_source_key": resource.data_source_key,
    }


@router.get("/registry/data-sources")
def list_data_sources(
    svc: RegistryService = Depends(_svc),
    tenant: TenantContext = Depends(require_permission("registry:read")),
):
    return [
        {
            "id": str(r.id),
            "scope": r.scope,
            "data_source_key": r.data_source_key,
            "name": r.name,
            "classification": r.classification,
            "contains_personal_data": r.contains_personal_data,
            "contains_sensitive_data": r.contains_sensitive_data,
        }
        for r in svc.list_data_sources()
    ]


# --- Risk ---
@router.post("/risk-assessments")
def create_assessment(
    body: RiskAssessmentCreate,
    svc: RegistryService = Depends(_svc),
    tenant: TenantContext = Depends(require_permission("registry:write")),
):
    try:
        assessment = svc.create_risk_assessment(
            assessed_by=tenant.user_id,
            **body.model_dump(),
        )
    except (RegistryError, ValueError) as exc:
        if isinstance(exc, ValueError):
            raise HTTPException(
                status_code=422, detail={"error": "INVALID_SCORE", "message": str(exc)}
            ) from exc
        raise _handle_registry_error(exc) from exc
    return {
        "id": str(assessment.id),
        "status": assessment.status,
        "risk_tier": assessment.risk_tier,
    }


@router.post("/risk-assessments/{assessment_id}/lifecycle")
def transition_assessment(
    assessment_id: UUID,
    body: LifecycleTransition,
    svc: RegistryService = Depends(_svc),
    tenant: TenantContext = Depends(require_permission("registry:write")),
):
    try:
        assessment = svc.transition_risk_assessment(
            assessment_id,
            body.status,
        )
    except RegistryError as exc:
        raise _handle_registry_error(exc) from exc
    return {
        "id": str(assessment.id),
        "status": assessment.status,
        "risk_tier": assessment.risk_tier,
        "overall_score": assessment.overall_score,
    }


@router.get("/risk-assessments/{assessment_id}")
def get_assessment(
    assessment_id: UUID,
    svc: RegistryService = Depends(_svc),
    tenant: TenantContext = Depends(require_permission("registry:read")),
):
    try:
        a = svc.get_risk_assessment(assessment_id)
    except RegistryError as exc:
        raise _handle_registry_error(exc) from exc
    return {
        "id": str(a.id),
        "ai_system_id": str(a.ai_system_id),
        "agent_version_id": str(a.agent_version_id) if a.agent_version_id else None,
        "status": a.status,
        "risk_tier": a.risk_tier,
        "overall_score": a.overall_score,
        "rationale": a.rationale,
    }


@router.post("/risk-assessments/{assessment_id}/findings")
def create_finding(
    assessment_id: UUID,
    body: RiskFindingCreate,
    svc: RegistryService = Depends(_svc),
    tenant: TenantContext = Depends(require_permission("registry:write")),
):
    try:
        finding = svc.create_risk_finding(
            assessment_id,
            **body.model_dump(),
        )
    except (RegistryError, ValueError) as exc:
        if isinstance(exc, ValueError):
            raise HTTPException(
                status_code=422, detail={"error": "INVALID_SCORE", "message": str(exc)}
            ) from exc
        raise _handle_registry_error(exc) from exc
    return {"id": str(finding.id), "title": finding.title, "severity": finding.severity}


@router.post("/registry/enterprise-risks")
def create_enterprise_risk(
    body: EnterpriseRiskCreate,
    svc: RegistryService = Depends(_svc),
    principal: Principal = Depends(require_platform_permission("platform:admin")),
):
    """Platform-global enterprise risk catalog (not organization-scoped)."""
    try:
        ref = svc.create_enterprise_risk_reference(**body.model_dump())
    except RegistryError as exc:
        raise _handle_registry_error(exc) from exc
    return {"id": str(ref.id), "external_key": ref.external_key}


@router.post("/risk-findings/{finding_id}/enterprise-risks")
def link_enterprise_risk(
    finding_id: UUID,
    body: EnterpriseRiskLinkCreate,
    svc: RegistryService = Depends(_svc),
    tenant: TenantContext = Depends(require_permission("registry:write")),
):
    try:
        link = svc.link_finding_to_enterprise_risk(
            finding_id,
            body.enterprise_risk_reference_id,
        )
    except RegistryError as exc:
        raise _handle_registry_error(exc) from exc
    return {"id": str(link.id)}


@router.get("/agent-versions/{version_id}/risk-assessments")
def list_version_assessments(
    version_id: UUID,
    svc: RegistryService = Depends(_svc),
    tenant: TenantContext = Depends(require_permission("registry:read")),
):
    try:
        assessments = svc.list_assessments_for_version(version_id)
    except RegistryError as exc:
        raise _handle_registry_error(exc) from exc
    return [
        {
            "id": str(a.id),
            "status": a.status,
            "risk_tier": a.risk_tier,
            "overall_score": a.overall_score,
        }
        for a in assessments
    ]


# --- Eligibility ---
@router.post("/registry/eligibility/check")
def check_eligibility(
    body: EligibilityCheckRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
):
    """Check eligibility. Available to all authenticated users."""
    result = EligibilityService(db).evaluate(**body.model_dump())
    return {
        "eligible": result.eligible,
        "reason": result.reason,
        "system_id": str(result.system_id) if result.system_id else None,
        "agent_id": str(result.agent_id) if result.agent_id else None,
        "version_id": str(result.version_id) if result.version_id else None,
    }


@router.get("/registry/catalog/import-template")
def download_catalog_import_template(
    tenant: TenantContext = Depends(require_permission("registry:read")),
):
    """Workbook with a blank Catalog sheet and an Example sheet of sample rows."""
    from rai_gateway.registry.catalog_import import template_workbook_bytes

    del tenant
    return Response(
        content=template_workbook_bytes(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="rai-catalog-template.xlsx"'
        },
    )


@router.post("/registry/catalog/import")
async def import_catalog_sheet(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("registry:write")),
):
    from rai_gateway.registry.catalog_import import (
        CatalogImportError,
        import_catalog_workbook,
    )

    content = await file.read()
    try:
        return import_catalog_workbook(
            db,
            content=content,
        )
    except CatalogImportError as exc:
        raise HTTPException(
            status_code=exc.http_status,
            detail={"error": "INVALID_REQUEST", "message": exc.message},
        ) from exc
