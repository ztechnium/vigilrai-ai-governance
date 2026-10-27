"""SQLAlchemy models for WP9 portfolio transparency & executive oversight."""

from __future__ import annotations

import uuid

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from rai_gateway.models.database import Base


class PortfolioReport(Base):
    """Immutable organization-scoped transparency report snapshot."""

    __tablename__ = "portfolio_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scope_type = Column(String, nullable=False, default="ORGANIZATION", index=True)
    scope_id = Column(String, nullable=True, index=True)
    period_start = Column(DateTime(timezone=True), nullable=True)
    period_end = Column(DateTime(timezone=True), nullable=True)
    generated_at = Column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    generated_by = Column(String, nullable=False)
    schema_version = Column(String, nullable=False, default="1.0")
    title = Column(String, nullable=False)
    data_snapshot = Column(JSON, nullable=False)
    source_manifest = Column(JSON, nullable=False)
    content_digest = Column(String, nullable=False, index=True)
    report_html = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PortfolioReportSchedule(Base):
    """In-app report schedule seam (delivery integration left optional)."""

    __tablename__ = "portfolio_report_schedules"
    __table_args__ = (
        UniqueConstraint(
            "cadence",
            "scope_type",
            "scope_id",
            name="uq_portfolio_report_schedule_scope",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cadence = Column(String, nullable=False, index=True)  # WEEKLY / MONTHLY / QUARTERLY
    scope_type = Column(String, nullable=False, default="ORGANIZATION")
    scope_id = Column(String, nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)
    next_run_at = Column(DateTime(timezone=True), nullable=True)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    last_report_id = Column(UUID(as_uuid=True), nullable=True)
    delivery = Column(JSON, nullable=True)  # seam: email/webhook later
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ExecutiveGovernanceDecision(Base):
    """Portfolio-level decision record; execution stays in source domains."""

    __tablename__ = "executive_governance_decisions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scope_type = Column(String, nullable=False, index=True)
    scope_id = Column(String, nullable=False, index=True)
    decision = Column(String, nullable=False, index=True)
    reason = Column(Text, nullable=False)
    actor = Column(String, nullable=False)
    actor_role = Column(String, nullable=True)
    evidence_refs = Column(JSON, nullable=True)
    recommended_domain_actions = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PortfolioProjectionState(Base):
    """Optional projection freshness tracker (idempotent refresh metadata)."""

    __tablename__ = "portfolio_projection_state"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    projection_key = Column(String, nullable=False, unique=True, index=True)
    freshness = Column(String, nullable=False, default="LIVE")
    last_refreshed_at = Column(DateTime(timezone=True), nullable=True)
    last_success_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    refresh_count = Column(Integer, nullable=False, default=0)
    payload_digest = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
