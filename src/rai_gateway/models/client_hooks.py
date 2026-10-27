"""SQLAlchemy model for runtime client hook integrations."""

from __future__ import annotations

import uuid

from sqlalchemy import JSON, Column, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from rai_gateway.models.database import Base


class RuntimeClientIntegration(Base):
    __tablename__ = "runtime_client_integrations"
    __table_args__ = (
        UniqueConstraint(
            "runtime_identity_id",
            "client_type",
            name="uq_runtime_client_integration",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    runtime_identity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_runtime_identities.id"),
        nullable=False,
        index=True,
    )
    client_type = Column(String, nullable=False)
    enforcement_mode = Column(String, nullable=False, default="HOOK_ENFORCED")
    deployment_control = Column(String, nullable=True, default="LOCAL_HOOK")
    verification_status = Column(String, nullable=True, default="DECLARED")
    status = Column(String, nullable=False, default="NOT_CONFIGURED")
    client_version = Column(String, nullable=True)
    bridge_version = Column(String, nullable=True)
    protocol_version = Column(String, nullable=True)
    configuration_status = Column(String, nullable=True)
    coverage = Column(JSON, nullable=True)
    # Managed-hook attestation (server-registered expectations).
    expected_bridge_hash = Column(String, nullable=True)
    expected_bridge_version = Column(String, nullable=True)
    observed_bridge_hash = Column(String, nullable=True)
    managed_profile_key = Column(String, nullable=True)
    last_attested_at = Column(DateTime(timezone=True), nullable=True)
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    last_decision_at = Column(DateTime(timezone=True), nullable=True)
    last_decision_effect = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
