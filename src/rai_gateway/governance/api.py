"""WP8 Governance / Pilot Operating Model REST API."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import rai_gateway.models.governance  # noqa: F401
from rai_gateway.core.authorization import (
    PLATFORM_ROLES,
    require_organization_member,
    require_platform_permission,
    require_user,
)
from rai_gateway.core.config import settings
from rai_gateway.core.database import get_db
from rai_gateway.core.errors import ErrorCode, RaiException
from rai_gateway.core.principal import Principal
from rai_gateway.core.tenant_context import TenantContext
from rai_gateway.governance.controls import ensure_pilot_control_framework
from rai_gateway.governance.domain import GovernanceRole, MembershipStatus
from rai_gateway.governance.errors import GovernanceError, GovernanceNotFoundError
from rai_gateway.governance.seed import seed_reference_pilots
from rai_gateway.governance.service import GovernanceService
from rai_gateway.models.governance import (
    OrganizationMembership,
    PilotReadinessEvaluation,
)

router = APIRouter(prefix="/v1", tags=["governance"])


def _svc(db: Session = Depends(get_db)) -> GovernanceService:
    return GovernanceService(db)


def _actor(principal: Principal) -> str:
    return principal.user_id or principal.email


def _handle(exc: GovernanceError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={"error": exc.error_code, "message": exc.message},
    )


# --- Request models -------------------------------------------------------


def _require_active_membership(db: Session, user_id: str) -> OrganizationMembership:
    """Return an active membership. Prefer the organization-admin row when present."""
    rows = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.status == MembershipStatus.ACTIVE.value,
        )
        .all()
    )
    if not rows:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "NOT_ALLOWED",
                "message": "No active membership",
            },
        )
    for row in rows:
        if row.role == GovernanceRole.ORGANIZATION_ADMIN.value:
            return row
    return rows[0]


class GovernanceProfilePatch(BaseModel):
    name: str | None = None
    description: str | None = None
    logo: str | None = None
    legal_name: str | None = None
    organization_type: str | None = None
    sector: str | None = None
    jurisdiction: str | None = None
    regulatory_context: dict[str, Any] | None = None
    risk_appetite: str | None = None
    governance_owner: str | None = None
    assurance_owner: str | None = None
    incident_owner: str | None = None
    default_review_frequency_days: int | None = None
    evidence_retention_policy: dict[str, Any] | None = None
    pilot_status: str | None = None


class MembershipCreate(BaseModel):
    user_id: str = Field(..., min_length=1)
    role: str = Field(..., min_length=1)
    status: str = "ACTIVE"
    valid_until: datetime | None = None


class MemberInvite(BaseModel):
    email: str = Field(..., min_length=3)
    full_name: str = Field(..., min_length=1)
    role: str = Field(default="RAI_OFFICER", min_length=1)
    department_id: UUID | None = None


class MemberUpdate(BaseModel):
    role: str | None = None
    status: str | None = None


class AccountabilityUpsert(BaseModel):
    business_owner_membership_id: UUID | None = None
    technical_owner_membership_id: UUID | None = None
    rai_officer_membership_id: UUID | None = None
    risk_owner_membership_id: UUID | None = None
    incident_owner_membership_id: UUID | None = None
    enforce_sod: bool = True


class ClassificationUpsert(BaseModel):
    business_criticality: str | None = None
    data_sensitivity: str | None = None
    customer_citizen_impact: str | None = None
    financial_impact: str | None = None
    autonomy_level: str | None = None
    external_facing: bool | None = None
    consequential_actions: bool | None = None
    personal_data: bool | None = None
    regulated_process: bool | None = None
    human_oversight_requirement: str | None = None
    production: bool | None = None


class ControlAssessmentCreate(BaseModel):
    control_requirement_id: UUID
    status: str = Field(..., min_length=1)
    agent_version_id: UUID | None = None
    applicability: str | None = None
    applicability_reason: str | None = None
    evidence_refs: list[dict[str, Any]] | None = None
    notes: str | None = None
    valid_until: datetime | None = None


class ControlAssessmentRefresh(BaseModel):
    agent_version_id: UUID | None = None


class ReviewCreate(BaseModel):
    ai_system_id: UUID
    review_type: str = Field(..., min_length=1)
    agent_version_id: UUID | None = None
    due_at: datetime | None = None
    status: str = "REQUESTED"


class ReviewDecide(BaseModel):
    decision: str = Field(..., min_length=1)
    decision_reason: str = Field(..., min_length=1)
    conditions: list[Any] | dict[str, Any] | None = None


class ReviewerAssignment(BaseModel):
    reviewer_user_id: str = Field(..., min_length=1)
    membership_id: UUID | None = None
    role: str | None = None


class ReviewAssign(BaseModel):
    reviewers: list[ReviewerAssignment] = Field(..., min_length=1)


class PeriodicScheduleCreate(BaseModel):
    ai_system_id: UUID
    frequency_days: int | None = None


class AttestationCreate(BaseModel):
    attestation_type: str = Field(..., min_length=1)
    statement: str = Field(..., min_length=1)
    ai_system_id: UUID | None = None
    agent_version_id: UUID | None = None
    actor_role: str | None = None
    scope: dict[str, Any] | None = None
    evidence_refs: list[dict[str, Any]] | None = None
    valid_until: datetime | None = None


class ExceptionCreate(BaseModel):
    ai_system_id: UUID
    business_justification: str = Field(..., min_length=1)
    control_requirement_id: UUID | None = None
    agent_version_id: UUID | None = None
    scope: dict[str, Any] | None = None
    risk: str | None = None
    compensating_controls: list[Any] | dict[str, Any] | None = None
    evidence_refs: list[dict[str, Any]] | None = None
    valid_until: datetime | None = None


class ExceptionDecision(BaseModel):
    decision_reason: str = Field(..., min_length=1)
    valid_until: datetime | None = None


class ExceptionRevoke(BaseModel):
    decision_reason: str | None = None


class IncidentCreate(BaseModel):
    ai_system_id: UUID
    title: str = Field(..., min_length=1)
    severity: str = "MEDIUM"
    category: str = "OTHER"
    description: str | None = None
    source: str = "MANUAL"
    source_ref: str | None = None
    agent_version_id: UUID | None = None
    runtime_identity_id: UUID | None = None
    trajectory_id: UUID | None = None
    incident_manager: str | None = None
    evidence_refs: list[dict[str, Any]] | None = None


class IncidentTransition(BaseModel):
    to_status: str = Field(..., min_length=1)
    reason: str | None = None
    metadata: dict[str, Any] | None = None


class IncidentContain(BaseModel):
    containment_action: str = Field(..., min_length=1)
    containment_ref: dict[str, Any] | list[Any] | None = None
    reason: str | None = None


class CorrectiveActionCreate(BaseModel):
    description: str = Field(..., min_length=1)
    owner: str = Field(..., min_length=1)
    due_at: datetime | None = None


class CorrectiveActionPatch(BaseModel):
    status: str | None = None
    evidence: dict[str, Any] | list[Any] | None = None
    description: str | None = None
    due_at: datetime | None = None


class EvidencePackageCreate(BaseModel):
    ai_system_id: UUID | None = None
    agent_id: UUID | None = None
    agent_version_id: UUID | None = None
    review_id: UUID | None = None
    incident_id: UUID | None = None
    period_start: datetime | None = None
    period_end: datetime | None = None
    include_html: bool = True


class PilotCreate(BaseModel):
    name: str = Field(..., min_length=1)
    description: str | None = None
    sponsor: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    success_criteria: dict[str, Any] | list[Any] | None = None
    status: str = "PLANNING"


class PilotAISystemAdd(BaseModel):
    ai_system_id: UUID
    agent_version_id: UUID | None = None


class PilotTransition(BaseModel):
    to_status: str = Field(..., min_length=1)
    readiness_evaluation_id: UUID | None = None


class PilotReadinessEvaluate(BaseModel):
    ai_system_id: UUID
    agent_version_id: UUID | None = None
    pilot_id: UUID | None = None


def _serialize_readiness(row: PilotReadinessEvaluation) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "pilot_id": str(row.pilot_id) if row.pilot_id else None,
        "ai_system_id": str(row.ai_system_id) if row.ai_system_id else None,
        "agent_version_id": str(row.agent_version_id) if row.agent_version_id else None,
        "decision": row.decision,
        "dimensions": row.dimensions,
        "gaps": row.gaps,
        "conditions": row.conditions,
        "evaluated_by": row.evaluated_by,
        "evaluated_at": row.evaluated_at.isoformat() if row.evaluated_at else None,
    }


# --- Organizations --------------------------------------------------------


@router.get("/organization/governance-profile")
def get_governance_profile(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: GovernanceService = Depends(_svc),
):
    """Get governance profile. Validates membership for tenant users."""
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _require_active_membership(db, principal.user_id)
    try:
        return svc.get_governance_profile()
    except GovernanceError as exc:
        raise _handle(exc) from exc


@router.patch("/organization/governance-profile")
def patch_governance_profile(
    payload: GovernanceProfilePatch,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: GovernanceService = Depends(_svc),
):
    """Patch governance profile. Validates organization admin membership for tenant users."""
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        membership = _require_active_membership(db, principal.user_id)
        # Tenant users must be organization admin to patch profile
        from rai_gateway.governance.domain import GovernanceRole

        if membership.role != GovernanceRole.ORGANIZATION_ADMIN.value:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "NOT_ALLOWED",
                    "message": "Organization admin role required",
                },
            )
    try:
        return svc.patch_governance_profile(
            updated_by=_actor(principal), **payload.model_dump(exclude_unset=True)
        )
    except GovernanceError as exc:
        raise _handle(exc) from exc


@router.post("/organization/memberships")
def create_membership(
    payload: MembershipCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: GovernanceService = Depends(_svc),
):
    """Create membership. Validates organization admin for tenant users."""
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        membership = _require_active_membership(db, principal.user_id)
        from rai_gateway.governance.domain import GovernanceRole

        if membership.role != GovernanceRole.ORGANIZATION_ADMIN.value:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "NOT_ALLOWED",
                    "message": "Organization admin role required",
                },
            )
    try:
        return svc.create_membership(
            **payload.model_dump(), created_by=_actor(principal)
        )
    except GovernanceError as exc:
        raise _handle(exc) from exc


@router.get("/organization/memberships")
def list_memberships(
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: GovernanceService = Depends(_svc),
):
    """List memberships. Validates membership for tenant users."""
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _require_active_membership(db, principal.user_id)
    try:
        items = svc.list_memberships(status=status, limit=limit, offset=offset)
        return {"items": items, "limit": limit, "offset": offset}
    except GovernanceError as exc:
        raise _handle(exc) from exc


@router.get("/organization/departments")
def list_current_organization_departments(
    tenant: TenantContext = Depends(require_organization_member),
    svc: GovernanceService = Depends(_svc),
):
    """List departments for the caller's active organization, seeding defaults once."""
    try:
        items = svc.list_departments()
        return {
            "items": items,
        }
    except GovernanceError as exc:
        raise _handle(exc) from exc


@router.get("/organization/members")
def list_current_organization_members(
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
    tenant: TenantContext = Depends(require_organization_member),
    svc: GovernanceService = Depends(_svc),
):
    """List members of the caller's active organization only."""
    try:
        items = svc.list_memberships(status=status, limit=limit, offset=offset)
        return {
            "items": items,
            "limit": limit,
            "offset": offset,
        }
    except GovernanceError as exc:
        raise _handle(exc) from exc


@router.post("/organization/members/invite")
def invite_current_organization_member(
    payload: MemberInvite,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_organization_member),
):
    """Invite a teammate into the caller's active organization only."""
    if not tenant.has_role(GovernanceRole.ORGANIZATION_ADMIN.value):
        raise RaiException(
            error_code=ErrorCode.NOT_ALLOWED, message="Organization admin role required"
        )
    if payload.role.strip().lower() in PLATFORM_ROLES:
        raise RaiException(
            error_code=ErrorCode.NOT_ALLOWED,
            message="Platform roles cannot be assigned from the organization team",
        )
    try:
        return GovernanceService(db).invite_member(
            email=payload.email,
            full_name=payload.full_name,
            role=payload.role,
            created_by=tenant.user_id,
            department_id=payload.department_id,
        )
    except GovernanceError as exc:
        raise _handle(exc) from exc


def _require_org_admin(tenant: TenantContext) -> None:
    if not tenant.has_role(GovernanceRole.ORGANIZATION_ADMIN.value):
        raise RaiException(
            error_code=ErrorCode.NOT_ALLOWED, message="Organization admin role required"
        )


@router.patch("/organization/members/{membership_id}")
def update_current_organization_member(
    membership_id: UUID,
    payload: MemberUpdate,
    tenant: TenantContext = Depends(require_organization_member),
    svc: GovernanceService = Depends(_svc),
):
    """Update a membership role or status inside the active organization."""
    _require_org_admin(tenant)
    if payload.role is None and payload.status is None:
        raise RaiException(
            error_code=ErrorCode.INVALID_REQUEST,
            message="Provide a role or status to update",
        )
    if payload.role and payload.role.strip().lower() in PLATFORM_ROLES:
        raise RaiException(
            error_code=ErrorCode.NOT_ALLOWED,
            message="Platform roles cannot be assigned from the organization team",
        )
    try:
        updated = svc.update_membership(
            membership_id, role=payload.role, status=payload.status
        )
    except GovernanceError as exc:
        raise _handle(exc) from exc
    return updated


@router.delete("/organization/members/{membership_id}")
def delete_current_organization_membership(
    membership_id: UUID,
    tenant: TenantContext = Depends(require_organization_member),
    svc: GovernanceService = Depends(_svc),
):
    """Remove one role membership from the active organization."""
    _require_org_admin(tenant)
    try:
        return svc.delete_membership(membership_id)
    except GovernanceError as exc:
        raise _handle(exc) from exc


@router.delete("/organization/people/{user_id}")
def remove_current_organization_person(
    user_id: str,
    tenant: TenantContext = Depends(require_organization_member),
    svc: GovernanceService = Depends(_svc),
):
    """Remove a person and their roles from the active organization only."""
    _require_org_admin(tenant)
    try:
        return svc.remove_organization_member(user_id)
    except GovernanceError as exc:
        raise _handle(exc) from exc


@router.post("/ai-systems/{ai_system_id}/link")
def link_ai_system(
    ai_system_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: GovernanceService = Depends(_svc),
):
    """Link AI system to organization. Validates org admin for tenant users."""
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        membership = _require_active_membership(db, principal.user_id)
        from rai_gateway.governance.domain import GovernanceRole

        if membership.role != GovernanceRole.ORGANIZATION_ADMIN.value:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "NOT_ALLOWED",
                    "message": "Organization admin role required",
                },
            )
    try:
        return svc.link_ai_system(ai_system_id, _actor(principal))
    except GovernanceError as exc:
        raise _handle(exc) from exc


# --- Accountability / classification --------------------------------------


@router.get("/ai-systems/{ai_system_id}/accountability")
def get_accountability(
    ai_system_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: GovernanceService = Depends(_svc),
):
    """Get accountability. Validates membership for tenant users."""
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _require_active_membership(db, principal.user_id)
    try:
        return svc.get_accountability(ai_system_id)
    except GovernanceError as exc:
        raise _handle(exc) from exc


@router.post("/ai-systems/{ai_system_id}/accountability")
def upsert_accountability(
    ai_system_id: UUID,
    payload: AccountabilityUpsert,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: GovernanceService = Depends(_svc),
):
    """Upsert accountability. Validates org admin for tenant users."""
    data = payload.model_dump()

    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        membership = _require_active_membership(db, principal.user_id)
        from rai_gateway.governance.domain import GovernanceRole

        if membership.role != GovernanceRole.ORGANIZATION_ADMIN.value:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "NOT_ALLOWED",
                    "message": "Organization admin role required",
                },
            )
    try:
        return svc.upsert_accountability(
            ai_system_id, created_by=_actor(principal), **data
        )
    except GovernanceError as exc:
        raise _handle(exc) from exc


@router.get("/ai-systems/{ai_system_id}/governance-classification")
def get_classification(
    ai_system_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: GovernanceService = Depends(_svc),
):
    """Get classification. Validates membership for tenant users."""
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _require_active_membership(db, principal.user_id)
    try:
        return svc.get_classification(ai_system_id)
    except GovernanceError as exc:
        raise _handle(exc) from exc


@router.put("/ai-systems/{ai_system_id}/governance-classification")
def upsert_classification(
    ai_system_id: UUID,
    payload: ClassificationUpsert,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: GovernanceService = Depends(_svc),
):
    """Upsert classification. Validates org admin for tenant users."""
    data = payload.model_dump(exclude_unset=True)

    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        membership = _require_active_membership(db, principal.user_id)
        from rai_gateway.governance.domain import GovernanceRole

        if membership.role != GovernanceRole.ORGANIZATION_ADMIN.value:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "NOT_ALLOWED",
                    "message": "Organization admin role required",
                },
            )
    try:
        return svc.upsert_classification(
            ai_system_id, updated_by=_actor(principal), **data
        )
    except GovernanceError as exc:
        raise _handle(exc) from exc


# --- Controls -------------------------------------------------------------


@router.get("/control-frameworks")
def list_control_frameworks(
    limit: int = 50,
    offset: int = 0,
    principal: Principal = Depends(require_user),
    svc: GovernanceService = Depends(_svc),
):
    """List control frameworks. Available to all authenticated users."""
    items = svc.list_frameworks(limit=limit, offset=offset)
    return {"items": items, "limit": limit, "offset": offset}


@router.post("/control-frameworks/ensure-pilot")
def ensure_pilot_framework(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_platform_permission("control:manage")),
    svc: GovernanceService = Depends(_svc),
):
    """Platform-only: Ensure pilot control framework exists."""
    try:
        ensure_pilot_control_framework(db, created_by=_actor(principal))
        frameworks = svc.list_frameworks(limit=100)
        pilot = next(
            (f for f in frameworks if f.get("framework_key") == "rai-pilot-v1"),
            frameworks[0] if frameworks else None,
        )
        if pilot is None:
            raise GovernanceNotFoundError(
                "Pilot control framework not found after seed"
            )
        return pilot
    except GovernanceError as exc:
        raise _handle(exc) from exc


@router.get("/ai-systems/{ai_system_id}/control-assessments")
def list_control_assessments(
    ai_system_id: UUID,
    agent_version_id: UUID | None = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: GovernanceService = Depends(_svc),
):
    """List control assessments. Validates membership for tenant users."""
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _require_active_membership(db, principal.user_id)
    try:
        items = svc.list_assessments(
            ai_system_id, agent_version_id=agent_version_id, limit=limit, offset=offset
        )
        return {"items": items, "limit": limit, "offset": offset}
    except GovernanceError as exc:
        raise _handle(exc) from exc


@router.post("/ai-systems/{ai_system_id}/control-assessments/refresh")
def refresh_control_assessments(
    ai_system_id: UUID,
    payload: ControlAssessmentRefresh,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: GovernanceService = Depends(_svc),
):
    """Refresh control assessments. Validates membership for tenant users."""
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _require_active_membership(db, principal.user_id)
    try:
        items = svc.refresh_automated_assessments(
            ai_system_id, payload.agent_version_id
        )
        return {"items": items}
    except GovernanceError as exc:
        raise _handle(exc) from exc


@router.post("/ai-systems/{ai_system_id}/control-assessments")
def create_control_assessment(
    ai_system_id: UUID,
    payload: ControlAssessmentCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: GovernanceService = Depends(_svc),
):
    """Create control assessment. Validates membership for tenant users."""
    data = payload.model_dump()

    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _require_active_membership(db, principal.user_id)
    try:
        return svc.record_manual_assessment(
            ai_system_id, assessed_by=_actor(principal), **data
        )
    except GovernanceError as exc:
        raise _handle(exc) from exc


# --- Reviews --------------------------------------------------------------


@router.get("/governance-reviews")
def list_reviews(
    ai_system_id: UUID | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: GovernanceService = Depends(_svc),
):
    """List governance reviews. Validates membership for tenant users."""
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _require_active_membership(db, principal.user_id)
    try:
        items = svc.list_reviews(
            ai_system_id=ai_system_id, status=status, limit=limit, offset=offset
        )
        return {"items": items, "limit": limit, "offset": offset}
    except GovernanceError as exc:
        raise _handle(exc) from exc


@router.post("/governance-reviews")
def create_review(
    payload: ReviewCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: GovernanceService = Depends(_svc),
):
    """Create governance review. Validates membership for tenant users."""
    data = payload.model_dump()
    ai_system_id = data.pop("ai_system_id")

    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _require_active_membership(db, principal.user_id)
    try:
        return svc.create_review(ai_system_id, created_by=_actor(principal), **data)
    except GovernanceError as exc:
        raise _handle(exc) from exc


@router.get("/governance-reviews/{review_id}")
def get_review(
    review_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: GovernanceService = Depends(_svc),
):
    """Get governance review. Validates an active membership for tenant users."""
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _require_active_membership(db, principal.user_id)
    try:
        return svc.get_review(review_id)
    except GovernanceError as exc:
        raise _handle(exc) from exc


@router.post("/governance-reviews/{review_id}/decide")
def decide_review(
    review_id: UUID,
    payload: ReviewDecide,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: GovernanceService = Depends(_svc),
):
    """Decide governance review. Validates membership for tenant users."""
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _require_active_membership(db, principal.user_id)
    try:
        return svc.decide_review(
            review_id,
            decision=payload.decision,
            decision_reason=payload.decision_reason,
            decided_by=_actor(principal),
            conditions=payload.conditions,
        )
    except GovernanceError as exc:
        raise _handle(exc) from exc


@router.post("/governance-reviews/{review_id}/assign")
def assign_review(
    review_id: UUID,
    payload: ReviewAssign,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: GovernanceService = Depends(_svc),
):
    """Assign reviewers. Validates membership for tenant users."""
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _require_active_membership(db, principal.user_id)
    try:
        return {
            "items": svc.assign_reviewers(
                review_id, reviewers=[r.model_dump() for r in payload.reviewers]
            )
        }
    except GovernanceError as exc:
        raise _handle(exc) from exc


@router.post("/periodic-review-schedules")
def create_periodic_schedule(
    payload: PeriodicScheduleCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: GovernanceService = Depends(_svc),
):
    """Create periodic review schedule. Validates membership for tenant users."""
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _require_active_membership(db, principal.user_id)
    try:
        return svc.ensure_periodic_schedule(
            payload.ai_system_id,
            created_by=_actor(principal),
            frequency_days=payload.frequency_days,
        )
    except GovernanceError as exc:
        raise _handle(exc) from exc


@router.post("/periodic-reviews/process-due")
def process_due_periodic_reviews(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: GovernanceService = Depends(_svc),
):
    """Process due periodic reviews. Validates membership for tenant users."""
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _require_active_membership(db, principal.user_id)
    try:
        items = svc.process_due_periodic_reviews()
        return {"items": items}
    except GovernanceError as exc:
        raise _handle(exc) from exc


# --- Attestations ---------------------------------------------------------


@router.get("/governance-attestations")
def list_attestations(
    ai_system_id: UUID | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: GovernanceService = Depends(_svc),
):
    """List attestations. Validates an active membership for tenant users."""
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _require_active_membership(db, principal.user_id)
    items = svc.list_attestations(ai_system_id=ai_system_id, limit=limit, offset=offset)
    return {"items": items, "limit": limit, "offset": offset}


@router.post("/governance-attestations")
def create_attestation(
    payload: AttestationCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: GovernanceService = Depends(_svc),
):
    """Create attestation. Validates membership for tenant users."""
    data = payload.model_dump()

    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _require_active_membership(db, principal.user_id)
    try:
        return svc.create_attestation(actor=_actor(principal), **data)
    except GovernanceError as exc:
        raise _handle(exc) from exc


# --- Exceptions -----------------------------------------------------------


@router.get("/governance-exceptions")
def list_exceptions(
    ai_system_id: UUID | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: GovernanceService = Depends(_svc),
):
    """List exceptions. Validates an active membership for tenant users."""
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _require_active_membership(db, principal.user_id)
    items = svc.list_exceptions(
        ai_system_id=ai_system_id, status=status, limit=limit, offset=offset
    )
    return {"items": items, "limit": limit, "offset": offset}


@router.post("/governance-exceptions")
def request_exception(
    payload: ExceptionCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: GovernanceService = Depends(_svc),
):
    """Request exception. Validates membership for tenant users."""
    data = payload.model_dump()
    ai_system_id = data.pop("ai_system_id")

    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _require_active_membership(db, principal.user_id)
    try:
        return svc.request_exception(ai_system_id, requester=_actor(principal), **data)
    except GovernanceError as exc:
        raise _handle(exc) from exc


@router.get("/governance-exceptions/{exception_id}")
def get_exception(
    exception_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: GovernanceService = Depends(_svc),
):
    """Get exception. Validates an active membership for tenant users."""
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _require_active_membership(db, principal.user_id)
    try:
        return svc.get_exception(exception_id)
    except GovernanceError as exc:
        raise _handle(exc) from exc


@router.post("/governance-exceptions/{exception_id}/approve")
def approve_exception(
    exception_id: UUID,
    payload: ExceptionDecision,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: GovernanceService = Depends(_svc),
):
    """Approve exception. Validates membership for tenant users."""
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _require_active_membership(db, principal.user_id)
    try:
        return svc.approve_exception(
            exception_id,
            approver=_actor(principal),
            decision_reason=payload.decision_reason,
            valid_until=payload.valid_until,
        )
    except GovernanceError as exc:
        raise _handle(exc) from exc


@router.post("/governance-exceptions/{exception_id}/reject")
def reject_exception(
    exception_id: UUID,
    payload: ExceptionDecision,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: GovernanceService = Depends(_svc),
):
    """Reject exception. Validates membership for tenant users."""
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _require_active_membership(db, principal.user_id)
    try:
        return svc.reject_exception(
            exception_id,
            approver=_actor(principal),
            decision_reason=payload.decision_reason,
        )
    except GovernanceError as exc:
        raise _handle(exc) from exc


@router.post("/governance-exceptions/{exception_id}/revoke")
def revoke_exception(
    exception_id: UUID,
    payload: ExceptionRevoke,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: GovernanceService = Depends(_svc),
):
    """Revoke exception. Validates membership for tenant users."""
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _require_active_membership(db, principal.user_id)
    try:
        return svc.revoke_exception(
            exception_id,
            actor=_actor(principal),
            decision_reason=payload.decision_reason,
        )
    except GovernanceError as exc:
        raise _handle(exc) from exc


@router.post("/governance-exceptions/expire")
def expire_exceptions(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: GovernanceService = Depends(_svc),
):
    """Expire exceptions. Validates membership for tenant users."""
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _require_active_membership(db, principal.user_id)
    try:
        items = svc.expire_exceptions()
        return {"items": items}
    except GovernanceError as exc:
        raise _handle(exc) from exc


# --- Incidents ------------------------------------------------------------


@router.get("/incidents")
def list_incidents(
    ai_system_id: UUID | None = None,
    status: str | None = None,
    severity: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: GovernanceService = Depends(_svc),
):
    """List incidents. Validates an active membership for tenant users."""
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _require_active_membership(db, principal.user_id)
    items = svc.list_incidents(
        ai_system_id=ai_system_id,
        status=status,
        severity=severity,
        limit=limit,
        offset=offset,
    )
    return {"items": items, "limit": limit, "offset": offset}


@router.post("/incidents")
def create_incident(
    payload: IncidentCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: GovernanceService = Depends(_svc),
):
    """Create incident. Validates membership for tenant users."""
    data = payload.model_dump()
    ai_system_id = data.pop("ai_system_id")

    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _require_active_membership(db, principal.user_id)
    try:
        return svc.create_incident(ai_system_id, reported_by=_actor(principal), **data)
    except GovernanceError as exc:
        raise _handle(exc) from exc


@router.get("/incidents/{incident_id}")
def get_incident(
    incident_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: GovernanceService = Depends(_svc),
):
    """Get incident. Validates an active membership for tenant users."""
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _require_active_membership(db, principal.user_id)
    try:
        return svc.get_incident(incident_id)
    except GovernanceError as exc:
        raise _handle(exc) from exc


@router.post("/incidents/{incident_id}/transition")
def transition_incident(
    incident_id: UUID,
    payload: IncidentTransition,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: GovernanceService = Depends(_svc),
):
    """Transition incident. Validates membership for tenant users."""
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _require_active_membership(db, principal.user_id)
    try:
        return svc.transition_incident(
            incident_id,
            to_status=payload.to_status,
            actor=_actor(principal),
            reason=payload.reason,
            metadata=payload.metadata,
        )
    except GovernanceError as exc:
        raise _handle(exc) from exc


@router.post("/incidents/{incident_id}/contain")
def contain_incident(
    incident_id: UUID,
    payload: IncidentContain,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: GovernanceService = Depends(_svc),
):
    """Contain incident. Validates membership for tenant users."""
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _require_active_membership(db, principal.user_id)
    try:
        return svc.contain_incident(
            incident_id,
            actor=_actor(principal),
            containment_action=payload.containment_action,
            containment_ref=payload.containment_ref,
            reason=payload.reason,
        )
    except GovernanceError as exc:
        raise _handle(exc) from exc


@router.post("/incidents/{incident_id}/corrective-actions")
def add_corrective_action(
    incident_id: UUID,
    payload: CorrectiveActionCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: GovernanceService = Depends(_svc),
):
    """Add corrective action. Validates membership for tenant users."""
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _require_active_membership(db, principal.user_id)
    try:
        return svc.add_corrective_action(
            incident_id,
            description=payload.description,
            owner=payload.owner,
            due_at=payload.due_at,
        )
    except GovernanceError as exc:
        raise _handle(exc) from exc


@router.patch("/corrective-actions/{action_id}")
def update_corrective_action(
    action_id: UUID,
    payload: CorrectiveActionPatch,
    principal: Principal = Depends(require_user),
    svc: GovernanceService = Depends(_svc),
):
    """Update corrective action. Validates ownership via service layer."""
    try:
        return svc.update_corrective_action(
            action_id, **payload.model_dump(exclude_unset=True)
        )
    except GovernanceError as exc:
        raise _handle(exc) from exc


# --- Evidence packages ----------------------------------------------------


@router.post("/evidence-packages")
def create_evidence_package(
    payload: EvidencePackageCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: GovernanceService = Depends(_svc),
):
    """Create evidence package. Validates membership for tenant users."""
    data = payload.model_dump()

    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _require_active_membership(db, principal.user_id)
    try:
        return svc.generate_evidence_package(generated_by=_actor(principal), **data)
    except GovernanceError as exc:
        raise _handle(exc) from exc


@router.get("/evidence-packages")
def list_evidence_packages(
    ai_system_id: UUID | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: GovernanceService = Depends(_svc),
):
    """List evidence packages. Validates an active membership for tenant users."""
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _require_active_membership(db, principal.user_id)
    items = svc.list_evidence_packages(
        ai_system_id=ai_system_id, limit=limit, offset=offset
    )
    return {"items": items, "limit": limit, "offset": offset}


@router.get("/evidence-packages/{package_id}")
def get_evidence_package(
    package_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: GovernanceService = Depends(_svc),
):
    """Get evidence package. Validates an active membership for tenant users."""
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _require_active_membership(db, principal.user_id)
    try:
        return svc.get_evidence_package(package_id)
    except GovernanceError as exc:
        raise _handle(exc) from exc


# --- Pilots / readiness ---------------------------------------------------


@router.get("/pilots")
def list_pilots(
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: GovernanceService = Depends(_svc),
):
    """List pilots. Validates membership for tenant users."""
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _require_active_membership(db, principal.user_id)
    try:
        items = svc.list_pilots(limit=limit, offset=offset)
        return {"items": items, "limit": limit, "offset": offset}
    except GovernanceError as exc:
        raise _handle(exc) from exc


@router.post("/pilots")
def create_pilot(
    payload: PilotCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: GovernanceService = Depends(_svc),
):
    """Create pilot. Validates membership for tenant users."""
    data = payload.model_dump()

    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _require_active_membership(db, principal.user_id)
    try:
        return svc.create_pilot(created_by=_actor(principal), **data)
    except GovernanceError as exc:
        raise _handle(exc) from exc


@router.get("/pilots/{pilot_id}")
def get_pilot(
    pilot_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: GovernanceService = Depends(_svc),
):
    """Get pilot. Validates an active membership for tenant users."""
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _require_active_membership(db, principal.user_id)
    try:
        return svc.get_pilot(pilot_id)
    except GovernanceError as exc:
        raise _handle(exc) from exc


@router.post("/pilots/{pilot_id}/ai-systems")
def add_pilot_ai_system(
    pilot_id: UUID,
    payload: PilotAISystemAdd,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: GovernanceService = Depends(_svc),
):
    """Add AI system to pilot. Validates membership for tenant users."""
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _require_active_membership(db, principal.user_id)
    try:
        return svc.add_ai_system_to_pilot(
            pilot_id, payload.ai_system_id, agent_version_id=payload.agent_version_id
        )
    except GovernanceError as exc:
        raise _handle(exc) from exc


@router.post("/pilots/{pilot_id}/transition")
def transition_pilot(
    pilot_id: UUID,
    payload: PilotTransition,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: GovernanceService = Depends(_svc),
):
    """Transition pilot. Validates membership for tenant users."""
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _require_active_membership(db, principal.user_id)
    try:
        return svc.transition_pilot_status(
            pilot_id,
            to_status=payload.to_status,
            actor=_actor(principal),
            readiness_evaluation_id=payload.readiness_evaluation_id,
        )
    except GovernanceError as exc:
        raise _handle(exc) from exc


@router.get("/pilot-readiness")
def get_pilot_readiness(
    ai_system_id: UUID,
    agent_version_id: UUID | None = None,
    pilot_id: UUID | None = None,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
):
    """Get pilot readiness. Validates membership for tenant users."""
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _require_active_membership(db, principal.user_id)
    q = db.query(PilotReadinessEvaluation).filter(
        PilotReadinessEvaluation.ai_system_id == ai_system_id
    )
    if agent_version_id is not None:
        q = q.filter(PilotReadinessEvaluation.agent_version_id == agent_version_id)
    if pilot_id is not None:
        q = q.filter(PilotReadinessEvaluation.pilot_id == pilot_id)
    row = q.order_by(PilotReadinessEvaluation.evaluated_at.desc()).first()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "GOVERNANCE_NOT_FOUND",
                "message": "Pilot readiness evaluation not found",
            },
        )
    return _serialize_readiness(row)


@router.post("/pilot-readiness/evaluate")
def evaluate_pilot_readiness_endpoint(
    payload: PilotReadinessEvaluate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: GovernanceService = Depends(_svc),
):
    """Evaluate pilot readiness. Validates membership for tenant users."""
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _require_active_membership(db, principal.user_id)
    try:
        return svc.evaluate_readiness(
            ai_system_id=payload.ai_system_id,
            evaluated_by=_actor(principal),
            agent_version_id=payload.agent_version_id,
            pilot_id=payload.pilot_id,
        )
    except GovernanceError as exc:
        raise _handle(exc) from exc


@router.get("/pilots/{pilot_id}/dashboard")
def get_pilot_dashboard(
    pilot_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: GovernanceService = Depends(_svc),
):
    """Get pilot dashboard. Validates an active membership for tenant users."""
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _require_active_membership(db, principal.user_id)
    try:
        return svc.get_pilot_dashboard(pilot_id=pilot_id)
    except GovernanceError as exc:
        raise _handle(exc) from exc


@router.get("/pilot-dashboard")
def get_organization_pilot_dashboard(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: GovernanceService = Depends(_svc),
):
    """Get organization pilot dashboard. Validates membership for tenant users."""
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _require_active_membership(db, principal.user_id)
    try:
        return svc.get_pilot_dashboard()
    except GovernanceError as exc:
        raise _handle(exc) from exc


@router.get("/due-work")
def list_due_work(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
    svc: GovernanceService = Depends(_svc),
):
    """List due work. Validates membership for tenant users."""
    is_platform = any(principal.has_platform_role(role) for role in PLATFORM_ROLES)
    if not is_platform:
        _require_active_membership(db, principal.user_id)
    try:
        return svc.list_due_work()
    except GovernanceError as exc:
        raise _handle(exc) from exc


# --- Seed -----------------------------------------------------------------


@router.post("/governance/seed-reference-pilots")
def seed_reference_pilots_endpoint(
    db: Session = Depends(get_db),
    _principal: Principal = Depends(require_platform_permission("platform:admin")),
):
    """Seed reference pilots. Disabled unless ENABLE_REFERENCE_PILOT_SEED=true."""
    if not settings.enable_reference_pilot_seed:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        return seed_reference_pilots(db)
    except GovernanceError as exc:
        raise _handle(exc) from exc
