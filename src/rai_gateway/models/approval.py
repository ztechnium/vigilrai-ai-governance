"""SQLAlchemy models for WP3 durable approval + multi-stage plans."""

from __future__ import annotations

import uuid

from sqlalchemy import (
    JSON,
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


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ai_system_id = Column(
        UUID(as_uuid=True), ForeignKey("ai_systems.id"), nullable=False, index=True
    )
    agent_id = Column(
        UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False, index=True
    )
    agent_version_id = Column(
        UUID(as_uuid=True), ForeignKey("agent_versions.id"), nullable=False, index=True
    )
    runtime_identity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_runtime_identities.id"),
        nullable=False,
        index=True,
    )
    delegation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("delegation_grants.id"),
        nullable=True,
        index=True,
    )
    initiating_principal = Column(String, nullable=True, index=True)

    action_type = Column(String, nullable=False, default="tool_invoke")
    integration_type = Column(String, nullable=False)
    integration_id = Column(UUID(as_uuid=True), nullable=True)
    tool_id = Column(UUID(as_uuid=True), ForeignKey("tool_resources.id"), nullable=True)
    model_id = Column(
        UUID(as_uuid=True), ForeignKey("model_resources.id"), nullable=True
    )
    data_source_id = Column(
        UUID(as_uuid=True), ForeignKey("data_sources.id"), nullable=True
    )

    target_type = Column(String, nullable=True)
    target_identifier = Column(String, nullable=True)
    canonical_action_payload = Column(JSON, nullable=False)
    action_digest = Column(String, nullable=False, index=True)

    business_reason = Column(Text, nullable=True)
    risk_tier = Column(String, nullable=True, index=True)
    risk_score = Column(Float, nullable=True)
    approval_policy_reference = Column(String, nullable=True)
    requirement_reason = Column(String, nullable=True)

    status = Column(String, nullable=False, default="PENDING", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    correlation_id = Column(String, nullable=True, index=True)
    created_by = Column(String, nullable=False)
    # Optional client-supplied key so retries while pending reuse one APR.
    runtime_idempotency_key = Column(String, nullable=True, index=True)

    decisions = relationship(
        "ApprovalDecision",
        back_populates="approval_request",
        order_by="ApprovalDecision.decided_at",
    )
    plan = relationship(
        "ApprovalPlan",
        back_populates="approval_request",
        uselist=False,
        cascade="all, delete-orphan",
    )


class ApprovalDecision(Base):
    __tablename__ = "approval_decisions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    approval_request_id = Column(
        UUID(as_uuid=True),
        ForeignKey("approval_requests.id"),
        nullable=False,
        index=True,
    )
    decision = Column(String, nullable=False)
    decided_by = Column(String, nullable=False)
    decision_reason = Column(Text, nullable=True)
    authentication_assurance = Column(String, nullable=True)
    decided_at = Column(DateTime(timezone=True), server_default=func.now())
    correlation_id = Column(String, nullable=True)

    approval_request = relationship("ApprovalRequest", back_populates="decisions")


class ApprovalPlan(Base):
    """Multi-stage approval plan bound to one ApprovalRequest + action digest."""

    __tablename__ = "approval_plans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    approval_request_id = Column(
        UUID(as_uuid=True),
        ForeignKey("approval_requests.id"),
        nullable=False,
        unique=True,
        index=True,
    )
    action_digest = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="IN_PROGRESS", index=True)
    current_stage_index = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    approval_request = relationship("ApprovalRequest", back_populates="plan")
    stages = relationship(
        "ApprovalStage",
        back_populates="plan",
        order_by="ApprovalStage.stage_index",
        cascade="all, delete-orphan",
    )


class ApprovalStage(Base):
    __tablename__ = "approval_stages"
    __table_args__ = (
        UniqueConstraint("plan_id", "stage_index", name="uq_approval_stage_index"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id = Column(
        UUID(as_uuid=True),
        ForeignKey("approval_plans.id"),
        nullable=False,
        index=True,
    )
    stage_index = Column(Integer, nullable=False)
    name = Column(String, nullable=False)
    mode = Column(String, nullable=False, default="QUORUM")
    required_roles = Column(JSON, nullable=False, default=list)
    quorum_count = Column(Integer, nullable=False, default=1)
    status = Column(String, nullable=False, default="PENDING", index=True)
    activated_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    plan = relationship("ApprovalPlan", back_populates="stages")
    decisions = relationship(
        "ApprovalStageDecision",
        back_populates="stage",
        order_by="ApprovalStageDecision.decided_at",
        cascade="all, delete-orphan",
    )


class ApprovalStageDecision(Base):
    __tablename__ = "approval_stage_decisions"
    __table_args__ = (
        UniqueConstraint(
            "stage_id",
            "decided_by",
            name="uq_approval_stage_approver",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    stage_id = Column(
        UUID(as_uuid=True),
        ForeignKey("approval_stages.id"),
        nullable=False,
        index=True,
    )
    decision = Column(String, nullable=False)
    decided_by = Column(String, nullable=False)
    approver_role = Column(String, nullable=False)
    decision_reason = Column(Text, nullable=True)
    authentication_assurance = Column(String, nullable=True)
    action_digest = Column(String, nullable=False)
    decided_at = Column(DateTime(timezone=True), server_default=func.now())
    correlation_id = Column(String, nullable=True)

    stage = relationship("ApprovalStage", back_populates="decisions")
