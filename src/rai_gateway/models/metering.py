"""Runtime metering spans — what consumed AI resources.

UsageSettlement remains the financial ledger. Spans explain attribution.
"""

from __future__ import annotations

import uuid

from sqlalchemy import JSON, Column, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from rai_gateway.models.database import Base


class RuntimeMeteringSpan(Base):
    __tablename__ = "finops_metering_spans"
    __table_args__ = (
        Index("ix_finops_span_started", "started_at"),
        Index("ix_finops_span_system_started", "ai_system_id", "started_at"),
        Index("ix_finops_span_agent_started", "agent_id", "started_at"),
        Index("ix_finops_span_version_started", "agent_version_id", "started_at"),
        Index("ix_finops_span_identity_started", "runtime_identity_id", "started_at"),
        Index("ix_finops_span_delegation_started", "delegation_id", "started_at"),
        Index(
            "ix_finops_span_conversation_started",
            "runtime_conversation_id",
            "started_at",
        ),
        Index("ix_finops_span_trajectory_started", "trajectory_id", "started_at"),
        Index(
            "ix_finops_span_provider_model_started", "provider", "model", "started_at"
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ai_system_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    agent_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    agent_version_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    runtime_identity_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    delegation_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    runtime_conversation_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    trajectory_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    enforcement_receipt_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    external_span_id = Column(String, nullable=True)
    parent_span_id = Column(UUID(as_uuid=True), nullable=True)
    correlation_id = Column(String, nullable=True, index=True)
    span_type = Column(String, nullable=False, default="MODEL_CALL", index=True)
    operation = Column(String, nullable=True)
    provider = Column(String, nullable=True)
    model = Column(String, nullable=True)
    environment = Column(String, nullable=True)
    integration_id = Column(UUID(as_uuid=True), nullable=True)
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    cached_input_tokens = Column(Integer, nullable=True)
    reasoning_tokens = Column(Integer, nullable=True)
    total_tokens = Column(Integer, nullable=True)
    estimated_cost = Column(Float, nullable=True)
    metered_cost = Column(Float, nullable=True)
    billed_cost = Column(Float, nullable=True)
    actual_cost = Column(Float, nullable=True)  # legacy compat
    currency = Column(String, nullable=False, default="USD")
    cost_state = Column(String, nullable=False, default="UNAVAILABLE", index=True)
    pricing_entry_id = Column(UUID(as_uuid=True), nullable=True)
    pricing_snapshot = Column(JSON, nullable=True)
    metering_source = Column(String, nullable=False, default="UNKNOWN")
    model_resource_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    tool_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    mcp_server_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    external_service_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    cache_write_tokens = Column(Integer, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True, index=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Integer, nullable=True)
    metadata_json = Column("metadata", JSON, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
