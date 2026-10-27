"""Pydantic schemas for reporting API contracts."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class FreshnessMode(str, Enum):
    """Report freshness mode."""

    LIVE = "LIVE"
    NEAR_REAL_TIME = "NEAR_REAL_TIME"
    SNAPSHOT = "SNAPSHOT"


class Freshness(BaseModel):
    """Report freshness metadata."""

    mode: FreshnessMode = FreshnessMode.LIVE
    last_refreshed_at: datetime = Field(default_factory=datetime.utcnow)


class ReportScope(BaseModel):
    """Report scope metadata."""

    ai_system_id: UUID | None = None
    agent_id: UUID | None = None
    runtime_identity_id: UUID | None = None


class ReportPeriod(BaseModel):
    """Report time period."""

    start: datetime
    end: datetime


class ReportFilters(BaseModel):
    """Common reporting filter schema."""

    period_start: datetime | None = None
    period_end: datetime | None = None

    business_unit: str | None = None
    ai_system_id: UUID | None = None
    agent_id: UUID | None = None
    agent_version_id: UUID | None = None
    runtime_identity_id: UUID | None = None
    environment: str | None = None

    conversation_id: UUID | None = None
    trajectory_id: UUID | None = None

    policy_type: str | None = None
    policy_id: UUID | None = None
    effect: str | None = None
    decision: str | None = None

    risk_severity: list[str] | None = None
    risk_category: list[str] | None = None
    finding_status: list[str] | None = None

    model_id: UUID | None = None
    tool_id: UUID | None = None
    mcp_server_id: UUID | None = None
    data_source_id: UUID | None = None

    budget_id: UUID | None = None
    budget_metric: str | None = None


class ComparisonMetric(BaseModel):
    """Metric with previous period comparison."""

    value: int | float
    previous_value: int | float | None = None
    change_pct: float | None = None
    trend_direction: str | None = None  # "up", "down", "stable"


class KpiMetric(BaseModel):
    """Key performance indicator metric."""

    title: str
    value: int | float
    previous_value: int | float | None = None
    change_pct: float | None = None
    trend_direction: str | None = None
    status_tone: str | None = None  # "neutral", "warn", "danger", "success"
    link: str | None = None


class SeverityDistribution(BaseModel):
    """Risk severity distribution."""

    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    info: int = 0


class EffectDistribution(BaseModel):
    """Policy effect distribution."""

    allow: int = 0
    monitor: int = 0
    require_approval: int = 0
    deny: int = 0
    suspend: int = 0


class AttentionItem(BaseModel):
    """Executive attention queue item."""

    type: str
    severity: str
    title: str
    ai_system_id: UUID | None = None
    source_type: str
    source_id: UUID
    reason: str
    recommended_action: str | None = None
    due_at: datetime | None = None
    created_at: datetime


class TimeSeriesPoint(BaseModel):
    """Time series data point."""

    timestamp: datetime
    value: int | float
    label: str | None = None


class RankedItem(BaseModel):
    """Ranked item for charts."""

    id: UUID
    name: str
    value: int | float
    secondary_value: int | float | None = None
    severity: str | None = None
    link: str | None = None


class ReportSummary(BaseModel):
    """Executive summary report."""

    scope: ReportScope
    period: ReportPeriod
    freshness: Freshness

    # Top-level KPIs
    ai_systems_governed: ComparisonMetric
    governed_actions: ComparisonMetric
    current_risk_exposure: ComparisonMetric
    policy_intervention_rate: ComparisonMetric
    budget_utilization_pct: ComparisonMetric
    assurance_coverage_pct: ComparisonMetric
    open_critical_findings: ComparisonMetric

    # Risk breakdown
    risk_by_severity: SeverityDistribution

    # Policy effectiveness
    policy_effects: EffectDistribution

    # Attention items
    attention: list[AttentionItem] = []


class RiskReport(BaseModel):
    """Risk analysis report."""

    scope: ReportScope
    period: ReportPeriod
    freshness: Freshness

    # Summary metrics
    open_findings: int
    new_findings: int
    resolved_findings: int
    critical_findings: int
    high_findings: int
    mean_time_to_resolution_hours: float | None = None

    # Distributions
    severity_distribution: SeverityDistribution
    category_distribution: dict[str, int] = {}
    status_distribution: dict[str, int] = {}

    # Risk by entity
    risk_by_ai_system: list[RankedItem] = []
    risk_by_agent: list[RankedItem] = []
    risk_by_tool: list[RankedItem] = []
    risk_by_model: list[RankedItem] = []

    # Trends
    finding_trends: list[TimeSeriesPoint] = []

    # Attention
    attention: list[AttentionItem] = []


class PolicyReport(BaseModel):
    """Policy effectiveness report."""

    scope: ReportScope
    period: ReportPeriod
    freshness: Freshness

    # Summary metrics
    evaluations: int
    triggers: int
    trigger_rate: float
    intervention_rate: float
    deny_rate: float

    # Effect distribution
    effects: EffectDistribution

    # Top policies
    top_policies: list[RankedItem] = []

    # Trends
    evaluation_trends: list[TimeSeriesPoint] = []
    trigger_trends: list[TimeSeriesPoint] = []


class BudgetStatus(BaseModel):
    """Budget status details."""

    id: UUID
    name: str
    metric: str
    current_usage: float
    limit_value: float
    warning_threshold: float
    utilization_pct: float
    status: str  # "OK", "WARNING", "EXCEEDED"
    window: str
    warning_events: int = 0
    exceeded_events: int = 0


class BudgetReport(BaseModel):
    """Budget and cost report."""

    scope: ReportScope
    period: ReportPeriod
    freshness: Freshness

    # Summary metrics
    total_budgets: int
    budgets_warning: int
    budgets_exceeded: int
    total_cost: float = 0.0
    total_tokens: int = 0

    # Budget statuses
    budgets: list[BudgetStatus] = []

    # Trends
    cost_trends: list[TimeSeriesPoint] = []
    token_trends: list[TimeSeriesPoint] = []


class RuntimeReport(BaseModel):
    """Runtime governance activity report."""

    scope: ReportScope
    period: ReportPeriod
    freshness: Freshness

    # Summary metrics
    governed_actions: int
    executions: int
    conversations: int
    execution_success_rate: float

    # Governance funnel
    policy_evaluations: int
    interventions: int
    approvals_required: int
    denied: int
    runtime_suspensions: int


class AssuranceReport(BaseModel):
    """Assurance and control coverage report."""

    scope: ReportScope
    period: ReportPeriod
    freshness: Freshness

    # Summary metrics
    assurance_coverage_pct: float
    valid_assurance: int
    conditional_assurance: int
    expired_assurance: int
    failed_assurance: int

    # Evaluations
    evaluation_pass_rate: float
    failed_deployment_gates: int

    # Waivers and exceptions
    active_waivers: int
    expiring_waivers: int
    open_exceptions: int
    expiring_exceptions: int


class AISystemReport(BaseModel):
    """AI System detailed report."""

    scope: ReportScope
    period: ReportPeriod
    freshness: Freshness

    # Execution metrics
    executions: int
    conversations: int
    governed_actions: int
    execution_success_rate: float

    # Risk metrics
    open_findings: int
    critical_findings: int
    risk_score: float | None = None
    risk_trend: str | None = None

    # Policy metrics
    policy_trigger_rate: float
    deny_rate: float
    approval_rate: float

    # Budget metrics
    budget_usage: float = 0.0
    token_usage: int = 0
    cost: float = 0.0

    # Assurance
    assurance_status: str | None = None
    evidence_completeness_pct: float | None = None

    # Incidents
    incidents: int = 0
    exceptions: int = 0
    evaluation_waivers: int = 0

    # Component breakdown
    risk_by_agent: list[RankedItem] = []
    risk_by_tool: list[RankedItem] = []
    risk_by_model: list[RankedItem] = []


class ConversationReport(BaseModel):
    """Conversation detailed report."""

    scope: ReportScope
    period: ReportPeriod
    freshness: Freshness

    # Conversation metrics
    turns: int
    actions: int
    tool_calls: int

    # Policy metrics
    policy_evaluations: int
    policy_triggers: int
    findings: int
    highest_risk: str | None = None

    # Approvals
    approvals_requested: int
    approvals_approved: int
    approvals_rejected: int
    denied_actions: int

    # Budget
    budget_events: int
    token_usage: int | None = None
    cost: float | None = None

    # Evidence
    evidence_completeness_pct: float | None = None

    # Event timeline
    events: list[dict[str, Any]] = []


class SnapshotFilters(BaseModel):
    """Report snapshot filters."""

    report_type: str | None = None
    scope_type: str | None = None
    generated_after: datetime | None = None
    generated_before: datetime | None = None
    limit: int = 50
    offset: int = 0


class ReportSnapshot(BaseModel):
    """Immutable historical report snapshot."""

    id: UUID
    report_type: str
    scope_type: str
    scope_id: UUID | None
    period_start: datetime
    period_end: datetime
    filters_json: dict[str, Any]
    generated_at: datetime
    generated_by: str
    schema_version: str
    data_snapshot: dict[str, Any]
    source_manifest: dict[str, list[UUID]] | None
    content_digest: str


class ReportSnapshotCreate(BaseModel):
    """Request to create a report snapshot."""

    report_type: str
    scope_type: str = "ORGANIZATION"
    scope_id: UUID | None = None
    filters: ReportFilters
