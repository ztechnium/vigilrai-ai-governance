"""SQLAlchemy models for AI System policy collections."""

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


class PolicyCollection(Base):
    __tablename__ = "policy_collections"
    __table_args__ = (
        UniqueConstraint("ai_system_id", name="uq_policy_collection_ai_system"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ai_system_id = Column(
        UUID(as_uuid=True), ForeignKey("ai_systems.id"), nullable=False, index=True
    )
    name = Column(String, nullable=False, default="Default Policy Collection")
    description = Column(Text)
    status = Column(String, nullable=False, default="ACTIVE", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    content_rules = relationship(
        "ContentRule", back_populates="policy_collection", cascade="all, delete-orphan"
    )
    tool_rules = relationship(
        "ToolRule", back_populates="policy_collection", cascade="all, delete-orphan"
    )


class ContentRule(Base):
    __tablename__ = "content_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    policy_collection_id = Column(
        UUID(as_uuid=True),
        ForeignKey("policy_collections.id"),
        nullable=False,
        index=True,
    )
    title = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    effect = Column(String, nullable=False, index=True)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    applies_to = Column(String, nullable=False, default="BOTH")
    rule_version = Column(Integer, nullable=False, default=1)
    category = Column(String, nullable=True)
    severity = Column(String, nullable=True)
    required_approver_role = Column(String)
    # ContentRule V2 fields (PR1). evaluator_profile_id has no FK until PR2.
    evaluation_type = Column(String, nullable=False, default="LLM_JUDGE")
    evaluator_profile_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    intervention_points = Column(
        JSON, nullable=False, default=lambda: ["INPUT", "OUTPUT"]
    )
    content_targets = Column(
        JSON, nullable=False, default=lambda: {"mode": "FULL_CONTENT"}
    )
    minimum_confidence = Column(Float, nullable=True)
    failure_mode = Column(String, nullable=False, default="INHERIT")
    remediation_type = Column(String, nullable=False, default="NONE")
    remediation_config = Column(JSON, nullable=True)
    inline_enforcement_required = Column(Boolean, nullable=False, default=False)
    evaluation_timeout_ms = Column(Integer, nullable=True)
    archived_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    policy_collection = relationship("PolicyCollection", back_populates="content_rules")


class ToolRule(Base):
    __tablename__ = "tool_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    policy_collection_id = Column(
        UUID(as_uuid=True),
        ForeignKey("policy_collections.id"),
        nullable=False,
        index=True,
    )
    title = Column(String, nullable=False)
    description = Column(Text)
    mcp_server_id = Column(UUID(as_uuid=True), ForeignKey("mcp_servers.id"), index=True)
    tool_id = Column(
        UUID(as_uuid=True), ForeignKey("tool_resources.id"), nullable=False, index=True
    )
    match_mode = Column(String, nullable=False, default="ALL")
    effect = Column(String, nullable=False, index=True)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    required_approver_role = Column(String)
    severity = Column(String, nullable=True)
    category = Column(String, nullable=True)
    archived_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    policy_collection = relationship("PolicyCollection", back_populates="tool_rules")
    conditions = relationship(
        "ToolRuleCondition",
        back_populates="tool_rule",
        cascade="all, delete-orphan",
        order_by="ToolRuleCondition.sort_order",
    )


class ToolRuleCondition(Base):
    __tablename__ = "tool_rule_conditions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tool_rule_id = Column(
        UUID(as_uuid=True), ForeignKey("tool_rules.id"), nullable=False, index=True
    )
    parameter_path = Column(String, nullable=False)
    operator = Column(String, nullable=False)
    value_type = Column(String, nullable=False, default="string")
    value_json = Column(JSON)
    sort_order = Column(Integer, nullable=False, default=0)

    tool_rule = relationship("ToolRule", back_populates="conditions")
