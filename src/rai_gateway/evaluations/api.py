"""WP7 Evaluation, Assurance & Deployment Gates REST API."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import rai_gateway.models.evaluations  # noqa: F401
from rai_gateway.core.authorization import require_permission
from rai_gateway.core.database import get_db
from rai_gateway.core.principal import Principal
from rai_gateway.core.tenant_context import TenantContext
from rai_gateway.evaluations.errors import EvaluationError
from rai_gateway.evaluations.service import EvaluationService

router = APIRouter(
    prefix="/v1",
    tags=["evaluations"],
)


def _svc(db: Session = Depends(get_db)) -> EvaluationService:
    return EvaluationService(db)


def _actor(principal: Principal) -> str:
    return principal.user_id or principal.email


def _handle(exc: EvaluationError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={"error": exc.error_code, "message": exc.message},
    )


# --- Request models -------------------------------------------------------


class SuiteCreate(BaseModel):
    ai_system_id: UUID
    suite_key: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    category: str = Field(..., min_length=1)
    description: str | None = None
    runner_type: str = "DETERMINISTIC"
    runner_config: dict[str, Any] | None = None


class CaseCreate(BaseModel):
    case_key: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    input_fixture: dict[str, Any] = Field(default_factory=dict)
    expected_behavior: dict[str, Any] = Field(default_factory=dict)
    scoring_method: str = "exact_match"
    threshold: float = 1.0
    failure_severity: str = "HIGH"
    description: str | None = None
    sort_order: int = 0


class RequirementCreate(BaseModel):
    ai_system_id: UUID
    name: str = Field(..., min_length=1)
    category: str = Field(..., min_length=1)
    evaluation_suite_id: UUID
    minimum_score: float = 1.0
    maximum_failed_critical_cases: int = 0
    required: bool = True
    validity_days: int | None = 30
    environment_scope: str = "PRODUCTION"
    enabled: bool = True
    accepted_runner_types: list[str] | None = None


class PlanCreate(BaseModel):
    target_environment: str = "PRODUCTION"
    categories: list[str] | None = None


class PlanRunsCreate(BaseModel):
    idempotency_key: str = "default"
    execute_inline: bool = True


class GateCreate(BaseModel):
    ai_system_id: UUID
    name: str = Field(..., min_length=1)
    environment: str = "PRODUCTION"
    description: str | None = None
    conditions: list[dict[str, Any]] | None = None
    auto_from_requirements: bool = True


class GateEvaluateRequest(BaseModel):
    environment: str = "PRODUCTION"
    gate_id: UUID | None = None
    plan_id: UUID | None = None


class WaiverCreate(BaseModel):
    agent_version_id: UUID
    justification: str = Field(..., min_length=1)
    failed_condition: dict[str, Any]
    environment: str = "PRODUCTION"
    compensating_controls: dict[str, Any] | list[Any] | None = None
    validity_days: int | None = 14
    gate_evaluation_id: UUID | None = None


class WaiverDecision(BaseModel):
    decision_reason: str | None = None


# --- Suites ---------------------------------------------------------------


@router.get("/evaluation-suites")
def list_suites(
    ai_system_id: UUID | None = None,
    published_only: bool = False,
    limit: int = 50,
    offset: int = 0,
    tenant: TenantContext = Depends(require_permission("evaluation:read")),
    svc: EvaluationService = Depends(_svc),
):
    items = svc.list_suites(
        ai_system_id=ai_system_id,
        published_only=published_only,
        limit=limit,
        offset=offset,
    )
    return {"items": items, "limit": limit, "offset": offset}


@router.post("/evaluation-suites")
def create_suite(
    payload: SuiteCreate,
    tenant: TenantContext = Depends(require_permission("evaluation:manage")),
    svc: EvaluationService = Depends(_svc),
):
    try:
        return svc.create_suite(
            **payload.model_dump(),
            created_by=_actor(tenant.principal),
        )
    except EvaluationError as exc:
        raise _handle(exc) from exc


@router.get("/evaluation-suites/{suite_id}")
def get_suite(
    suite_id: UUID,
    tenant: TenantContext = Depends(require_permission("evaluation:read")),
    svc: EvaluationService = Depends(_svc),
):
    try:
        return svc.get_suite(suite_id)
    except EvaluationError as exc:
        raise _handle(exc) from exc


@router.post("/evaluation-suites/{suite_id}/publish")
def publish_suite(
    suite_id: UUID,
    tenant: TenantContext = Depends(require_permission("evaluation:manage")),
    svc: EvaluationService = Depends(_svc),
):
    try:
        return svc.publish_suite(suite_id)
    except EvaluationError as exc:
        raise _handle(exc) from exc


@router.post("/evaluation-suites/{suite_id}/cases")
def add_case(
    suite_id: UUID,
    payload: CaseCreate,
    tenant: TenantContext = Depends(require_permission("evaluation:manage")),
    svc: EvaluationService = Depends(_svc),
):
    try:
        return svc.add_case(
            suite_id,
            **payload.model_dump(),
        )
    except EvaluationError as exc:
        raise _handle(exc) from exc


# --- Requirements ---------------------------------------------------------


@router.get("/evaluation-requirements")
def list_requirements(
    ai_system_id: UUID | None = None,
    environment: str | None = None,
    tenant: TenantContext = Depends(require_permission("evaluation:read")),
    svc: EvaluationService = Depends(_svc),
):
    return {
        "items": svc.list_requirements(
            ai_system_id=ai_system_id,
            environment=environment,
        )
    }


@router.post("/evaluation-requirements")
def create_requirement(
    payload: RequirementCreate,
    tenant: TenantContext = Depends(require_permission("evaluation:manage")),
    svc: EvaluationService = Depends(_svc),
):
    try:
        return svc.create_requirement(
            **payload.model_dump(),
            created_by=_actor(tenant.principal),
        )
    except EvaluationError as exc:
        raise _handle(exc) from exc


# --- Plans / Runs ---------------------------------------------------------


@router.get("/agent-versions/{version_id}/evaluation-plans")
def list_plans(
    version_id: UUID,
    tenant: TenantContext = Depends(require_permission("evaluation:read")),
    svc: EvaluationService = Depends(_svc),
):
    return {
        "items": svc.list_plans(
            agent_version_id=version_id,
        )
    }


@router.post("/agent-versions/{version_id}/evaluation-plans")
def create_plan(
    version_id: UUID,
    payload: PlanCreate,
    tenant: TenantContext = Depends(require_permission("evaluation:execute")),
    svc: EvaluationService = Depends(_svc),
):
    try:
        cats = set(payload.categories) if payload.categories else None
        return svc.create_plan(
            agent_version_id=version_id,
            target_environment=payload.target_environment,
            created_by=_actor(tenant.principal),
            categories=cats,
        )
    except EvaluationError as exc:
        raise _handle(exc) from exc


@router.post("/evaluation-plans/{plan_id}/runs")
def start_plan_runs(
    plan_id: UUID,
    payload: PlanRunsCreate,
    tenant: TenantContext = Depends(require_permission("evaluation:execute")),
    svc: EvaluationService = Depends(_svc),
):
    try:
        items = svc.start_runs_for_plan(
            plan_id,
            created_by=_actor(tenant.principal),
            idempotency_key=payload.idempotency_key,
            execute_inline=payload.execute_inline,
        )
        return {"items": items}
    except EvaluationError as exc:
        raise _handle(exc) from exc


@router.get("/evaluation-runs")
def list_runs(
    agent_version_id: UUID | None = None,
    ai_system_id: UUID | None = None,
    plan_id: UUID | None = None,
    limit: int = 50,
    offset: int = 0,
    tenant: TenantContext = Depends(require_permission("evaluation:read")),
    svc: EvaluationService = Depends(_svc),
):
    items = svc.list_runs(
        agent_version_id=agent_version_id,
        ai_system_id=ai_system_id,
        plan_id=plan_id,
        limit=limit,
        offset=offset,
    )
    return {"items": items, "limit": limit, "offset": offset}


@router.get("/evaluation-runs/{run_id}")
def get_run(
    run_id: UUID,
    tenant: TenantContext = Depends(require_permission("evaluation:read")),
    svc: EvaluationService = Depends(_svc),
):
    try:
        return svc.get_run(run_id)
    except EvaluationError as exc:
        raise _handle(exc) from exc


# --- Gates / Assurance ----------------------------------------------------


@router.get("/deployment-gates")
def list_gates(
    ai_system_id: UUID | None = None,
    environment: str | None = None,
    tenant: TenantContext = Depends(require_permission("deployment_gate:read")),
    svc: EvaluationService = Depends(_svc),
):
    return {
        "items": svc.list_gates(
            ai_system_id=ai_system_id,
            environment=environment,
        )
    }


@router.post("/deployment-gates")
def create_gate(
    payload: GateCreate,
    tenant: TenantContext = Depends(require_permission("deployment_gate:manage")),
    svc: EvaluationService = Depends(_svc),
):
    try:
        return svc.create_gate(
            **payload.model_dump(),
            created_by=_actor(tenant.principal),
        )
    except EvaluationError as exc:
        raise _handle(exc) from exc


@router.post("/agent-versions/{version_id}/deployment-gates/evaluate")
def evaluate_gate(
    version_id: UUID,
    payload: GateEvaluateRequest,
    tenant: TenantContext = Depends(require_permission("deployment_gate:manage")),
    svc: EvaluationService = Depends(_svc),
):
    try:
        return svc.evaluate_deployment_gate(
            agent_version_id=version_id,
            environment=payload.environment,
            evaluated_by=_actor(tenant.principal),
            gate_id=payload.gate_id,
            plan_id=payload.plan_id,
        )
    except EvaluationError as exc:
        raise _handle(exc) from exc


@router.get("/agent-versions/{version_id}/assurance")
def get_assurance(
    version_id: UUID,
    environment: str = "PRODUCTION",
    include_history: bool = False,
    tenant: TenantContext = Depends(require_permission("assurance:read")),
    svc: EvaluationService = Depends(_svc),
):
    return svc.get_assurance(
        version_id,
        environment=environment,
        include_history=include_history,
    )


@router.get("/agent-versions/{version_id}/deployment-readiness")
def deployment_readiness(
    version_id: UUID,
    environment: str = "PRODUCTION",
    tenant: TenantContext = Depends(require_permission("assurance:read")),
    svc: EvaluationService = Depends(_svc),
):
    try:
        return svc.deployment_readiness(
            version_id,
            environment=environment,
        )
    except EvaluationError as exc:
        raise _handle(exc) from exc


@router.get("/agent-versions/{version_id}/reassessment-triggers")
def list_reassessment_triggers(
    version_id: UUID,
    tenant: TenantContext = Depends(require_permission("assurance:read")),
    svc: EvaluationService = Depends(_svc),
):
    return {
        "items": svc.list_reassessment_triggers(
            version_id,
        )
    }


# --- Waivers --------------------------------------------------------------


@router.get("/evaluation-waivers")
def list_waivers(
    agent_version_id: UUID | None = None,
    ai_system_id: UUID | None = None,
    status: str | None = None,
    tenant: TenantContext = Depends(require_permission("assurance:read")),
    svc: EvaluationService = Depends(_svc),
):
    return {
        "items": svc.list_waivers(
            agent_version_id=agent_version_id,
            ai_system_id=ai_system_id,
            status=status,
        )
    }


@router.post("/evaluation-waivers")
def request_waiver(
    payload: WaiverCreate,
    tenant: TenantContext = Depends(require_permission("waiver:request")),
    svc: EvaluationService = Depends(_svc),
):
    try:
        return svc.request_waiver(
            **payload.model_dump(),
            requester=_actor(tenant.principal),
        )
    except EvaluationError as exc:
        raise _handle(exc) from exc


@router.post("/evaluation-waivers/{waiver_id}/approve")
def approve_waiver(
    waiver_id: UUID,
    payload: WaiverDecision,
    tenant: TenantContext = Depends(require_permission("waiver:approve")),
    svc: EvaluationService = Depends(_svc),
):
    try:
        return svc.approve_waiver(
            waiver_id,
            approver=_actor(tenant.principal),
            decision_reason=payload.decision_reason,
        )
    except EvaluationError as exc:
        raise _handle(exc) from exc


@router.post("/evaluation-waivers/{waiver_id}/reject")
def reject_waiver(
    waiver_id: UUID,
    payload: WaiverDecision,
    tenant: TenantContext = Depends(require_permission("waiver:approve")),
    svc: EvaluationService = Depends(_svc),
):
    try:
        return svc.reject_waiver(
            waiver_id,
            approver=_actor(tenant.principal),
            decision_reason=payload.decision_reason,
        )
    except EvaluationError as exc:
        raise _handle(exc) from exc


@router.post("/evaluation-waivers/{waiver_id}/revoke")
def revoke_waiver(
    waiver_id: UUID,
    payload: WaiverDecision,
    tenant: TenantContext = Depends(require_permission("waiver:approve")),
    svc: EvaluationService = Depends(_svc),
):
    try:
        return svc.revoke_waiver(
            waiver_id,
            actor=_actor(tenant.principal),
            decision_reason=payload.decision_reason,
        )
    except EvaluationError as exc:
        raise _handle(exc) from exc


# Silence unused datetime import for potential future date parsing
_ = datetime
