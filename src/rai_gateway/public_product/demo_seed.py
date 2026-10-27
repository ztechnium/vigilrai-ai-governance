"""Seed one developer-lab example on this instance."""

from __future__ import annotations

import hashlib
import uuid
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from rai_gateway.models.identity import AgentRuntimeIdentity
from rai_gateway.models.policy_engine import ContentRule, PolicyCollection, ToolRule
from rai_gateway.models.policy_library import PolicySource
from rai_gateway.models.productization import SdkIntegration
from rai_gateway.models.registry import (
    Agent,
    AgentVersionDependency,
    AISystem,
    MCPServer,
    ModelResource,
    ToolResource,
)
from rai_gateway.policy.errors import PolicyError
from rai_gateway.policy.service import PolicyCollectionService
from rai_gateway.public_product.demo_templates import (
    DemoTemplateError,
    default_tool_url,
    template_by_key,
)
from rai_gateway.public_product.onboarding import OnboardingService
from rai_gateway.registry.errors import RegistryError
from rai_gateway.registry.service import RegistryService


class DemoSeedError(Exception):
    def __init__(self, message: str, *, http_status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.http_status = http_status


def seed_demo_template(
    db: Session,
    *,
    template_key: str,
    actor: str,
) -> dict[str, Any]:
    try:
        spec = template_by_key(template_key)
    except DemoTemplateError as exc:
        raise DemoSeedError(exc.message, http_status=404) from exc

    registry = RegistryService(db)
    try:
        system = _ensure_system(db, spec, actor)
        system = _approve_system(registry, system, actor)
        model = _ensure_model(db, spec["model"])
        mcp = _ensure_mcp(db, spec, default_tool_url())
        tools = {
            tool["tool_key"]: _ensure_tool(db, tool, mcp.id)
            for tool in spec.get("tools") or []
        }
        agent = _ensure_agent(db, registry, system, spec, actor)
        version = _ensure_version(
            db,
            registry,
            agent,
            spec,
            actor,
            model_id=model.id,
            mcp_id=mcp.id,
            tool_ids=[row.id for row in tools.values()],
        )
        version = _approve_version(registry, version, actor)
        runtime = _ensure_runtime(db, agent, version.id, spec, actor)
        integration = _ensure_integration(
            db,
            spec,
            runtime.id,
            actor,
            tool_name=_primary_tool(spec),
        )
        _ensure_policy(
            db,
            system.id,
            spec,
            actor,
            mcp_id=mcp.id,
            tools=tools,
        )
    except (RegistryError, PolicyError, DemoTemplateError) as exc:
        message = getattr(exc, "message", None) or str(exc)
        status = getattr(exc, "status_code", None) or getattr(exc, "http_status", 400)
        raise DemoSeedError(message, http_status=int(status)) from exc

    tool_name = _primary_tool(spec)
    _record_onboarding(
        db,
        system_id=system.id,
        integration_id=integration.id,
    )
    return {
        "template_key": spec["system_key"],
        "system_name": spec["name"],
        "ai_system_id": str(system.id),
        "agent_id": str(agent.id),
        "agent_version_id": str(version.id),
        "integration_id": str(integration.id),
        "runtime_identity_id": str(runtime.id),
        "tool_name": tool_name,
    }


def _primary_tool(spec: dict[str, Any]) -> str:
    tools = spec.get("tools") or []
    if not tools:
        return "tool"
    return str(tools[0].get("tool_key") or "tool")


def _approve_system(
    registry: RegistryService, system: AISystem, actor: str
) -> AISystem:
    if system.status == "DRAFT":
        system = registry.transition_ai_system(
            system.id, "UNDER_REVIEW", updated_by=actor
        )
    if system.status == "UNDER_REVIEW":
        system = registry.transition_ai_system(system.id, "APPROVED", updated_by=actor)
    return system


def _approve_version(registry: RegistryService, version: Any, actor: str) -> Any:
    if version.lifecycle_status == "DRAFT":
        version = registry.transition_agent_version(
            version.id,
            "UNDER_REVIEW",
            updated_by=actor,
        )
    if version.lifecycle_status == "UNDER_REVIEW":
        version = registry.transition_agent_version(
            version.id,
            "APPROVED",
            updated_by=actor,
        )
    return version


def _ensure_system(db: Session, spec: dict[str, Any], actor: str) -> AISystem:
    existing = (
        db.query(AISystem).filter(AISystem.system_key == spec["system_key"]).first()
    )
    if existing:
        return existing
    system = AISystem(
        system_key=spec["system_key"],
        name=spec["name"],
        description=spec.get("description"),
        business_purpose=spec.get("business_purpose"),
        risk_tier=spec.get("risk_tier"),
        data_classification=spec.get("data_classification"),
        status="DRAFT",
        created_by=actor,
        updated_by=actor,
    )
    db.add(system)
    db.commit()
    db.refresh(system)
    return system


def _ensure_model(db: Session, model: dict[str, Any]) -> ModelResource:
    version = model.get("model_version") or ""
    rows = (
        db.query(ModelResource)
        .filter(
            ModelResource.provider == model["provider"],
            ModelResource.model_name == model["model_name"],
        )
        .all()
    )
    for row in rows:
        if (row.model_version or "") == version:
            return row
    row = ModelResource(
        scope="ORGANIZATION",
        provider=model["provider"],
        model_name=model["model_name"],
        model_version=model.get("model_version"),
        hosting_type=model.get("hosting_type") or "EXTERNAL_API",
        deployment_reference=model.get("deployment_reference"),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _ensure_mcp(db: Session, spec: dict[str, Any], tool_url: str) -> MCPServer:
    server_key = f"{spec['system_key']}-mcp"
    existing = db.query(MCPServer).filter(MCPServer.server_key == server_key).first()
    if existing:
        return existing
    row = MCPServer(
        scope="ORGANIZATION",
        server_key=server_key,
        name=f"{spec['name']} MCP",
        description=f"Example MCP server for {spec['name']}.",
        provider="developer-lab",
        environment="development",
        endpoint_reference=tool_url,
        trust_classification="INTERNAL",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _ensure_tool(db: Session, tool: dict[str, Any], mcp_id: UUID) -> ToolResource:
    existing = (
        db.query(ToolResource).filter(ToolResource.tool_key == tool["tool_key"]).first()
    )
    if existing:
        return existing
    row = ToolResource(
        scope="ORGANIZATION",
        tool_key=tool["tool_key"],
        name=tool["name"],
        description=tool.get("description"),
        category=tool.get("category"),
        provider="developer-lab",
        mcp_server_id=mcp_id,
        consequential_action=bool(tool.get("consequential_action")),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _ensure_agent(
    db: Session,
    registry: RegistryService,
    system: AISystem,
    spec: dict[str, Any],
    actor: str,
) -> Agent:
    agent_key = str(spec["agent_key"])[:64]
    existing = db.query(Agent).filter(Agent.agent_key == agent_key).first()
    if existing:
        return existing
    return registry.create_agent(
        system.id,
        agent_key=agent_key,
        name=spec["agent_name"],
        created_by=actor,
        description=spec.get("description"),
        business_purpose=spec.get("business_purpose"),
    )


def _ensure_version(
    db: Session,
    registry: RegistryService,
    agent: Agent,
    spec: dict[str, Any],
    actor: str,
    *,
    model_id: UUID,
    mcp_id: UUID,
    tool_ids: list[UUID],
) -> Any:
    versions = registry.list_agent_versions(agent.id)
    if versions:
        version = versions[0]
    else:
        model = spec.get("model") or {}
        version = registry.create_agent_version(
            agent.id,
            created_by=actor,
            change_summary=f"Seeded from the {spec['name']} example",
            risk_tier=spec.get("risk_tier"),
            configuration_snapshot={
                "template": spec["system_key"],
                "model": model.get("model_name"),
                "tools": [tool["tool_key"] for tool in spec.get("tools") or []],
            },
        )
    if version.lifecycle_status != "DRAFT":
        return version
    _add_dependency(
        db,
        version.id,
        resource_type="model",
        resource_id=model_id,
        usage_purpose="inference",
    )
    _add_dependency(
        db,
        version.id,
        resource_type="mcp_server",
        resource_id=mcp_id,
        usage_purpose="tools",
    )
    for tool_id in tool_ids:
        _add_dependency(
            db,
            version.id,
            resource_type="tool",
            resource_id=tool_id,
            usage_purpose="action",
        )
    return registry.get_agent_version(version.id)


def _add_dependency(
    db: Session,
    version_id: UUID,
    *,
    resource_type: str,
    resource_id: UUID,
    usage_purpose: str,
) -> None:
    existing = (
        db.query(AgentVersionDependency)
        .filter(
            AgentVersionDependency.agent_version_id == version_id,
            AgentVersionDependency.resource_type == resource_type,
            AgentVersionDependency.resource_id == resource_id,
        )
        .first()
    )
    if existing:
        return
    db.add(
        AgentVersionDependency(
            agent_version_id=version_id,
            resource_type=resource_type,
            resource_id=resource_id,
            usage_purpose=usage_purpose,
        )
    )
    db.commit()


def _ensure_runtime(
    db: Session,
    agent: Agent,
    version_id: UUID,
    spec: dict[str, Any],
    actor: str,
) -> AgentRuntimeIdentity:
    name = f"{spec['agent_name']} runtime"
    existing = (
        db.query(AgentRuntimeIdentity)
        .filter(
            AgentRuntimeIdentity.agent_id == agent.id,
            AgentRuntimeIdentity.name == name,
        )
        .first()
    )
    if existing:
        return existing
    row = AgentRuntimeIdentity(
        identity_key=f"rti_{uuid.uuid4().hex[:16]}",
        agent_id=agent.id,
        agent_version_id=version_id,
        name=name,
        environment="development",
        status="ACTIVE",
        created_by=actor,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _ensure_integration(
    db: Session,
    spec: dict[str, Any],
    runtime_id: UUID,
    actor: str,
    *,
    tool_name: str,
) -> SdkIntegration:
    integration_key = f"{spec['system_key']}-sdk"
    existing = (
        db.query(SdkIntegration)
        .filter(SdkIntegration.integration_key == integration_key)
        .first()
    )
    if existing:
        return existing
    row = SdkIntegration(
        integration_key=integration_key,
        name=f"{spec['name']} SDK",
        runtime_identity_id=runtime_id,
        created_by=actor,
        environment="development",
        metadata_json={
            "template_key": spec["system_key"],
            "tool_name": tool_name,
        },
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _ensure_policy(
    db: Session,
    system_id: UUID,
    spec: dict[str, Any],
    actor: str,
    *,
    mcp_id: UUID,
    tools: dict[str, ToolResource],
) -> None:
    policy = spec.get("policy") or {}
    title = (policy.get("title") or "").strip()
    content = (policy.get("content_text") or "").strip()
    if title and content:
        existing = db.query(PolicySource).filter(PolicySource.title == title).first()
        if existing is None:
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
            db.add(
                PolicySource(
                    scope="ORGANIZATION",
                    title=title,
                    source_type="MANUAL_TEXT",
                    authority=policy.get("authority"),
                    jurisdiction=policy.get("jurisdiction"),
                    policy_type=policy.get("policy_type"),
                    version=policy.get("version"),
                    content_text=content,
                    content_digest=digest,
                    status="ACTIVE",
                )
            )
            db.commit()

    policies = PolicyCollectionService(db)
    for rule in spec.get("content_rules") or []:
        if _content_rule_exists(db, system_id, rule["title"]):
            continue
        policies.create_content_rule(
            system_id,
            title=rule["title"],
            content=rule["content"],
            effect=rule["effect"],
            applies_to=rule.get("applies_to") or "BOTH",
            category=rule.get("category"),
            severity=rule.get("severity"),
            evaluation_type=rule.get("evaluation_type") or "KEYWORD",
            actor=actor,
        )

    for rule in spec.get("tool_rules") or []:
        tool = tools.get(rule["tool_key"])
        if tool is None or _tool_rule_exists(db, system_id, rule["title"]):
            continue
        policies.create_tool_rule(
            system_id,
            title=rule["title"],
            description=rule.get("description"),
            tool_id=tool.id,
            mcp_server_id=mcp_id,
            effect=rule["effect"],
            required_approver_role=rule.get("required_approver_role"),
            severity=rule.get("severity"),
            category=rule.get("category"),
            conditions=rule.get("conditions") or [],
            actor=actor,
        )


def _content_rule_exists(db: Session, system_id: UUID, title: str) -> bool:
    return (
        db.query(ContentRule)
        .join(PolicyCollection, ContentRule.policy_collection_id == PolicyCollection.id)
        .filter(
            PolicyCollection.ai_system_id == system_id,
            ContentRule.title == title,
            ContentRule.archived_at.is_(None),
        )
        .first()
        is not None
    )


def _tool_rule_exists(db: Session, system_id: UUID, title: str) -> bool:
    return (
        db.query(ToolRule)
        .join(PolicyCollection, ToolRule.policy_collection_id == PolicyCollection.id)
        .filter(
            PolicyCollection.ai_system_id == system_id,
            ToolRule.title == title,
            ToolRule.archived_at.is_(None),
        )
        .first()
        is not None
    )


def _record_onboarding(
    db: Session,
    *,
    system_id: UUID,
    integration_id: UUID,
) -> None:
    service = OnboardingService(db)
    record = service.get_or_create()
    steps = set(record.completed_steps or [])
    steps.update(
        {
            "first_ai_system",
            "agent_version",
            "resources",
            "first_policies",
            "choose_integration",
            "runtime_identity",
        }
    )
    service.update(
        current_step="connect_application",
        completed_steps=sorted(steps),
        first_ai_system_id=system_id,
        first_integration_id=integration_id,
    )
