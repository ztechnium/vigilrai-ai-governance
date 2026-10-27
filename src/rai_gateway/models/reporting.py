"""SQLAlchemy models for reporting and analytics snapshots."""

from __future__ import annotations

import uuid

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from rai_gateway.models.database import Base


class ReportSnapshot(Base):
    """Immutable historical report snapshot.

    Preserves point-in-time governance, risk, and compliance metrics for audit trail.
    """

    __tablename__ = "report_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    report_type = Column(String, nullable=False, index=True)
    scope_type = Column(String, nullable=False, default="ORGANIZATION")
    scope_id = Column(UUID(as_uuid=True), nullable=True, index=True)

    period_start = Column(DateTime(timezone=True), nullable=False, index=True)
    period_end = Column(DateTime(timezone=True), nullable=False, index=True)

    filters_json = Column(JSON, nullable=False)

    generated_at = Column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    generated_by = Column(String, nullable=False)

    schema_version = Column(String, nullable=False, default="1.0")

    # Immutable snapshot data
    data_snapshot = Column(JSON, nullable=False)

    # Source entity IDs for audit traceability
    source_manifest = Column(JSON, nullable=True)

    # Content integrity
    content_digest = Column(String, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ReportSchedule(Base):
    """Scheduled report generation configuration.

    Optional future enhancement for automated report delivery.
    """

    __tablename__ = "report_schedules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)

    report_type = Column(String, nullable=False)
    scope_type = Column(String, nullable=False, default="ORGANIZATION")
    scope_id = Column(UUID(as_uuid=True), nullable=True)

    cadence = Column(String, nullable=False)  # DAILY, WEEKLY, MONTHLY
    enabled = Column(Boolean, nullable=False, default=True, index=True)

    filters_json = Column(JSON, nullable=False)
    delivery_config = Column(JSON, nullable=True)

    next_run_at = Column(DateTime(timezone=True), nullable=True, index=True)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    last_snapshot_id = Column(
        UUID(as_uuid=True),
        ForeignKey("report_snapshots.id"),
        nullable=True,
    )

    created_by = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
