"""FinOps admin / estimate API."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import rai_gateway.models.finops  # noqa: F401
from rai_gateway.core.authorization import (
    Principal,
    require_any_permission,
    require_permission,
    require_platform_permission,
    require_user,
)
from rai_gateway.core.database import get_db
from rai_gateway.core.tenant_context import TenantContext
from rai_gateway.finops.cursor_catalog import cursor_catalog_document
from rai_gateway.finops.service import FinOpsService
from rai_gateway.governance.domain import MembershipStatus
from rai_gateway.models.governance import OrganizationMembership

router = APIRouter(prefix="/v1/finops", tags=["finops"])

PLATFORM_ROLES = ["platform_admin", "platform_support", "admin"]


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


class PricingUpsertBody(BaseModel):
    provider: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    input_token_price: float = Field(..., ge=0)
    output_token_price: float = Field(..., ge=0)
    currency: str = "USD"
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    cached_input_token_price: float | None = Field(default=None, ge=0)
    reasoning_token_price: float | None = Field(default=None, ge=0)
    minimum_request_cost: float | None = Field(default=None, ge=0)
    cache_write_token_price: float | None = Field(default=None, ge=0)
    image_input_price: float | None = Field(default=None, ge=0)
    image_output_price: float | None = Field(default=None, ge=0)
    audio_input_price: float | None = Field(default=None, ge=0)
    audio_output_price: float | None = Field(default=None, ge=0)
    request_price: float | None = Field(default=None, ge=0)
    provider_tool_price: float | None = Field(default=None, ge=0)
    pricing_metadata: dict[str, Any] | None = None
    source_url: str | None = None
    verified_at: datetime | None = None
    region: str | None = None
    service_tier: str | None = None
    pricing_unit: int = Field(default=1000, ge=1)


class EstimateBody(BaseModel):
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0
    currency: str = "USD"
    fast: bool = False
    plan: str | None = None
    apply_cursor_token_rate: bool | None = None
    max_mode: bool = False
    regional_residency: bool = False


class ReserveBody(BaseModel):
    estimated_cost: float = Field(..., ge=0)
    currency: str = "USD"
    ai_system_id: UUID | None = None
    runtime_identity_id: UUID | None = None
    correlation_id: str | None = None
    provider: str | None = None
    model: str | None = None
    estimated_input_tokens: int | None = None
    estimated_output_tokens: int | None = None
    allocation: dict[str, Any] | None = None


class SettleBody(BaseModel):
    reservation_id: UUID | None = None
    enforcement_receipt_id: UUID | None = None
    correlation_id: str | None = None
    usage: dict[str, Any] | None = None
    cost: dict[str, Any] | None = None
    allocation: dict[str, Any] | None = None


@router.post("/pricing")
def upsert_pricing(
    body: PricingUpsertBody,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_platform_permission("platform:admin")),
) -> dict[str, Any]:
    """Upsert pricing catalog entry. Platform-only operation."""
    svc = FinOpsService(db)
    row = svc.upsert_pricing(
        provider=body.provider,
        model=body.model,
        input_token_price=body.input_token_price,
        output_token_price=body.output_token_price,
        currency=body.currency,
        effective_from=body.effective_from,
        effective_to=body.effective_to,
        cached_input_token_price=body.cached_input_token_price,
        reasoning_token_price=body.reasoning_token_price,
        minimum_request_cost=body.minimum_request_cost,
        cache_write_token_price=body.cache_write_token_price,
        image_input_price=body.image_input_price,
        image_output_price=body.image_output_price,
        audio_input_price=body.audio_input_price,
        audio_output_price=body.audio_output_price,
        request_price=body.request_price,
        provider_tool_price=body.provider_tool_price,
        pricing_metadata=body.pricing_metadata,
        source_url=body.source_url,
        verified_at=body.verified_at,
        region=body.region,
        service_tier=body.service_tier,
        pricing_unit=body.pricing_unit,
        created_by=principal.user_id or principal.email,
    )
    return svc.serialize_pricing(row)


@router.get("/pricing/resolve")
def resolve_pricing(
    provider: str = Query(...),
    model: str = Query(...),
    currency: str = Query(default="USD"),
    at: datetime | None = Query(default=None),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
) -> dict[str, Any]:
    """Resolve the active pricing entry for provider/model at a point in time."""
    svc = FinOpsService(db)
    row = svc.get_active_pricing(
        provider=provider, model=model, currency=currency, at=at
    )
    if row is None:
        raise HTTPException(status_code=404, detail="No active pricing entry")
    return svc.serialize_pricing(row)


@router.get("/pricing/cursor")
def cursor_pricing_catalog(
    principal: Principal = Depends(require_user),
) -> dict[str, Any]:
    """Published Cursor model and plan rates used by the pricing calculator."""
    return cursor_catalog_document()


@router.post("/pricing/seed/cursor")
def seed_cursor_pricing(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_platform_permission("platform:admin")),
) -> dict[str, Any]:
    """Persist Cursor's published rates. Active admin-owned rows are left in place."""
    return FinOpsService(db).seed_cursor_pricing(
        created_by=principal.user_id or principal.email
    )


@router.get("/pricing/{pricing_id}")
def get_pricing(
    pricing_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
) -> dict[str, Any]:
    """Get a pricing catalog entry by id."""
    svc = FinOpsService(db)
    row = svc.get_pricing(pricing_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Pricing entry not found")
    return svc.serialize_pricing(row)


@router.get("/pricing")
def list_pricing(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    provider: str | None = Query(default=None),
    model: str | None = Query(default=None),
) -> dict[str, Any]:
    """List pricing catalog. Available to all authenticated users."""
    svc = FinOpsService(db)
    rows = svc.list_pricing(provider=provider, model=model)
    return {"items": [svc.serialize_pricing(r) for r in rows]}


@router.post("/estimate")
def estimate_cost(
    body: EstimateBody,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
) -> dict[str, Any]:
    """Estimate cost for given usage. Available to all authenticated users."""
    return FinOpsService(db).estimate_cost(
        provider=body.provider,
        model=body.model,
        input_tokens=body.input_tokens,
        output_tokens=body.output_tokens,
        cached_input_tokens=body.cached_input_tokens,
        cache_write_tokens=body.cache_write_tokens,
        reasoning_tokens=body.reasoning_tokens,
        currency=body.currency,
        fast=body.fast,
        plan=body.plan,
        apply_cursor_token_rate=body.apply_cursor_token_rate,
        max_mode=body.max_mode,
        regional_residency=body.regional_residency,
    )


@router.post("/reservations")
def create_reservation(
    body: ReserveBody,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
) -> dict[str, Any]:
    """Create cost reservation. Validates active membership for non-platform users."""
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _validate_org_membership(db, principal.user_id)

    svc = FinOpsService(db)
    row = svc.reserve(
        estimated_cost=body.estimated_cost,
        currency=body.currency,
        ai_system_id=body.ai_system_id,
        runtime_identity_id=body.runtime_identity_id,
        correlation_id=body.correlation_id,
        provider=body.provider,
        model=body.model,
        estimated_input_tokens=body.estimated_input_tokens,
        estimated_output_tokens=body.estimated_output_tokens,
        allocation=body.allocation,
    )
    db.commit()
    return svc.serialize_reservation(row)


@router.post("/settlements")
def create_settlement(
    body: SettleBody,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
) -> dict[str, Any]:
    """Create settlement. Service layer validates ownership via reservation/receipt."""
    if (
        not body.reservation_id
        and not body.enforcement_receipt_id
        and not body.correlation_id
    ):
        raise HTTPException(
            status_code=400,
            detail="reservation_id, enforcement_receipt_id, or correlation_id required",
        )
    svc = FinOpsService(db)
    row = svc.settle(
        usage=body.usage,
        cost=body.cost,
        reservation_id=body.reservation_id,
        enforcement_receipt_id=body.enforcement_receipt_id,
        correlation_id=body.correlation_id,
        allocation=body.allocation,
    )
    db.commit()
    return svc.serialize_settlement(row)


def _filters(
    period_start: datetime | None,
    period_end: datetime | None,
    ai_system_id: UUID | None,
    agent_id: UUID | None,
    agent_version_id: UUID | None,
    runtime_identity_id: UUID | None,
    delegation_id: UUID | None,
    provider: str | None,
    model: str | None,
    environment: str | None,
    cost_state: str | None,
    metering_source: str | None,
):
    from rai_gateway.finops.reporting import FinOpsFilters, default_window

    start, end = default_window()
    return FinOpsFilters(
        period_start=period_start or start,
        period_end=period_end or end,
        ai_system_id=ai_system_id,
        agent_id=agent_id,
        agent_version_id=agent_version_id,
        runtime_identity_id=runtime_identity_id,
        delegation_id=delegation_id,
        provider=provider,
        model=model,
        environment=environment,
        cost_state=cost_state,
        metering_source=metering_source,
    )


@router.get("/dashboard")
@router.get("/summary")
def finops_dashboard(
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("finops:read")),
    period_start: datetime | None = None,
    period_end: datetime | None = None,
    ai_system_id: UUID | None = None,
    agent_id: UUID | None = None,
    agent_version_id: UUID | None = None,
    runtime_identity_id: UUID | None = None,
    delegation_id: UUID | None = None,
    provider: str | None = None,
    model: str | None = None,
    environment: str | None = None,
    cost_state: str | None = None,
    metering_source: str | None = None,
) -> dict[str, Any]:
    from rai_gateway.finops.reporting import FinOpsReportingService

    filters = _filters(
        period_start,
        period_end,
        ai_system_id,
        agent_id,
        agent_version_id,
        runtime_identity_id,
        delegation_id,
        provider,
        model,
        environment,
        cost_state,
        metering_source,
    )
    return FinOpsReportingService(db).dashboard(filters)


@router.get("/timeseries")
@router.get("/costs/timeseries")
def finops_timeseries(
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("finops:read")),
    period_start: datetime | None = None,
    period_end: datetime | None = None,
    ai_system_id: UUID | None = None,
    agent_id: UUID | None = None,
    provider: str | None = None,
    model: str | None = None,
    environment: str | None = None,
    delegation_id: UUID | None = None,
) -> dict[str, Any]:
    from rai_gateway.finops.reporting import FinOpsReportingService

    filters = _filters(
        period_start,
        period_end,
        ai_system_id,
        agent_id,
        None,
        None,
        delegation_id,
        provider,
        model,
        environment,
        None,
        None,
    )
    return FinOpsReportingService(db).timeseries(filters)


@router.get("/breakdown")
@router.get("/costs/breakdown")
@router.get("/costs")
def finops_breakdown(
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("finops:read")),
    dimension: str = Query(default="ai_system"),
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    period_start: datetime | None = None,
    period_end: datetime | None = None,
    ai_system_id: UUID | None = None,
    agent_id: UUID | None = None,
    provider: str | None = None,
    model: str | None = None,
    environment: str | None = None,
    delegation_id: UUID | None = None,
    cost_state: str | None = None,
) -> dict[str, Any]:
    from rai_gateway.finops.reporting import FinOpsReportingService

    filters = _filters(
        period_start,
        period_end,
        ai_system_id,
        agent_id,
        None,
        None,
        delegation_id,
        provider,
        model,
        environment,
        cost_state,
        None,
    )
    try:
        return FinOpsReportingService(db).breakdown(
            filters, dimension=dimension, limit=limit, offset=offset
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/top-spenders")
def finops_top_spenders(
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("finops:read")),
    dimension: str = Query(default="ai_system"),
    limit: int = Query(default=10, ge=1, le=50),
    period_start: datetime | None = None,
    period_end: datetime | None = None,
) -> dict[str, Any]:
    from rai_gateway.finops.reporting import FinOpsReportingService

    filters = _filters(
        period_start,
        period_end,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )
    try:
        return FinOpsReportingService(db).breakdown(
            filters, dimension=dimension, limit=limit
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/trajectories")
def finops_trajectories(
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("finops:read")),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    period_start: datetime | None = None,
    period_end: datetime | None = None,
    ai_system_id: UUID | None = None,
    provider: str | None = None,
    model: str | None = None,
    cost_state: str | None = None,
) -> dict[str, Any]:
    from rai_gateway.finops.reporting import FinOpsReportingService

    filters = _filters(
        period_start,
        period_end,
        ai_system_id,
        None,
        None,
        None,
        None,
        provider,
        model,
        None,
        cost_state,
        None,
    )
    return FinOpsReportingService(db).trajectories(filters, limit=limit, offset=offset)


@router.get("/trajectories/{trajectory_id}")
def finops_trajectory_detail(
    trajectory_id: UUID,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("finops:read")),
) -> dict[str, Any]:
    from rai_gateway.finops.metering import RuntimeMeteringService

    return RuntimeMeteringService(db).trajectory_economics(trajectory_id)


@router.get("/models")
def finops_models(
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("finops:read")),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    period_start: datetime | None = None,
    period_end: datetime | None = None,
    provider: str | None = None,
) -> dict[str, Any]:
    from rai_gateway.finops.reporting import FinOpsReportingService

    filters = _filters(
        period_start,
        period_end,
        None,
        None,
        None,
        None,
        None,
        provider,
        None,
        None,
        None,
        None,
    )
    return FinOpsReportingService(db).breakdown(
        filters, dimension="model", limit=limit, offset=offset
    )


@router.get("/tenants")
def finops_tenants(
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("finops:read")),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    period_start: datetime | None = None,
    period_end: datetime | None = None,
    ai_system_id: UUID | None = None,
) -> dict[str, Any]:
    from rai_gateway.finops.reporting import FinOpsReportingService

    filters = _filters(
        period_start,
        period_end,
        ai_system_id,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )
    return FinOpsReportingService(db).breakdown(
        filters, dimension="delegation", limit=limit, offset=offset
    )


@router.get("/export")
def finops_export(
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(
        require_any_permission("finops:export", "finops:read")
    ),
    view: str = Query(default="summary"),
    export_format: str = Query(default="json", alias="format"),
    period_start: datetime | None = None,
    period_end: datetime | None = None,
):
    import csv
    import io
    import json

    from fastapi.responses import Response

    from rai_gateway.finops.reporting import FinOpsReportingService

    if not tenant.has_permission("finops:export") and view != "summary":
        raise HTTPException(status_code=403, detail="finops:export required")
    filters = _filters(
        period_start,
        period_end,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )
    rows = FinOpsReportingService(db).export_rows(filters, view)
    if export_format == "csv":
        buffer = io.StringIO()
        flat = [_flatten(row) for row in rows] or [{}]
        writer = csv.DictWriter(
            buffer, fieldnames=sorted({key for row in flat for key in row})
        )
        writer.writeheader()
        writer.writerows(flat)
        return Response(
            buffer.getvalue(),
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="finops-{view}.csv"'
            },
        )
    return Response(
        json.dumps({"view": view, "items": rows}), media_type="application/json"
    )


def _flatten(row: dict[str, Any]) -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, (dict, list)):
            continue
        flat[key] = value
    return flat
