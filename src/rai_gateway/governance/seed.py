"""Deterministic reference pilot fixtures for the single instance."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from rai_gateway.governance.controls import ensure_pilot_control_framework
from rai_gateway.governance.domain import (
    GovernanceRole,
    MembershipStatus,
    PilotOrgStatus,
)
from rai_gateway.governance.service import GovernanceService
from rai_gateway.models.governance import Pilot
from rai_gateway.models.registry import AISystem

# Deterministic seed user ids for all governance roles.
SEED_USERS: dict[str, str] = {
    GovernanceRole.ORGANIZATION_ADMIN.value: "seed-org-admin",
    GovernanceRole.AI_SYSTEM_OWNER.value: "seed-ai-system-owner",
    GovernanceRole.BUSINESS_OWNER.value: "seed-business-owner",
    GovernanceRole.RAI_OFFICER.value: "seed-rai-officer",
    GovernanceRole.RISK_COMPLIANCE_REVIEWER.value: "seed-risk-compliance",
    GovernanceRole.BUSINESS_APPROVER.value: "seed-business-approver",
    GovernanceRole.TECHNICAL_OWNER.value: "seed-technical-owner",
    GovernanceRole.AUDITOR.value: "seed-auditor",
    GovernanceRole.INCIDENT_MANAGER.value: "seed-incident-manager",
}


def _find_system_by_name_or_key(
    db: Session, *, names: list[str], keys: list[str]
) -> AISystem | None:
    for key in keys:
        row = db.query(AISystem).filter(AISystem.system_key == key).first()
        if row:
            return row
    for name in names:
        row = (
            db.query(AISystem)
            .filter(AISystem.name.ilike(f"%{name}%"))
            .order_by(AISystem.created_at.asc())
            .first()
        )
        if row:
            return row
    return None


def _ensure_memberships(svc: GovernanceService, *, created_by: str) -> dict[str, str]:
    membership_ids: dict[str, str] = {}
    for role, user_id in SEED_USERS.items():
        membership = svc.create_membership(
            user_id=user_id,
            role=role,
            created_by=created_by,
            status=MembershipStatus.ACTIVE.value,
        )
        membership_ids[role] = membership["id"]
    return membership_ids


def _seed_system(
    svc: GovernanceService,
    db: Session,
    *,
    names: list[str],
    keys: list[str],
    created_by: str,
    memberships: dict[str, str],
    classification: dict[str, Any],
) -> dict[str, Any] | None:
    system = _find_system_by_name_or_key(db, names=names, keys=keys)
    if system is None:
        return None
    link = svc.link_ai_system(system.id, created_by)
    svc.upsert_classification(system.id, updated_by=created_by, **classification)
    svc.upsert_accountability(
        system.id,
        created_by=created_by,
        business_owner_membership_id=UUID(
            memberships[GovernanceRole.BUSINESS_OWNER.value]
        ),
        technical_owner_membership_id=UUID(
            memberships[GovernanceRole.TECHNICAL_OWNER.value]
        ),
        rai_officer_membership_id=UUID(memberships[GovernanceRole.RAI_OFFICER.value]),
        risk_owner_membership_id=UUID(
            memberships[GovernanceRole.RISK_COMPLIANCE_REVIEWER.value]
        ),
        incident_owner_membership_id=UUID(
            memberships[GovernanceRole.INCIDENT_MANAGER.value]
        ),
        enforce_sod=True,
    )
    return link


def _ensure_pilot(
    svc: GovernanceService,
    db: Session,
    *,
    name: str,
    created_by: str,
    description: str,
    sponsor: str,
    success_criteria: dict[str, Any],
    system: AISystem | None,
) -> dict[str, Any]:
    row = db.query(Pilot).filter(Pilot.name == name).first()
    if row is None:
        pilot = svc.create_pilot(
            name=name,
            created_by=created_by,
            description=description,
            sponsor=sponsor,
            success_criteria=success_criteria,
            status=PilotOrgStatus.PLANNING.value,
        )
    else:
        pilot = svc.get_pilot(row.id)
    if system is not None:
        svc.add_ai_system_to_pilot(UUID(pilot["id"]), system.id)
    return pilot


def seed_reference_pilots(db: Session) -> dict[str, Any]:
    """Seed sample systems and pilots on this instance.

    Does not create an organization row. Links existing AI systems when they
    are already present.
    """
    created_by = "system:wp8-seed"
    framework = ensure_pilot_control_framework(db, created_by=created_by)
    svc = GovernanceService(db)
    svc.get_governance_profile()
    memberships = _ensure_memberships(svc, created_by=created_by)

    sales_system = _find_system_by_name_or_key(
        db,
        names=["WhatsApp AI Sales", "Sales AI", "Sales Platform"],
        keys=["whatsapp-ai-sales-platform", "sales-ai", "acme-sales-ai"],
    )
    sales_link = _seed_system(
        svc,
        db,
        names=["WhatsApp AI Sales", "Sales AI", "Sales Platform"],
        keys=["whatsapp-ai-sales-platform", "sales-ai", "acme-sales-ai"],
        created_by=created_by,
        memberships=memberships,
        classification={
            "business_criticality": "HIGH",
            "external_facing": True,
            "consequential_actions": True,
            "personal_data": True,
            "production": True,
            "customer_citizen_impact": "CUSTOMER",
        },
    )
    sales_pilot = _ensure_pilot(
        svc,
        db,
        name="Acme Sales AI Pilot",
        created_by=created_by,
        description="Reference SaaS sales AI bot operating-model pilot",
        sponsor=SEED_USERS[GovernanceRole.BUSINESS_OWNER.value],
        success_criteria={
            "consequential_actions_governed": True,
            "assurance_valid": True,
            "incident_process_established": True,
        },
        system=sales_system,
    )

    citizen_system = _find_system_by_name_or_key(
        db,
        names=["Citizen Service", "Citizen Support", "Public Service Assistant"],
        keys=["citizen-service-assistant", "citizen-support-agent"],
    )
    citizen_link = _seed_system(
        svc,
        db,
        names=["Citizen Service", "Citizen Support", "Public Service Assistant"],
        keys=["citizen-service-assistant", "citizen-support-agent"],
        created_by=created_by,
        memberships=memberships,
        classification={
            "business_criticality": "HIGH",
            "external_facing": True,
            "consequential_actions": False,
            "personal_data": True,
            "production": True,
            "customer_citizen_impact": "CITIZEN",
            "regulated_process": True,
        },
    )
    citizen_pilot = _ensure_pilot(
        svc,
        db,
        name="Citizen Service Assistant Pilot",
        created_by=created_by,
        description="Neutral government / regulated-enterprise pilot fixture",
        sponsor=SEED_USERS[GovernanceRole.ORGANIZATION_ADMIN.value],
        success_criteria={
            "accountability_assigned": True,
            "privacy_safety_evaluation": True,
            "periodic_review_enabled": True,
        },
        system=citizen_system,
    )

    return {
        "control_framework": {
            "id": str(framework.id),
            "framework_key": framework.framework_key,
            "name": framework.name,
        },
        "memberships": memberships,
        "acme": {
            "ai_system": sales_link,
            "pilot": sales_pilot,
            "system_linked": sales_system is not None,
        },
        "public_services": {
            "ai_system": citizen_link,
            "pilot": citizen_pilot,
            "system_linked": citizen_system is not None,
        },
        "seed_users": SEED_USERS,
    }
