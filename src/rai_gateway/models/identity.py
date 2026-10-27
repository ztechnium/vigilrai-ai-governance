"""SQLAlchemy models for WP2 runtime identity and delegation."""

from __future__ import annotations

import uuid

from sqlalchemy import (
    JSON,
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


class AgentRuntimeIdentity(Base):
    __tablename__ = "agent_runtime_identities"
    __table_args__ = (UniqueConstraint("identity_key", name="uq_runtime_identity_key"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    identity_key = Column(String, nullable=False, index=True)
    agent_id = Column(
        UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False, index=True
    )
    agent_version_id = Column(
        UUID(as_uuid=True), ForeignKey("agent_versions.id"), nullable=False, index=True
    )
    name = Column(String, nullable=False)
    identity_type = Column(String, nullable=False, default="RAI_API_CREDENTIAL")
    auth_provider = Column(String)
    external_subject = Column(String)
    environment = Column(String)
    status = Column(String, nullable=False, default="ACTIVE", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(String, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    updated_by = Column(String)
    expires_at = Column(DateTime(timezone=True))
    last_authenticated_at = Column(DateTime(timezone=True))
    revoked_at = Column(DateTime(timezone=True))
    revocation_reason = Column(Text)

    agent = relationship("Agent", foreign_keys=[agent_id])
    agent_version = relationship("AgentVersion", foreign_keys=[agent_version_id])
    credentials = relationship(
        "RuntimeCredential",
        back_populates="runtime_identity",
        foreign_keys="RuntimeCredential.runtime_identity_id",
    )
    delegations = relationship(
        "DelegationGrant",
        back_populates="delegate_runtime_identity",
        foreign_keys="DelegationGrant.delegate_runtime_identity_id",
    )


class RuntimeCredential(Base):
    __tablename__ = "runtime_credentials"
    __table_args__ = (
        UniqueConstraint("credential_key", name="uq_runtime_credential_key"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    runtime_identity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_runtime_identities.id"),
        nullable=False,
        index=True,
    )
    credential_key = Column(String, nullable=False, index=True)
    credential_type = Column(String, nullable=False, default="API_KEY")
    key_hash = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="ACTIVE", index=True)
    issued_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True))
    last_used_at = Column(DateTime(timezone=True))
    revoked_at = Column(DateTime(timezone=True))
    replaced_by_id = Column(UUID(as_uuid=True), ForeignKey("runtime_credentials.id"))
    created_by = Column(String, nullable=False)

    runtime_identity = relationship(
        "AgentRuntimeIdentity",
        back_populates="credentials",
        foreign_keys=[runtime_identity_id],
    )
    replaced_by = relationship("RuntimeCredential", remote_side=[id])


class DelegationGrant(Base):
    __tablename__ = "delegation_grants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    delegator_type = Column(String, nullable=False)
    delegator_id = Column(String, nullable=False, index=True)
    delegate_runtime_identity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_runtime_identities.id"),
        nullable=False,
        index=True,
    )
    parent_delegation_id = Column(
        UUID(as_uuid=True), ForeignKey("delegation_grants.id"), index=True
    )
    status = Column(String, nullable=False, default="ACTIVE", index=True)
    scope = Column(JSON, nullable=False, default=dict)
    scope_version = Column(Integer, nullable=False, default=2)
    revision_number = Column(Integer, nullable=False, default=1)
    scope_digest = Column(String)
    valid_from = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True))
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    revoked_at = Column(DateTime(timezone=True))
    revocation_reason = Column(Text)

    delegate_runtime_identity = relationship(
        "AgentRuntimeIdentity",
        back_populates="delegations",
        foreign_keys=[delegate_runtime_identity_id],
    )
    parent_delegation = relationship(
        "DelegationGrant",
        remote_side=[id],
        foreign_keys=[parent_delegation_id],
    )
    revisions = relationship(
        "DelegationRevision",
        back_populates="delegation",
        foreign_keys="DelegationRevision.delegation_id",
        order_by="DelegationRevision.revision_number",
    )


class DelegationRevision(Base):
    __tablename__ = "delegation_revisions"
    __table_args__ = (
        UniqueConstraint(
            "delegation_id", "revision_number", name="uq_delegation_revision_number"
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    delegation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("delegation_grants.id"),
        nullable=False,
        index=True,
    )
    revision_number = Column(Integer, nullable=False)
    scope_version = Column(Integer, nullable=False, default=2)
    scope_snapshot = Column(JSON, nullable=False, default=dict)
    scope_digest = Column(String)
    valid_from = Column(DateTime(timezone=True))
    expires_at = Column(DateTime(timezone=True))
    change_type = Column(String, nullable=False)
    change_reason = Column(Text)
    changed_by = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    delegation = relationship(
        "DelegationGrant",
        back_populates="revisions",
        foreign_keys=[delegation_id],
    )
