"""SQLAlchemy models for Phase 2 data-access governance."""

from __future__ import annotations

import uuid

from sqlalchemy import JSON, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from rai_gateway.models.database import Base


class DataAccessPolicy(Base):
    """Declarative field/purpose/classification policy for data access."""

    __tablename__ = "data_access_policies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ai_system_id = Column(
        UUID(as_uuid=True), ForeignKey("ai_systems.id"), nullable=True, index=True
    )
    name = Column(String, nullable=False)
    enabled = Column(String, nullable=False, default="true")  # keep simple string/bool
    # Match dimensions (null = any)
    data_source_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    resource = Column(String, nullable=True)  # table/index
    field_name = Column(String, nullable=True, index=True)
    classification = Column(String, nullable=True)
    purpose = Column(String, nullable=True)
    access_mode = Column(String, nullable=True)
    # Effect: ALLOW | MASK | DENY | REQUIRE_APPROVAL | FILTER
    effect = Column(String, nullable=False, default="DENY")
    mask_style = Column(String, nullable=True, default="REDACT")
    row_predicate = Column(JSON, nullable=True)
    priority = Column(String, nullable=False, default="100")
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DataAccessReceipt(Base):
    """Evidence that a data-access decision was evaluated (and optionally applied)."""

    __tablename__ = "data_access_receipts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ai_system_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    agent_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    agent_version_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    runtime_identity_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    data_source_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    tool_id = Column(UUID(as_uuid=True), nullable=True)
    principal = Column(String, nullable=True)
    resource = Column(String, nullable=False)
    purpose = Column(String, nullable=True)
    access_mode = Column(String, nullable=False)
    requested_fields = Column(JSON, nullable=False, default=list)
    allowed_fields = Column(JSON, nullable=False, default=list)
    denied_fields = Column(JSON, nullable=False, default=list)
    masked_fields = Column(JSON, nullable=False, default=list)
    decision = Column(String, nullable=False)
    reason_code = Column(String, nullable=False)
    human_explanation = Column(Text, nullable=True)
    transforms = Column(JSON, nullable=True)
    row_filter = Column(JSON, nullable=True)
    policy_rule_ids = Column(JSON, nullable=True)
    correlation_id = Column(String, nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
