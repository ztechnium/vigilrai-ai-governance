"""Policy collection REST API."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import rai_gateway.models.policy_engine  # noqa: F401
import rai_gateway.models.policy_library  # noqa: F401
from rai_gateway.core.authorization import require_permission
from rai_gateway.core.database import get_db
from rai_gateway.core.tenant_context import TenantContext
from rai_gateway.policy.errors import PolicyError
from rai_gateway.policy.library import PolicyLibraryError, PolicyLibraryService
from rai_gateway.policy.rule_query import RaiRulesQueryService
from rai_gateway.policy.service import PolicyCollectionService

router = APIRouter(prefix="/v1", tags=["policies"])


def _handle_error(exc: PolicyError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={"error": exc.error_code, "message": exc.message},
    )


def _handle_library_error(exc: PolicyLibraryError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={"error": exc.error_code, "message": exc.message},
    )


def _svc(db: Session = Depends(get_db)) -> PolicyCollectionService:
    return PolicyCollectionService(db)


def _rules_query(db: Session = Depends(get_db)) -> RaiRulesQueryService:
    return RaiRulesQueryService(db)


def _library(db: Session = Depends(get_db)) -> PolicyLibraryService:
    return PolicyLibraryService(db)


def _maybe_link_rule(
    library: PolicyLibraryService,
    *,
    source_policy_id: UUID | None,
    source_obligation_id: UUID | None,
    rule_type: str,
    rule_id: UUID,
) -> None:
    if source_policy_id is None:
        return
    library.link_rule(
        policy_source_id=source_policy_id,
        rule_type=rule_type,
        rule_id=rule_id,
        obligation_id=source_obligation_id,
    )


class ContentRuleCreate(BaseModel):
    title: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    effect: str
    enabled: bool = True
    required_approver_role: str | None = None
    applies_to: str = "BOTH"
    category: str | None = None
    severity: str | None = None
    source_policy_id: UUID | None = None
    source_obligation_id: UUID | None = None
    evaluation_type: str | None = None
    evaluator_profile_id: UUID | None = None
    intervention_points: list[str] | None = None
    content_targets: dict[str, Any] | None = None
    minimum_confidence: float | None = None
    failure_mode: str | None = None
    remediation_type: str | None = None
    remediation_config: dict[str, Any] | None = None
    inline_enforcement_required: bool = False
    evaluation_timeout_ms: int | None = None


class ContentRuleUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    effect: str | None = None
    enabled: bool | None = None
    required_approver_role: str | None = None
    applies_to: str | None = None
    category: str | None = None
    severity: str | None = None
    ai_system_id: UUID | None = None
    evaluation_type: str | None = None
    evaluator_profile_id: UUID | None = None
    clear_evaluator_profile_id: bool = False
    intervention_points: list[str] | None = None
    content_targets: dict[str, Any] | None = None
    minimum_confidence: float | None = None
    failure_mode: str | None = None
    remediation_type: str | None = None
    remediation_config: dict[str, Any] | None = None
    inline_enforcement_required: bool | None = None
    evaluation_timeout_ms: int | None = None


class ToolRuleConditionCreate(BaseModel):
    parameter_path: str = Field(..., min_length=1)
    operator: str
    value_type: str = "string"
    value: Any = None


class ToolRuleCreate(BaseModel):
    title: str = Field(..., min_length=1)
    description: str | None = None
    mcp_server_id: UUID | None = None
    tool_id: UUID
    match_mode: str = "ALL"
    effect: str
    enabled: bool = True
    required_approver_role: str | None = None
    severity: str | None = None
    category: str | None = None
    source_policy_id: UUID | None = None
    source_obligation_id: UUID | None = None
    conditions: list[ToolRuleConditionCreate] = Field(default_factory=list)


class ToolRuleUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    mcp_server_id: UUID | None = None
    clear_mcp_server_id: bool = False
    tool_id: UUID | None = None
    match_mode: str | None = None
    effect: str | None = None
    enabled: bool | None = None
    required_approver_role: str | None = None
    severity: str | None = None
    category: str | None = None
    conditions: list[ToolRuleConditionCreate] | None = None
    ai_system_id: UUID | None = None


@router.get("/ai-systems/{system_id}/policies")
def get_policies(
    system_id: UUID,
    tenant: TenantContext = Depends(require_permission("policies:read")),
    svc: PolicyCollectionService = Depends(_svc),
) -> dict[str, Any]:
    try:
        return svc.get_collection_detail(system_id)
    except PolicyError as exc:
        raise _handle_error(exc) from exc


@router.get("/rai-rules")
def list_rai_rules(
    tenant: TenantContext = Depends(require_permission("policies:read")),
    query: RaiRulesQueryService = Depends(_rules_query),
    search: str | None = Query(default=None),
    ai_system_id: UUID | None = Query(default=None),
    rule_type: str | None = Query(default=None),
    tool_id: UUID | None = Query(default=None),
    mcp_server_id: UUID | None = Query(default=None),
    effect: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    status: str | None = Query(default=None),
    category: str | None = Query(default=None),
    source_policy_id: str | None = Query(default=None),
    intervention_point: str | None = Query(default=None),
    evaluation_type: str | None = Query(default=None),
    coverage_status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    sort: str | None = Query(default=None),
) -> dict[str, Any]:
    try:
        return query.query(
            search=search,
            ai_system_id=ai_system_id,
            rule_type=rule_type,
            tool_id=tool_id,
            mcp_server_id=mcp_server_id,
            effect=effect,
            severity=severity,
            status=status,
            category=category,
            source_policy_id=source_policy_id,
            intervention_point=intervention_point,
            evaluation_type=evaluation_type,
            coverage_status=coverage_status,
            limit=limit,
            offset=offset,
            sort=sort,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "INVALID_FILTER", "message": str(exc)},
        ) from exc


@router.get("/policy-library")
def list_policy_library(
    tenant: TenantContext = Depends(require_permission("policies:read")),
    library: PolicyLibraryService = Depends(_library),
    search: str | None = Query(default=None),
    source_type: str | None = Query(default=None),
    authority: str | None = Query(default=None),
    jurisdiction: str | None = Query(default=None),
    policy_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    return library.list_sources(
        search=search,
        source_type=source_type,
        authority=authority,
        jurisdiction=jurisdiction,
        policy_type=policy_type,
        status=status,
        limit=limit,
        offset=offset,
    )


class PolicySourceCreate(BaseModel):
    title: str = Field(..., min_length=1)
    source_type: str
    authority: str | None = None
    owner: str | None = None
    jurisdiction: str | None = None
    policy_type: str | None = None
    version: str | None = None
    effective_date: datetime | str | None = None
    source_uri: str | None = None
    content_text: str | None = None
    content_ref: str | None = None
    crawl_metadata: dict[str, Any] | None = None


@router.post("/policy-library")
def create_policy_source(
    payload: PolicySourceCreate,
    tenant: TenantContext = Depends(require_permission("policies:write")),
    library: PolicyLibraryService = Depends(_library),
) -> dict[str, Any]:
    try:
        return library.create_source(
            title=payload.title,
            source_type=payload.source_type,
            authority=payload.authority,
            owner=payload.owner,
            jurisdiction=payload.jurisdiction,
            policy_type=payload.policy_type,
            version=payload.version,
            effective_date=payload.effective_date,
            source_uri=payload.source_uri,
            content_text=payload.content_text,
            content_ref=payload.content_ref,
            crawl_metadata=payload.crawl_metadata,
            actor=tenant.user_id,
        )
    except PolicyLibraryError as exc:
        raise _handle_library_error(exc) from exc


@router.get("/policy-library/{source_id}")
def get_policy_source(
    source_id: UUID,
    tenant: TenantContext = Depends(require_permission("policies:read")),
    library: PolicyLibraryService = Depends(_library),
) -> dict[str, Any]:
    try:
        return library.get_source(source_id)
    except PolicyLibraryError as exc:
        raise _handle_library_error(exc) from exc


class PolicyRuleLinkCreate(BaseModel):
    rule_type: str
    rule_id: UUID
    obligation_id: UUID | None = None
    relationship_type: str = "DERIVED_FROM"


@router.post("/policy-library/{source_id}/rule-links")
def create_policy_rule_link(
    source_id: UUID,
    payload: PolicyRuleLinkCreate,
    tenant: TenantContext = Depends(require_permission("policies:write")),
    library: PolicyLibraryService = Depends(_library),
) -> dict[str, Any]:
    try:
        return library.link_rule(
            policy_source_id=source_id,
            rule_type=payload.rule_type,
            rule_id=payload.rule_id,
            obligation_id=payload.obligation_id,
            relationship_type=payload.relationship_type,
        )
    except PolicyLibraryError as exc:
        raise _handle_library_error(exc) from exc


@router.get("/policies/rules")
def list_all_rules(
    tenant: TenantContext = Depends(require_permission("policies:read")),
    svc: PolicyCollectionService = Depends(_svc),
) -> dict[str, Any]:
    return svc.list_all_rules()


@router.post("/ai-systems/{system_id}/policies/content-rules")
def create_content_rule(
    system_id: UUID,
    payload: ContentRuleCreate,
    tenant: TenantContext = Depends(require_permission("policies:write")),
    svc: PolicyCollectionService = Depends(_svc),
    library: PolicyLibraryService = Depends(_library),
) -> dict[str, Any]:
    try:
        rule = svc.create_content_rule(
            system_id,
            title=payload.title,
            content=payload.content,
            effect=payload.effect,
            enabled=payload.enabled,
            required_approver_role=payload.required_approver_role,
            applies_to=payload.applies_to,
            category=payload.category,
            severity=payload.severity,
            evaluation_type=payload.evaluation_type,
            evaluator_profile_id=payload.evaluator_profile_id,
            intervention_points=payload.intervention_points,
            content_targets=payload.content_targets,
            minimum_confidence=payload.minimum_confidence,
            failure_mode=payload.failure_mode,
            remediation_type=payload.remediation_type,
            remediation_config=payload.remediation_config,
            inline_enforcement_required=payload.inline_enforcement_required,
            evaluation_timeout_ms=payload.evaluation_timeout_ms,
            actor=tenant.user_id,
        )
        try:
            _maybe_link_rule(
                library,
                source_policy_id=payload.source_policy_id,
                source_obligation_id=payload.source_obligation_id,
                rule_type="CONTENT",
                rule_id=rule.id,
            )
        except PolicyLibraryError as exc:
            raise _handle_library_error(exc) from exc
        return svc._serialize_content_rule(rule)
    except PolicyError as exc:
        raise _handle_error(exc) from exc


@router.get("/policies/content-rules/{rule_id}")
def get_content_rule(
    rule_id: UUID,
    tenant: TenantContext = Depends(require_permission("policies:read")),
    svc: PolicyCollectionService = Depends(_svc),
) -> dict[str, Any]:
    try:
        return svc._serialize_content_rule(svc.get_content_rule(rule_id))
    except PolicyError as exc:
        raise _handle_error(exc) from exc


@router.patch("/policies/content-rules/{rule_id}")
def update_content_rule(
    rule_id: UUID,
    payload: ContentRuleUpdate,
    tenant: TenantContext = Depends(require_permission("policies:write")),
    svc: PolicyCollectionService = Depends(_svc),
) -> dict[str, Any]:
    try:
        rule = svc.update_content_rule(
            rule_id,
            actor=tenant.user_id,
            title=payload.title,
            content=payload.content,
            effect=payload.effect,
            enabled=payload.enabled,
            required_approver_role=payload.required_approver_role,
            applies_to=payload.applies_to,
            category=payload.category,
            severity=payload.severity,
            evaluation_type=payload.evaluation_type,
            evaluator_profile_id=payload.evaluator_profile_id,
            clear_evaluator_profile_id=payload.clear_evaluator_profile_id,
            intervention_points=payload.intervention_points,
            content_targets=payload.content_targets,
            minimum_confidence=payload.minimum_confidence,
            failure_mode=payload.failure_mode,
            remediation_type=payload.remediation_type,
            remediation_config=payload.remediation_config,
            inline_enforcement_required=payload.inline_enforcement_required,
            evaluation_timeout_ms=payload.evaluation_timeout_ms,
            ai_system_id=payload.ai_system_id,
        )
        return svc._serialize_content_rule(rule)
    except PolicyError as exc:
        raise _handle_error(exc) from exc


@router.delete("/policies/content-rules/{rule_id}", status_code=204)
def delete_content_rule(
    rule_id: UUID,
    tenant: TenantContext = Depends(require_permission("policies:write")),
    svc: PolicyCollectionService = Depends(_svc),
) -> None:
    try:
        svc.delete_content_rule(rule_id, actor=tenant.user_id)
    except PolicyError as exc:
        raise _handle_error(exc) from exc


@router.post("/ai-systems/{system_id}/policies/tool-rules")
def create_tool_rule(
    system_id: UUID,
    payload: ToolRuleCreate,
    tenant: TenantContext = Depends(require_permission("policies:write")),
    svc: PolicyCollectionService = Depends(_svc),
    library: PolicyLibraryService = Depends(_library),
) -> dict[str, Any]:
    try:
        rule = svc.create_tool_rule(
            system_id,
            title=payload.title,
            description=payload.description,
            mcp_server_id=payload.mcp_server_id,
            tool_id=payload.tool_id,
            match_mode=payload.match_mode,
            effect=payload.effect,
            enabled=payload.enabled,
            required_approver_role=payload.required_approver_role,
            severity=payload.severity,
            category=payload.category,
            conditions=[c.model_dump() for c in payload.conditions],
            actor=tenant.user_id,
        )
        try:
            _maybe_link_rule(
                library,
                source_policy_id=payload.source_policy_id,
                source_obligation_id=payload.source_obligation_id,
                rule_type="TOOL",
                rule_id=rule.id,
            )
        except PolicyLibraryError as exc:
            raise _handle_library_error(exc) from exc
        return svc._serialize_tool_rule(rule)
    except PolicyError as exc:
        raise _handle_error(exc) from exc


@router.get("/policies/tool-rules/{rule_id}")
def get_tool_rule(
    rule_id: UUID,
    tenant: TenantContext = Depends(require_permission("policies:read")),
    svc: PolicyCollectionService = Depends(_svc),
) -> dict[str, Any]:
    try:
        return svc._serialize_tool_rule(svc.get_tool_rule(rule_id))
    except PolicyError as exc:
        raise _handle_error(exc) from exc


@router.patch("/policies/tool-rules/{rule_id}")
def update_tool_rule(
    rule_id: UUID,
    payload: ToolRuleUpdate,
    tenant: TenantContext = Depends(require_permission("policies:write")),
    svc: PolicyCollectionService = Depends(_svc),
) -> dict[str, Any]:
    try:
        rule = svc.update_tool_rule(
            rule_id,
            actor=tenant.user_id,
            title=payload.title,
            description=payload.description,
            mcp_server_id=payload.mcp_server_id,
            clear_mcp_server_id=payload.clear_mcp_server_id,
            tool_id=payload.tool_id,
            match_mode=payload.match_mode,
            effect=payload.effect,
            enabled=payload.enabled,
            required_approver_role=payload.required_approver_role,
            conditions=[c.model_dump() for c in payload.conditions]
            if payload.conditions is not None
            else None,
            severity=payload.severity,
            category=payload.category,
            ai_system_id=payload.ai_system_id,
        )
        return svc._serialize_tool_rule(rule)
    except PolicyError as exc:
        raise _handle_error(exc) from exc


@router.delete("/policies/tool-rules/{rule_id}", status_code=204)
def delete_tool_rule(
    rule_id: UUID,
    tenant: TenantContext = Depends(require_permission("policies:write")),
    svc: PolicyCollectionService = Depends(_svc),
) -> None:
    try:
        svc.delete_tool_rule(rule_id, actor=tenant.user_id)
    except PolicyError as exc:
        raise _handle_error(exc) from exc
