"""Instance onboarding state and checklist service."""

from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from rai_gateway.models.governance import (
    ControlAssessment,
    OrganizationGovernanceProfile,
    OrganizationMembership,
)
from rai_gateway.models.productization import (
    OrganizationOnboarding,
    SdkDecisionRecord,
    SdkIntegration,
)
from rai_gateway.models.registry import AgentVersion, AgentVersionDependency, AISystem

_SINGLETON_KEY = "default"


class OnboardingStatus(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    INTEGRATED = "INTEGRATED"
    READY = "READY"


ONBOARDING_STEP_DEFS: list[tuple[str, str]] = [
    ("organization_profile", "Organization Profile"),
    ("team_roles", "Team & Governance Roles"),
    ("first_ai_system", "Register First AI System"),
    ("agent_version", "Add Agent + Version"),
    ("resources", "Add Model / MCP / Tools / Data Sources"),
    ("first_policies", "Configure First Policies"),
    ("choose_integration", "Choose Integration"),
    ("runtime_identity", "Create Runtime Identity"),
    ("connect_application", "Connect Application"),
    ("test_connection", "Test Connection"),
    ("first_governed_action", "Run First Governed Action"),
    ("inspect_trajectory", "Inspect First Trajectory"),
    ("production_readiness", "Production Readiness"),
]

LEGACY_ONBOARDING_STEPS: list[tuple[str, str]] = [
    ("organization", "Create Organization"),
    ("admin", "Invite Organization Admin"),
    ("ai_system", "Register first AI System"),
    ("integration", "Create SDK Integration"),
]

ONBOARDING_STEP_IDS = {step_id for step_id, _ in ONBOARDING_STEP_DEFS}


class OnboardingError(Exception):
    def __init__(self, message: str, *, http_status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.http_status = http_status


class OnboardingService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_record(self) -> OrganizationOnboarding | None:
        return (
            self._db.query(OrganizationOnboarding)
            .filter(OrganizationOnboarding.singleton_key == _SINGLETON_KEY)
            .first()
        )

    def get_or_create(
        self,
        *,
        status: str = OnboardingStatus.NOT_STARTED.value,
        current_step: str = "organization_profile",
        completed_steps: list[str] | None = None,
    ) -> OrganizationOnboarding:
        record = self.get_record()
        if record:
            return record
        record = OrganizationOnboarding(
            singleton_key=_SINGLETON_KEY,
            status=status,
            current_step=current_step,
            completed_steps=completed_steps or [],
        )
        self._db.add(record)
        self._db.flush()
        return record

    def serialize(self, record: OrganizationOnboarding) -> dict[str, Any]:
        return {
            "current_step": record.current_step,
            "completed_steps": list(record.completed_steps or []),
            "first_ai_system_id": str(record.first_ai_system_id)
            if record.first_ai_system_id
            else None,
            "first_integration_id": str(record.first_integration_id)
            if record.first_integration_id
            else None,
            "first_trajectory_id": str(record.first_trajectory_id)
            if record.first_trajectory_id
            else None,
            "status": record.status,
            "welcome_completed": record.welcome_completed_at is not None,
            "welcome_completed_at": record.welcome_completed_at.isoformat()
            if record.welcome_completed_at
            else None,
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "updated_at": record.updated_at.isoformat() if record.updated_at else None,
        }

    def update(
        self,
        *,
        current_step: str | None = None,
        complete_step: str | None = None,
        completed_steps: list[str] | None = None,
        first_ai_system_id: UUID | None = None,
        first_integration_id: UUID | None = None,
        first_trajectory_id: UUID | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        record = self.get_or_create()

        if current_step is not None:
            if current_step not in ONBOARDING_STEP_IDS:
                raise OnboardingError(f"Unknown onboarding step: {current_step}")
            record.current_step = current_step
            if record.status == OnboardingStatus.NOT_STARTED.value:
                record.status = OnboardingStatus.IN_PROGRESS.value

        if completed_steps is not None:
            record.completed_steps = list(completed_steps)

        if complete_step is not None:
            if complete_step not in ONBOARDING_STEP_IDS:
                raise OnboardingError(f"Unknown onboarding step: {complete_step}")
            steps = set(record.completed_steps or [])
            steps.add(complete_step)
            record.completed_steps = sorted(steps)
            if record.status == OnboardingStatus.NOT_STARTED.value:
                record.status = OnboardingStatus.IN_PROGRESS.value

        if first_ai_system_id is not None:
            record.first_ai_system_id = first_ai_system_id
        if first_integration_id is not None:
            record.first_integration_id = first_integration_id
        if first_trajectory_id is not None:
            record.first_trajectory_id = first_trajectory_id

        if status is not None:
            if status not in {item.value for item in OnboardingStatus}:
                raise OnboardingError(f"Invalid onboarding status: {status}")
            record.status = status

        self._db.commit()
        self._db.refresh(record)
        return self.build_checklist(record)

    def build_checklist(
        self,
        record: OrganizationOnboarding | None = None,
    ) -> dict[str, Any]:
        if record is None:
            record = self.get_record()

        persisted_completed = set(record.completed_steps or []) if record else set()
        computed = self._compute_step_completion(record)

        steps: list[dict[str, Any]] = []
        blocked: list[str] = []
        for step_id, label in ONBOARDING_STEP_DEFS:
            done = step_id in persisted_completed or computed.get(step_id, False)
            blocked_reason = None
            if not done and step_id in computed and computed.get(f"{step_id}_blocked"):
                blocked_reason = computed[f"{step_id}_blocked"]
                blocked.append(step_id)
            steps.append(
                {
                    "id": step_id,
                    "label": label,
                    "done": done,
                    "blocked": blocked_reason is not None,
                    "blocked_reason": blocked_reason,
                }
            )

        legacy_steps = self._legacy_steps()

        completed_count = sum(1 for step in steps if step["done"])
        next_step = next((step for step in steps if not step["done"]), None)
        onboarding_payload = (
            self.serialize(record)
            if record
            else {
                "current_step": "organization_profile",
                "completed_steps": [],
                "first_ai_system_id": None,
                "first_integration_id": None,
                "first_trajectory_id": None,
                "status": OnboardingStatus.NOT_STARTED.value,
                "welcome_completed": False,
                "welcome_completed_at": None,
                "created_at": None,
                "updated_at": None,
            }
        )

        status = onboarding_payload["status"]
        if completed_count == len(steps):
            status = OnboardingStatus.READY.value
        elif computed.get("integrated"):
            status = OnboardingStatus.INTEGRATED.value
        elif completed_count > 0 or record:
            status = OnboardingStatus.IN_PROGRESS.value

        return {
            "onboarding": {**onboarding_payload, "status": status},
            "steps": steps,
            "legacy_steps": legacy_steps,
            "complete": all(step["done"] for step in steps),
            "legacy_complete": all(step["done"] for step in legacy_steps),
            "progress": {
                "completed": completed_count,
                "total": len(steps),
            },
            "next_recommended_action": next_step["label"] if next_step else None,
            "blocked_steps": blocked,
        }

    def _legacy_steps(self) -> list[dict[str, Any]]:
        systems = self._db.query(AISystem).count()
        integrations = self._db.query(SdkIntegration).count()
        admins = (
            self._db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.role == "ORGANIZATION_ADMIN",
                OrganizationMembership.status == "ACTIVE",
            )
            .count()
        )
        profile = (
            self._db.query(OrganizationGovernanceProfile)
            .filter(OrganizationGovernanceProfile.singleton_key == _SINGLETON_KEY)
            .first()
        )
        legacy_done = {
            "organization": profile is not None,
            "admin": admins > 0,
            "ai_system": systems > 0,
            "integration": integrations > 0,
        }
        return [
            {"id": step_id, "label": label, "done": legacy_done.get(step_id, False)}
            for step_id, label in LEGACY_ONBOARDING_STEPS
        ]

    def _compute_step_completion(
        self,
        record: OrganizationOnboarding | None,
    ) -> dict[str, Any]:
        profile = (
            self._db.query(OrganizationGovernanceProfile)
            .filter(OrganizationGovernanceProfile.singleton_key == _SINGLETON_KEY)
            .first()
        )
        memberships = (
            self._db.query(OrganizationMembership)
            .filter(OrganizationMembership.status == "ACTIVE")
            .all()
        )
        membership_roles = {row.role for row in memberships}

        systems = self._db.query(AISystem).all()
        system_ids = [row.id for row in systems]

        agent_versions = 0
        resources = 0
        if system_ids:
            from rai_gateway.models.registry import Agent

            agents = (
                self._db.query(Agent).filter(Agent.ai_system_id.in_(system_ids)).all()
            )
            agent_ids = [row.id for row in agents]
            if agent_ids:
                agent_versions = (
                    self._db.query(AgentVersion)
                    .filter(AgentVersion.agent_id.in_(agent_ids))
                    .count()
                )
                version_ids = [
                    row.id
                    for row in self._db.query(AgentVersion)
                    .filter(AgentVersion.agent_id.in_(agent_ids))
                    .all()
                ]
                if version_ids:
                    resources = (
                        self._db.query(AgentVersionDependency)
                        .filter(
                            AgentVersionDependency.agent_version_id.in_(version_ids)
                        )
                        .count()
                    )

        integrations = self._db.query(SdkIntegration).all()
        policies = self._db.query(ControlAssessment).count()

        runtime_identities = 0
        if integrations:
            runtime_identities = len(
                {
                    row.runtime_identity_id
                    for row in integrations
                    if row.runtime_identity_id
                }
            )

        connected = any(row.last_heartbeat_at is not None for row in integrations)
        tested = any(
            (row.verification_status or "").upper()
            in {"VERIFIED", "CONNECTED", "TESTED"}
            for row in integrations
        )
        governed_actions = self._db.query(SdkDecisionRecord).count()
        has_trajectory = record is not None and record.first_trajectory_id is not None

        return {
            "organization_profile": bool(
                profile
                and (profile.sector or profile.jurisdiction or profile.legal_name)
            ),
            "team_roles": "RAI_OFFICER" in membership_roles
            and "ORGANIZATION_ADMIN" in membership_roles,
            "first_ai_system": len(systems) > 0
            or (record is not None and record.first_ai_system_id is not None),
            "agent_version": agent_versions > 0,
            "resources": resources > 0,
            "first_policies": policies > 0,
            "choose_integration": len(integrations) > 0
            or (record is not None and record.first_integration_id is not None),
            "runtime_identity": runtime_identities > 0,
            "connect_application": connected,
            "test_connection": tested or connected,
            "first_governed_action": governed_actions > 0,
            "inspect_trajectory": has_trajectory,
            "production_readiness": record is not None
            and record.status == OnboardingStatus.READY.value,
            "integrated": connected and governed_actions > 0,
        }
