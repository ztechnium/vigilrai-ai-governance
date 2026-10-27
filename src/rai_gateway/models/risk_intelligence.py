"""SQLAlchemy models for WP6 continuous risk intelligence."""

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
from sqlalchemy.sql import func

from rai_gateway.models.database import Base


class ContentEvaluatorConfig(Base):
    """Server-side content evaluator provider configuration."""

    __tablename__ = "content_evaluator_configs"
    __table_args__ = (
        UniqueConstraint(
            "ai_system_id",
            name="uq_content_evaluator_config_ai_system",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ai_system_id = Column(
        UUID(as_uuid=True), ForeignKey("ai_systems.id"), nullable=True, index=True
    )
    provider = Column(String, nullable=False, default="mock")
    model = Column(String, nullable=False, default="mock-evaluator")
    temperature = Column(Float, nullable=False, default=0.0)
    timeout_seconds = Column(Integer, nullable=False, default=30)
    max_rules_per_call = Column(Integer, nullable=False, default=20)
    confidence_threshold = Column(Float, nullable=False, default=0.5)
    minimum_confidence_to_mark = Column(Float, nullable=False, default=0.5)
    minimum_confidence_to_monitor = Column(Float, nullable=False, default=0.7)
    minimum_confidence_to_intervene = Column(Float, nullable=False, default=0.9)
    fail_closed = Column(Boolean, nullable=False, default=False)
    fallback_provider = Column(String, nullable=True)
    enabled = Column(Boolean, nullable=False, default=False, index=True)
    # API key stored server-side only; never returned to clients.
    api_key_encrypted = Column(Text, nullable=True)
    health_status = Column(String, nullable=False, default="UNAVAILABLE")
    last_success_at = Column(DateTime(timezone=True), nullable=True)
    last_error_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    latency_ms_avg = Column(Float, nullable=True)
    error_rate = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RiskSignal(Base):
    __tablename__ = "risk_signals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trajectory_id = Column(
        UUID(as_uuid=True),
        ForeignKey("runtime_trajectories.id"),
        nullable=True,
        index=True,
    )
    ai_system_id = Column(
        UUID(as_uuid=True), ForeignKey("ai_systems.id"), nullable=False, index=True
    )
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=True)
    agent_version_id = Column(
        UUID(as_uuid=True), ForeignKey("agent_versions.id"), nullable=True
    )
    runtime_identity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_runtime_identities.id"),
        nullable=True,
        index=True,
    )
    signal_type = Column(String, nullable=False, index=True)
    source_event_id = Column(UUID(as_uuid=True), nullable=True)
    source_type = Column(String, nullable=False, default="DERIVED")
    confidence = Column(Float, nullable=False, default=0.0)
    severity = Column(String, nullable=False, default="INFO", index=True)
    sensitivity = Column(String, nullable=False, default="NORMAL")
    dimensions = Column(JSON, nullable=True)
    evidence_refs = Column(JSON, nullable=True)
    category = Column(String, nullable=True, index=True)
    payload = Column(JSON, nullable=True)
    occurred_at = Column(DateTime(timezone=True), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class RiskState(Base):
    __tablename__ = "risk_states"
    __table_args__ = (
        UniqueConstraint("scope_type", "scope_id", name="uq_risk_state_scope"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ai_system_id = Column(
        UUID(as_uuid=True), ForeignKey("ai_systems.id"), nullable=False, index=True
    )
    scope_type = Column(String, nullable=False, index=True)
    scope_id = Column(String, nullable=False, index=True)
    current_level = Column(String, nullable=False, default="NONE", index=True)
    cumulative_score = Column(Integer, nullable=False, default=0)
    signal_count = Column(Integer, nullable=False, default=0)
    high_severity_count = Column(Integer, nullable=False, default=0)
    score_breakdown = Column(JSON, nullable=True)
    dimensions = Column(JSON, nullable=True)
    last_signal_at = Column(DateTime(timezone=True), nullable=True)
    monitoring_status = Column(String, nullable=False, default="NONE")
    require_approval = Column(Boolean, nullable=False, default=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class RuntimeRiskFinding(Base):
    """Runtime risk finding (distinct from WP1 design-time risk_findings)."""

    __tablename__ = "runtime_risk_findings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trajectory_id = Column(
        UUID(as_uuid=True),
        ForeignKey("runtime_trajectories.id"),
        nullable=True,
        index=True,
    )
    ai_system_id = Column(
        UUID(as_uuid=True), ForeignKey("ai_systems.id"), nullable=False, index=True
    )
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=True)
    agent_version_id = Column(
        UUID(as_uuid=True), ForeignKey("agent_versions.id"), nullable=True
    )
    runtime_identity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_runtime_identities.id"),
        nullable=True,
        index=True,
    )
    finding_type = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    severity = Column(String, nullable=False, default="INFO", index=True)
    confidence = Column(Float, nullable=False, default=0.0)
    sensitivity = Column(String, nullable=False, default="NORMAL")
    category = Column(String, nullable=True, index=True)
    dimensions = Column(JSON, nullable=True)
    signal_ids = Column(JSON, nullable=True)
    evidence_refs = Column(JSON, nullable=True)
    policy_rule_ids = Column(JSON, nullable=True)
    intervention_effect = Column(String, nullable=True)
    status = Column(String, nullable=False, default="OPEN", index=True)
    explanation = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RiskMonitorRule(Base):
    __tablename__ = "risk_monitor_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ai_system_id = Column(
        UUID(as_uuid=True), ForeignKey("ai_systems.id"), nullable=False, index=True
    )
    name = Column(String, nullable=False)
    scope = Column(String, nullable=False, default="RUNTIME_IDENTITY")
    signal_type = Column(String, nullable=True)
    tool_id = Column(UUID(as_uuid=True), ForeignKey("tool_resources.id"), nullable=True)
    tool_name = Column(String, nullable=True)
    window_seconds = Column(Integer, nullable=False, default=600)
    aggregation = Column(String, nullable=False, default="COUNT")
    threshold = Column(Float, nullable=False)
    amount_parameter_path = Column(String, nullable=True)
    effect = Column(String, nullable=False, default="MARK_AND_MONITOR")
    monitor_duration_seconds = Column(Integer, nullable=True, default=1800)
    monitor_action_count = Column(Integer, nullable=True)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RiskMonitor(Base):
    __tablename__ = "risk_monitors"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ai_system_id = Column(
        UUID(as_uuid=True), ForeignKey("ai_systems.id"), nullable=False, index=True
    )
    monitor_rule_id = Column(
        UUID(as_uuid=True), ForeignKey("risk_monitor_rules.id"), nullable=True
    )
    scope_type = Column(String, nullable=False, index=True)
    scope_id = Column(String, nullable=False, index=True)
    reason = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="ACTIVE", index=True)
    current_count = Column(Integer, nullable=False, default=0)
    current_sum = Column(Float, nullable=False, default=0.0)
    threshold = Column(Float, nullable=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    finding_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RuntimeConstraint(Base):
    __tablename__ = "runtime_constraints"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ai_system_id = Column(
        UUID(as_uuid=True), ForeignKey("ai_systems.id"), nullable=False, index=True
    )
    scope_type = Column(String, nullable=False, index=True)
    scope_id = Column(String, nullable=False, index=True)
    resource_type = Column(String, nullable=True)
    resource_id = Column(String, nullable=True)
    constraint_type = Column(String, nullable=False)
    value = Column(JSON, nullable=True)
    reason = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="ACTIVE", index=True)
    starts_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    intervention_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class InterventionDecision(Base):
    __tablename__ = "intervention_decisions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trajectory_id = Column(
        UUID(as_uuid=True),
        ForeignKey("runtime_trajectories.id"),
        nullable=True,
        index=True,
    )
    ai_system_id = Column(
        UUID(as_uuid=True), ForeignKey("ai_systems.id"), nullable=False, index=True
    )
    scope_type = Column(String, nullable=False)
    scope_id = Column(String, nullable=False, index=True)
    effect = Column(String, nullable=False, index=True)
    reason = Column(Text, nullable=True)
    risk_level = Column(String, nullable=True)
    confidence = Column(Float, nullable=True)
    triggering_signal_ids = Column(JSON, nullable=True)
    policy_rule_ids = Column(JSON, nullable=True)
    finding_id = Column(UUID(as_uuid=True), nullable=True)
    status = Column(String, nullable=False, default="RECOMMENDED", index=True)
    authorization_mode = Column(String, nullable=True)
    automatic = Column(Boolean, nullable=False, default=False)
    explanation = Column(JSON, nullable=True)
    executed_at = Column(DateTime(timezone=True), nullable=True)
    executed_by = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PolicyRecommendation(Base):
    __tablename__ = "policy_recommendations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ai_system_id = Column(
        UUID(as_uuid=True), ForeignKey("ai_systems.id"), nullable=False, index=True
    )
    recommendation_type = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False)
    rationale = Column(Text, nullable=True)
    evidence_refs = Column(JSON, nullable=True)
    proposed_rule = Column(JSON, nullable=True)
    confidence = Column(Float, nullable=False, default=0.0)
    pattern_key = Column(String, nullable=True, index=True)
    status = Column(String, nullable=False, default="NEW", index=True)
    draft_rule_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ContentEvaluationResult(Base):
    __tablename__ = "content_evaluation_results"
    __table_args__ = (
        UniqueConstraint(
            "cache_key",
            name="uq_content_evaluation_cache_key",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ai_system_id = Column(
        UUID(as_uuid=True), ForeignKey("ai_systems.id"), nullable=False, index=True
    )
    trajectory_id = Column(
        UUID(as_uuid=True),
        ForeignKey("runtime_trajectories.id"),
        nullable=True,
        index=True,
    )
    content_type = Column(String, nullable=False)
    evaluation_mode = Column(String, nullable=False)
    status = Column(String, nullable=False, index=True)
    failure_type = Column(String, nullable=True)
    provider = Column(String, nullable=True)
    model = Column(String, nullable=True)
    content_digest = Column(String, nullable=False, index=True)
    rule_set_digest = Column(String, nullable=False)
    cache_key = Column(String, nullable=False)
    evaluations = Column(JSON, nullable=True)
    rule_ids = Column(JSON, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class RuntimeBudget(Base):
    """Operational runtime budget / limit configuration."""

    __tablename__ = "runtime_budgets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ai_system_id = Column(
        UUID(as_uuid=True), ForeignKey("ai_systems.id"), nullable=True, index=True
    )
    name = Column(String, nullable=False)
    scope_type = Column(String, nullable=False, default="RUNTIME_IDENTITY", index=True)
    scope_id = Column(String, nullable=True, index=True)
    metric = Column(String, nullable=False, index=True)
    tool_name = Column(String, nullable=True, index=True)
    tool_id = Column(UUID(as_uuid=True), ForeignKey("tool_resources.id"), nullable=True)
    resource_filter = Column(JSON, nullable=True)
    limit_value = Column(Float, nullable=False)
    window_seconds = Column(Integer, nullable=False, default=3600)
    warning_threshold = Column(Float, nullable=False, default=0.8)
    effect_on_exceed = Column(String, nullable=False, default="DENY")
    amount_parameter_path = Column(String, nullable=True)
    # BEST_EFFORT: missing measurement → SKIP; MANDATORY → DENY
    enforcement_mode = Column(String, nullable=False, default="BEST_EFFORT")
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RuntimeBudgetWindow(Base):
    """Locked current usage window for concurrency-safe budget checks."""

    __tablename__ = "runtime_budget_windows"
    __table_args__ = (
        UniqueConstraint(
            "budget_id",
            "scope_id",
            "window_start",
            name="uq_budget_window_scope_start",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    budget_id = Column(
        UUID(as_uuid=True),
        ForeignKey("runtime_budgets.id"),
        nullable=False,
        index=True,
    )
    ai_system_id = Column(
        UUID(as_uuid=True), ForeignKey("ai_systems.id"), nullable=True, index=True
    )
    scope_type = Column(String, nullable=False)
    scope_id = Column(String, nullable=False, index=True)
    window_start = Column(DateTime(timezone=True), nullable=False, index=True)
    window_end = Column(DateTime(timezone=True), nullable=False)
    usage_value = Column(Float, nullable=False, default=0.0)
    reserved_value = Column(Float, nullable=False, default=0.0)
    status = Column(String, nullable=False, default="OK", index=True)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class RuntimeBudgetCheck(Base):
    """Evidence record for each budget evaluation."""

    __tablename__ = "runtime_budget_checks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    budget_id = Column(
        UUID(as_uuid=True),
        ForeignKey("runtime_budgets.id"),
        nullable=False,
        index=True,
    )
    ai_system_id = Column(
        UUID(as_uuid=True), ForeignKey("ai_systems.id"), nullable=True, index=True
    )
    runtime_identity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_runtime_identities.id"),
        nullable=True,
        index=True,
    )
    agent_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    agent_version_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    delegation_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    model_resource_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    tool_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    trajectory_id = Column(
        UUID(as_uuid=True),
        ForeignKey("runtime_trajectories.id"),
        nullable=True,
        index=True,
    )
    enforcement_receipt_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    metering_span_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    reservation_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    reconciliation_status = Column(String, nullable=True)
    metric = Column(String, nullable=False)
    window_seconds = Column(Integer, nullable=False)
    usage_before = Column(Float, nullable=False)
    attempted_increment = Column(Float, nullable=False)
    projected_usage = Column(Float, nullable=False)
    limit_value = Column(Float, nullable=False)
    status = Column(String, nullable=False)
    decision = Column(String, nullable=False)
    effect = Column(String, nullable=True)
    evidence_refs = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class RuntimeBudgetReservation(Base):
    """Pre-execution hold against a budget window for COST/TOKEN metrics."""

    __tablename__ = "runtime_budget_reservations"
    __table_args__ = (
        UniqueConstraint(
            "budget_id",
            "idempotency_key",
            name="uq_budget_reservation_idempotency",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    budget_id = Column(
        UUID(as_uuid=True),
        ForeignKey("runtime_budgets.id"),
        nullable=False,
        index=True,
    )
    budget_window_id = Column(
        UUID(as_uuid=True),
        ForeignKey("runtime_budget_windows.id"),
        nullable=True,
        index=True,
    )
    runtime_identity_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    delegation_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    trajectory_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    enforcement_receipt_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    finops_usage_reservation_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    idempotency_key = Column(String, nullable=False, index=True)
    metric = Column(String, nullable=False)
    reserved_value = Column(Float, nullable=False, default=0.0)
    settled_value = Column(Float, nullable=True)
    delta_value = Column(Float, nullable=True)
    status = Column(String, nullable=False, default="RESERVED", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    settled_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)


class EmergingRiskCandidate(Base):
    """Human-review candidate for unclassified/emerging patterns (never auto-policy)."""

    __tablename__ = "emerging_risk_candidates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ai_system_id = Column(
        UUID(as_uuid=True), ForeignKey("ai_systems.id"), nullable=False, index=True
    )
    pattern_key = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    severity = Column(String, nullable=False, default="MEDIUM")
    evidence_refs = Column(JSON, nullable=True)
    signal_ids = Column(JSON, nullable=True)
    status = Column(String, nullable=False, default="NEW", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
