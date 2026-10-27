"""SQLAlchemy models for WP4 runtime enforcement receipts and idempotency."""

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


class RuntimeEnforcementReceipt(Base):
    __tablename__ = "runtime_enforcement_receipts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    receipt_schema_version = Column(Integer, nullable=False, default=1)
    runtime_identity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_runtime_identities.id"),
        nullable=False,
        index=True,
    )
    ai_system_id = Column(
        UUID(as_uuid=True), ForeignKey("ai_systems.id"), nullable=False, index=True
    )
    agent_id = Column(
        UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False, index=True
    )
    agent_version_id = Column(
        UUID(as_uuid=True), ForeignKey("agent_versions.id"), nullable=False, index=True
    )
    delegation_id = Column(
        UUID(as_uuid=True), ForeignKey("delegation_grants.id"), nullable=True
    )
    enforcement_mode = Column(String, nullable=False, default="PROXY_ENFORCED")
    deployment_control = Column(String, nullable=True)
    verification_status = Column(String, nullable=True)
    integration_type = Column(String, nullable=False)
    integration_id = Column(UUID(as_uuid=True), nullable=True)
    tool_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    action_digest = Column(String, nullable=False, index=True)
    policy_effect = Column(String, nullable=True)
    matched_rule_ids = Column(JSON, nullable=True)
    approval_request_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    approval_consumed = Column(Boolean, nullable=False, default=False)
    enforcement_decision = Column(String, nullable=False)
    reason_code = Column(String, nullable=True)
    human_explanation = Column(Text, nullable=True)
    execution_attempted = Column(Boolean, nullable=False, default=False)
    execution_status = Column(String, nullable=False, default="NOT_ATTEMPTED")
    execution_source = Column(String, nullable=True)
    downstream_reference = Column(String, nullable=True)
    policy_decision = Column(JSON, nullable=True)
    action_summary = Column(JSON, nullable=True)
    client_context = Column(JSON, nullable=True)
    execution_report = Column(JSON, nullable=True)
    idempotency_key = Column(String, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    monitor = Column(Boolean, nullable=False, default=False)
    monitoring_instruction = Column(Text, nullable=True)
    correlation_id = Column(String, nullable=True, index=True)
    trace_id = Column(String, nullable=True, index=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    reported_at = Column(DateTime(timezone=True), nullable=True)

    # Canonical Enforcement V2 fields
    decision_phase = Column(String, nullable=True)
    decision_finalized_at = Column(DateTime(timezone=True), nullable=True)
    decision_digest = Column(String, nullable=True)
    authority_digest = Column(String, nullable=True)
    authority_snapshot = Column(JSON, nullable=True)
    effective_scope_digest = Column(String, nullable=True)
    policy_bundle_digest = Column(String, nullable=True)
    control_summary = Column(JSON, nullable=True)
    resume_of_receipt_id = Column(
        UUID(as_uuid=True),
        ForeignKey("runtime_enforcement_receipts.id"),
        nullable=True,
        index=True,
    )
    decision_chain_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    revalidated_at = Column(DateTime(timezone=True), nullable=True)
    revalidation_count = Column(Integer, nullable=False, default=0)

    control_decisions = relationship(
        "RuntimeControlDecision",
        back_populates="receipt",
        foreign_keys="RuntimeControlDecision.receipt_id",
        order_by="RuntimeControlDecision.sequence",
    )


class RuntimeControlDecision(Base):
    __tablename__ = "runtime_control_decisions"
    __table_args__ = (
        UniqueConstraint(
            "receipt_id", "sequence", name="uq_runtime_control_decision_sequence"
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    receipt_id = Column(
        UUID(as_uuid=True),
        ForeignKey("runtime_enforcement_receipts.id"),
        nullable=False,
        index=True,
    )
    sequence = Column(Integer, nullable=False)
    phase = Column(String, nullable=True)
    control_type = Column(String, nullable=False)
    policy_domain = Column(String, nullable=True)
    status = Column(String, nullable=False, default="EVALUATED")
    effect = Column(String, nullable=True)
    reason_code = Column(String, nullable=True)
    human_explanation = Column(Text, nullable=True)
    source_type = Column(String, nullable=True)
    source_id = Column(String, nullable=True)
    source_version = Column(String, nullable=True)
    matched_rule_ids = Column(JSON, nullable=True)
    control_snapshot = Column(JSON, nullable=True)
    evidence_refs = Column(JSON, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    receipt = relationship(
        "RuntimeEnforcementReceipt",
        back_populates="control_decisions",
        foreign_keys=[receipt_id],
    )


class RuntimeIdempotencyRecord(Base):
    __tablename__ = "runtime_idempotency_records"
    __table_args__ = (
        UniqueConstraint(
            "runtime_identity_id",
            "idempotency_key",
            name="uq_runtime_idempotency_key",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    runtime_identity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_runtime_identities.id"),
        nullable=False,
        index=True,
    )
    idempotency_key = Column(String, nullable=False)
    action_digest = Column(String, nullable=False)
    receipt_id = Column(
        UUID(as_uuid=True),
        ForeignKey("runtime_enforcement_receipts.id"),
        nullable=False,
    )
    execution_status = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
