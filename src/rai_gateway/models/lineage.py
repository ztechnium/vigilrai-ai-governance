"""SQLAlchemy models for derived-data lineage and disposal."""

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


class DataSourceVersion(Base):
    """Immutable version of a registered DataSource (lineage root)."""

    __tablename__ = "data_source_versions"
    __table_args__ = (
        UniqueConstraint(
            "data_source_id",
            "version_number",
            name="uq_data_source_version_number",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    data_source_id = Column(
        UUID(as_uuid=True),
        ForeignKey("data_sources.id"),
        nullable=False,
        index=True,
    )
    version_number = Column(Integer, nullable=False)
    content_digest = Column(String, nullable=True, index=True)
    change_summary = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="ACTIVE")
    legal_hold = Column(Boolean, nullable=False, default=False, index=True)
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    retired_at = Column(DateTime(timezone=True), nullable=True)


class DerivedAsset(Base):
    """Tracked derivative of a DataSourceVersion (chunk/embedding/cache/memory/…)."""

    __tablename__ = "derived_assets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_version_id = Column(
        UUID(as_uuid=True),
        ForeignKey("data_source_versions.id"),
        nullable=False,
        index=True,
    )
    parent_asset_id = Column(
        UUID(as_uuid=True),
        ForeignKey("derived_assets.id"),
        nullable=True,
        index=True,
    )
    asset_type = Column(String, nullable=False, index=True)
    store = Column(String, nullable=False, index=True)
    locator = Column(String, nullable=False)
    digest = Column(String, nullable=True, index=True)
    retention_class = Column(String, nullable=False, default="STANDARD")
    status = Column(String, nullable=False, default="ACTIVE", index=True)
    legal_hold = Column(Boolean, nullable=False, default=False, index=True)
    ai_system_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    agent_version_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    evidence_ref = Column(String, nullable=True)
    metadata_ = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    disposed_at = Column(DateTime(timezone=True), nullable=True)


class DisposalRequest(Base):
    """Disposal workflow for a source version's derivatives."""

    __tablename__ = "disposal_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_version_id = Column(
        UUID(as_uuid=True),
        ForeignKey("data_source_versions.id"),
        nullable=False,
        index=True,
    )
    status = Column(String, nullable=False, default="PENDING", index=True)
    requested_by = Column(String, nullable=False)
    reason = Column(Text, nullable=True)
    access_revoked_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    # Do not promise immediate backup deletion — track separately.
    backup_expiry_tracked_until = Column(DateTime(timezone=True), nullable=True)
    evidence = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DisposalAcknowledgement(Base):
    """Per-store acknowledgement for one derived asset in a disposal request."""

    __tablename__ = "disposal_acknowledgements"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    disposal_request_id = Column(
        UUID(as_uuid=True),
        ForeignKey("disposal_requests.id"),
        nullable=False,
        index=True,
    )
    derived_asset_id = Column(
        UUID(as_uuid=True),
        ForeignKey("derived_assets.id"),
        nullable=False,
        index=True,
    )
    store = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="RETRYING", index=True)
    attempts = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    adapter_response = Column(JSON, nullable=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
