"""SQLAlchemy models for WP8 governance / pilot operating model."""

from __future__ import annotations

import uuid

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from rai_gateway.models.database import Base


class OrganizationGovernanceProfile(Base):
    """Singleton instance profile. This edition has one organization, not a tenant."""

    __tablename__ = "organization_governance_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    singleton_key = Column(String, nullable=False, unique=True, default="default")
    name = Column(String, nullable=False, default="Organization")
    description = Column(Text, nullable=True)
    logo = Column(Text, nullable=True)
    legal_name = Column(String, nullable=True)
    organization_type = Column(String, nullable=False, default="PRIVATE_ENTERPRISE")
    sector = Column(String, nullable=True)
    jurisdiction = Column(String, nullable=True)
    regulatory_context = Column(JSON, nullable=True)
    risk_appetite = Column(String, nullable=True)
    governance_owner = Column(String, nullable=True)
    assurance_owner = Column(String, nullable=True)
    incident_owner = Column(String, nullable=True)
    default_review_frequency_days = Column(Integer, nullable=False, default=90)
    evidence_retention_policy = Column(JSON, nullable=True)
    pilot_status = Column(String, nullable=False, default="PLANNING", index=True)
    updated_by = Column(String, nullable=True)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Department(Base):
    __tablename__ = "departments"
    __table_args__ = (UniqueConstraint("name", name="uq_department_name"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class OrganizationMembership(Base):
    __tablename__ = "organization_memberships"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "role",
            name="uq_membership_user_role",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, nullable=False, index=True)
    role = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="ACTIVE", index=True)
    valid_from = Column(DateTime(timezone=True), server_default=func.now())
    valid_until = Column(DateTime(timezone=True), nullable=True)
    department_id = Column(
        UUID(as_uuid=True),
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    department = relationship("Department")


class AISystemAccountability(Base):
    __tablename__ = "ai_system_accountabilities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ai_system_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ai_systems.id"),
        nullable=False,
        unique=True,
        index=True,
    )
    business_owner_membership_id = Column(
        UUID(as_uuid=True), ForeignKey("organization_memberships.id"), nullable=True
    )
    technical_owner_membership_id = Column(
        UUID(as_uuid=True), ForeignKey("organization_memberships.id"), nullable=True
    )
    rai_officer_membership_id = Column(
        UUID(as_uuid=True), ForeignKey("organization_memberships.id"), nullable=True
    )
    risk_owner_membership_id = Column(
        UUID(as_uuid=True), ForeignKey("organization_memberships.id"), nullable=True
    )
    incident_owner_membership_id = Column(
        UUID(as_uuid=True), ForeignKey("organization_memberships.id"), nullable=True
    )
    effective_from = Column(DateTime(timezone=True), server_default=func.now())
    effective_until = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AISystemGovernanceClassification(Base):
    __tablename__ = "ai_system_governance_classifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ai_system_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ai_systems.id"),
        nullable=False,
        unique=True,
        index=True,
    )
    business_criticality = Column(String, nullable=True)
    data_sensitivity = Column(String, nullable=True)
    customer_citizen_impact = Column(String, nullable=True)
    financial_impact = Column(String, nullable=True)
    autonomy_level = Column(String, nullable=True)
    external_facing = Column(Boolean, nullable=False, default=False)
    consequential_actions = Column(Boolean, nullable=False, default=False)
    personal_data = Column(Boolean, nullable=False, default=False)
    regulated_process = Column(Boolean, nullable=False, default=False)
    human_oversight_requirement = Column(String, nullable=True)
    production = Column(Boolean, nullable=False, default=False)
    updated_by = Column(String, nullable=True)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ControlFramework(Base):
    __tablename__ = "control_frameworks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    framework_key = Column(String, nullable=False, unique=True, index=True)
    name = Column(String, nullable=False)
    version = Column(String, nullable=False, default="1.0")
    description = Column(Text, nullable=True)
    is_internal = Column(Boolean, nullable=False, default=True)
    published = Column(Boolean, nullable=False, default=True)
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    objectives = relationship(
        "ControlObjective",
        back_populates="framework",
        cascade="all, delete-orphan",
    )


class ControlObjective(Base):
    __tablename__ = "control_objectives"
    __table_args__ = (
        UniqueConstraint("framework_id", "code", name="uq_control_objective_code"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    framework_id = Column(
        UUID(as_uuid=True),
        ForeignKey("control_frameworks.id"),
        nullable=False,
        index=True,
    )
    code = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False)
    category = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    framework = relationship("ControlFramework", back_populates="objectives")
    requirements = relationship(
        "ControlRequirement",
        back_populates="objective",
        cascade="all, delete-orphan",
    )


class ControlRequirement(Base):
    __tablename__ = "control_requirements"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    objective_id = Column(
        UUID(as_uuid=True),
        ForeignKey("control_objectives.id"),
        nullable=False,
        index=True,
    )
    requirement_key = Column(String, nullable=False, index=True)
    statement = Column(Text, nullable=False)
    default_applicability = Column(String, nullable=False, default="CONDITIONAL")
    applicability_rules = Column(JSON, nullable=True)
    automated_check = Column(String, nullable=True)
    non_waivable = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    objective = relationship("ControlObjective", back_populates="requirements")


class ControlMapping(Base):
    __tablename__ = "control_mappings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    internal_requirement_id = Column(
        UUID(as_uuid=True),
        ForeignKey("control_requirements.id"),
        nullable=False,
        index=True,
    )
    external_framework = Column(String, nullable=False, index=True)
    external_requirement_id = Column(String, nullable=False)
    external_requirement_title = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ControlAssessment(Base):
    __tablename__ = "control_assessments"
    __table_args__ = (
        UniqueConstraint(
            "ai_system_id",
            "control_requirement_id",
            "agent_version_id",
            name="uq_control_assessment_scope",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ai_system_id = Column(
        UUID(as_uuid=True), ForeignKey("ai_systems.id"), nullable=False, index=True
    )
    agent_version_id = Column(
        UUID(as_uuid=True), ForeignKey("agent_versions.id"), nullable=True, index=True
    )
    control_requirement_id = Column(
        UUID(as_uuid=True),
        ForeignKey("control_requirements.id"),
        nullable=False,
        index=True,
    )
    applicability = Column(String, nullable=False, default="REQUIRED")
    applicability_reason = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="NOT_ASSESSED", index=True)
    assessment_method = Column(String, nullable=False, default="MANUAL")
    evidence_refs = Column(JSON, nullable=True)
    assessed_by = Column(String, nullable=True)
    assessed_at = Column(DateTime(timezone=True), nullable=True)
    valid_until = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class GovernanceReview(Base):
    __tablename__ = "governance_reviews"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ai_system_id = Column(
        UUID(as_uuid=True), ForeignKey("ai_systems.id"), nullable=False, index=True
    )
    agent_version_id = Column(
        UUID(as_uuid=True), ForeignKey("agent_versions.id"), nullable=True, index=True
    )
    review_type = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="REQUESTED", index=True)
    requested_by = Column(String, nullable=False)
    due_at = Column(DateTime(timezone=True), nullable=True)
    decision = Column(String, nullable=True)
    decision_reason = Column(Text, nullable=True)
    conditions = Column(JSON, nullable=True)
    evidence_snapshot = Column(JSON, nullable=True)
    checklist = Column(JSON, nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    decided_by = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    assignments = relationship(
        "GovernanceReviewAssignment",
        back_populates="review",
        cascade="all, delete-orphan",
    )


class GovernanceReviewAssignment(Base):
    __tablename__ = "governance_review_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    review_id = Column(
        UUID(as_uuid=True),
        ForeignKey("governance_reviews.id"),
        nullable=False,
        index=True,
    )
    membership_id = Column(
        UUID(as_uuid=True), ForeignKey("organization_memberships.id"), nullable=True
    )
    reviewer_user_id = Column(String, nullable=False, index=True)
    role = Column(String, nullable=True)
    assigned_at = Column(DateTime(timezone=True), server_default=func.now())

    review = relationship("GovernanceReview", back_populates="assignments")


class GovernanceAttestation(Base):
    __tablename__ = "governance_attestations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ai_system_id = Column(
        UUID(as_uuid=True), ForeignKey("ai_systems.id"), nullable=True, index=True
    )
    agent_version_id = Column(
        UUID(as_uuid=True), ForeignKey("agent_versions.id"), nullable=True
    )
    attestation_type = Column(String, nullable=False, index=True)
    statement = Column(Text, nullable=False)
    scope = Column(JSON, nullable=True)
    actor = Column(String, nullable=False)
    actor_role = Column(String, nullable=True)
    evidence_refs = Column(JSON, nullable=True)
    valid_until = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class GovernanceException(Base):
    __tablename__ = "governance_exceptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ai_system_id = Column(
        UUID(as_uuid=True), ForeignKey("ai_systems.id"), nullable=False, index=True
    )
    agent_version_id = Column(
        UUID(as_uuid=True), ForeignKey("agent_versions.id"), nullable=True
    )
    control_requirement_id = Column(
        UUID(as_uuid=True), ForeignKey("control_requirements.id"), nullable=True
    )
    scope = Column(JSON, nullable=True)
    business_justification = Column(Text, nullable=False)
    risk = Column(String, nullable=True)
    compensating_controls = Column(JSON, nullable=True)
    evidence_refs = Column(JSON, nullable=True)
    status = Column(String, nullable=False, default="REQUESTED", index=True)
    requester = Column(String, nullable=False)
    approver = Column(String, nullable=True)
    decision_reason = Column(Text, nullable=True)
    valid_until = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    decided_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)


class AIIncident(Base):
    __tablename__ = "ai_incidents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ai_system_id = Column(
        UUID(as_uuid=True), ForeignKey("ai_systems.id"), nullable=False, index=True
    )
    agent_version_id = Column(
        UUID(as_uuid=True), ForeignKey("agent_versions.id"), nullable=True, index=True
    )
    runtime_identity_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    trajectory_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    severity = Column(String, nullable=False, default="MEDIUM", index=True)
    category = Column(String, nullable=False, default="OTHER", index=True)
    status = Column(String, nullable=False, default="OPEN", index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    source = Column(String, nullable=False, default="MANUAL")
    source_ref = Column(String, nullable=True)
    detected_at = Column(DateTime(timezone=True), server_default=func.now())
    reported_by = Column(String, nullable=False)
    incident_manager = Column(String, nullable=True)
    containment_action = Column(String, nullable=True)
    containment_ref = Column(JSON, nullable=True)
    root_cause = Column(Text, nullable=True)
    corrective_actions_summary = Column(Text, nullable=True)
    evidence_refs = Column(JSON, nullable=True)
    external_ticket_ref = Column(String, nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    corrective_actions = relationship(
        "IncidentCorrectiveAction",
        back_populates="incident",
        cascade="all, delete-orphan",
    )
    transitions = relationship(
        "IncidentTransition",
        back_populates="incident",
        cascade="all, delete-orphan",
        order_by="IncidentTransition.created_at",
    )


class IncidentTransition(Base):
    """Append-only incident lifecycle events."""

    __tablename__ = "incident_transitions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id = Column(
        UUID(as_uuid=True), ForeignKey("ai_incidents.id"), nullable=False, index=True
    )
    from_status = Column(String, nullable=True)
    to_status = Column(String, nullable=False)
    actor = Column(String, nullable=False)
    reason = Column(Text, nullable=True)
    metadata_ = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    incident = relationship("AIIncident", back_populates="transitions")


class IncidentCorrectiveAction(Base):
    __tablename__ = "incident_corrective_actions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id = Column(
        UUID(as_uuid=True), ForeignKey("ai_incidents.id"), nullable=False, index=True
    )
    description = Column(Text, nullable=False)
    owner = Column(String, nullable=False)
    due_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String, nullable=False, default="OPEN", index=True)
    evidence = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    incident = relationship("AIIncident", back_populates="corrective_actions")


class GovernanceEvidencePackage(Base):
    __tablename__ = "governance_evidence_packages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ai_system_id = Column(
        UUID(as_uuid=True), ForeignKey("ai_systems.id"), nullable=True, index=True
    )
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=True)
    agent_version_id = Column(
        UUID(as_uuid=True), ForeignKey("agent_versions.id"), nullable=True
    )
    review_id = Column(
        UUID(as_uuid=True), ForeignKey("governance_reviews.id"), nullable=True
    )
    incident_id = Column(
        UUID(as_uuid=True), ForeignKey("ai_incidents.id"), nullable=True
    )
    period_start = Column(DateTime(timezone=True), nullable=True)
    period_end = Column(DateTime(timezone=True), nullable=True)
    generated_by = Column(String, nullable=False)
    generated_at = Column(DateTime(timezone=True), server_default=func.now())
    manifest = Column(JSON, nullable=False)
    package_digest = Column(String, nullable=False, index=True)
    report_html = Column(Text, nullable=True)


class PeriodicReviewSchedule(Base):
    __tablename__ = "periodic_review_schedules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ai_system_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ai_systems.id"),
        nullable=False,
        unique=True,
        index=True,
    )
    frequency_days = Column(Integer, nullable=False, default=90)
    next_due_at = Column(DateTime(timezone=True), nullable=False)
    last_completed_at = Column(DateTime(timezone=True), nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Pilot(Base):
    __tablename__ = "pilots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    sponsor = Column(String, nullable=True)
    start_at = Column(DateTime(timezone=True), nullable=True)
    end_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String, nullable=False, default="PLANNING", index=True)
    success_criteria = Column(JSON, nullable=True)
    readiness_gate_id = Column(UUID(as_uuid=True), nullable=True)
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    ai_systems = relationship(
        "PilotAISystem",
        back_populates="pilot",
        cascade="all, delete-orphan",
    )
    readiness_evaluations = relationship(
        "PilotReadinessEvaluation",
        back_populates="pilot",
        cascade="all, delete-orphan",
    )


class PilotAISystem(Base):
    __tablename__ = "pilot_ai_systems"
    __table_args__ = (
        UniqueConstraint("pilot_id", "ai_system_id", name="uq_pilot_ai_system"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pilot_id = Column(
        UUID(as_uuid=True), ForeignKey("pilots.id"), nullable=False, index=True
    )
    ai_system_id = Column(
        UUID(as_uuid=True), ForeignKey("ai_systems.id"), nullable=False, index=True
    )
    agent_version_id = Column(
        UUID(as_uuid=True), ForeignKey("agent_versions.id"), nullable=True
    )
    added_at = Column(DateTime(timezone=True), server_default=func.now())

    pilot = relationship("Pilot", back_populates="ai_systems")


class PilotReadinessEvaluation(Base):
    __tablename__ = "pilot_readiness_evaluations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pilot_id = Column(
        UUID(as_uuid=True), ForeignKey("pilots.id"), nullable=True, index=True
    )
    ai_system_id = Column(
        UUID(as_uuid=True), ForeignKey("ai_systems.id"), nullable=True, index=True
    )
    agent_version_id = Column(
        UUID(as_uuid=True), ForeignKey("agent_versions.id"), nullable=True
    )
    decision = Column(String, nullable=False, index=True)
    dimensions = Column(JSON, nullable=False)
    gaps = Column(JSON, nullable=True)
    conditions = Column(JSON, nullable=True)
    evaluated_by = Column(String, nullable=False)
    evaluated_at = Column(DateTime(timezone=True), server_default=func.now())

    pilot = relationship("Pilot", back_populates="readiness_evaluations")
