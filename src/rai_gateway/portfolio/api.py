"""WP9 Portfolio Transparency & Executive Oversight REST API."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import rai_gateway.models.portfolio  # noqa: F401
from rai_gateway.core.authorization import Principal, require_user
from rai_gateway.core.database import get_db
from rai_gateway.governance.domain import MembershipStatus
from rai_gateway.models.governance import OrganizationMembership
from rai_gateway.portfolio.errors import PortfolioError
from rai_gateway.portfolio.service import PortfolioService

router = APIRouter(
    prefix="/v1/portfolio",
    tags=["portfolio"],
)

PLATFORM_ROLES = ["platform_admin", "platform_support", "admin"]


def _svc(db: Session = Depends(get_db)) -> PortfolioService:
    return PortfolioService(db)


def _actor(principal: Principal) -> str:
    return principal.user_id or principal.email


def _validate_org_membership(
    db: Session,
    user_id: str,
) -> OrganizationMembership:
    """Validate user has active membership in organization."""
    membership = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.status == MembershipStatus.ACTIVE.value,
        )
        .first()
    )
    if membership is None:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "NOT_ALLOWED",
                "message": "No active membership for organization",
            },
        )
    return membership


def _handle(exc: PortfolioError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={"error": exc.error_code, "message": exc.message},
    )


# --- Request models -------------------------------------------------------


class ReportCreate(BaseModel):
    scope_type: str = "ORGANIZATION"
    scope_id: str | None = None
    period_start: datetime | None = None
    period_end: datetime | None = None
    period_days: int = Field(default=30, ge=1, le=366)
    include_html: bool = True


class ReportScheduleCreate(BaseModel):
    cadence: str
    scope_type: str = "ORGANIZATION"
    scope_id: str | None = None
    enabled: bool = True
    delivery: dict[str, Any] | None = None


class ReportSchedulePatch(BaseModel):
    enabled: bool | None = None
    delivery: dict[str, Any] | None = None


class ExecutiveDecisionCreate(BaseModel):
    scope_type: str
    scope_id: str
    decision: str
    reason: str = Field(..., min_length=1)
    evidence_refs: list[Any] | dict[str, Any] | None = None


# --- Read endpoints -------------------------------------------------------


@router.get("/summary")
def portfolio_summary(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: PortfolioService = Depends(_svc),
) -> dict[str, Any]:
    """Get portfolio summary. Validates membership for tenant users."""
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _validate_org_membership(db, principal.user_id)
    try:
        return svc.get_summary()
    except PortfolioError as exc:
        raise _handle(exc) from exc


@router.get("/dashboard")
def portfolio_dashboard(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: PortfolioService = Depends(_svc),
) -> dict[str, Any]:
    """Get portfolio dashboard. Validates membership for tenant users."""
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _validate_org_membership(db, principal.user_id)
    try:
        return svc.get_dashboard()
    except PortfolioError as exc:
        raise _handle(exc) from exc


@router.get("/ai-systems")
def portfolio_ai_systems(
    business_unit: str | None = None,
    owner: str | None = None,
    lifecycle: str | None = None,
    risk: str | None = None,
    assurance: str | None = None,
    control_status: str | None = None,
    incident_state: str | None = None,
    pilot_state: str | None = None,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: PortfolioService = Depends(_svc),
) -> dict[str, Any]:
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _validate_org_membership(db, principal.user_id)
    try:
        return svc.get_inventory(
            business_unit=business_unit,
            owner=owner,
            lifecycle=lifecycle,
            risk=risk,
            assurance=assurance,
            control_status=control_status,
            incident_state=incident_state,
            pilot_state=pilot_state,
        )
    except PortfolioError as exc:
        raise _handle(exc) from exc


@router.get("/risk")
def portfolio_risk(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: PortfolioService = Depends(_svc),
) -> dict[str, Any]:
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _validate_org_membership(db, principal.user_id)
    try:
        return svc.get_risk()
    except PortfolioError as exc:
        raise _handle(exc) from exc


@router.get("/assurance")
def portfolio_assurance(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: PortfolioService = Depends(_svc),
) -> dict[str, Any]:
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _validate_org_membership(db, principal.user_id)
    try:
        return svc.get_assurance()
    except PortfolioError as exc:
        raise _handle(exc) from exc


@router.get("/controls")
def portfolio_controls(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: PortfolioService = Depends(_svc),
) -> dict[str, Any]:
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _validate_org_membership(db, principal.user_id)
    try:
        return svc.get_controls()
    except PortfolioError as exc:
        raise _handle(exc) from exc


@router.get("/incidents")
def portfolio_incidents(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: PortfolioService = Depends(_svc),
) -> dict[str, Any]:
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _validate_org_membership(db, principal.user_id)
    try:
        return svc.get_incidents()
    except PortfolioError as exc:
        raise _handle(exc) from exc


@router.get("/runtime-activity")
def portfolio_runtime_activity(
    period_days: int = Query(default=30, ge=1, le=366),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: PortfolioService = Depends(_svc),
) -> dict[str, Any]:
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _validate_org_membership(db, principal.user_id)
    try:
        return svc.get_runtime_activity(period_days=period_days)
    except PortfolioError as exc:
        raise _handle(exc) from exc


@router.get("/evidence")
def portfolio_evidence(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: PortfolioService = Depends(_svc),
) -> dict[str, Any]:
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _validate_org_membership(db, principal.user_id)
    try:
        return svc.get_evidence()
    except PortfolioError as exc:
        raise _handle(exc) from exc


@router.get("/ownership")
def portfolio_ownership(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: PortfolioService = Depends(_svc),
) -> dict[str, Any]:
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _validate_org_membership(db, principal.user_id)
    try:
        return svc.get_ownership()
    except PortfolioError as exc:
        raise _handle(exc) from exc


@router.get("/attention")
def portfolio_attention(
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: PortfolioService = Depends(_svc),
) -> dict[str, Any]:
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _validate_org_membership(db, principal.user_id)
    try:
        return svc.get_attention(limit=limit)
    except PortfolioError as exc:
        raise _handle(exc) from exc


@router.get("/trends")
def portfolio_trends(
    period_days: int = Query(default=30, ge=1, le=366),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: PortfolioService = Depends(_svc),
) -> dict[str, Any]:
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _validate_org_membership(db, principal.user_id)
    try:
        return svc.get_trends(period_days=period_days)
    except PortfolioError as exc:
        raise _handle(exc) from exc


@router.get("/changes")
def portfolio_changes(
    period_days: int = Query(default=30, ge=1, le=366),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: PortfolioService = Depends(_svc),
) -> dict[str, Any]:
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _validate_org_membership(db, principal.user_id)
    try:
        return svc.get_changes(period_days=period_days, limit=limit)
    except PortfolioError as exc:
        raise _handle(exc) from exc


@router.get("/export")
def portfolio_export(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: PortfolioService = Depends(_svc),
) -> dict[str, Any]:
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _validate_org_membership(db, principal.user_id)
    try:
        return svc.export_portfolio(exported_by=_actor(principal))
    except PortfolioError as exc:
        raise _handle(exc) from exc


# --- Reports --------------------------------------------------------------


@router.get("/reports")
def list_portfolio_reports(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: PortfolioService = Depends(_svc),
) -> dict[str, Any]:
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _validate_org_membership(db, principal.user_id)
    try:
        return svc.list_reports(limit=limit, offset=offset)
    except PortfolioError as exc:
        raise _handle(exc) from exc


@router.post("/reports")
def create_portfolio_report(
    payload: ReportCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: PortfolioService = Depends(_svc),
) -> dict[str, Any]:
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _validate_org_membership(db, principal.user_id)
    try:
        return svc.generate_report(
            generated_by=_actor(principal),
            scope_type=payload.scope_type,
            scope_id=payload.scope_id,
            period_start=payload.period_start,
            period_end=payload.period_end,
            period_days=payload.period_days,
            include_html=payload.include_html,
        )
    except PortfolioError as exc:
        raise _handle(exc) from exc


@router.get("/reports/{report_id}")
def get_portfolio_report(
    report_id: UUID,
    include_html: bool = Query(default=False),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: PortfolioService = Depends(_svc),
) -> dict[str, Any]:
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _validate_org_membership(db, principal.user_id)
    try:
        return svc.get_report(
            report_id,
            include_html=include_html,
        )
    except PortfolioError as exc:
        raise _handle(exc) from exc


@router.get("/report-schedules")
def list_report_schedules(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: PortfolioService = Depends(_svc),
) -> dict[str, Any]:
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _validate_org_membership(db, principal.user_id)
    try:
        return svc.list_report_schedules()
    except PortfolioError as exc:
        raise _handle(exc) from exc


@router.post("/report-schedules")
def create_report_schedule(
    payload: ReportScheduleCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: PortfolioService = Depends(_svc),
) -> dict[str, Any]:
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _validate_org_membership(db, principal.user_id)
    try:
        return svc.create_report_schedule(
            cadence=payload.cadence,
            created_by=_actor(principal),
            scope_type=payload.scope_type,
            scope_id=payload.scope_id,
            enabled=payload.enabled,
            delivery=payload.delivery,
        )
    except PortfolioError as exc:
        raise _handle(exc) from exc


@router.patch("/report-schedules/{schedule_id}")
def patch_report_schedule(
    schedule_id: UUID,
    payload: ReportSchedulePatch,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: PortfolioService = Depends(_svc),
) -> dict[str, Any]:
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _validate_org_membership(db, principal.user_id)
    try:
        return svc.update_report_schedule(
            schedule_id,
            enabled=payload.enabled,
            delivery=payload.delivery,
            updated_by=_actor(principal),
        )
    except PortfolioError as exc:
        raise _handle(exc) from exc


# --- Executive decisions --------------------------------------------------


@router.get("/decisions")
def list_decisions(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: PortfolioService = Depends(_svc),
) -> dict[str, Any]:
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _validate_org_membership(db, principal.user_id)
    try:
        return svc.list_decisions(limit=limit, offset=offset)
    except PortfolioError as exc:
        raise _handle(exc) from exc


@router.post("/decisions")
def create_decision(
    payload: ExecutiveDecisionCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: PortfolioService = Depends(_svc),
) -> dict[str, Any]:
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _validate_org_membership(db, principal.user_id)
    try:
        return svc.create_decision(
            scope_type=payload.scope_type,
            scope_id=payload.scope_id,
            decision=payload.decision,
            reason=payload.reason,
            actor=_actor(principal),
            actor_role=None,
            evidence_refs=payload.evidence_refs,
        )
    except PortfolioError as exc:
        raise _handle(exc) from exc


@router.post("/projections/refresh")
def refresh_projection(
    projection_key: str = Query(default="summary"),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: PortfolioService = Depends(_svc),
) -> dict[str, Any]:
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _validate_org_membership(db, principal.user_id)
    try:
        result = svc.refresh_projection(projection_key=projection_key)
        db.commit()
        return result
    except PortfolioError as exc:
        raise _handle(exc) from exc
