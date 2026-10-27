"""Derived-data lineage & disposal admin API."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import rai_gateway.models.lineage  # noqa: F401
from rai_gateway.core.authorization import Principal, require_user
from rai_gateway.core.database import get_db
from rai_gateway.lineage.domain import RetentionClass
from rai_gateway.lineage.service import LineageError, LineageService

router = APIRouter(prefix="/v1/lineage", tags=["lineage"])


class DataSourceVersionCreate(BaseModel):
    data_source_id: UUID
    content_digest: str | None = None
    change_summary: str | None = None


class DerivedAssetCreate(BaseModel):
    source_version_id: UUID
    asset_type: str
    store: str
    locator: str = Field(..., min_length=1)
    digest: str | None = None
    retention_class: str = RetentionClass.STANDARD.value
    parent_asset_id: UUID | None = None
    ai_system_id: UUID | None = None
    agent_version_id: UUID | None = None
    evidence_ref: str | None = None
    metadata: dict[str, Any] | None = None


class LegalHoldBody(BaseModel):
    legal_hold: bool
    reason: str | None = None
    cascade_assets: bool = True


class DisposalBody(BaseModel):
    reason: str | None = None
    execute: bool = True
    max_retries: int | None = Field(default=None, ge=1, le=10)


def _handle(exc: LineageError) -> HTTPException:
    status = 404 if exc.code == "NOT_FOUND" else 409 if "LEGAL" in exc.code else 400
    return HTTPException(
        status_code=status, detail={"error": exc.code, "message": exc.message}
    )


@router.post("/data-source-versions")
def create_data_source_version(
    body: DataSourceVersionCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
) -> dict[str, Any]:
    """Create data source version. Service layer validates data source ownership."""
    svc = LineageService(db)
    try:
        row = svc.create_data_source_version(
            body.data_source_id,
            created_by=principal.user_id or principal.email or "admin",
            content_digest=body.content_digest,
            change_summary=body.change_summary,
        )
    except LineageError as exc:
        raise _handle(exc) from exc
    return svc.serialize_version(row)


@router.get("/data-source-versions/{version_id}")
def get_data_source_version(
    version_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
) -> dict[str, Any]:
    svc = LineageService(db)
    try:
        row = svc.get_data_source_version(version_id)
    except LineageError as exc:
        raise _handle(exc) from exc
    return svc.serialize_version(row)


@router.post("/data-source-versions/{version_id}/legal-hold")
def set_version_legal_hold(
    version_id: UUID,
    body: LegalHoldBody,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
) -> dict[str, Any]:
    svc = LineageService(db)
    try:
        row = svc.set_version_legal_hold(
            version_id,
            legal_hold=body.legal_hold,
            actor=principal.user_id or principal.email or "admin",
            reason=body.reason,
            cascade_assets=body.cascade_assets,
        )
    except LineageError as exc:
        raise _handle(exc) from exc
    return svc.serialize_version(row)


@router.post("/derived-assets")
def register_derived_asset(
    body: DerivedAssetCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
) -> dict[str, Any]:
    svc = LineageService(db)
    try:
        row = svc.register_derived_asset(
            source_version_id=body.source_version_id,
            asset_type=body.asset_type,
            store=body.store,
            locator=body.locator,
            digest=body.digest,
            retention_class=body.retention_class,
            parent_asset_id=body.parent_asset_id,
            ai_system_id=body.ai_system_id,
            agent_version_id=body.agent_version_id,
            evidence_ref=body.evidence_ref,
            metadata=body.metadata,
        )
    except LineageError as exc:
        raise _handle(exc) from exc
    return svc.serialize_asset(row)


@router.get("/data-source-versions/{version_id}/lineage")
def list_lineage(
    version_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    include_disposed: bool = True,
) -> dict[str, Any]:
    svc = LineageService(db)
    try:
        rows = svc.list_lineage(version_id, include_disposed=include_disposed)
    except LineageError as exc:
        raise _handle(exc) from exc
    return {"items": [svc.serialize_asset(r) for r in rows]}


@router.post("/data-source-versions/{version_id}/dispose")
def request_disposal(
    version_id: UUID,
    body: DisposalBody,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
) -> dict[str, Any]:
    svc = LineageService(db)
    try:
        row = svc.request_disposal(
            version_id,
            requested_by=principal.user_id or principal.email or "admin",
            reason=body.reason,
            execute=body.execute,
            max_retries=body.max_retries,
        )
    except LineageError as exc:
        raise _handle(exc) from exc
    return svc.serialize_disposal(row)


@router.post("/disposal-requests/{request_id}/retry")
def retry_disposal(
    request_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
) -> dict[str, Any]:
    svc = LineageService(db)
    try:
        row = svc.retry_disposal(
            request_id,
            actor=principal.user_id or principal.email or "admin",
        )
    except LineageError as exc:
        raise _handle(exc) from exc
    return svc.serialize_disposal(row)


@router.get("/disposal-requests/{request_id}")
def get_disposal_request(
    request_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
) -> dict[str, Any]:
    from rai_gateway.models.lineage import DisposalRequest

    row = db.query(DisposalRequest).filter(DisposalRequest.id == request_id).first()
    if not row:
        raise HTTPException(
            status_code=404,
            detail={"error": "NOT_FOUND", "message": "Disposal request not found"},
        )
    return LineageService(db).serialize_disposal(row)
