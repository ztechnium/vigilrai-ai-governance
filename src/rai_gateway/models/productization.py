"""WP10 productization ORM models."""

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


class SdkIntegration(Base):
    """Product-level integration registry entry (extends WP4 client hooks)."""

    __tablename__ = "sdk_integrations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    integration_key = Column(String, nullable=False, unique=True, index=True)
    name = Column(String, nullable=False)
    integration_type = Column(String, nullable=False, default="SDK")
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
    environment = Column(String, nullable=False, default="production")
    auth_method = Column(String, nullable=False, default="API_KEY")
    protocol_version = Column(Integer, nullable=False, default=1)
    sdk_version = Column(String, nullable=True)
    enforcement_mode = Column(String, nullable=False, default="HOOK_ENFORCED")
    deployment_control = Column(String, nullable=True)
    verification_status = Column(String, nullable=True, default="DECLARED")
    certification_status = Column(String, nullable=False, default="SUPPORTED")
    capability_matrix = Column(JSON, nullable=True)
    fail_closed = Column(Boolean, nullable=False, default=True)
    status = Column(String, nullable=False, default="ACTIVE", index=True)
    oidc_issuer = Column(String, nullable=True)
    oidc_audience = Column(String, nullable=True)
    oidc_subject_claim = Column(String, nullable=True, default="sub")
    last_heartbeat_at = Column(DateTime(timezone=True), nullable=True)
    last_sdk_version = Column(String, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SdkSession(Base):
    """External integration session correlated to WP5 trajectory."""

    __tablename__ = "sdk_sessions"
    __table_args__ = (
        UniqueConstraint(
            "integration_id",
            "external_session_id",
            name="uq_sdk_session_external",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    integration_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sdk_integrations.id"),
        nullable=False,
        index=True,
    )
    runtime_identity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_runtime_identities.id"),
        nullable=False,
        index=True,
    )
    trajectory_id = Column(
        UUID(as_uuid=True),
        ForeignKey("runtime_trajectories.id"),
        nullable=True,
        index=True,
    )
    delegation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("delegation_grants.id"),
        nullable=True,
        index=True,
    )
    correlation_id = Column(String, nullable=False, index=True)
    external_session_id = Column(String, nullable=True, index=True)
    external_conversation_id = Column(String, nullable=True)
    principal = Column(String, nullable=True)
    channel = Column(String, nullable=True)
    status = Column(String, nullable=False, default="ACTIVE", index=True)
    metadata_json = Column(JSON, nullable=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    ended_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SdkDecisionRecord(Base):
    """Maps public decision_id to enforcement receipt for execution reporting."""

    __tablename__ = "sdk_decision_records"
    __table_args__ = (
        UniqueConstraint(
            "integration_id",
            "idempotency_key",
            name="uq_sdk_decision_integration_idempotency",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(
        UUID(as_uuid=True), ForeignKey("sdk_sessions.id"), nullable=False, index=True
    )
    integration_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sdk_integrations.id"),
        nullable=False,
        index=True,
    )
    enforcement_receipt_id = Column(
        UUID(as_uuid=True),
        ForeignKey("runtime_enforcement_receipts.id"),
        nullable=True,
        index=True,
    )
    decision = Column(String, nullable=False)
    reason_code = Column(String, nullable=True)
    tool_key = Column(String, nullable=True)
    idempotency_key = Column(String, nullable=True, index=True)
    action_digest = Column(String, nullable=True, index=True)
    approval_request_id = Column(UUID(as_uuid=True), nullable=True)
    payload = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class WebhookEndpoint(Base):
    __tablename__ = "webhook_endpoints"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    url = Column(String, nullable=False)
    secret_hash = Column(String, nullable=False)
    secret_prefix = Column(String, nullable=False)
    secret_ciphertext = Column(Text, nullable=True)
    event_types = Column(JSON, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    status = Column(String, nullable=False, default="ACTIVE")
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    last_rotated_at = Column(DateTime(timezone=True), nullable=True)


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    endpoint_id = Column(
        UUID(as_uuid=True),
        ForeignKey("webhook_endpoints.id"),
        nullable=False,
        index=True,
    )
    event_type = Column(String, nullable=False, index=True)
    event_id = Column(String, nullable=False, index=True)
    payload = Column(JSON, nullable=False)
    status = Column(String, nullable=False, default="PENDING", index=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    next_attempt_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class BackgroundJob(Base):
    __tablename__ = "background_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_type = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="PENDING", index=True)
    idempotency_key = Column(String, nullable=True, unique=True, index=True)
    payload = Column(JSON, nullable=True)
    result = Column(JSON, nullable=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=5)
    next_attempt_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    created_by = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)


class OrganizationOnboarding(Base):
    """Singleton in-app welcome progress for this instance."""

    __tablename__ = "organization_onboarding"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    singleton_key = Column(String, nullable=False, unique=True, default="default")
    current_step = Column(String, nullable=False, default="organization_profile")
    completed_steps = Column(JSON, nullable=False, default=list)
    first_ai_system_id = Column(UUID(as_uuid=True), nullable=True)
    first_integration_id = Column(UUID(as_uuid=True), nullable=True)
    first_trajectory_id = Column(UUID(as_uuid=True), nullable=True)
    status = Column(String, nullable=False, default="NOT_STARTED", index=True)
    welcome_completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class OidcRuntimeBinding(Base):
    """Maps OIDC issuer/subject to a registered runtime identity."""

    __tablename__ = "oidc_runtime_bindings"
    __table_args__ = (
        UniqueConstraint(
            "issuer",
            "subject",
            name="uq_oidc_runtime_issuer_subject",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    runtime_identity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_runtime_identities.id"),
        nullable=False,
        index=True,
    )
    issuer = Column(String, nullable=False, index=True)
    audience = Column(String, nullable=False)
    subject = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="ACTIVE")
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
