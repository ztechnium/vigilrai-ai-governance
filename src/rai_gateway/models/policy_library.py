"""Policy Library models — source policies distinct from executable RAI Rules."""

from __future__ import annotations

import uuid

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from rai_gateway.models.database import Base


class PolicySource(Base):
    """Policy source (file / URL / manual text).

    Coexists with legacy ``policy_documents``; new library UX writes here.
    PLATFORM scope marks built-in standards. ORGANIZATION scope marks instance sources.
    """

    __tablename__ = "policy_sources"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scope = Column(String, nullable=False, default="ORGANIZATION", index=True)
    source_key = Column(String, nullable=True, index=True)
    title = Column(String, nullable=False)
    source_type = Column(String, nullable=False, index=True)  # FILE / URL / MANUAL_TEXT
    authority = Column(String)
    owner = Column(String)
    jurisdiction = Column(String, index=True)
    policy_type = Column(String, index=True)
    version = Column(String)
    effective_date = Column(DateTime(timezone=True))
    status = Column(String, nullable=False, default="ACTIVE", index=True)
    source_uri = Column(String)
    content_digest = Column(String)
    content_text = Column(Text)
    ingestion_status = Column(
        String, nullable=False, default="READY", index=True
    )  # PENDING / READY / FAILED
    crawl_metadata = Column(JSON)
    legacy_doc_id = Column(String, ForeignKey("policy_documents.doc_id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    obligations = relationship(
        "PolicySourceObligation",
        back_populates="policy_source",
        cascade="all, delete-orphan",
    )
    rule_links = relationship(
        "PolicyRuleLink",
        back_populates="policy_source",
        cascade="all, delete-orphan",
    )


class PolicySourceObligation(Base):
    """Obligation extracted or manually attached to a policy source."""

    __tablename__ = "policy_source_obligations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    policy_source_id = Column(
        UUID(as_uuid=True),
        ForeignKey("policy_sources.id"),
        nullable=False,
        index=True,
    )
    section_ref = Column(String)
    topic = Column(String)
    scope = Column(String)
    constraint_action = Column(String)
    text = Column(Text)
    status = Column(String, nullable=False, default="draft", index=True)
    structured = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    policy_source = relationship("PolicySource", back_populates="obligations")


class PolicyRuleLink(Base):
    """Many-to-many link between policy sources/obligations and RAI rules."""

    __tablename__ = "policy_rule_links"
    __table_args__ = (
        UniqueConstraint(
            "policy_source_id",
            "rule_type",
            "rule_id",
            name="uq_policy_rule_link_source_rule",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    policy_source_id = Column(
        UUID(as_uuid=True),
        ForeignKey("policy_sources.id"),
        nullable=False,
        index=True,
    )
    obligation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("policy_source_obligations.id"),
        nullable=True,
        index=True,
    )
    rule_type = Column(String, nullable=False)  # CONTENT / TOOL
    rule_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    relationship_type = Column(String, nullable=False, default="DERIVED_FROM")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    policy_source = relationship("PolicySource", back_populates="rule_links")
