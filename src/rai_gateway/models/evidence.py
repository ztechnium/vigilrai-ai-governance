"""SQLAlchemy models for WP5 runtime trajectory evidence and audit graph."""

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
from sqlalchemy.sql import func

from rai_gateway.models.database import Base


class RuntimeTrajectory(Base):
    __tablename__ = "runtime_trajectories"
    __table_args__ = (
        UniqueConstraint(
            "runtime_identity_id",
            "session_key",
            name="uq_runtime_trajectory_session",
        ),
    )

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
    client_integration_id = Column(
        UUID(as_uuid=True),
        ForeignKey("runtime_client_integrations.id"),
        nullable=True,
        index=True,
    )
    delegation_id = Column(
        UUID(as_uuid=True), ForeignKey("delegation_grants.id"), nullable=True
    )
    session_key = Column(String, nullable=False, index=True)
    conversation_id = Column(String, nullable=True, index=True)
    client_session_id = Column(String, nullable=True, index=True)
    correlation_id = Column(String, nullable=True, index=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    last_event_at = Column(DateTime(timezone=True), server_default=func.now())
    ended_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String, nullable=False, default="ACTIVE", index=True)
    enforcement_mode = Column(String, nullable=True)
    deployment_control = Column(String, nullable=True)
    assurance_summary = Column(JSON, nullable=True)
    coverage_summary = Column(JSON, nullable=True)
    event_count = Column(Integer, nullable=False, default=0)
    finding_count = Column(Integer, nullable=False, default=0)
    completeness_pct = Column(Integer, nullable=True)
    retention_days = Column(Integer, nullable=True)
    eligible_for_purge_at = Column(DateTime(timezone=True), nullable=True, index=True)
    legal_hold = Column(Boolean, nullable=False, default=False, index=True)
    runtime_conversation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("runtime_conversations.id"),
        nullable=True,
        index=True,
    )
    trajectory_semantics = Column(String, nullable=True, default="TURN")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RuntimeConversation(Base):
    """Durable conversation projection for enterprise runtime lists."""

    __tablename__ = "runtime_conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_key = Column(String, nullable=False, unique=True, index=True)
    external_conversation_id = Column(String, nullable=False, index=True)
    client_integration_id = Column(
        UUID(as_uuid=True),
        ForeignKey("runtime_client_integrations.id"),
        nullable=True,
        index=True,
    )
    runtime_identity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_runtime_identities.id"),
        nullable=True,
        index=True,
    )
    ai_system_id = Column(
        UUID(as_uuid=True), ForeignKey("ai_systems.id"), nullable=True, index=True
    )
    primary_agent_id = Column(
        UUID(as_uuid=True), ForeignKey("agents.id"), nullable=True, index=True
    )
    principal_reference = Column(String, nullable=True)
    channel = Column(String, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    last_activity_at = Column(DateTime(timezone=True), nullable=True, index=True)
    status = Column(String, nullable=False, default="ACTIVE", index=True)
    trajectory_count = Column(Integer, nullable=False, default=0)
    event_count = Column(Integer, nullable=False, default=0)
    action_count = Column(Integer, nullable=False, default=0)
    finding_count = Column(Integer, nullable=False, default=0)
    highest_risk_level = Column(String, nullable=True, index=True)
    highest_assurance_level = Column(String, nullable=True)
    last_trajectory_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class EvidenceEvent(Base):
    __tablename__ = "evidence_events"
    __table_args__ = (
        UniqueConstraint(
            "trajectory_id",
            "source_type",
            "source_reference",
            "event_type",
            name="uq_evidence_event_idempotency",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trajectory_id = Column(
        UUID(as_uuid=True),
        ForeignKey("runtime_trajectories.id"),
        nullable=False,
        index=True,
    )
    event_type = Column(String, nullable=False, index=True)
    occurred_at = Column(DateTime(timezone=True), nullable=False, index=True)
    recorded_at = Column(DateTime(timezone=True), server_default=func.now())
    sequence_number = Column(Integer, nullable=False)
    source_type = Column(String, nullable=False)
    source_reference = Column(String, nullable=False, index=True)
    assurance_level = Column(String, nullable=False, default="UNKNOWN")
    correlation_id = Column(String, nullable=True, index=True)
    trace_id = Column(String, nullable=True)
    payload = Column(JSON, nullable=True)
    payload_digest = Column(String, nullable=True)
    content_handling_mode = Column(String, nullable=False, default="METADATA_ONLY")
    redaction_status = Column(String, nullable=False, default="NOT_REQUIRED")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class EvidenceArtifact(Base):
    __tablename__ = "evidence_artifacts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trajectory_id = Column(
        UUID(as_uuid=True),
        ForeignKey("runtime_trajectories.id"),
        nullable=False,
        index=True,
    )
    event_id = Column(
        UUID(as_uuid=True), ForeignKey("evidence_events.id"), nullable=True, index=True
    )
    artifact_type = Column(String, nullable=False)
    source_type = Column(String, nullable=False)
    content_location = Column(String, nullable=True)
    inline_content = Column(Text, nullable=True)
    content_digest = Column(String, nullable=True)
    mime_type = Column(String, nullable=True)
    size_bytes = Column(Integer, nullable=True)
    content_handling_mode = Column(String, nullable=False, default="METADATA_ONLY")
    sensitivity_classification = Column(String, nullable=True)
    encrypted = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class EvidenceRelation(Base):
    __tablename__ = "evidence_relations"
    __table_args__ = (
        UniqueConstraint(
            "trajectory_id",
            "source_entity_type",
            "source_entity_id",
            "relation_type",
            "target_entity_type",
            "target_entity_id",
            name="uq_evidence_relation",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trajectory_id = Column(
        UUID(as_uuid=True),
        ForeignKey("runtime_trajectories.id"),
        nullable=False,
        index=True,
    )
    source_entity_type = Column(String, nullable=False)
    source_entity_id = Column(String, nullable=False)
    relation_type = Column(String, nullable=False)
    target_entity_type = Column(String, nullable=False)
    target_entity_id = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class EvidenceFinding(Base):
    __tablename__ = "evidence_findings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trajectory_id = Column(
        UUID(as_uuid=True),
        ForeignKey("runtime_trajectories.id"),
        nullable=False,
        index=True,
    )
    finding_type = Column(String, nullable=False, index=True)
    severity = Column(String, nullable=False, default="INFO", index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    source_event_ids = Column(JSON, nullable=True)
    status = Column(String, nullable=False, default="OPEN", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
