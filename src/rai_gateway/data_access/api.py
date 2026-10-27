"""Data-access governance HTTP API (admin policies + receipts)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import rai_gateway.models.data_access  # noqa: F401
from rai_gateway.core.authorization import Principal, require_user
from rai_gateway.core.database import get_db
from rai_gateway.data_access.service import DataAccessService
from rai_gateway.governance.domain import MembershipStatus
from rai_gateway.models.data_access import DataAccessPolicy, DataAccessReceipt
from rai_gateway.models.governance import OrganizationMembership
from rai_gateway.models.registry import AISystem

router = APIRouter(prefix="/v1/data-access", tags=["data-access"])
PLATFORM_ROLES = ["platform_admin", "platform_support", "admin"]


def _require_membership(db: Session, user_id: str) -> OrganizationMembership:
    """Require an active membership on this instance."""
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
                "message": "No active membership",
            },
        )
    return membership


def _get_ai_system(db: Session, ai_system_id: UUID) -> AISystem:
    system = db.query(AISystem).filter(AISystem.id == ai_system_id).first()
    if not system:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "NOT_FOUND",
                "message": "AI system not found",
            },
        )
    return system


class CreatePolicyBody(BaseModel):
    name: str = Field(..., min_length=1)
    effect: str = "DENY"
    ai_system_id: UUID | None = None
    data_source_id: UUID | None = None
    resource: str | None = None
    field_name: str | None = None
    classification: str | None = None
    purpose: str | None = None
    access_mode: str | None = None
    mask_style: str = "REDACT"
    row_predicate: dict[str, Any] | None = None
    priority: int = 100


@router.post("/policies")
def create_policy(
    body: CreatePolicyBody,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
) -> dict[str, Any]:
    """Create data access policy. Validates AI system ownership if provided."""
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if body.ai_system_id and not is_platform:
        _get_ai_system(db, body.ai_system_id)
        _require_membership(db, principal.user_id)
    svc = DataAccessService(db)
    row = svc.create_policy(
        name=body.name,
        created_by=principal.user_id or principal.email,
        effect=body.effect,
        ai_system_id=body.ai_system_id,
        data_source_id=body.data_source_id,
        resource=body.resource,
        field_name=body.field_name,
        classification=body.classification,
        purpose=body.purpose,
        access_mode=body.access_mode,
        mask_style=body.mask_style,
        row_predicate=body.row_predicate,
        priority=body.priority,
    )
    return _serialize_policy(row)


@router.get("/policies")
def list_policies(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    ai_system_id: UUID | None = Query(default=None),
) -> dict[str, Any]:
    """List data access policies. Validates AI system ownership if filtered."""
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    q = db.query(DataAccessPolicy).order_by(DataAccessPolicy.priority.asc())
    if ai_system_id:
        if not is_platform:
            _get_ai_system(db, ai_system_id)
            _require_membership(db, principal.user_id)
        q = q.filter(DataAccessPolicy.ai_system_id == ai_system_id)
    elif not is_platform:
        _require_membership(db, principal.user_id)
    return {"items": [_serialize_policy(r) for r in q.limit(200).all()]}


@router.get("/receipts/{receipt_id}")
def get_receipt(
    receipt_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
) -> dict[str, Any]:
    """Get data access receipt. Service layer validates ownership."""
    row = db.query(DataAccessReceipt).filter(DataAccessReceipt.id == receipt_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Receipt not found")
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _require_membership(db, principal.user_id)
    return {
        "id": str(row.id),
        "decision": row.decision,
        "reason_code": row.reason_code,
        "human_explanation": row.human_explanation,
        "resource": row.resource,
        "purpose": row.purpose,
        "requested_fields": row.requested_fields,
        "allowed_fields": row.allowed_fields,
        "denied_fields": row.denied_fields,
        "masked_fields": row.masked_fields,
        "transforms": row.transforms,
        "row_filter": row.row_filter,
        "policy_rule_ids": row.policy_rule_ids,
        "correlation_id": row.correlation_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _serialize_policy(row: DataAccessPolicy) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "name": row.name,
        "enabled": row.enabled,
        "effect": row.effect,
        "ai_system_id": str(row.ai_system_id) if row.ai_system_id else None,
        "data_source_id": str(row.data_source_id) if row.data_source_id else None,
        "resource": row.resource,
        "field_name": row.field_name,
        "classification": row.classification,
        "purpose": row.purpose,
        "access_mode": row.access_mode,
        "mask_style": row.mask_style,
        "row_predicate": row.row_predicate,
        "priority": row.priority,
        "created_by": row.created_by,
    }
