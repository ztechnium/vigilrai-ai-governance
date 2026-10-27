"""SQLAlchemy models for WP7 evaluation, assurance, and deployment gates."""

from __future__ import annotations

import uuid

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
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


class EvaluationSuite(Base):
    """Versioned reusable evaluation suite. Published versions are immutable."""

    __tablename__ = "evaluation_suites"
    __table_args__ = (
        UniqueConstraint(
            "ai_system_id",
            "suite_key",
            "version",
            name="uq_evaluation_suite_key_version",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ai_system_id = Column(
        UUID(as_uuid=True), ForeignKey("ai_systems.id"), nullable=False, index=True
    )
    suite_key = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    category = Column(String, nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    description = Column(Text, nullable=True)
    published = Column(Boolean, nullable=False, default=False, index=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    runner_type = Column(String, nullable=False, default="DETERMINISTIC")
    runner_config = Column(JSON, nullable=True)
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    cases = relationship(
        "EvaluationCase",
        back_populates="suite",
        cascade="all, delete-orphan",
    )


class EvaluationCase(Base):
    __tablename__ = "evaluation_cases"
    __table_args__ = (
        UniqueConstraint(
            "suite_id",
            "case_key",
            name="uq_evaluation_case_key",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    suite_id = Column(
        UUID(as_uuid=True),
        ForeignKey("evaluation_suites.id"),
        nullable=False,
        index=True,
    )
    case_key = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    input_fixture = Column(JSON, nullable=False, default=dict)
    expected_behavior = Column(JSON, nullable=False, default=dict)
    scoring_method = Column(String, nullable=False, default="exact_match")
    threshold = Column(Float, nullable=False, default=1.0)
    failure_severity = Column(String, nullable=False, default="HIGH")
    enabled = Column(Boolean, nullable=False, default=True)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    suite = relationship("EvaluationSuite", back_populates="cases")


class EvaluationRequirement(Base):
    __tablename__ = "evaluation_requirements"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ai_system_id = Column(
        UUID(as_uuid=True), ForeignKey("ai_systems.id"), nullable=False, index=True
    )
    name = Column(String, nullable=False)
    category = Column(String, nullable=False, index=True)
    evaluation_suite_id = Column(
        UUID(as_uuid=True),
        ForeignKey("evaluation_suites.id"),
        nullable=False,
        index=True,
    )
    minimum_score = Column(Float, nullable=False, default=1.0)
    maximum_failed_critical_cases = Column(Integer, nullable=False, default=0)
    required = Column(Boolean, nullable=False, default=True)
    validity_days = Column(Integer, nullable=True)
    environment_scope = Column(String, nullable=False, default="PRODUCTION", index=True)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    # Optional allow-list of runner types that may satisfy this requirement.
    # Empty/null → use category/environment defaults at gate evaluation time.
    accepted_runner_types = Column(JSON, nullable=True)
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class EvaluationPlan(Base):
    __tablename__ = "evaluation_plans"
    __table_args__ = (
        UniqueConstraint(
            "agent_version_id",
            "target_environment",
            "plan_digest",
            name="uq_evaluation_plan_digest",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ai_system_id = Column(
        UUID(as_uuid=True), ForeignKey("ai_systems.id"), nullable=False, index=True
    )
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False)
    agent_version_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_versions.id"),
        nullable=False,
        index=True,
    )
    target_environment = Column(String, nullable=False, index=True)
    requirement_snapshot = Column(JSON, nullable=False, default=list)
    agent_config_digest = Column(String, nullable=True)
    dependency_digest = Column(String, nullable=True)
    plan_digest = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="ACTIVE", index=True)
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"
    __table_args__ = (
        UniqueConstraint(
            "plan_id",
            "suite_id",
            "idempotency_key",
            name="uq_evaluation_run_idempotency",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id = Column(
        UUID(as_uuid=True),
        ForeignKey("evaluation_plans.id"),
        nullable=False,
        index=True,
    )
    ai_system_id = Column(
        UUID(as_uuid=True), ForeignKey("ai_systems.id"), nullable=False, index=True
    )
    agent_version_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_versions.id"),
        nullable=False,
        index=True,
    )
    suite_id = Column(
        UUID(as_uuid=True),
        ForeignKey("evaluation_suites.id"),
        nullable=False,
        index=True,
    )
    suite_version = Column(Integer, nullable=False)
    requirement_id = Column(
        UUID(as_uuid=True),
        ForeignKey("evaluation_requirements.id"),
        nullable=True,
        index=True,
    )
    runner_type = Column(String, nullable=False)
    runner_version = Column(String, nullable=False, default="1.0.0")
    status = Column(String, nullable=False, default="PENDING", index=True)
    score = Column(Float, nullable=True)
    total_cases = Column(Integer, nullable=False, default=0)
    passed_cases = Column(Integer, nullable=False, default=0)
    failed_cases = Column(Integer, nullable=False, default=0)
    critical_failures = Column(Integer, nullable=False, default=0)
    evidence = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    idempotency_key = Column(String, nullable=False, default="default")
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    case_results = relationship(
        "EvaluationCaseResult",
        back_populates="run",
        cascade="all, delete-orphan",
    )


class EvaluationCaseResult(Base):
    __tablename__ = "evaluation_case_results"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "case_key",
            name="uq_evaluation_case_result",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("evaluation_runs.id"),
        nullable=False,
        index=True,
    )
    case_id = Column(
        UUID(as_uuid=True),
        ForeignKey("evaluation_cases.id"),
        nullable=True,
    )
    case_key = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False)
    score = Column(Float, nullable=False, default=0.0)
    severity = Column(String, nullable=True)
    explanation = Column(Text, nullable=True)
    actual_output = Column(JSON, nullable=True)
    evidence_refs = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    run = relationship("EvaluationRun", back_populates="case_results")


class DeploymentGate(Base):
    __tablename__ = "deployment_gates"
    __table_args__ = (
        UniqueConstraint(
            "ai_system_id",
            "name",
            "environment",
            name="uq_deployment_gate_name_env",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ai_system_id = Column(
        UUID(as_uuid=True), ForeignKey("ai_systems.id"), nullable=False, index=True
    )
    name = Column(String, nullable=False)
    environment = Column(String, nullable=False, default="PRODUCTION", index=True)
    description = Column(Text, nullable=True)
    conditions = Column(JSON, nullable=False, default=list)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DeploymentGateEvaluation(Base):
    __tablename__ = "deployment_gate_evaluations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    gate_id = Column(
        UUID(as_uuid=True),
        ForeignKey("deployment_gates.id"),
        nullable=True,
        index=True,
    )
    ai_system_id = Column(
        UUID(as_uuid=True), ForeignKey("ai_systems.id"), nullable=False, index=True
    )
    agent_version_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_versions.id"),
        nullable=False,
        index=True,
    )
    evaluation_plan_id = Column(
        UUID(as_uuid=True),
        ForeignKey("evaluation_plans.id"),
        nullable=True,
    )
    environment = Column(String, nullable=False, index=True)
    decision = Column(String, nullable=False, index=True)
    condition_results = Column(JSON, nullable=False, default=list)
    reason = Column(Text, nullable=True)
    evidence_refs = Column(JSON, nullable=True)
    evaluated_by = Column(String, nullable=False)
    evaluated_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AssuranceRecord(Base):
    __tablename__ = "assurance_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ai_system_id = Column(
        UUID(as_uuid=True), ForeignKey("ai_systems.id"), nullable=False, index=True
    )
    agent_version_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_versions.id"),
        nullable=False,
        index=True,
    )
    environment = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, index=True)
    valid_from = Column(DateTime(timezone=True), nullable=True)
    valid_until = Column(DateTime(timezone=True), nullable=True, index=True)
    gate_evaluation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("deployment_gate_evaluations.id"),
        nullable=True,
    )
    evaluation_plan_id = Column(
        UUID(as_uuid=True),
        ForeignKey("evaluation_plans.id"),
        nullable=True,
    )
    config_digest = Column(String, nullable=True)
    evidence_refs = Column(JSON, nullable=True)
    reason = Column(Text, nullable=True)
    superseded_at = Column(DateTime(timezone=True), nullable=True)
    superseded_by_id = Column(UUID(as_uuid=True), nullable=True)
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class EvaluationWaiver(Base):
    __tablename__ = "evaluation_waivers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ai_system_id = Column(
        UUID(as_uuid=True), ForeignKey("ai_systems.id"), nullable=False, index=True
    )
    agent_version_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_versions.id"),
        nullable=False,
        index=True,
    )
    gate_evaluation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("deployment_gate_evaluations.id"),
        nullable=True,
    )
    environment = Column(String, nullable=False, default="PRODUCTION")
    failed_condition = Column(JSON, nullable=False, default=dict)
    justification = Column(Text, nullable=False)
    compensating_controls = Column(JSON, nullable=True)
    status = Column(String, nullable=False, default="REQUESTED", index=True)
    requester = Column(String, nullable=False)
    approver = Column(String, nullable=True)
    decision_reason = Column(Text, nullable=True)
    valid_until = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    decided_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)


class ReassessmentTrigger(Base):
    __tablename__ = "reassessment_triggers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ai_system_id = Column(
        UUID(as_uuid=True), ForeignKey("ai_systems.id"), nullable=False, index=True
    )
    agent_version_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_versions.id"),
        nullable=False,
        index=True,
    )
    trigger_type = Column(String, nullable=False, index=True)
    change_category = Column(String, nullable=True)
    impacted_categories = Column(JSON, nullable=True)
    status = Column(String, nullable=False, default="REQUIRED", index=True)
    reason = Column(Text, nullable=True)
    source_ref = Column(String, nullable=True)
    created_by = Column(String, nullable=False, default="system")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
