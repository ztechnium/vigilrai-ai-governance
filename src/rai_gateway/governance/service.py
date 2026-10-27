"""WP8 Governance / Pilot operating model service."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from rai_gateway.core.observability import log_siem_event
from rai_gateway.governance.controls import (
    automated_assess,
    ensure_pilot_control_framework,
)
from rai_gateway.governance.domain import (
    INCOMPATIBLE_ACCOUNTABILITY_PAIRS,
    AssessmentMethod,
    CorrectiveActionStatus,
    EvidenceAvailability,
    ExceptionStatus,
    GovernanceRole,
    IncidentSeverity,
    IncidentStatus,
    MembershipStatus,
    PilotOrgStatus,
    PilotReadinessDecision,
    ReviewDecision,
    ReviewStatus,
    ReviewType,
)
from rai_gateway.governance.errors import (
    GovernanceConflictError,
    GovernanceDeniedError,
    GovernanceNotFoundError,
    SeparationOfDutiesError,
    TenantIsolationError,
)
from rai_gateway.governance.readiness import evaluate_pilot_readiness
from rai_gateway.models.governance import (
    AIIncident,
    AISystemAccountability,
    AISystemGovernanceClassification,
    ControlAssessment,
    ControlFramework,
    ControlObjective,
    ControlRequirement,
    Department,
    GovernanceAttestation,
    GovernanceEvidencePackage,
    GovernanceException,
    GovernanceReview,
    GovernanceReviewAssignment,
    IncidentCorrectiveAction,
    IncidentTransition,
    OrganizationGovernanceProfile,
    OrganizationMembership,
    PeriodicReviewSchedule,
    Pilot,
    PilotAISystem,
    PilotReadinessEvaluation,
)
from rai_gateway.models.registry import AISystem

_INCIDENT_TRANSITIONS: dict[str, frozenset[str]] = {
    IncidentStatus.OPEN.value: frozenset(
        {
            IncidentStatus.TRIAGED.value,
            IncidentStatus.CONTAINED.value,
            IncidentStatus.INVESTIGATING.value,
            IncidentStatus.CLOSED.value,
        }
    ),
    IncidentStatus.TRIAGED.value: frozenset(
        {
            IncidentStatus.CONTAINED.value,
            IncidentStatus.INVESTIGATING.value,
            IncidentStatus.REMEDIATING.value,
        }
    ),
    IncidentStatus.CONTAINED.value: frozenset(
        {
            IncidentStatus.INVESTIGATING.value,
            IncidentStatus.REMEDIATING.value,
            IncidentStatus.RESOLVED.value,
        }
    ),
    IncidentStatus.INVESTIGATING.value: frozenset(
        {
            IncidentStatus.CONTAINED.value,
            IncidentStatus.REMEDIATING.value,
            IncidentStatus.RESOLVED.value,
        }
    ),
    IncidentStatus.REMEDIATING.value: frozenset(
        {
            IncidentStatus.RESOLVED.value,
            IncidentStatus.INVESTIGATING.value,
        }
    ),
    IncidentStatus.RESOLVED.value: frozenset({IncidentStatus.CLOSED.value}),
    IncidentStatus.CLOSED.value: frozenset(),
}

_PILOT_TRANSITIONS: dict[str, frozenset[str]] = {
    PilotOrgStatus.PLANNING.value: frozenset(
        {
            PilotOrgStatus.CONFIGURING.value,
            PilotOrgStatus.READINESS_REVIEW.value,
            PilotOrgStatus.CANCELLED.value,
        }
    ),
    PilotOrgStatus.CONFIGURING.value: frozenset(
        {
            PilotOrgStatus.READINESS_REVIEW.value,
            PilotOrgStatus.PLANNING.value,
            PilotOrgStatus.CANCELLED.value,
        }
    ),
    PilotOrgStatus.READINESS_REVIEW.value: frozenset(
        {
            PilotOrgStatus.READY.value,
            PilotOrgStatus.CONFIGURING.value,
            PilotOrgStatus.CANCELLED.value,
        }
    ),
    PilotOrgStatus.READY.value: frozenset(
        {
            PilotOrgStatus.ACTIVE.value,
            PilotOrgStatus.PAUSED.value,
            PilotOrgStatus.CANCELLED.value,
        }
    ),
    PilotOrgStatus.ACTIVE.value: frozenset(
        {
            PilotOrgStatus.PAUSED.value,
            PilotOrgStatus.COMPLETED.value,
            PilotOrgStatus.CANCELLED.value,
        }
    ),
    PilotOrgStatus.PAUSED.value: frozenset(
        {
            PilotOrgStatus.ACTIVE.value,
            PilotOrgStatus.COMPLETED.value,
            PilotOrgStatus.CANCELLED.value,
        }
    ),
    PilotOrgStatus.COMPLETED.value: frozenset(),
    PilotOrgStatus.CANCELLED.value: frozenset(),
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ser_dt(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _digest(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class GovernanceService:
    """Authoritative WP8 governance / pilot operating-model orchestration."""

    def __init__(self, db: Session) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Organizations
    # ------------------------------------------------------------------

    def get_governance_profile(self) -> dict[str, Any]:
        profile = self._get_profile()
        if profile is None:
            raise GovernanceNotFoundError("Governance profile not found")
        return self._serialize_profile(profile)

    def patch_governance_profile(
        self, *, updated_by: str, **fields: Any
    ) -> dict[str, Any]:
        profile = self._get_profile()
        if profile is None:
            raise GovernanceNotFoundError("Governance profile not found")
        allowed = {
            "name",
            "description",
            "logo",
            "legal_name",
            "organization_type",
            "sector",
            "jurisdiction",
            "regulatory_context",
            "risk_appetite",
            "governance_owner",
            "assurance_owner",
            "incident_owner",
            "default_review_frequency_days",
            "evidence_retention_policy",
            "pilot_status",
        }
        for key, value in fields.items():
            if key in allowed and value is not None:
                setattr(profile, key, value)
        profile.updated_by = updated_by
        self._db.commit()
        self._db.refresh(profile)
        return self._serialize_profile(profile)

    def create_membership(
        self,
        *,
        user_id: str,
        role: str,
        created_by: str,
        status: str = MembershipStatus.ACTIVE.value,
        valid_until: datetime | None = None,
        department_id: UUID | None = None,
    ) -> dict[str, Any]:
        if role not in {r.value for r in GovernanceRole}:
            raise GovernanceConflictError(f"Unknown governance role: {role}")
        if department_id is not None:
            from rai_gateway.governance.departments import require_department

            require_department(self._db, department_id)
        existing = (
            self._db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.user_id == user_id,
                OrganizationMembership.role == role,
            )
            .first()
        )
        if existing:
            existing.status = status
            existing.valid_until = valid_until
            membership = existing
        else:
            membership = OrganizationMembership(
                user_id=user_id,
                role=role,
                status=status,
                created_by=created_by,
                valid_until=valid_until,
            )
            self._db.add(membership)
            self._db.flush()
        if department_id is not None:
            self._assign_user_department(user_id, department_id)
        self._db.commit()
        self._db.refresh(membership)
        return self._serialize_membership(
            membership,
            self._lookup_user(membership.user_id),
            self._department_for(membership),
        )

    def invite_member(
        self,
        *,
        email: str,
        full_name: str,
        role: str,
        created_by: str,
        temporary_password: str | None = None,
        department_id: UUID | None = None,
    ) -> dict[str, Any]:
        """Create or reuse a user and add an active membership on this instance."""
        import secrets
        import uuid

        from rai_gateway.auth.passwords import hash_password
        from rai_gateway.auth.verification import issue_and_send_verification
        from rai_gateway.core.config import settings
        from rai_gateway.models.database import AdminCredential, UserAccount
        from rai_gateway.services.admin_console import _ensure_default_rbac_seed

        if role not in {item.value for item in GovernanceRole}:
            raise GovernanceConflictError(f"Unknown governance role: {role}")

        email_norm = email.strip().lower()
        if not email_norm or "@" not in email_norm:
            raise GovernanceConflictError("A valid email is required")

        _ensure_default_rbac_seed(self._db)
        created_user = False
        password_out: str | None = None
        user = (
            self._db.query(UserAccount).filter(UserAccount.email == email_norm).first()
        )
        if user is None:
            created_user = True
            suffix = uuid.uuid4().hex[:6]
            user_id = f"user_{email_norm.split('@')[0][:24]}_{suffix}"[:64]
            password_out = temporary_password or secrets.token_urlsafe(12)
            user = UserAccount(
                user_id=user_id,
                email=email_norm,
                name=(full_name or email_norm.split("@")[0]).strip(),
                status="active",
            )
            self._db.add(user)
            self._db.flush()
            self._db.add(
                AdminCredential(
                    email=email_norm,
                    user_id=user_id,
                    password_hash=hash_password(password_out),
                    is_active=True,
                )
            )
        else:
            user_id = user.user_id

        if not settings.email_enabled:
            user.email_verified_at = _utcnow()

        self._db.commit()
        self._db.refresh(user)
        membership = self.create_membership(
            user_id=user_id,
            role=role,
            created_by=created_by,
            status=MembershipStatus.ACTIVE.value,
            department_id=department_id,
        )
        verification_meta: dict[str, Any] = {"email_sent": False}
        if settings.email_enabled:
            try:
                verification_meta = issue_and_send_verification(self._db, user=user)
            except Exception:
                verification_meta = {
                    "email_sent": False,
                    "email_error": "verification_email_unavailable",
                }
        return {
            "user": {
                "user_id": user.user_id,
                "email": user.email,
                "name": user.name,
                "created": created_user,
            },
            "membership": membership,
            "temporary_password": password_out,
            "verification_email_sent": bool(verification_meta.get("email_sent")),
            "verification_email_error": verification_meta.get("email_error"),
        }

    def list_memberships(
        self, *, status: str | None = None, limit: int = 100, offset: int = 0
    ) -> list[dict[str, Any]]:
        from rai_gateway.governance.departments import ensure_default_departments

        ensure_default_departments(self._db)
        q = self._db.query(OrganizationMembership)
        if status:
            q = q.filter(OrganizationMembership.status == status)
        rows = (
            q.order_by(OrganizationMembership.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        user_ids = {row.user_id for row in rows}
        users_by_id = self._lookup_users(user_ids)
        departments_by_id = self._departments_by_id(
            {row.department_id for row in rows if row.department_id}
        )
        return [
            self._serialize_membership(
                row,
                users_by_id.get(row.user_id),
                departments_by_id.get(row.department_id),
            )
            for row in rows
        ]

    def list_departments(self) -> list[dict[str, Any]]:
        from rai_gateway.governance.departments import (
            ensure_default_departments,
            serialize_department,
        )

        rows = ensure_default_departments(self._db)
        return [serialize_department(row) for row in rows]

    def _assign_user_department(self, user_id: str, department_id: UUID) -> None:
        rows = (
            self._db.query(OrganizationMembership)
            .filter(OrganizationMembership.user_id == user_id)
            .all()
        )
        for row in rows:
            row.department_id = department_id

    def _department_for(self, membership: OrganizationMembership) -> Department | None:
        if membership.department_id is None:
            return None
        return (
            self._db.query(Department)
            .filter(Department.id == membership.department_id)
            .first()
        )

    def _departments_by_id(self, department_ids: set[UUID]) -> dict[UUID, Department]:
        if not department_ids:
            return {}
        rows = (
            self._db.query(Department)
            .filter(Department.id.in_(list(department_ids)))
            .all()
        )
        return {row.id: row for row in rows}

    def update_membership(
        self, membership_id: UUID, *, role: str | None = None, status: str | None = None
    ) -> dict[str, Any]:
        membership = self._membership_in_org(membership_id)
        next_role = role if role is not None else membership.role
        next_status = status if status is not None else membership.status
        if next_role not in {item.value for item in GovernanceRole}:
            raise GovernanceConflictError(f"Unknown governance role: {next_role}")
        if next_status not in {item.value for item in MembershipStatus}:
            raise GovernanceConflictError(f"Unknown membership status: {next_status}")
        self._guard_last_admin(membership, next_role=next_role, next_status=next_status)
        if next_role != membership.role:
            clash = (
                self._db.query(OrganizationMembership)
                .filter(
                    OrganizationMembership.user_id == membership.user_id,
                    OrganizationMembership.role == next_role,
                    OrganizationMembership.id != membership.id,
                )
                .first()
            )
            if clash is not None:
                raise GovernanceConflictError("This person already has that role")
        membership.role = next_role
        membership.status = next_status
        self._db.commit()
        self._db.refresh(membership)
        return self._serialize_membership(
            membership, self._lookup_user(membership.user_id)
        )

    def delete_membership(self, membership_id: UUID) -> dict[str, Any]:
        membership = self._membership_in_org(membership_id)
        self._guard_last_admin(membership, removing=True)
        self._db.delete(membership)
        self._db.commit()
        return {
            "id": str(membership_id),
            "deleted": True,
        }

    def remove_organization_member(self, user_id: str) -> dict[str, Any]:
        rows = (
            self._db.query(OrganizationMembership)
            .filter(OrganizationMembership.user_id == user_id)
            .all()
        )
        if not rows:
            raise GovernanceNotFoundError("Member not found in this organization")
        remaining_admins = (
            self._db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.user_id != user_id,
                OrganizationMembership.role == GovernanceRole.ORGANIZATION_ADMIN.value,
                OrganizationMembership.status == MembershipStatus.ACTIVE.value,
            )
            .count()
        )
        removing_active_admin = any(
            row.role == GovernanceRole.ORGANIZATION_ADMIN.value
            and row.status == MembershipStatus.ACTIVE.value
            for row in rows
        )
        if removing_active_admin and remaining_admins == 0:
            raise GovernanceConflictError(
                "The organization must keep one active organization admin"
            )
        deleted = len(rows)
        for row in rows:
            self._db.delete(row)
        self._db.commit()
        return {
            "user_id": user_id,
            "deleted": deleted,
        }

    def _membership_in_org(self, membership_id: UUID) -> OrganizationMembership:
        membership = (
            self._db.query(OrganizationMembership)
            .filter(OrganizationMembership.id == membership_id)
            .first()
        )
        if membership is None:
            raise GovernanceNotFoundError("Membership not found in this organization")
        return membership

    def _guard_last_admin(
        self,
        membership: OrganizationMembership,
        *,
        next_role: str | None = None,
        next_status: str | None = None,
        removing: bool = False,
    ) -> None:
        is_active_admin = (
            membership.role == GovernanceRole.ORGANIZATION_ADMIN.value
            and membership.status == MembershipStatus.ACTIVE.value
        )
        if not is_active_admin:
            return
        stays_active_admin = (
            not removing
            and next_role == GovernanceRole.ORGANIZATION_ADMIN.value
            and next_status == MembershipStatus.ACTIVE.value
        )
        if stays_active_admin:
            return
        others = (
            self._db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.id != membership.id,
                OrganizationMembership.role == GovernanceRole.ORGANIZATION_ADMIN.value,
                OrganizationMembership.status == MembershipStatus.ACTIVE.value,
            )
            .count()
        )
        if others == 0:
            raise GovernanceConflictError(
                "The organization must keep one active organization admin"
            )

    def assert_membership(
        self, user_id: str, roles: list[str] | None = None
    ) -> OrganizationMembership:
        q = self._db.query(OrganizationMembership).filter(
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.status == MembershipStatus.ACTIVE.value,
        )
        if roles:
            q = q.filter(OrganizationMembership.role.in_(roles))
        membership = q.first()
        if membership is None:
            raise TenantIsolationError(f"User {user_id} is not an active member")
        return membership

    def link_ai_system(self, ai_system_id: UUID, actor: str) -> dict[str, Any]:
        system = self._db.query(AISystem).filter(AISystem.id == ai_system_id).first()
        if system is None:
            raise GovernanceNotFoundError(f"AI System {ai_system_id} not found")
        system.updated_by = actor
        self._db.commit()
        self._db.refresh(system)
        log_siem_event(
            trace_id=str(ai_system_id),
            event_type="governance.ai_system.linked",
            decision="allow",
            metadata={
                "ai_system_id": str(ai_system_id),
                "actor": actor,
            },
        )
        return {
            "id": str(system.id),
            "system_key": system.system_key,
            "name": system.name,
        }

    # ------------------------------------------------------------------
    # Accountability
    # ------------------------------------------------------------------

    def upsert_accountability(
        self,
        ai_system_id: UUID,
        *,
        created_by: str,
        business_owner_membership_id: UUID | None = None,
        technical_owner_membership_id: UUID | None = None,
        rai_officer_membership_id: UUID | None = None,
        risk_owner_membership_id: UUID | None = None,
        incident_owner_membership_id: UUID | None = None,
        enforce_sod: bool = True,
    ) -> dict[str, Any]:
        self._require_ai_system(ai_system_id)
        membership_ids = {
            "business_owner_membership_id": business_owner_membership_id,
            "technical_owner_membership_id": technical_owner_membership_id,
            "rai_officer_membership_id": rai_officer_membership_id,
            "risk_owner_membership_id": risk_owner_membership_id,
            "incident_owner_membership_id": incident_owner_membership_id,
        }
        for field, mid in membership_ids.items():
            if mid is not None:
                self._validate_membership_belongs(mid, field)

        classification = (
            self._db.query(AISystemGovernanceClassification)
            .filter(AISystemGovernanceClassification.ai_system_id == ai_system_id)
            .first()
        )
        production = bool(classification and classification.production)

        row = (
            self._db.query(AISystemAccountability)
            .filter(AISystemAccountability.ai_system_id == ai_system_id)
            .first()
        )
        if row is None:
            row = AISystemAccountability(
                ai_system_id=ai_system_id, created_by=created_by
            )
            self._db.add(row)
        for field, mid in membership_ids.items():
            if mid is not None:
                setattr(row, field, mid)

        if enforce_sod and production:
            for left, right in INCOMPATIBLE_ACCOUNTABILITY_PAIRS:
                left_id = getattr(row, left)
                right_id = getattr(row, right)
                if left_id and right_id and left_id == right_id:
                    raise SeparationOfDutiesError(
                        f"Separation of duties violated for production: {left} != {right}"
                    )

        self._db.commit()
        self._db.refresh(row)
        log_siem_event(
            trace_id=str(row.id),
            event_type="governance.accountability.assigned",
            decision="allow",
            metadata={
                "ai_system_id": str(ai_system_id),
                "created_by": created_by,
            },
        )
        return self._serialize_accountability(row)

    def get_accountability(self, ai_system_id: UUID) -> dict[str, Any]:
        self._require_ai_system(ai_system_id)
        row = (
            self._db.query(AISystemAccountability)
            .filter(AISystemAccountability.ai_system_id == ai_system_id)
            .first()
        )
        if row is None:
            raise GovernanceNotFoundError("Accountability record not found")
        data = self._serialize_accountability(row)
        data["missing_required_roles"] = self.missing_required_roles(row)
        return data

    @staticmethod
    def missing_required_roles(accountability: AISystemAccountability) -> list[str]:
        missing: list[str] = []
        if not accountability.business_owner_membership_id:
            missing.append("BUSINESS_OWNER")
        if not accountability.technical_owner_membership_id:
            missing.append("TECHNICAL_OWNER")
        if not accountability.rai_officer_membership_id:
            missing.append("RAI_OFFICER")
        return missing

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------

    def upsert_classification(
        self, ai_system_id: UUID, *, updated_by: str, **fields: Any
    ) -> dict[str, Any]:
        self._require_ai_system(ai_system_id)
        row = (
            self._db.query(AISystemGovernanceClassification)
            .filter(AISystemGovernanceClassification.ai_system_id == ai_system_id)
            .first()
        )
        if row is None:
            row = AISystemGovernanceClassification(ai_system_id=ai_system_id)
            self._db.add(row)
        allowed = {
            "business_criticality",
            "data_sensitivity",
            "customer_citizen_impact",
            "financial_impact",
            "autonomy_level",
            "external_facing",
            "consequential_actions",
            "personal_data",
            "regulated_process",
            "human_oversight_requirement",
            "production",
        }
        for key, value in fields.items():
            if key in allowed and value is not None:
                setattr(row, key, value)
        row.updated_by = updated_by
        self._db.commit()
        self._db.refresh(row)
        return self._serialize_classification(row)

    def get_classification(self, ai_system_id: UUID) -> dict[str, Any]:
        self._require_ai_system(ai_system_id)
        row = (
            self._db.query(AISystemGovernanceClassification)
            .filter(AISystemGovernanceClassification.ai_system_id == ai_system_id)
            .first()
        )
        if row is None:
            raise GovernanceNotFoundError("Classification not found")
        return self._serialize_classification(row)

    # ------------------------------------------------------------------
    # Controls
    # ------------------------------------------------------------------

    def list_frameworks(
        self, *, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        ensure_pilot_control_framework(self._db, created_by="system")
        rows = (
            self._db.query(ControlFramework)
            .order_by(ControlFramework.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [self._serialize_framework(f) for f in rows]

    def list_assessments(
        self,
        ai_system_id: UUID,
        *,
        agent_version_id: UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        self._require_ai_system(ai_system_id)
        q = self._db.query(ControlAssessment).filter(
            ControlAssessment.ai_system_id == ai_system_id
        )
        if agent_version_id is not None:
            q = q.filter(
                (ControlAssessment.agent_version_id == agent_version_id)
                | (ControlAssessment.agent_version_id.is_(None))
            )
        rows = (
            q.order_by(ControlAssessment.updated_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [self._serialize_assessment(a) for a in rows]

    def refresh_automated_assessments(
        self, ai_system_id: UUID, agent_version_id: UUID | None = None
    ) -> list[dict[str, Any]]:
        self._require_ai_system(ai_system_id)
        rows = automated_assess(self._db, ai_system_id, agent_version_id)
        return [self._serialize_assessment(a) for a in rows]

    def record_manual_assessment(
        self,
        ai_system_id: UUID,
        *,
        control_requirement_id: UUID,
        status: str,
        assessed_by: str,
        agent_version_id: UUID | None = None,
        applicability: str | None = None,
        applicability_reason: str | None = None,
        evidence_refs: list[dict[str, Any]] | None = None,
        notes: str | None = None,
        valid_until: datetime | None = None,
    ) -> dict[str, Any]:
        self._require_ai_system(ai_system_id)
        requirement = (
            self._db.query(ControlRequirement)
            .filter(ControlRequirement.id == control_requirement_id)
            .first()
        )
        if requirement is None:
            raise GovernanceNotFoundError("Control requirement not found")
        q = self._db.query(ControlAssessment).filter(
            ControlAssessment.ai_system_id == ai_system_id,
            ControlAssessment.control_requirement_id == control_requirement_id,
        )
        if agent_version_id is None:
            q = q.filter(ControlAssessment.agent_version_id.is_(None))
        else:
            q = q.filter(ControlAssessment.agent_version_id == agent_version_id)
        row = q.first()
        if row is None:
            row = ControlAssessment(
                ai_system_id=ai_system_id,
                agent_version_id=agent_version_id,
                control_requirement_id=control_requirement_id,
            )
            self._db.add(row)
        row.status = status
        row.assessment_method = AssessmentMethod.MANUAL.value
        row.assessed_by = assessed_by
        row.assessed_at = _utcnow()
        row.evidence_refs = evidence_refs or []
        row.notes = notes
        row.valid_until = valid_until
        if applicability:
            row.applicability = applicability
        if applicability_reason:
            row.applicability_reason = applicability_reason
        self._db.commit()
        self._db.refresh(row)
        log_siem_event(
            trace_id=str(row.id),
            event_type="governance.control.assessed",
            decision="allow",
            metadata={
                "ai_system_id": str(ai_system_id),
                "method": AssessmentMethod.MANUAL.value,
                "status": status,
                "assessed_by": assessed_by,
            },
        )
        return self._serialize_assessment(row)

    # ------------------------------------------------------------------
    # Reviews
    # ------------------------------------------------------------------

    def create_review(
        self,
        ai_system_id: UUID,
        *,
        review_type: str,
        requested_by: str,
        agent_version_id: UUID | None = None,
        due_at: datetime | None = None,
        status: str = ReviewStatus.REQUESTED.value,
    ) -> dict[str, Any]:
        self._require_ai_system(ai_system_id)
        checklist = self.build_review_checklist(
            ai_system_id, agent_version_id=agent_version_id
        )
        review = GovernanceReview(
            ai_system_id=ai_system_id,
            agent_version_id=agent_version_id,
            review_type=review_type,
            status=status,
            requested_by=requested_by,
            due_at=due_at,
            checklist=checklist,
            evidence_snapshot={"checklist": checklist},
        )
        self._db.add(review)
        self._db.commit()
        self._db.refresh(review)
        log_siem_event(
            trace_id=str(review.id),
            event_type="governance.review.created",
            decision="allow",
            metadata={
                "ai_system_id": str(ai_system_id),
                "review_type": review_type,
                "requested_by": requested_by,
            },
        )
        return self._serialize_review(review)

    def get_review(self, review_id: UUID) -> dict[str, Any]:
        review = self._get_review(review_id)
        data = self._serialize_review(review)
        assignments = (
            self._db.query(GovernanceReviewAssignment)
            .filter(GovernanceReviewAssignment.review_id == review.id)
            .all()
        )
        data["assignments"] = [
            self._serialize_review_assignment(a) for a in assignments
        ]
        return data

    def list_reviews(
        self,
        *,
        ai_system_id: UUID | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        q = self._db.query(GovernanceReview)
        if ai_system_id:
            q = q.filter(GovernanceReview.ai_system_id == ai_system_id)
        if status:
            q = q.filter(GovernanceReview.status == status)
        rows = (
            q.order_by(GovernanceReview.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [self._serialize_review(r) for r in rows]

    def decide_review(
        self,
        review_id: UUID,
        *,
        decision: str,
        decision_reason: str,
        decided_by: str,
        conditions: list[Any] | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not decision_reason or not decision_reason.strip():
            raise GovernanceConflictError("decision_reason is required")
        if decision not in {d.value for d in ReviewDecision}:
            raise GovernanceConflictError(f"Invalid review decision: {decision}")
        review = self._get_review(review_id)
        if review.status == ReviewStatus.COMPLETED.value:
            raise GovernanceConflictError(
                "Completed reviews are append-only / immutable"
            )
        review.decision = decision
        review.decision_reason = decision_reason
        review.conditions = conditions
        review.decided_by = decided_by
        review.completed_at = _utcnow()
        review.status = ReviewStatus.COMPLETED.value
        review.checklist = self.build_review_checklist(
            review.ai_system_id, agent_version_id=review.agent_version_id
        )
        self._db.commit()
        self._db.refresh(review)
        log_siem_event(
            trace_id=str(review.id),
            event_type="governance.review.decided",
            decision="allow",
            metadata={
                "review_id": str(review.id),
                "decision": decision,
                "decided_by": decided_by,
            },
        )
        return self._serialize_review(review)

    def assign_reviewers(
        self, review_id: UUID, *, reviewers: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        review = self._get_review(review_id)
        out: list[GovernanceReviewAssignment] = []
        for item in reviewers:
            assignment = GovernanceReviewAssignment(
                review_id=review.id,
                membership_id=item.get("membership_id"),
                reviewer_user_id=item["reviewer_user_id"],
                role=item.get("role"),
            )
            self._db.add(assignment)
            out.append(assignment)
        if review.status == ReviewStatus.REQUESTED.value:
            review.status = ReviewStatus.IN_REVIEW.value
        self._db.commit()
        for a in out:
            self._db.refresh(a)
        return [self._serialize_review_assignment(a) for a in out]

    def build_review_checklist(
        self, ai_system_id: UUID, *, agent_version_id: UUID | None = None
    ) -> dict[str, Any]:
        accountability = (
            self._db.query(AISystemAccountability)
            .filter(AISystemAccountability.ai_system_id == ai_system_id)
            .first()
        )
        missing_roles = (
            self.missing_required_roles(accountability) if accountability else ["ALL"]
        )
        risk: dict[str, Any] = {"available": False}
        try:
            from rai_gateway.models.registry import RiskAssessment

            ra = (
                self._db.query(RiskAssessment)
                .filter(RiskAssessment.ai_system_id == ai_system_id)
                .order_by(RiskAssessment.created_at.desc())
                .first()
            )
            if ra:
                risk = {
                    "available": True,
                    "id": str(ra.id),
                    "status": ra.status,
                    "risk_tier": ra.risk_tier,
                }
        except Exception:
            pass

        assurance: dict[str, Any] = {"available": False}
        if agent_version_id:
            try:
                from rai_gateway.models.evaluations import AssuranceRecord

                ar = (
                    self._db.query(AssuranceRecord)
                    .filter(
                        AssuranceRecord.agent_version_id == agent_version_id,
                        AssuranceRecord.superseded_at.is_(None),
                    )
                    .order_by(AssuranceRecord.created_at.desc())
                    .first()
                )
                if ar:
                    assurance = {
                        "available": True,
                        "id": str(ar.id),
                        "status": ar.status,
                    }
            except Exception:
                pass

        open_incidents = (
            self._db.query(AIIncident)
            .filter(
                AIIncident.ai_system_id == ai_system_id,
                ~AIIncident.status.in_(
                    [IncidentStatus.RESOLVED.value, IncidentStatus.CLOSED.value]
                ),
            )
            .count()
        )
        open_exceptions = (
            self._db.query(GovernanceException)
            .filter(
                GovernanceException.ai_system_id == ai_system_id,
                GovernanceException.status.in_(
                    [
                        ExceptionStatus.REQUESTED.value,
                        ExceptionStatus.UNDER_REVIEW.value,
                        ExceptionStatus.APPROVED.value,
                    ]
                ),
            )
            .count()
        )
        control_gaps = (
            self._db.query(ControlAssessment)
            .filter(
                ControlAssessment.ai_system_id == ai_system_id,
                ControlAssessment.applicability == "REQUIRED",
                ControlAssessment.status.in_(
                    ["NOT_SATISFIED", "NOT_ASSESSED", "PARTIALLY_SATISFIED"]
                ),
            )
            .count()
        )
        return {
            "accountability": {
                "present": accountability is not None,
                "missing_required_roles": missing_roles,
            },
            "risk": risk,
            "assurance": assurance,
            "open_incidents": open_incidents,
            "open_exceptions": open_exceptions,
            "control_gaps": control_gaps,
        }

    def ensure_periodic_schedule(
        self, ai_system_id: UUID, *, created_by: str, frequency_days: int | None = None
    ) -> dict[str, Any]:
        self._require_ai_system(ai_system_id)
        profile = (
            self._db.query(OrganizationGovernanceProfile)
            .filter(OrganizationGovernanceProfile.singleton_key == "default")
            .first()
        )
        days = frequency_days or (
            profile.default_review_frequency_days if profile else 90
        )
        schedule = (
            self._db.query(PeriodicReviewSchedule)
            .filter(PeriodicReviewSchedule.ai_system_id == ai_system_id)
            .first()
        )
        if schedule is None:
            schedule = PeriodicReviewSchedule(
                ai_system_id=ai_system_id,
                frequency_days=days,
                next_due_at=_utcnow() + timedelta(days=days),
                enabled=True,
                created_by=created_by,
            )
            self._db.add(schedule)
        else:
            schedule.frequency_days = days
            schedule.enabled = True
            if schedule.next_due_at is None:
                schedule.next_due_at = _utcnow() + timedelta(days=days)
        self._db.commit()
        self._db.refresh(schedule)
        return self._serialize_periodic_schedule(schedule)

    def process_due_periodic_reviews(
        self, *, actor: str = "system"
    ) -> list[dict[str, Any]]:
        now = _utcnow()
        q = self._db.query(PeriodicReviewSchedule).filter(
            PeriodicReviewSchedule.enabled.is_(True),
            PeriodicReviewSchedule.next_due_at <= now,
        )
        created: list[dict[str, Any]] = []
        for schedule in q.all():
            existing = (
                self._db.query(GovernanceReview)
                .filter(
                    GovernanceReview.ai_system_id == schedule.ai_system_id,
                    GovernanceReview.review_type == ReviewType.PERIODIC.value,
                    GovernanceReview.status.in_(
                        [
                            ReviewStatus.REQUESTED.value,
                            ReviewStatus.IN_REVIEW.value,
                            ReviewStatus.DRAFT.value,
                        ]
                    ),
                )
                .first()
            )
            if existing:
                continue
            review = self.create_review(
                schedule.ai_system_id,
                review_type=ReviewType.PERIODIC.value,
                requested_by=actor,
                due_at=schedule.next_due_at,
            )
            schedule.next_due_at = now + timedelta(days=schedule.frequency_days)
            self._db.commit()
            created.append(review)
        return created

    # ------------------------------------------------------------------
    # Attestations
    # ------------------------------------------------------------------

    def create_attestation(
        self,
        *,
        attestation_type: str,
        statement: str,
        actor: str,
        ai_system_id: UUID | None = None,
        agent_version_id: UUID | None = None,
        actor_role: str | None = None,
        scope: dict[str, Any] | None = None,
        evidence_refs: list[dict[str, Any]] | None = None,
        valid_until: datetime | None = None,
    ) -> dict[str, Any]:
        if ai_system_id:
            self._require_ai_system(ai_system_id)
        row = GovernanceAttestation(
            ai_system_id=ai_system_id,
            agent_version_id=agent_version_id,
            attestation_type=attestation_type,
            statement=statement,
            scope=scope,
            actor=actor,
            actor_role=actor_role,
            evidence_refs=evidence_refs,
            valid_until=valid_until,
        )
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        return self._serialize_attestation(row)

    # ------------------------------------------------------------------
    # Exceptions
    # ------------------------------------------------------------------

    def request_exception(
        self,
        ai_system_id: UUID,
        *,
        business_justification: str,
        requester: str,
        control_requirement_id: UUID | None = None,
        agent_version_id: UUID | None = None,
        scope: dict[str, Any] | None = None,
        risk: str | None = None,
        compensating_controls: list[Any] | dict[str, Any] | None = None,
        evidence_refs: list[dict[str, Any]] | None = None,
        valid_until: datetime | None = None,
    ) -> dict[str, Any]:
        self._require_ai_system(ai_system_id)
        if control_requirement_id:
            requirement = (
                self._db.query(ControlRequirement)
                .filter(ControlRequirement.id == control_requirement_id)
                .first()
            )
            if requirement is None:
                raise GovernanceNotFoundError("Control requirement not found")
            if requirement.non_waivable:
                raise GovernanceDeniedError(
                    f"Control requirement {requirement.requirement_key} is non-waivable"
                )
        row = GovernanceException(
            ai_system_id=ai_system_id,
            agent_version_id=agent_version_id,
            control_requirement_id=control_requirement_id,
            scope=scope,
            business_justification=business_justification,
            risk=risk,
            compensating_controls=compensating_controls,
            evidence_refs=evidence_refs,
            status=ExceptionStatus.REQUESTED.value,
            requester=requester,
            valid_until=valid_until,
        )
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        log_siem_event(
            trace_id=str(row.id),
            event_type="governance.exception.requested",
            decision="allow",
            metadata={
                "ai_system_id": str(ai_system_id),
                "requester": requester,
            },
        )
        return self._serialize_exception(row)

    def approve_exception(
        self,
        exception_id: UUID,
        *,
        approver: str,
        decision_reason: str,
        valid_until: datetime | None = None,
    ) -> dict[str, Any]:
        row = self._get_exception(exception_id)
        if row.requester == approver:
            raise SeparationOfDutiesError(
                "Requester cannot approve their own exception"
            )
        if row.control_requirement_id:
            requirement = (
                self._db.query(ControlRequirement)
                .filter(ControlRequirement.id == row.control_requirement_id)
                .first()
            )
            if requirement and requirement.non_waivable:
                raise GovernanceDeniedError(
                    f"Control requirement {requirement.requirement_key} is non-waivable"
                )
        row.status = ExceptionStatus.APPROVED.value
        row.approver = approver
        row.decision_reason = decision_reason
        row.decided_at = _utcnow()
        if valid_until:
            row.valid_until = valid_until
        self._db.commit()
        self._db.refresh(row)
        log_siem_event(
            trace_id=str(row.id),
            event_type="governance.exception.approved",
            decision="allow",
            metadata={
                "exception_id": str(row.id),
                "approver": approver,
            },
        )
        return self._serialize_exception(row)

    def reject_exception(
        self, exception_id: UUID, *, approver: str, decision_reason: str
    ) -> dict[str, Any]:
        row = self._get_exception(exception_id)
        if row.requester == approver:
            raise SeparationOfDutiesError("Requester cannot reject their own exception")
        row.status = ExceptionStatus.REJECTED.value
        row.approver = approver
        row.decision_reason = decision_reason
        row.decided_at = _utcnow()
        self._db.commit()
        self._db.refresh(row)
        log_siem_event(
            trace_id=str(row.id),
            event_type="governance.exception.rejected",
            decision="deny",
            metadata={
                "exception_id": str(row.id),
                "approver": approver,
            },
        )
        return self._serialize_exception(row)

    def revoke_exception(
        self, exception_id: UUID, *, actor: str, decision_reason: str | None = None
    ) -> dict[str, Any]:
        row = self._get_exception(exception_id)
        if row.status != ExceptionStatus.APPROVED.value:
            raise GovernanceConflictError("Only APPROVED exceptions can be revoked")
        row.status = ExceptionStatus.REVOKED.value
        row.revoked_at = _utcnow()
        if decision_reason:
            row.decision_reason = decision_reason
        self._db.commit()
        self._db.refresh(row)
        log_siem_event(
            trace_id=str(row.id),
            event_type="governance.exception.revoked",
            decision="deny",
            metadata={
                "exception_id": str(row.id),
                "actor": actor,
            },
        )
        return self._serialize_exception(row)

    def expire_exceptions(self) -> list[dict[str, Any]]:
        now = _utcnow()
        q = self._db.query(GovernanceException).filter(
            GovernanceException.status == ExceptionStatus.APPROVED.value,
            GovernanceException.valid_until.isnot(None),
            GovernanceException.valid_until <= now,
        )
        expired: list[dict[str, Any]] = []
        for row in q.all():
            row.status = ExceptionStatus.EXPIRED.value
            log_siem_event(
                trace_id=str(row.id),
                event_type="governance.exception.expired",
                decision="deny",
                metadata={
                    "exception_id": str(row.id),
                },
            )
            expired.append(self._serialize_exception(row))
        if expired:
            self._db.commit()
        return expired

    def list_exceptions(
        self,
        *,
        ai_system_id: UUID | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        q = self._db.query(GovernanceException)
        if ai_system_id:
            q = q.filter(GovernanceException.ai_system_id == ai_system_id)
        if status:
            q = q.filter(GovernanceException.status == status)
        rows = (
            q.order_by(GovernanceException.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [self._serialize_exception(r) for r in rows]

    def get_exception(self, exception_id: UUID) -> dict[str, Any]:
        return self._serialize_exception(self._get_exception(exception_id))

    def list_attestations(
        self, *, ai_system_id: UUID | None = None, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        q = self._db.query(GovernanceAttestation)
        if ai_system_id:
            q = q.filter(GovernanceAttestation.ai_system_id == ai_system_id)
        rows = (
            q.order_by(GovernanceAttestation.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [self._serialize_attestation(r) for r in rows]

    # ------------------------------------------------------------------
    # Incidents
    # ------------------------------------------------------------------

    def create_incident(
        self,
        ai_system_id: UUID,
        *,
        title: str,
        reported_by: str,
        severity: str = IncidentSeverity.MEDIUM.value,
        category: str = "OTHER",
        description: str | None = None,
        source: str = "MANUAL",
        source_ref: str | None = None,
        agent_version_id: UUID | None = None,
        runtime_identity_id: UUID | None = None,
        trajectory_id: UUID | None = None,
        incident_manager: str | None = None,
        evidence_refs: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        self._require_ai_system(ai_system_id)
        incident = AIIncident(
            ai_system_id=ai_system_id,
            agent_version_id=agent_version_id,
            runtime_identity_id=runtime_identity_id,
            trajectory_id=trajectory_id,
            severity=severity,
            category=category,
            status=IncidentStatus.OPEN.value,
            title=title,
            description=description,
            source=source,
            source_ref=source_ref,
            reported_by=reported_by,
            incident_manager=incident_manager,
            evidence_refs=evidence_refs,
        )
        self._db.add(incident)
        self._db.flush()
        self._db.add(
            IncidentTransition(
                incident_id=incident.id,
                from_status=None,
                to_status=IncidentStatus.OPEN.value,
                actor=reported_by,
                reason="Incident created",
            )
        )
        self._db.commit()
        self._db.refresh(incident)
        log_siem_event(
            trace_id=str(incident.id),
            event_type="incident.created",
            decision="allow",
            metadata={
                "ai_system_id": str(ai_system_id),
                "severity": severity,
                "reported_by": reported_by,
            },
        )
        if severity in {IncidentSeverity.HIGH.value, IncidentSeverity.CRITICAL.value}:
            self._trigger_incident_driven_followups(incident)
        return self._serialize_incident(incident)

    def transition_incident(
        self,
        incident_id: UUID,
        *,
        to_status: str,
        actor: str,
        reason: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        incident = self._get_incident(incident_id)
        allowed = _INCIDENT_TRANSITIONS.get(incident.status, frozenset())
        if to_status not in allowed:
            raise GovernanceConflictError(
                f"Invalid incident transition {incident.status} -> {to_status}"
            )
        if (
            to_status == IncidentStatus.CLOSED.value
            and incident.severity == IncidentSeverity.CRITICAL.value
            and actor == incident.reported_by
        ):
            raise SeparationOfDutiesError(
                "CRITICAL incidents cannot be closed by the reporter"
            )
        from_status = incident.status
        incident.status = to_status
        if to_status == IncidentStatus.CLOSED.value:
            incident.closed_at = _utcnow()
        self._db.add(
            IncidentTransition(
                incident_id=incident.id,
                from_status=from_status,
                to_status=to_status,
                actor=actor,
                reason=reason,
                metadata_=metadata,
            )
        )
        self._db.commit()
        self._db.refresh(incident)
        event_map = {
            IncidentStatus.TRIAGED.value: "incident.triaged",
            IncidentStatus.CONTAINED.value: "incident.contained",
            IncidentStatus.RESOLVED.value: "incident.resolved",
            IncidentStatus.CLOSED.value: "incident.closed",
        }
        log_siem_event(
            trace_id=str(incident.id),
            event_type=event_map.get(to_status, "incident.transitioned"),
            decision="allow",
            metadata={
                "from_status": from_status,
                "to_status": to_status,
                "actor": actor,
            },
        )
        return self._serialize_incident(incident)

    def contain_incident(
        self,
        incident_id: UUID,
        *,
        actor: str,
        containment_action: str,
        containment_ref: dict[str, Any] | list[Any] | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        incident = self._get_incident(incident_id)
        incident.containment_action = containment_action
        incident.containment_ref = containment_ref
        if incident.status in {
            IncidentStatus.OPEN.value,
            IncidentStatus.TRIAGED.value,
            IncidentStatus.INVESTIGATING.value,
        }:
            return self.transition_incident(
                incident.id,
                to_status=IncidentStatus.CONTAINED.value,
                actor=actor,
                reason=reason or f"Containment: {containment_action}",
                metadata={"containment_ref": containment_ref},
            )
        self._db.commit()
        self._db.refresh(incident)
        log_siem_event(
            trace_id=str(incident.id),
            event_type="incident.contained",
            decision="allow",
            metadata={
                "containment_action": containment_action,
                "actor": actor,
            },
        )
        return self._serialize_incident(incident)

    def add_corrective_action(
        self,
        incident_id: UUID,
        *,
        description: str,
        owner: str,
        due_at: datetime | None = None,
    ) -> dict[str, Any]:
        incident = self._get_incident(incident_id)
        action = IncidentCorrectiveAction(
            incident_id=incident.id,
            description=description,
            owner=owner,
            due_at=due_at,
            status=CorrectiveActionStatus.OPEN.value,
        )
        self._db.add(action)
        self._db.commit()
        self._db.refresh(action)
        return self._serialize_corrective_action(action)

    def update_corrective_action(
        self,
        action_id: UUID,
        *,
        status: str | None = None,
        evidence: dict[str, Any] | list[Any] | None = None,
        description: str | None = None,
        due_at: datetime | None = None,
    ) -> dict[str, Any]:
        action = (
            self._db.query(IncidentCorrectiveAction)
            .filter(IncidentCorrectiveAction.id == action_id)
            .first()
        )
        if action is None:
            raise GovernanceNotFoundError("Corrective action not found")
        incident = self._get_incident(action.incident_id)
        _ = incident
        if status:
            action.status = status
            if status == CorrectiveActionStatus.DONE.value:
                action.completed_at = _utcnow()
        if evidence is not None:
            action.evidence = evidence
        if description is not None:
            action.description = description
        if due_at is not None:
            action.due_at = due_at
        self._db.commit()
        self._db.refresh(action)
        return self._serialize_corrective_action(action)

    def _trigger_incident_driven_followups(self, incident: AIIncident) -> None:
        try:
            self.create_review(
                incident.ai_system_id,
                review_type=ReviewType.INCIDENT_DRIVEN.value,
                requested_by="system:incident",
                agent_version_id=incident.agent_version_id,
            )
        except Exception:
            pass
        if incident.agent_version_id:
            try:
                from rai_gateway.evaluations.service import EvaluationService

                EvaluationService(self._db).invalidate_assurance(
                    incident.agent_version_id,
                    reason=f"HIGH/CRITICAL incident {incident.id}",
                    trigger_type="INCIDENT",
                    created_by="system:incident",
                )
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Evidence packages
    # ------------------------------------------------------------------

    def generate_evidence_package(
        self,
        *,
        generated_by: str,
        ai_system_id: UUID | None = None,
        agent_id: UUID | None = None,
        agent_version_id: UUID | None = None,
        review_id: UUID | None = None,
        incident_id: UUID | None = None,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
        include_html: bool = True,
    ) -> dict[str, Any]:
        if ai_system_id:
            self._require_ai_system(ai_system_id)

        sections: dict[str, Any] = {}

        def section(
            name: str, available: bool, payload: Any = None, note: str | None = None
        ) -> None:
            sections[name] = {
                "availability": (
                    EvidenceAvailability.AVAILABLE.value
                    if available
                    else EvidenceAvailability.NOT_AVAILABLE.value
                ),
                "note": note,
                "data": payload if available else None,
            }

        profile = self._get_profile()
        section("organization", True, self._serialize_profile(profile))

        if ai_system_id:
            system = (
                self._db.query(AISystem).filter(AISystem.id == ai_system_id).first()
            )
            section(
                "ai_system",
                system is not None,
                {
                    "id": str(system.id),
                    "system_key": system.system_key,
                    "name": system.name,
                    "status": system.status,
                }
                if system
                else None,
            )
            accountability = (
                self._db.query(AISystemAccountability)
                .filter(AISystemAccountability.ai_system_id == ai_system_id)
                .first()
            )
            section(
                "accountability",
                accountability is not None,
                self._serialize_accountability(accountability)
                if accountability
                else None,
            )
        else:
            section("ai_system", False, note="ai_system_id not provided")
            section("accountability", False, note="ai_system_id not provided")

        # Risk
        risk_payload = None
        try:
            from rai_gateway.models.registry import RiskAssessment

            if ai_system_id:
                ra = (
                    self._db.query(RiskAssessment)
                    .filter(RiskAssessment.ai_system_id == ai_system_id)
                    .order_by(RiskAssessment.created_at.desc())
                    .first()
                )
                if ra:
                    risk_payload = {
                        "id": str(ra.id),
                        "status": ra.status,
                        "risk_tier": ra.risk_tier,
                    }
        except Exception:
            pass
        section("risk", risk_payload is not None, risk_payload)

        # Identity
        identity_payload = None
        try:
            from rai_gateway.models.identity import AgentRuntimeIdentity

            if agent_version_id:
                identity = (
                    self._db.query(AgentRuntimeIdentity)
                    .filter(AgentRuntimeIdentity.agent_version_id == agent_version_id)
                    .first()
                )
                if identity:
                    identity_payload = {
                        "id": str(identity.id),
                        "status": identity.status,
                        "identity_key": identity.identity_key,
                    }
        except Exception:
            pass
        section("identity", identity_payload is not None, identity_payload)

        # Approvals
        approvals_payload = None
        try:
            from rai_gateway.models.approval import ApprovalRequest

            if ai_system_id:
                approvals = (
                    self._db.query(ApprovalRequest)
                    .filter(ApprovalRequest.ai_system_id == ai_system_id)
                    .order_by(ApprovalRequest.created_at.desc())
                    .limit(25)
                    .all()
                )
                if approvals:
                    approvals_payload = [
                        {"id": str(a.id), "status": a.status} for a in approvals
                    ]
        except Exception:
            pass
        section("approvals", approvals_payload is not None, approvals_payload)

        # Trajectories
        traj_payload = None
        try:
            from rai_gateway.models.evidence import RuntimeTrajectory

            if ai_system_id:
                tq = self._db.query(RuntimeTrajectory).filter(
                    RuntimeTrajectory.ai_system_id == ai_system_id
                )
                if agent_version_id:
                    tq = tq.filter(
                        RuntimeTrajectory.agent_version_id == agent_version_id
                    )
                trajs = tq.order_by(RuntimeTrajectory.created_at.desc()).limit(25).all()
                if trajs:
                    traj_payload = [
                        {"id": str(t.id), "status": t.status} for t in trajs
                    ]
        except Exception:
            pass
        section("trajectories", traj_payload is not None, traj_payload)

        # Findings
        findings_payload = None
        try:
            from rai_gateway.models.risk_intelligence import RuntimeRiskFinding

            if ai_system_id:
                findings = (
                    self._db.query(RuntimeRiskFinding)
                    .filter(RuntimeRiskFinding.ai_system_id == ai_system_id)
                    .order_by(RuntimeRiskFinding.created_at.desc())
                    .limit(25)
                    .all()
                )
                if findings:
                    findings_payload = [
                        {
                            "id": str(f.id),
                            "severity": f.severity,
                            "status": f.status,
                        }
                        for f in findings
                    ]
        except Exception:
            pass
        section("findings", findings_payload is not None, findings_payload)

        # Assurance
        assurance_payload = None
        try:
            from rai_gateway.models.evaluations import AssuranceRecord

            if agent_version_id:
                ar = (
                    self._db.query(AssuranceRecord)
                    .filter(
                        AssuranceRecord.agent_version_id == agent_version_id,
                        AssuranceRecord.superseded_at.is_(None),
                    )
                    .order_by(AssuranceRecord.created_at.desc())
                    .first()
                )
                if ar:
                    assurance_payload = {
                        "id": str(ar.id),
                        "status": ar.status,
                        "valid_until": _ser_dt(ar.valid_until),
                    }
        except Exception:
            pass
        section("assurance", assurance_payload is not None, assurance_payload)

        # Controls / exceptions / incidents / reviews / attestations
        if ai_system_id:
            assessments = (
                self._db.query(ControlAssessment)
                .filter(ControlAssessment.ai_system_id == ai_system_id)
                .limit(100)
                .all()
            )
            section(
                "controls",
                bool(assessments),
                [self._serialize_assessment(a) for a in assessments]
                if assessments
                else None,
            )
            exceptions = (
                self._db.query(GovernanceException)
                .filter(GovernanceException.ai_system_id == ai_system_id)
                .limit(50)
                .all()
            )
            section(
                "exceptions",
                bool(exceptions),
                [self._serialize_exception(e) for e in exceptions]
                if exceptions
                else None,
            )
            incidents = (
                self._db.query(AIIncident)
                .filter(AIIncident.ai_system_id == ai_system_id)
                .limit(50)
                .all()
            )
            section(
                "incidents",
                bool(incidents),
                [self._serialize_incident(i) for i in incidents] if incidents else None,
            )
            reviews = (
                self._db.query(GovernanceReview)
                .filter(GovernanceReview.ai_system_id == ai_system_id)
                .limit(50)
                .all()
            )
            section(
                "reviews",
                bool(reviews),
                [self._serialize_review(r) for r in reviews] if reviews else None,
            )
            attestations = (
                self._db.query(GovernanceAttestation)
                .filter(GovernanceAttestation.ai_system_id == ai_system_id)
                .limit(50)
                .all()
            )
            section(
                "attestations",
                bool(attestations),
                [self._serialize_attestation(a) for a in attestations]
                if attestations
                else None,
            )
        else:
            for name in (
                "controls",
                "exceptions",
                "incidents",
                "reviews",
                "attestations",
            ):
                section(name, False, note="ai_system_id not provided")

        missing = [
            name
            for name, body in sections.items()
            if body["availability"] == EvidenceAvailability.NOT_AVAILABLE.value
        ]
        manifest = {
            "ai_system_id": str(ai_system_id) if ai_system_id else None,
            "agent_id": str(agent_id) if agent_id else None,
            "agent_version_id": str(agent_version_id) if agent_version_id else None,
            "review_id": str(review_id) if review_id else None,
            "incident_id": str(incident_id) if incident_id else None,
            "period_start": _ser_dt(period_start),
            "period_end": _ser_dt(period_end),
            "generated_by": generated_by,
            "generated_at": _ser_dt(_utcnow()),
            "sections": sections,
            "missing_evidence": missing,
        }
        package_digest = _digest(manifest)
        manifest["package_digest"] = package_digest

        report_html = None
        if include_html:
            rows_html = "".join(
                f"<tr><td>{name}</td><td>{body['availability']}</td>"
                f"<td>{body.get('note') or ''}</td></tr>"
                for name, body in sections.items()
            )
            report_html = (
                "<html><head><title>Governance Evidence Package</title></head><body>"
                f"<h1>Governance Evidence Package</h1>"
                ""
                f"<p>Digest: {package_digest}</p>"
                "<table border='1'><tr><th>Section</th><th>Availability</th><th>Note</th></tr>"
                f"{rows_html}</table></body></html>"
            )

        package = GovernanceEvidencePackage(
            ai_system_id=ai_system_id,
            agent_id=agent_id,
            agent_version_id=agent_version_id,
            review_id=review_id,
            incident_id=incident_id,
            period_start=period_start,
            period_end=period_end,
            generated_by=generated_by,
            manifest=manifest,
            package_digest=package_digest,
            report_html=report_html,
        )
        self._db.add(package)
        self._db.commit()
        self._db.refresh(package)
        log_siem_event(
            trace_id=str(package.id),
            event_type="evidence_package.generated",
            decision="allow",
            metadata={
                "package_id": str(package.id),
                "digest": package_digest,
                "generated_by": generated_by,
            },
        )
        return self._serialize_evidence_package(package)

    def get_evidence_package(self, package_id: UUID) -> dict[str, Any]:
        package = (
            self._db.query(GovernanceEvidencePackage)
            .filter(GovernanceEvidencePackage.id == package_id)
            .first()
        )
        if not package:
            raise GovernanceNotFoundError("Evidence package not found")
        return self._serialize_evidence_package(package, include_manifest=True)

    def list_evidence_packages(
        self, *, ai_system_id: UUID | None = None, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        q = self._db.query(GovernanceEvidencePackage)
        if ai_system_id:
            q = q.filter(GovernanceEvidencePackage.ai_system_id == ai_system_id)
        rows = (
            q.order_by(GovernanceEvidencePackage.generated_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [self._serialize_evidence_package(r) for r in rows]

    def list_incidents(
        self,
        *,
        ai_system_id: UUID | None = None,
        status: str | None = None,
        severity: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        q = self._db.query(AIIncident)
        if ai_system_id:
            q = q.filter(AIIncident.ai_system_id == ai_system_id)
        if status:
            q = q.filter(AIIncident.status == status)
        if severity:
            q = q.filter(AIIncident.severity == severity)
        rows = (
            q.order_by(AIIncident.created_at.desc()).offset(offset).limit(limit).all()
        )
        return [self._serialize_incident(r) for r in rows]

    def get_incident(self, incident_id: UUID) -> dict[str, Any]:
        incident = self._get_incident(incident_id)
        data = self._serialize_incident(incident)
        data["corrective_actions"] = [
            self._serialize_corrective_action(a) for a in incident.corrective_actions
        ]
        data["transitions"] = [
            {
                "id": str(t.id),
                "from_status": t.from_status,
                "to_status": t.to_status,
                "actor": t.actor,
                "reason": t.reason,
                "metadata": t.metadata_,
                "created_at": _ser_dt(t.created_at),
            }
            for t in incident.transitions
        ]
        return data

    # ------------------------------------------------------------------
    # Pilots
    # ------------------------------------------------------------------

    def create_pilot(
        self,
        *,
        name: str,
        created_by: str,
        description: str | None = None,
        sponsor: str | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        success_criteria: dict[str, Any] | list[Any] | None = None,
        status: str = PilotOrgStatus.PLANNING.value,
    ) -> dict[str, Any]:
        pilot = Pilot(
            name=name,
            description=description,
            sponsor=sponsor,
            start_at=start_at,
            end_at=end_at,
            status=status,
            success_criteria=success_criteria,
            created_by=created_by,
        )
        self._db.add(pilot)
        self._db.commit()
        self._db.refresh(pilot)
        return self._serialize_pilot(pilot)

    def add_ai_system_to_pilot(
        self,
        pilot_id: UUID,
        ai_system_id: UUID,
        *,
        agent_version_id: UUID | None = None,
    ) -> dict[str, Any]:
        pilot = self._get_pilot(pilot_id)
        self._require_ai_system(ai_system_id)
        existing = (
            self._db.query(PilotAISystem)
            .filter(
                PilotAISystem.pilot_id == pilot.id,
                PilotAISystem.ai_system_id == ai_system_id,
            )
            .first()
        )
        if existing:
            if agent_version_id:
                existing.agent_version_id = agent_version_id
                self._db.commit()
                self._db.refresh(existing)
            return self._serialize_pilot_ai_system(existing)
        link = PilotAISystem(
            pilot_id=pilot.id,
            ai_system_id=ai_system_id,
            agent_version_id=agent_version_id,
        )
        self._db.add(link)
        self._db.commit()
        self._db.refresh(link)
        return self._serialize_pilot_ai_system(link)

    def get_pilot(self, pilot_id: UUID) -> dict[str, Any]:
        pilot = self._get_pilot(pilot_id)
        data = self._serialize_pilot(pilot)
        links = (
            self._db.query(PilotAISystem)
            .filter(PilotAISystem.pilot_id == pilot.id)
            .all()
        )
        data["ai_systems"] = [self._serialize_pilot_ai_system(link) for link in links]
        return data

    def list_pilots(self, *, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        rows = (
            self._db.query(Pilot)
            .order_by(Pilot.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [self._serialize_pilot(p) for p in rows]

    def transition_pilot_status(
        self,
        pilot_id: UUID,
        *,
        to_status: str,
        actor: str,
        readiness_evaluation_id: UUID | None = None,
    ) -> dict[str, Any]:
        pilot = self._get_pilot(pilot_id)
        allowed = _PILOT_TRANSITIONS.get(pilot.status, frozenset())
        if to_status not in allowed:
            raise GovernanceConflictError(
                f"Invalid pilot transition {pilot.status} -> {to_status}"
            )
        if to_status == PilotOrgStatus.ACTIVE.value:
            ready = False
            if readiness_evaluation_id:
                evaluation = (
                    self._db.query(PilotReadinessEvaluation)
                    .filter(PilotReadinessEvaluation.id == readiness_evaluation_id)
                    .first()
                )
                if evaluation and evaluation.decision in {
                    PilotReadinessDecision.READY.value,
                    PilotReadinessDecision.READY_WITH_CONDITIONS.value,
                }:
                    ready = True
                    pilot.readiness_gate_id = evaluation.id
            else:
                latest = (
                    self._db.query(PilotReadinessEvaluation)
                    .filter(
                        (PilotReadinessEvaluation.pilot_id == pilot.id)
                        | (PilotReadinessEvaluation.pilot_id.is_(None))
                    )
                    .order_by(PilotReadinessEvaluation.evaluated_at.desc())
                    .first()
                )
                if latest and latest.decision in {
                    PilotReadinessDecision.READY.value,
                    PilotReadinessDecision.READY_WITH_CONDITIONS.value,
                }:
                    ready = True
                    pilot.readiness_gate_id = latest.id
            if not ready:
                raise GovernanceDeniedError(
                    "Pilot requires READY / READY_WITH_CONDITIONS readiness before ACTIVE"
                )
        pilot.status = to_status
        self._db.commit()
        self._db.refresh(pilot)
        event_map = {
            PilotOrgStatus.ACTIVE.value: "pilot.activated",
            PilotOrgStatus.PAUSED.value: "pilot.paused",
            PilotOrgStatus.COMPLETED.value: "pilot.completed",
        }
        log_siem_event(
            trace_id=str(pilot.id),
            event_type=event_map.get(to_status, "pilot.status_changed"),
            decision="allow",
            metadata={
                "pilot_id": str(pilot.id),
                "status": to_status,
                "actor": actor,
            },
        )
        return self._serialize_pilot(pilot)

    def evaluate_readiness(
        self,
        *,
        ai_system_id: UUID,
        evaluated_by: str,
        agent_version_id: UUID | None = None,
        pilot_id: UUID | None = None,
    ) -> dict[str, Any]:
        self._require_ai_system(ai_system_id)
        if pilot_id:
            self._get_pilot(pilot_id)
        return evaluate_pilot_readiness(
            self._db,
            ai_system_id=ai_system_id,
            agent_version_id=agent_version_id,
            pilot_id=pilot_id,
            evaluated_by=evaluated_by,
        )

    def get_pilot_dashboard(self, *, pilot_id: UUID | None = None) -> dict[str, Any]:
        pilot = self._get_pilot(pilot_id) if pilot_id else None

        now = _utcnow()
        open_incidents = (
            self._db.query(AIIncident)
            .filter(
                ~AIIncident.status.in_(
                    [IncidentStatus.RESOLVED.value, IncidentStatus.CLOSED.value]
                )
            )
            .count()
        )
        critical_incidents = (
            self._db.query(AIIncident)
            .filter(
                AIIncident.severity.in_(
                    [IncidentSeverity.HIGH.value, IncidentSeverity.CRITICAL.value]
                ),
                ~AIIncident.status.in_(
                    [IncidentStatus.RESOLVED.value, IncidentStatus.CLOSED.value]
                ),
            )
            .count()
        )
        pending_reviews = (
            self._db.query(GovernanceReview)
            .filter(
                GovernanceReview.status.in_(
                    [
                        ReviewStatus.REQUESTED.value,
                        ReviewStatus.IN_REVIEW.value,
                        ReviewStatus.DRAFT.value,
                    ]
                )
            )
            .count()
        )
        expiring_exceptions = (
            self._db.query(GovernanceException)
            .filter(
                GovernanceException.status == ExceptionStatus.APPROVED.value,
                GovernanceException.valid_until.isnot(None),
                GovernanceException.valid_until <= now + timedelta(days=14),
            )
            .count()
        )
        control_gaps = (
            self._db.query(ControlAssessment)
            .filter(
                ControlAssessment.applicability == "REQUIRED",
                ControlAssessment.status.in_(
                    ["NOT_SATISFIED", "NOT_ASSESSED", "PARTIALLY_SATISFIED"]
                ),
            )
            .count()
        )
        latest_readiness = (
            self._db.query(PilotReadinessEvaluation)
            .order_by(PilotReadinessEvaluation.evaluated_at.desc())
            .first()
        )
        systems_in_scope = 0
        if pilot:
            systems_in_scope = (
                self._db.query(PilotAISystem)
                .filter(PilotAISystem.pilot_id == pilot.id)
                .count()
            )

        return {
            "pilot": self._serialize_pilot(pilot) if pilot else None,
            "pilot_status": pilot.status if pilot else None,
            "readiness": {
                "decision": latest_readiness.decision if latest_readiness else None,
                "evaluated_at": _ser_dt(latest_readiness.evaluated_at)
                if latest_readiness
                else None,
                "id": str(latest_readiness.id) if latest_readiness else None,
            },
            "kpis": {
                "ai_systems_in_scope": systems_in_scope,
                "open_incidents": open_incidents,
                "critical_open_incidents": critical_incidents,
                "pending_reviews": pending_reviews,
                "expiring_exceptions": expiring_exceptions,
                "control_gaps": control_gaps,
            },
        }

    # ------------------------------------------------------------------
    # Due work
    # ------------------------------------------------------------------

    def list_due_work(self) -> dict[str, Any]:
        now = _utcnow()
        reviews_due = (
            self._db.query(GovernanceReview)
            .filter(
                GovernanceReview.status.in_(
                    [
                        ReviewStatus.REQUESTED.value,
                        ReviewStatus.IN_REVIEW.value,
                        ReviewStatus.DRAFT.value,
                    ]
                ),
                GovernanceReview.due_at.isnot(None),
                GovernanceReview.due_at <= now + timedelta(days=7),
            )
            .all()
        )
        exceptions_expiring = (
            self._db.query(GovernanceException)
            .filter(
                GovernanceException.status == ExceptionStatus.APPROVED.value,
                GovernanceException.valid_until.isnot(None),
                GovernanceException.valid_until <= now + timedelta(days=14),
            )
            .all()
        )
        corrective_overdue = (
            self._db.query(IncidentCorrectiveAction)
            .join(AIIncident, AIIncident.id == IncidentCorrectiveAction.incident_id)
            .filter(
                IncidentCorrectiveAction.status.in_(
                    [
                        CorrectiveActionStatus.OPEN.value,
                        CorrectiveActionStatus.IN_PROGRESS.value,
                    ]
                ),
                IncidentCorrectiveAction.due_at.isnot(None),
                IncidentCorrectiveAction.due_at <= now,
            )
            .all()
        )
        open_incidents = (
            self._db.query(AIIncident)
            .filter(
                ~AIIncident.status.in_(
                    [IncidentStatus.RESOLVED.value, IncidentStatus.CLOSED.value]
                )
            )
            .all()
        )

        assurance_expiring: list[dict[str, Any]] = []
        try:
            from rai_gateway.models.evaluations import AssuranceRecord

            systems = self._db.query(AISystem).all()
            system_ids = [s.id for s in systems]
            if system_ids:
                rows = (
                    self._db.query(AssuranceRecord)
                    .filter(
                        AssuranceRecord.ai_system_id.in_(system_ids),
                        AssuranceRecord.superseded_at.is_(None),
                        AssuranceRecord.valid_until.isnot(None),
                        AssuranceRecord.valid_until <= now + timedelta(days=14),
                    )
                    .limit(50)
                    .all()
                )
                assurance_expiring = [
                    {
                        "id": str(r.id),
                        "ai_system_id": str(r.ai_system_id),
                        "agent_version_id": str(r.agent_version_id),
                        "status": r.status,
                        "valid_until": _ser_dt(r.valid_until),
                    }
                    for r in rows
                ]
        except Exception:
            pass

        return {
            "reviews_due": [self._serialize_review(r) for r in reviews_due],
            "exceptions_expiring": [
                self._serialize_exception(e) for e in exceptions_expiring
            ],
            "assurance_expiring": assurance_expiring,
            "corrective_actions_overdue": [
                self._serialize_corrective_action(a) for a in corrective_overdue
            ],
            "open_incidents": [self._serialize_incident(i) for i in open_incidents],
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _validate_membership_belongs(
        self, membership_id: UUID, field: str
    ) -> OrganizationMembership:
        membership = (
            self._db.query(OrganizationMembership)
            .filter(OrganizationMembership.id == membership_id)
            .first()
        )
        if membership is None:
            raise GovernanceNotFoundError(
                f"Membership {membership_id} not found ({field})"
            )
        return membership

    def _get_review(self, review_id: UUID) -> GovernanceReview:
        review = (
            self._db.query(GovernanceReview)
            .filter(GovernanceReview.id == review_id)
            .first()
        )
        if review is None:
            raise GovernanceNotFoundError(f"Review {review_id} not found")
        return review

    def _get_exception(self, exception_id: UUID) -> GovernanceException:
        row = (
            self._db.query(GovernanceException)
            .filter(GovernanceException.id == exception_id)
            .first()
        )
        if row is None:
            raise GovernanceNotFoundError(f"Exception {exception_id} not found")
        return row

    def _get_incident(self, incident_id: UUID) -> AIIncident:
        incident = (
            self._db.query(AIIncident).filter(AIIncident.id == incident_id).first()
        )
        if incident is None:
            raise GovernanceNotFoundError(f"Incident {incident_id} not found")
        return incident

    def _get_pilot(self, pilot_id: UUID) -> Pilot:
        pilot = self._db.query(Pilot).filter(Pilot.id == pilot_id).first()
        if pilot is None:
            raise GovernanceNotFoundError(f"Pilot {pilot_id} not found")
        return pilot

    def _get_profile(self) -> OrganizationGovernanceProfile:
        profile = (
            self._db.query(OrganizationGovernanceProfile)
            .filter(OrganizationGovernanceProfile.singleton_key == "default")
            .first()
        )
        if profile is None:
            profile = OrganizationGovernanceProfile(
                singleton_key="default",
                name="Organization",
                legal_name="Organization",
                updated_by="system",
            )
            self._db.add(profile)
            self._db.flush()
        return profile

    def _require_ai_system(self, ai_system_id: UUID) -> AISystem:
        system = self._db.query(AISystem).filter(AISystem.id == ai_system_id).first()
        if system is None:
            raise GovernanceNotFoundError(f"AI System {ai_system_id} not found")
        return system

    def _serialize_profile(
        self, profile: OrganizationGovernanceProfile
    ) -> dict[str, Any]:
        return {
            "id": str(profile.id),
            "name": profile.name,
            "description": profile.description,
            "logo": profile.logo,
            "legal_name": profile.legal_name,
            "organization_type": profile.organization_type,
            "sector": profile.sector,
            "jurisdiction": profile.jurisdiction,
            "regulatory_context": profile.regulatory_context,
            "risk_appetite": profile.risk_appetite,
            "governance_owner": profile.governance_owner,
            "assurance_owner": profile.assurance_owner,
            "incident_owner": profile.incident_owner,
            "default_review_frequency_days": profile.default_review_frequency_days,
            "evidence_retention_policy": profile.evidence_retention_policy,
            "pilot_status": profile.pilot_status,
            "updated_by": profile.updated_by,
            "updated_at": _ser_dt(profile.updated_at),
        }

    def _lookup_user(self, user_id: str):
        from rai_gateway.models.database import UserAccount

        return (
            self._db.query(UserAccount).filter(UserAccount.user_id == user_id).first()
        )

    def _lookup_users(self, user_ids: set[str]) -> dict[str, Any]:
        from rai_gateway.models.database import UserAccount

        if not user_ids:
            return {}
        rows = (
            self._db.query(UserAccount)
            .filter(UserAccount.user_id.in_(list(user_ids)))
            .all()
        )
        return {row.user_id: row for row in rows}

    def _serialize_membership(
        self,
        membership: OrganizationMembership,
        user: Any | None = None,
        department: Department | None = None,
    ) -> dict[str, Any]:
        return {
            "id": str(membership.id),
            "user_id": membership.user_id,
            "user_name": user.name if user is not None else None,
            "user_email": user.email if user is not None else None,
            "role": membership.role,
            "status": membership.status,
            "department_id": str(membership.department_id)
            if membership.department_id
            else None,
            "department_name": department.name if department is not None else None,
            "valid_from": _ser_dt(membership.valid_from),
            "valid_until": _ser_dt(membership.valid_until),
            "created_by": membership.created_by,
            "created_at": _ser_dt(membership.created_at),
        }

    def _serialize_accountability(self, row: AISystemAccountability) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "ai_system_id": str(row.ai_system_id),
            "business_owner_membership_id": str(row.business_owner_membership_id)
            if row.business_owner_membership_id
            else None,
            "technical_owner_membership_id": str(row.technical_owner_membership_id)
            if row.technical_owner_membership_id
            else None,
            "rai_officer_membership_id": str(row.rai_officer_membership_id)
            if row.rai_officer_membership_id
            else None,
            "risk_owner_membership_id": str(row.risk_owner_membership_id)
            if row.risk_owner_membership_id
            else None,
            "incident_owner_membership_id": str(row.incident_owner_membership_id)
            if row.incident_owner_membership_id
            else None,
            "effective_from": _ser_dt(row.effective_from),
            "effective_until": _ser_dt(row.effective_until),
            "created_by": row.created_by,
            "created_at": _ser_dt(row.created_at),
            "updated_at": _ser_dt(row.updated_at),
            "missing_required_roles": self.missing_required_roles(row),
        }

    def _serialize_classification(
        self, row: AISystemGovernanceClassification
    ) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "ai_system_id": str(row.ai_system_id),
            "business_criticality": row.business_criticality,
            "data_sensitivity": row.data_sensitivity,
            "customer_citizen_impact": row.customer_citizen_impact,
            "financial_impact": row.financial_impact,
            "autonomy_level": row.autonomy_level,
            "external_facing": bool(row.external_facing),
            "consequential_actions": bool(row.consequential_actions),
            "personal_data": bool(row.personal_data),
            "regulated_process": bool(row.regulated_process),
            "human_oversight_requirement": row.human_oversight_requirement,
            "production": bool(row.production),
            "updated_by": row.updated_by,
            "updated_at": _ser_dt(row.updated_at),
        }

    def _serialize_framework(self, framework: ControlFramework) -> dict[str, Any]:
        objectives = (
            self._db.query(ControlObjective)
            .filter(ControlObjective.framework_id == framework.id)
            .all()
        )
        return {
            "id": str(framework.id),
            "framework_key": framework.framework_key,
            "name": framework.name,
            "version": framework.version,
            "description": framework.description,
            "is_internal": framework.is_internal,
            "published": framework.published,
            "created_by": framework.created_by,
            "created_at": _ser_dt(framework.created_at),
            "objectives": [
                {
                    "id": str(o.id),
                    "code": o.code,
                    "title": o.title,
                    "category": o.category,
                    "description": o.description,
                }
                for o in objectives
            ],
        }

    def _serialize_assessment(self, row: ControlAssessment) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "ai_system_id": str(row.ai_system_id),
            "agent_version_id": str(row.agent_version_id)
            if row.agent_version_id
            else None,
            "control_requirement_id": str(row.control_requirement_id),
            "applicability": row.applicability,
            "applicability_reason": row.applicability_reason,
            "status": row.status,
            "assessment_method": row.assessment_method,
            "evidence_refs": row.evidence_refs,
            "assessed_by": row.assessed_by,
            "assessed_at": _ser_dt(row.assessed_at),
            "valid_until": _ser_dt(row.valid_until),
            "notes": row.notes,
            "created_at": _ser_dt(row.created_at),
            "updated_at": _ser_dt(row.updated_at),
        }

    def _serialize_review(self, review: GovernanceReview) -> dict[str, Any]:
        return {
            "id": str(review.id),
            "ai_system_id": str(review.ai_system_id),
            "agent_version_id": str(review.agent_version_id)
            if review.agent_version_id
            else None,
            "review_type": review.review_type,
            "status": review.status,
            "requested_by": review.requested_by,
            "due_at": _ser_dt(review.due_at),
            "decision": review.decision,
            "decision_reason": review.decision_reason,
            "conditions": review.conditions,
            "evidence_snapshot": review.evidence_snapshot,
            "checklist": review.checklist,
            "completed_at": _ser_dt(review.completed_at),
            "decided_by": review.decided_by,
            "created_at": _ser_dt(review.created_at),
        }

    def _serialize_review_assignment(
        self, assignment: GovernanceReviewAssignment
    ) -> dict[str, Any]:
        return {
            "id": str(assignment.id),
            "review_id": str(assignment.review_id),
            "membership_id": str(assignment.membership_id)
            if assignment.membership_id
            else None,
            "reviewer_user_id": assignment.reviewer_user_id,
            "role": assignment.role,
            "assigned_at": _ser_dt(assignment.assigned_at),
        }

    def _serialize_attestation(self, row: GovernanceAttestation) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "ai_system_id": str(row.ai_system_id) if row.ai_system_id else None,
            "agent_version_id": str(row.agent_version_id)
            if row.agent_version_id
            else None,
            "attestation_type": row.attestation_type,
            "statement": row.statement,
            "scope": row.scope,
            "actor": row.actor,
            "actor_role": row.actor_role,
            "evidence_refs": row.evidence_refs,
            "valid_until": _ser_dt(row.valid_until),
            "created_at": _ser_dt(row.created_at),
        }

    def _serialize_exception(self, row: GovernanceException) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "ai_system_id": str(row.ai_system_id),
            "agent_version_id": str(row.agent_version_id)
            if row.agent_version_id
            else None,
            "control_requirement_id": str(row.control_requirement_id)
            if row.control_requirement_id
            else None,
            "scope": row.scope,
            "business_justification": row.business_justification,
            "risk": row.risk,
            "compensating_controls": row.compensating_controls,
            "evidence_refs": row.evidence_refs,
            "status": row.status,
            "requester": row.requester,
            "approver": row.approver,
            "decision_reason": row.decision_reason,
            "valid_until": _ser_dt(row.valid_until),
            "created_at": _ser_dt(row.created_at),
            "decided_at": _ser_dt(row.decided_at),
            "revoked_at": _ser_dt(row.revoked_at),
        }

    def _serialize_incident(self, incident: AIIncident) -> dict[str, Any]:
        return {
            "id": str(incident.id),
            "ai_system_id": str(incident.ai_system_id),
            "agent_version_id": str(incident.agent_version_id)
            if incident.agent_version_id
            else None,
            "runtime_identity_id": str(incident.runtime_identity_id)
            if incident.runtime_identity_id
            else None,
            "trajectory_id": str(incident.trajectory_id)
            if incident.trajectory_id
            else None,
            "severity": incident.severity,
            "category": incident.category,
            "status": incident.status,
            "title": incident.title,
            "description": incident.description,
            "source": incident.source,
            "source_ref": incident.source_ref,
            "detected_at": _ser_dt(incident.detected_at),
            "reported_by": incident.reported_by,
            "incident_manager": incident.incident_manager,
            "containment_action": incident.containment_action,
            "containment_ref": incident.containment_ref,
            "root_cause": incident.root_cause,
            "corrective_actions_summary": incident.corrective_actions_summary,
            "evidence_refs": incident.evidence_refs,
            "external_ticket_ref": incident.external_ticket_ref,
            "closed_at": _ser_dt(incident.closed_at),
            "created_at": _ser_dt(incident.created_at),
            "updated_at": _ser_dt(incident.updated_at),
        }

    def _serialize_corrective_action(
        self, action: IncidentCorrectiveAction
    ) -> dict[str, Any]:
        return {
            "id": str(action.id),
            "incident_id": str(action.incident_id),
            "description": action.description,
            "owner": action.owner,
            "due_at": _ser_dt(action.due_at),
            "status": action.status,
            "evidence": action.evidence,
            "created_at": _ser_dt(action.created_at),
            "completed_at": _ser_dt(action.completed_at),
        }

    def _serialize_evidence_package(
        self, package: GovernanceEvidencePackage, *, include_manifest: bool = True
    ) -> dict[str, Any]:
        data = {
            "id": str(package.id),
            "ai_system_id": str(package.ai_system_id) if package.ai_system_id else None,
            "agent_id": str(package.agent_id) if package.agent_id else None,
            "agent_version_id": str(package.agent_version_id)
            if package.agent_version_id
            else None,
            "review_id": str(package.review_id) if package.review_id else None,
            "incident_id": str(package.incident_id) if package.incident_id else None,
            "period_start": _ser_dt(package.period_start),
            "period_end": _ser_dt(package.period_end),
            "generated_by": package.generated_by,
            "generated_at": _ser_dt(package.generated_at),
            "package_digest": package.package_digest,
            "has_report_html": bool(package.report_html),
        }
        if include_manifest:
            data["manifest"] = package.manifest
            data["report_html"] = package.report_html
        return data

    def _serialize_periodic_schedule(
        self, schedule: PeriodicReviewSchedule
    ) -> dict[str, Any]:
        return {
            "id": str(schedule.id),
            "ai_system_id": str(schedule.ai_system_id),
            "frequency_days": schedule.frequency_days,
            "next_due_at": _ser_dt(schedule.next_due_at),
            "last_completed_at": _ser_dt(schedule.last_completed_at),
            "enabled": schedule.enabled,
            "created_by": schedule.created_by,
            "created_at": _ser_dt(schedule.created_at),
        }

    def _serialize_pilot(self, pilot: Pilot) -> dict[str, Any]:
        return {
            "id": str(pilot.id),
            "name": pilot.name,
            "description": pilot.description,
            "sponsor": pilot.sponsor,
            "start_at": _ser_dt(pilot.start_at),
            "end_at": _ser_dt(pilot.end_at),
            "status": pilot.status,
            "success_criteria": pilot.success_criteria,
            "readiness_gate_id": str(pilot.readiness_gate_id)
            if pilot.readiness_gate_id
            else None,
            "created_by": pilot.created_by,
            "created_at": _ser_dt(pilot.created_at),
            "updated_at": _ser_dt(pilot.updated_at),
        }

    def _serialize_pilot_ai_system(self, link: PilotAISystem) -> dict[str, Any]:
        return {
            "id": str(link.id),
            "pilot_id": str(link.pilot_id),
            "ai_system_id": str(link.ai_system_id),
            "agent_version_id": str(link.agent_version_id)
            if link.agent_version_id
            else None,
            "added_at": _ser_dt(link.added_at),
        }
