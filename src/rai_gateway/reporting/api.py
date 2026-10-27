"""FastAPI REST endpoints for reporting and analytics."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

import rai_gateway.models.reporting  # noqa: F401 — register snapshot models
from rai_gateway.core.authorization import require_permission
from rai_gateway.core.database import get_db
from rai_gateway.core.tenant_context import TenantContext
from rai_gateway.reporting.schemas import (
    AISystemReport,
    AssuranceReport,
    BudgetReport,
    ConversationReport,
    PolicyReport,
    ReportFilters,
    ReportSnapshot,
    ReportSnapshotCreate,
    ReportSummary,
    RiskReport,
    RuntimeReport,
)
from rai_gateway.reporting.service import ReportingService
from rai_gateway.reporting.snapshots import (
    create_snapshot,
    get_snapshot,
    list_snapshots,
)

router = APIRouter(prefix="/v1/reports", tags=["reporting"])


@router.get("/summary", response_model=ReportSummary)
def get_summary_report(
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("reports:read")),
    ai_system_id: UUID | None = Query(None),
    agent_id: UUID | None = Query(None),
    period_start: str | None = Query(None),
    period_end: str | None = Query(None),
    risk_severity: list[str] | None = Query(None),
) -> ReportSummary:
    """Get executive summary report.

    Returns organization-wide or system-scoped governance posture metrics.
    """
    filters = ReportFilters(
        ai_system_id=ai_system_id,
        agent_id=agent_id,
        period_start=period_start,
        period_end=period_end,
        risk_severity=risk_severity,
    )

    service = ReportingService(db)
    return service.get_summary_report(filters)


@router.get("/risk", response_model=RiskReport)
def get_risk_report(
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("reports:read")),
    ai_system_id: UUID | None = Query(None),
    period_start: str | None = Query(None),
    period_end: str | None = Query(None),
    risk_severity: list[str] | None = Query(None),
    risk_category: list[str] | None = Query(None),
    finding_status: list[str] | None = Query(None),
) -> RiskReport:
    """Get risk analysis report.

    Returns detailed risk findings, severity distribution, and trends.
    """
    filters = ReportFilters(
        ai_system_id=ai_system_id,
        period_start=period_start,
        period_end=period_end,
        risk_severity=risk_severity,
        risk_category=risk_category,
        finding_status=finding_status,
    )

    service = ReportingService(db)
    return service.get_risk_report(filters)


@router.get("/policies", response_model=PolicyReport)
def get_policy_report(
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("reports:read")),
    ai_system_id: UUID | None = Query(None),
    period_start: str | None = Query(None),
    period_end: str | None = Query(None),
    effect: str | None = Query(None),
) -> PolicyReport:
    """Get policy effectiveness report.

    Returns policy evaluation metrics, trigger rates, and effect distribution.
    """
    filters = ReportFilters(
        ai_system_id=ai_system_id,
        period_start=period_start,
        period_end=period_end,
        effect=effect,
    )

    service = ReportingService(db)
    return service.get_policy_report(filters)


@router.get("/budgets", response_model=BudgetReport)
def get_budget_report(
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("reports:read")),
    ai_system_id: UUID | None = Query(None),
    period_start: str | None = Query(None),
    period_end: str | None = Query(None),
    budget_metric: str | None = Query(None),
) -> BudgetReport:
    """Get budget and cost report.

    Returns budget utilization, cost metrics, and budget status.
    """
    filters = ReportFilters(
        ai_system_id=ai_system_id,
        period_start=period_start,
        period_end=period_end,
        budget_metric=budget_metric,
    )

    service = ReportingService(db)
    return service.get_budget_report(filters)


@router.get("/runtime", response_model=RuntimeReport)
def get_runtime_report(
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("reports:read")),
    ai_system_id: UUID | None = Query(None),
    period_start: str | None = Query(None),
    period_end: str | None = Query(None),
) -> RuntimeReport:
    """Get runtime governance activity report.

    Returns execution metrics and governance funnel statistics.
    """
    filters = ReportFilters(
        ai_system_id=ai_system_id,
        period_start=period_start,
        period_end=period_end,
    )

    service = ReportingService(db)
    return service.get_runtime_report(filters)


@router.get("/assurance", response_model=AssuranceReport)
def get_assurance_report(
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("reports:read")),
    ai_system_id: UUID | None = Query(None),
) -> AssuranceReport:
    """Get assurance and control coverage report.

    Returns assurance status, evaluation metrics, and control coverage.
    """
    filters = ReportFilters(ai_system_id=ai_system_id)

    service = ReportingService(db)
    return service.get_assurance_report(filters)


@router.get("/ai-systems/{ai_system_id}", response_model=AISystemReport)
def get_ai_system_report(
    ai_system_id: UUID,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("reports:read")),
    period_start: str | None = Query(None),
    period_end: str | None = Query(None),
) -> AISystemReport:
    """Get AI System detailed report.

    Returns comprehensive metrics for a specific AI system.
    """
    filters = ReportFilters(
        ai_system_id=ai_system_id,
        period_start=period_start,
        period_end=period_end,
    )

    service = ReportingService(db)
    try:
        return service.get_ai_system_report(ai_system_id, filters)
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.get("/conversations/{conversation_id}", response_model=ConversationReport)
def get_conversation_report(
    conversation_id: UUID,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("reports:read")),
) -> ConversationReport:
    """Get conversation detailed report.

    Returns metrics and events for a specific conversation.
    """
    filters = ReportFilters(conversation_id=conversation_id)

    service = ReportingService(db)
    try:
        return service.get_conversation_report(conversation_id, filters)
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


# ============================================================================
# Report Snapshots
# ============================================================================


@router.post(
    "/snapshots", response_model=ReportSnapshot, status_code=status.HTTP_201_CREATED
)
def create_report_snapshot(
    request: ReportSnapshotCreate,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("reports:read")),
) -> ReportSnapshot:
    """Create an immutable report snapshot.

    Generates and stores a point-in-time report for historical reference.
    """
    # Generate the report based on type
    service = ReportingService(db)

    if request.report_type == "EXECUTIVE_SUMMARY":
        report = service.get_summary_report(request.filters)
    elif request.report_type == "RISK_REPORT":
        report = service.get_risk_report(request.filters)
    elif request.report_type == "POLICY_REPORT":
        report = service.get_policy_report(request.filters)
    elif request.report_type == "BUDGET_REPORT":
        report = service.get_budget_report(request.filters)
    elif request.report_type == "RUNTIME_REPORT":
        report = service.get_runtime_report(request.filters)
    elif request.report_type == "ASSURANCE_REPORT":
        report = service.get_assurance_report(request.filters)
    elif request.report_type == "AI_SYSTEM_REPORT":
        if request.filters.ai_system_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="ai_system_id is required for an AI system report snapshot",
            )
        report = service.get_ai_system_report(
            request.filters.ai_system_id, request.filters
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported report type: {request.report_type}",
        )

    # Create snapshot
    snapshot = create_snapshot(
        db=db,
        report_data=report.model_dump(mode="json"),
        request=request,
        generated_by=tenant.user_id,
    )

    return snapshot


@router.get("/snapshots", response_model=list[ReportSnapshot])
def list_report_snapshots(
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("reports:read")),
    report_type: str | None = Query(None),
    scope_type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[ReportSnapshot]:
    """List report snapshots.

    Returns historical report snapshots with optional filters.
    """
    filters_dict = {
        "report_type": report_type,
        "scope_type": scope_type,
        "limit": limit,
        "offset": offset,
    }

    return list_snapshots(db, filters_dict)


@router.get("/snapshots/{snapshot_id}", response_model=ReportSnapshot)
def get_report_snapshot(
    snapshot_id: UUID,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("reports:read")),
) -> ReportSnapshot:
    """Get a specific report snapshot.

    Returns an immutable historical report.
    """
    snapshot = get_snapshot(db, snapshot_id)

    if not snapshot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Report snapshot not found"
        )

    return snapshot
