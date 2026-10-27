"""WP6 Continuous Risk Intelligence REST API."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import rai_gateway.models.risk_intelligence  # noqa: F401
from rai_gateway.core.authorization import require_permission
from rai_gateway.core.database import get_db
from rai_gateway.core.tenant_context import TenantContext
from rai_gateway.risk_intelligence.service import RiskIntelligenceService

router = APIRouter(
    prefix="/v1",
    tags=["risk"],
)


def _svc(db: Session = Depends(get_db)) -> RiskIntelligenceService:
    return RiskIntelligenceService(db)


# --- Request models -------------------------------------------------------


class EvaluatorConfigUpsert(BaseModel):
    ai_system_id: UUID | None = None
    provider: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    enabled: bool = True
    api_key: str | None = None
    temperature: float = 0.0
    timeout_seconds: int = 30
    max_rules_per_call: int = 20
    confidence_threshold: float = 0.5
    minimum_confidence_to_mark: float = 0.5
    minimum_confidence_to_monitor: float = 0.7
    minimum_confidence_to_intervene: float = 0.9
    fail_closed: bool = False
    fallback_provider: str | None = None


class ContentEvaluateRequest(BaseModel):
    ai_system_id: UUID
    content: str = Field(..., min_length=1)
    content_type: str = "OUTPUT"
    evaluation_mode: str = "OFFLINE_EVALUATED"
    trajectory_id: UUID | None = None
    runtime_identity_id: UUID | None = None
    agent_id: UUID | None = None
    agent_version_id: UUID | None = None
    apply_risk: bool = True


class ContentTestRequest(BaseModel):
    ai_system_id: UUID
    content: str = Field(..., min_length=1)
    content_type: str = "OUTPUT"


class MonitorRuleCreate(BaseModel):
    ai_system_id: UUID
    name: str = Field(..., min_length=1)
    scope: str = "RUNTIME_IDENTITY"
    signal_type: str | None = None
    tool_id: UUID | None = None
    tool_name: str | None = None
    window_seconds: int | None = 600
    window: str | None = None  # preset: 5m, 15m, 1h, 24h
    aggregation: str = "COUNT"
    threshold: float
    amount_parameter_path: str | None = None
    effect: str = "MARK_AND_MONITOR"
    monitor_duration_seconds: int | None = 1800
    enabled: bool = True


class BudgetCreate(BaseModel):
    ai_system_id: UUID | None = None
    name: str = Field(..., min_length=1)
    scope_type: str = "RUNTIME_IDENTITY"
    scope_id: str | None = None
    metric: str = Field(..., min_length=1)
    tool_name: str | None = None
    tool_id: UUID | None = None
    resource_filter: dict[str, Any] | None = None
    limit_value: float
    window_seconds: int | None = 3600
    window: str | None = None
    warning_threshold: float = 0.8
    effect_on_exceed: str = "DENY"
    amount_parameter_path: str | None = None
    enforcement_mode: str = "BEST_EFFORT"
    enabled: bool = True


class BudgetPatch(BaseModel):
    name: str | None = None
    scope_id: str | None = None
    tool_name: str | None = None
    tool_id: UUID | None = None
    limit_value: float | None = None
    window_seconds: int | None = None
    window: str | None = None
    warning_threshold: float | None = None
    effect_on_exceed: str | None = None
    amount_parameter_path: str | None = None
    enforcement_mode: str | None = None
    enabled: bool | None = None


class EmergencySuspendRequest(BaseModel):
    reason: str = Field(..., min_length=1)
    confirm: bool = False


class EmergencyReactivateRequest(BaseModel):
    reason: str = Field(..., min_length=1)
    confirm: bool = False


# --- Endpoints ------------------------------------------------------------


@router.get("/risk/overview")
def risk_overview(
    ai_system_id: UUID | None = None,
    tenant: TenantContext = Depends(require_permission("risk:read")),
    svc: RiskIntelligenceService = Depends(_svc),
):
    try:
        return svc.overview(ai_system_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/risk/findings")
def list_findings(
    ai_system_id: UUID | None = None,
    trajectory_id: UUID | None = None,
    severity: str | None = None,
    status: str | None = None,
    finding_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
    tenant: TenantContext = Depends(require_permission("risk:read")),
    svc: RiskIntelligenceService = Depends(_svc),
):
    items = svc.list_findings(
        ai_system_id=ai_system_id,
        trajectory_id=trajectory_id,
        severity=severity,
        status=status,
        finding_type=finding_type,
        limit=limit,
        offset=offset,
        include_evidence=True,
    )
    total = svc.count_findings(
        ai_system_id=ai_system_id,
        trajectory_id=trajectory_id,
        severity=severity,
        status=status,
        finding_type=finding_type,
        include_evidence=True,
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/risk/findings/{finding_id}")
def get_finding(
    finding_id: UUID,
    tenant: TenantContext = Depends(require_permission("risk:read")),
    svc: RiskIntelligenceService = Depends(_svc),
):
    row = svc.get_finding(finding_id)
    if not row:
        raise HTTPException(status_code=404, detail="Finding not found")
    return row


@router.get("/risk/signals")
def list_signals(
    ai_system_id: UUID | None = None,
    trajectory_id: UUID | None = None,
    runtime_identity_id: UUID | None = None,
    signal_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
    tenant: TenantContext = Depends(require_permission("risk:read")),
    svc: RiskIntelligenceService = Depends(_svc),
):
    items = svc.list_signals(
        ai_system_id=ai_system_id,
        trajectory_id=trajectory_id,
        runtime_identity_id=runtime_identity_id,
        signal_type=signal_type,
        limit=limit,
        offset=offset,
    )
    return {"items": items, "limit": limit, "offset": offset}


@router.get("/risk/states")
def list_risk_states(
    ai_system_id: UUID | None = None,
    monitoring_only: bool = False,
    limit: int = 50,
    offset: int = 0,
    tenant: TenantContext = Depends(require_permission("risk:read")),
    svc: RiskIntelligenceService = Depends(_svc),
):
    items = svc.list_risk_states(
        ai_system_id=ai_system_id,
        monitoring_only=monitoring_only,
        limit=limit,
        offset=offset,
    )
    return {"items": items, "limit": limit, "offset": offset}


@router.get("/risk/monitors")
def list_monitors(
    ai_system_id: UUID | None = None,
    status: str | None = "ACTIVE",
    limit: int = 50,
    offset: int = 0,
    tenant: TenantContext = Depends(require_permission("risk:read")),
    svc: RiskIntelligenceService = Depends(_svc),
):
    items = svc.list_monitors(
        ai_system_id=ai_system_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    return {"items": items, "limit": limit, "offset": offset}


@router.get("/risk/monitor-rules")
def list_monitor_rules(
    ai_system_id: UUID,
    tenant: TenantContext = Depends(require_permission("risk:read")),
    svc: RiskIntelligenceService = Depends(_svc),
):
    try:
        return {"items": svc.list_monitor_rules(ai_system_id)}
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/risk/monitor-rules")
def create_monitor_rule(
    payload: MonitorRuleCreate,
    tenant: TenantContext = Depends(require_permission("risk:manage")),
    svc: RiskIntelligenceService = Depends(_svc),
):
    try:
        return svc.create_monitor_rule(
            **payload.model_dump(exclude_none=True),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/risk/budgets")
def list_budgets(
    ai_system_id: UUID | None = None,
    limit: int = 50,
    offset: int = 0,
    tenant: TenantContext = Depends(require_permission("risk:read")),
    svc: RiskIntelligenceService = Depends(_svc),
):
    items = svc.list_budgets(
        ai_system_id=ai_system_id,
        limit=limit,
        offset=offset,
    )
    return {"items": items, "limit": limit, "offset": offset}


@router.get("/risk/budgets/effective")
def list_effective_budgets(
    ai_system_id: UUID | None = None,
    agent_id: UUID | None = None,
    agent_version_id: UUID | None = None,
    runtime_identity_id: UUID | None = None,
    delegation_id: UUID | None = None,
    model: str | None = None,
    tool_id: UUID | None = None,
    tool_name: str | None = None,
    provider: str | None = None,
    tenant: TenantContext = Depends(require_permission("risk:read")),
    svc: RiskIntelligenceService = Depends(_svc),
):
    """Return all budgets that would apply to the given governance context."""
    from rai_gateway.risk_intelligence.budget_scope import BudgetEvaluationContext

    ctx = BudgetEvaluationContext(
        ai_system_id=ai_system_id,
        agent_id=agent_id,
        agent_version_id=agent_version_id,
        runtime_identity_id=runtime_identity_id,
        delegation_id=delegation_id,
        model=model,
        tool_id=tool_id,
        tool_name=tool_name,
        provider=provider,
    )
    return {"items": svc._budgets.effective_budgets(ctx)}


@router.post("/risk/budgets")
def create_budget(
    payload: BudgetCreate,
    tenant: TenantContext = Depends(require_permission("risk:manage")),
    svc: RiskIntelligenceService = Depends(_svc),
):
    try:
        return svc.create_budget(
            **payload.model_dump(exclude_none=True),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/risk/budgets/{budget_id}")
def get_budget(
    budget_id: UUID,
    tenant: TenantContext = Depends(require_permission("risk:read")),
    svc: RiskIntelligenceService = Depends(_svc),
):
    row = svc.get_budget(budget_id)
    if not row:
        raise HTTPException(status_code=404, detail="Budget not found")
    return row


@router.get("/risk/budgets/{budget_id}/checks")
def list_budget_checks(
    budget_id: UUID,
    status: str | None = None,
    triggers_only: bool = False,
    limit: int = 50,
    offset: int = 0,
    tenant: TenantContext = Depends(require_permission("risk:read")),
    svc: RiskIntelligenceService = Depends(_svc),
):
    try:
        return svc.list_budget_checks(
            budget_id,
            status=status,
            triggers_only=triggers_only,
            limit=min(limit, 200),
            offset=offset,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/risk/budgets/{budget_id}")
def patch_budget(
    budget_id: UUID,
    payload: BudgetPatch,
    tenant: TenantContext = Depends(require_permission("risk:manage")),
    svc: RiskIntelligenceService = Depends(_svc),
):
    try:
        return svc.update_budget(
            budget_id,
            **payload.model_dump(exclude_none=True),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/risk/anomalies")
def list_anomalies(
    ai_system_id: UUID | None = None,
    limit: int = 50,
    offset: int = 0,
    tenant: TenantContext = Depends(require_permission("risk:read")),
    svc: RiskIntelligenceService = Depends(_svc),
):
    items = svc.list_anomalies(
        ai_system_id=ai_system_id,
        limit=limit,
        offset=offset,
    )
    return {"items": items, "limit": limit, "offset": offset}


@router.post("/risk/emergency/ai-systems/{system_id}/stop")
def emergency_stop_ai_system(
    system_id: UUID,
    payload: EmergencySuspendRequest,
    tenant: TenantContext = Depends(require_permission("risk:emergency")),
    db: Session = Depends(get_db),
):
    """Authoritative emergency stop: STOPPED system + suspend identities + deny overlay."""
    if not payload.confirm:
        raise HTTPException(
            status_code=400,
            detail="Confirmation required: set confirm=true with a reason",
        )
    from rai_gateway.core.observability import generate_trace_id, log_admin_audit
    from rai_gateway.models.registry import AISystem
    from rai_gateway.risk_intelligence.domain import (
        InterventionAuthorizationMode,
        InterventionEffect,
        InterventionStatus,
        RiskScopeType,
        RiskSeverity,
    )
    from rai_gateway.risk_intelligence.intervention import InterventionService
    from rai_gateway.risk_intelligence.repository import RiskIntelligenceRepository

    actor = tenant.user_id
    system = (
        db.query(AISystem)
        .filter(
            AISystem.id == system_id,
        )
        .first()
    )
    if not system:
        raise HTTPException(status_code=404, detail="AI system not found")

    repo = RiskIntelligenceRepository(db)
    intervention = repo.create_intervention(
        trajectory_id=None,
        ai_system_id=system_id,
        scope_type=RiskScopeType.AI_SYSTEM.value,
        scope_id=str(system_id),
        effect=InterventionEffect.EMERGENCY_STOP.value,
        reason=payload.reason,
        risk_level=RiskSeverity.CRITICAL.value,
        confidence=1.0,
        triggering_signal_ids=[],
        policy_rule_ids=[],
        finding_id=None,
        status=InterventionStatus.PENDING_CONFIRMATION.value,
        authorization_mode=InterventionAuthorizationMode.HUMAN_CONFIRM_HIGH_CRITICAL.value,
        automatic=False,
        explanation={"source": "emergency_api", "actor": actor},
    )
    executed = InterventionService(db).confirm_intervention(
        intervention.id, executed_by=actor
    )
    log_admin_audit(
        trace_id=generate_trace_id(),
        actor_user_id=actor,
        actor_role="rai_officer",
        action="ai_system.emergency_stopped",
        target={
            "ai_system_id": str(system_id),
            "intervention_id": str(executed.id),
            "reason": payload.reason,
        },
    )
    db.commit()
    db.refresh(system)
    return {
        "ai_system_id": str(system_id),
        "status": system.status,
        "intervention_id": str(executed.id),
        "intervention_status": executed.status,
        "reason": payload.reason,
    }


@router.post("/risk/emergency/runtime-identities/{identity_id}/suspend")
def emergency_suspend_runtime_identity(
    identity_id: UUID,
    payload: EmergencySuspendRequest,
    tenant: TenantContext = Depends(require_permission("risk:emergency")),
    db: Session = Depends(get_db),
):
    if not payload.confirm:
        raise HTTPException(
            status_code=400,
            detail="Confirmation required: set confirm=true with a reason",
        )
    from rai_gateway.core.observability import generate_trace_id, log_admin_audit
    from rai_gateway.evidence.domain import EvidenceEventType, EvidenceSourceType
    from rai_gateway.identity.errors import IdentityError
    from rai_gateway.identity.service import RuntimeIdentityService
    from rai_gateway.risk_intelligence.evidence_projection import (
        project_operational_event,
    )

    actor = tenant.user_id
    try:
        identity = RuntimeIdentityService(db).suspend_runtime_identity(
            identity_id,
            updated_by=actor,
            reason=payload.reason,
        )
    except IdentityError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    project_operational_event(
        db,
        event_type=EvidenceEventType.RUNTIME_IDENTITY_SUSPENDED.value,
        source_type=EvidenceSourceType.RAI_AUTHORITATIVE.value,
        payload={
            "runtime_identity_id": str(identity_id),
            "reason": payload.reason,
            "actor": actor,
            "previous_status": "ACTIVE",
            "new_status": "SUSPENDED",
        },
        runtime_identity_id=identity_id,
    )
    log_admin_audit(
        trace_id=generate_trace_id(),
        actor_user_id=actor,
        actor_role="rai_officer",
        action="runtime_identity.emergency_suspended",
        target={
            "runtime_identity_id": str(identity_id),
            "reason": payload.reason,
        },
    )
    db.commit()
    return {
        "id": str(identity.id),
        "status": identity.status,
        "reason": payload.reason,
    }


@router.post("/risk/emergency/runtime-identities/{identity_id}/reactivate")
def emergency_reactivate_runtime_identity(
    identity_id: UUID,
    payload: EmergencyReactivateRequest,
    tenant: TenantContext = Depends(require_permission("risk:emergency")),
    db: Session = Depends(get_db),
):
    if not payload.confirm:
        raise HTTPException(
            status_code=400,
            detail="Confirmation required: set confirm=true with a reason",
        )
    from rai_gateway.core.observability import generate_trace_id, log_admin_audit
    from rai_gateway.evidence.domain import EvidenceEventType, EvidenceSourceType
    from rai_gateway.identity.errors import IdentityError
    from rai_gateway.identity.service import RuntimeIdentityService
    from rai_gateway.risk_intelligence.evidence_projection import (
        project_operational_event,
    )

    actor = tenant.user_id
    try:
        identity = RuntimeIdentityService(db).activate_runtime_identity(
            identity_id,
            updated_by=actor,
            reason=payload.reason,
        )
    except IdentityError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    project_operational_event(
        db,
        event_type=EvidenceEventType.RUNTIME_IDENTITY_REACTIVATED.value,
        source_type=EvidenceSourceType.RAI_AUTHORITATIVE.value,
        payload={
            "runtime_identity_id": str(identity_id),
            "reason": payload.reason,
            "actor": actor,
            "previous_status": "SUSPENDED",
            "new_status": "ACTIVE",
        },
        runtime_identity_id=identity_id,
    )
    log_admin_audit(
        trace_id=generate_trace_id(),
        actor_user_id=actor,
        actor_role="rai_officer",
        action="runtime_identity.emergency_reactivated",
        target={
            "runtime_identity_id": str(identity_id),
            "reason": payload.reason,
        },
    )
    db.commit()
    return {
        "id": str(identity.id),
        "status": identity.status,
        "reason": payload.reason,
    }


@router.get("/risk/interventions")
def list_interventions(
    ai_system_id: UUID | None = None,
    trajectory_id: UUID | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    tenant: TenantContext = Depends(require_permission("risk:read")),
    svc: RiskIntelligenceService = Depends(_svc),
):
    items = svc.list_interventions(
        ai_system_id=ai_system_id,
        trajectory_id=trajectory_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    return {"items": items, "limit": limit, "offset": offset}


@router.post("/risk/interventions/{intervention_id}/confirm")
def confirm_intervention(
    intervention_id: UUID,
    tenant: TenantContext = Depends(require_permission("risk:intervene")),
    svc: RiskIntelligenceService = Depends(_svc),
):
    try:
        return svc.confirm_intervention(
            intervention_id,
            actor=tenant.user_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/risk/interventions/{intervention_id}/cancel")
def cancel_intervention(
    intervention_id: UUID,
    tenant: TenantContext = Depends(require_permission("risk:intervene")),
    svc: RiskIntelligenceService = Depends(_svc),
):
    try:
        return svc.cancel_intervention(
            intervention_id,
            actor=tenant.user_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/risk/recommendations")
def list_recommendations(
    ai_system_id: UUID | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    tenant: TenantContext = Depends(require_permission("risk:recommendations")),
    svc: RiskIntelligenceService = Depends(_svc),
):
    items = svc.list_recommendations(
        ai_system_id=ai_system_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    return {"items": items, "limit": limit, "offset": offset}


@router.post("/risk/recommendations/scan")
def scan_recommendations(
    ai_system_id: UUID,
    tenant: TenantContext = Depends(require_permission("risk:manage")),
    svc: RiskIntelligenceService = Depends(_svc),
):
    try:
        return {"items": svc.scan_recommendations(ai_system_id)}
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/risk/recommendations/{recommendation_id}/accept")
def accept_recommendation(
    recommendation_id: UUID,
    tenant: TenantContext = Depends(require_permission("risk:recommendations")),
    svc: RiskIntelligenceService = Depends(_svc),
):
    try:
        return svc.accept_recommendation(
            recommendation_id,
            actor=tenant.user_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/risk/recommendations/{recommendation_id}/dismiss")
def dismiss_recommendation(
    recommendation_id: UUID,
    reject: bool = False,
    tenant: TenantContext = Depends(require_permission("risk:recommendations")),
    svc: RiskIntelligenceService = Depends(_svc),
):
    try:
        return svc.dismiss_recommendation(
            recommendation_id,
            reject=reject,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/risk/trajectories/{trajectory_id}")
def trajectory_risk(
    trajectory_id: UUID,
    tenant: TenantContext = Depends(require_permission("risk:read")),
    svc: RiskIntelligenceService = Depends(_svc),
):
    return svc.trajectory_risk(trajectory_id)


@router.get("/content-evaluator/config")
def get_evaluator_config(
    ai_system_id: UUID | None = None,
    tenant: TenantContext = Depends(require_permission("content_evaluator:manage")),
    svc: RiskIntelligenceService = Depends(_svc),
):
    try:
        return svc.get_evaluator_config(ai_system_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/content-evaluator/config")
def upsert_evaluator_config(
    payload: EvaluatorConfigUpsert,
    tenant: TenantContext = Depends(require_permission("content_evaluator:manage")),
    svc: RiskIntelligenceService = Depends(_svc),
):
    try:
        return svc.upsert_evaluator_config(
            **payload.model_dump(),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/content-evaluator/evaluate")
def evaluate_content(
    payload: ContentEvaluateRequest,
    tenant: TenantContext = Depends(require_permission("risk:manage")),
    svc: RiskIntelligenceService = Depends(_svc),
):
    try:
        return svc.evaluate_content(
            **payload.model_dump(),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/content-evaluator/test")
def test_evaluate_content(
    payload: ContentTestRequest,
    tenant: TenantContext = Depends(require_permission("content_evaluator:manage")),
    svc: RiskIntelligenceService = Depends(_svc),
):
    try:
        return svc.test_evaluate_content(
            **payload.model_dump(),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
