"""SQLAlchemy models for AI FinOps — pricing, reservation, settlement."""

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
from sqlalchemy.sql import func

from rai_gateway.models.database import Base


class PricingCatalogEntry(Base):
    """Versioned provider/model token pricing."""

    __tablename__ = "finops_pricing_catalog"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "model",
            "currency",
            "effective_from",
            name="uq_finops_pricing_version",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider = Column(String, nullable=False, index=True)
    model = Column(String, nullable=False, index=True)
    input_token_price = Column(Float, nullable=False)  # per pricing_unit tokens
    output_token_price = Column(Float, nullable=False)  # per pricing_unit tokens
    cached_input_token_price = Column(Float, nullable=True)
    reasoning_token_price = Column(Float, nullable=True)
    minimum_request_cost = Column(Float, nullable=True)
    cache_write_token_price = Column(Float, nullable=True)
    image_input_price = Column(Float, nullable=True)
    image_output_price = Column(Float, nullable=True)
    audio_input_price = Column(Float, nullable=True)
    audio_output_price = Column(Float, nullable=True)
    request_price = Column(Float, nullable=True)
    provider_tool_price = Column(Float, nullable=True)
    pricing_metadata = Column(JSON, nullable=True)
    source_url = Column(String, nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    region = Column(String, nullable=True)
    service_tier = Column(String, nullable=True)
    pricing_unit = Column(Integer, nullable=False, default=1000, server_default="1000")
    currency = Column(String, nullable=False, default="USD")
    effective_from = Column(DateTime(timezone=True), nullable=False, index=True)
    effective_to = Column(DateTime(timezone=True), nullable=True, index=True)
    enabled = Column(Boolean, nullable=False, default=True)
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class UsageReservation(Base):
    """Estimated cost hold before a consequential model/tool call."""

    __tablename__ = "finops_usage_reservations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ai_system_id = Column(
        UUID(as_uuid=True), ForeignKey("ai_systems.id"), nullable=True, index=True
    )
    agent_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    agent_version_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    runtime_identity_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    delegation_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    runtime_conversation_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    trajectory_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    enforcement_receipt_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    correlation_id = Column(String, nullable=True, index=True)
    provider = Column(String, nullable=True)
    model = Column(String, nullable=True)
    estimated_input_tokens = Column(Integer, nullable=True)
    estimated_output_tokens = Column(Integer, nullable=True)
    estimated_cost = Column(Float, nullable=False, default=0.0)
    currency = Column(String, nullable=False, default="USD")
    pricing_entry_id = Column(UUID(as_uuid=True), nullable=True)
    status = Column(String, nullable=False, default="RESERVED", index=True)
    allocation = Column(JSON, nullable=True)  # org/dept/workflow/principal dims
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class UsageSettlement(Base):
    """Actual usage settlement against a reservation (or standalone)."""

    __tablename__ = "finops_usage_settlements"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ai_system_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    agent_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    agent_version_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    runtime_identity_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    delegation_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    runtime_conversation_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    trajectory_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    metering_span_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    reservation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("finops_usage_reservations.id"),
        nullable=True,
        index=True,
    )
    enforcement_receipt_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    correlation_id = Column(String, nullable=True, index=True)
    provider = Column(String, nullable=True)
    model = Column(String, nullable=True)
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    total_tokens = Column(Integer, nullable=True)
    actual_cost = Column(Float, nullable=True)  # legacy compat; prefer metered/billed
    estimated_cost = Column(Float, nullable=True)
    metered_cost = Column(Float, nullable=True)
    billed_cost = Column(Float, nullable=True)
    currency = Column(String, nullable=False, default="USD")
    cost_state = Column(String, nullable=True, index=True)
    metering_source = Column(String, nullable=False, index=True)
    pricing_entry_id = Column(UUID(as_uuid=True), nullable=True)
    pricing_snapshot = Column(JSON, nullable=True)
    reserved_cost = Column(Float, nullable=True)
    delta_cost = Column(Float, nullable=True)
    allocation = Column(JSON, nullable=True)
    raw_usage = Column(JSON, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
