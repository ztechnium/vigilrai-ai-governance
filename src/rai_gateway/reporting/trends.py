"""Time-series aggregation for trend analysis."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import func
from sqlalchemy.orm import Session

from rai_gateway.models.evidence import EvidenceFinding, RuntimeTrajectory
from rai_gateway.models.finops import UsageSettlement
from rai_gateway.models.metering import RuntimeMeteringSpan
from rai_gateway.models.registry import AISystem, RiskAssessment, RiskFinding
from rai_gateway.models.risk_intelligence import RuntimeRiskFinding
from rai_gateway.models.runtime_enforcement import RuntimeEnforcementReceipt
from rai_gateway.reporting.queries import (
    _known_cost,
    _scoped_metering_spans,
    _scoped_usage_settlements,
    _span_occurred_at,
)
from rai_gateway.reporting.schemas import TimeSeriesPoint

if TYPE_CHECKING:
    from rai_gateway.reporting.schemas import ReportFilters


def _points_from_buckets(
    rows, label: str, value_attr: str = "count"
) -> list[TimeSeriesPoint]:
    totals: dict[datetime, float] = {}
    for row in rows:
        bucket = row.bucket
        if bucket is None:
            continue
        totals[bucket] = totals.get(bucket, 0) + float(getattr(row, value_attr) or 0)
    return [
        TimeSeriesPoint(timestamp=bucket, value=totals[bucket], label=label)
        for bucket in sorted(totals)
    ]


def get_spend_trends(
    db: Session,
    filters: ReportFilters,
    start: datetime,
    end: datetime,
) -> tuple[list[TimeSeriesPoint], list[TimeSeriesPoint]]:
    """Daily cost and token totals from metering spans and unlinked settlements."""
    if filters.period_start is None or filters.period_end is None:
        filters = filters.model_copy(update={"period_start": start, "period_end": end})
    span_bucket = func.date_trunc("day", _span_occurred_at()).label("bucket")
    span_rows = (
        _scoped_metering_spans(db, filters)
        .with_entities(
            span_bucket,
            func.coalesce(func.sum(_known_cost(RuntimeMeteringSpan)), 0.0).label(
                "count"
            ),
            func.coalesce(func.sum(RuntimeMeteringSpan.total_tokens), 0).label(
                "tokens"
            ),
        )
        .group_by("bucket")
        .all()
    )
    settlement_bucket = func.date_trunc("day", UsageSettlement.created_at).label(
        "bucket"
    )
    settlement_rows = (
        _scoped_usage_settlements(db, filters)
        .with_entities(
            settlement_bucket,
            func.coalesce(func.sum(_known_cost(UsageSettlement)), 0.0).label("count"),
            func.coalesce(func.sum(UsageSettlement.total_tokens), 0).label("tokens"),
        )
        .group_by("bucket")
        .all()
    )
    rows = list(span_rows) + list(settlement_rows)
    return (
        _points_from_buckets(rows, "Cost"),
        _points_from_buckets(rows, "Tokens", value_attr="tokens"),
    )


def generate_time_buckets(
    start: datetime,
    end: datetime,
    bucket_size_days: int = 1,
) -> list[datetime]:
    """Generate time bucket boundaries for aggregation."""
    buckets = []
    current = start
    while current <= end:
        buckets.append(current)
        current += timedelta(days=bucket_size_days)
    return buckets


def get_finding_trends(
    db: Session,
    filters: ReportFilters,
    start: datetime,
    end: datetime,
) -> dict[str, list[TimeSeriesPoint]]:
    """Get risk finding trends over time.

    Returns trends for:
    - new_findings: Findings created in period
    - open_findings: Findings open at each point
    - resolved_findings: Findings resolved in period
    """
    # Query new findings per day
    new_query = (
        db.query(
            func.date_trunc("day", RiskFinding.created_at).label("bucket"),
            func.count(RiskFinding.id).label("count"),
        )
        .join(RiskAssessment, RiskFinding.risk_assessment_id == RiskAssessment.id)
        .join(AISystem, RiskAssessment.ai_system_id == AISystem.id)
        .filter(RiskFinding.created_at >= start, RiskFinding.created_at <= end)
    )

    if filters.ai_system_id:
        new_query = new_query.filter(
            RiskAssessment.ai_system_id == filters.ai_system_id
        )

    new_query = new_query.group_by("bucket").order_by("bucket")
    new_results = new_query.all()

    runtime_new = (
        db.query(
            func.date_trunc("day", RuntimeRiskFinding.created_at).label("bucket"),
            func.count(RuntimeRiskFinding.id).label("count"),
        )
        .join(AISystem, RuntimeRiskFinding.ai_system_id == AISystem.id)
        .filter(
            RuntimeRiskFinding.created_at >= start, RuntimeRiskFinding.created_at <= end
        )
    )
    if filters.ai_system_id:
        runtime_new = runtime_new.filter(
            RuntimeRiskFinding.ai_system_id == filters.ai_system_id
        )
    runtime_new = runtime_new.group_by("bucket").order_by("bucket")

    evidence_new = (
        db.query(
            func.date_trunc("day", EvidenceFinding.created_at).label("bucket"),
            func.count(EvidenceFinding.id).label("count"),
        )
        .join(RuntimeTrajectory, EvidenceFinding.trajectory_id == RuntimeTrajectory.id)
        .join(AISystem, RuntimeTrajectory.ai_system_id == AISystem.id)
        .filter(EvidenceFinding.created_at >= start, EvidenceFinding.created_at <= end)
    )
    if filters.ai_system_id:
        evidence_new = evidence_new.filter(
            RuntimeTrajectory.ai_system_id == filters.ai_system_id
        )
    evidence_new = evidence_new.group_by("bucket").order_by("bucket")

    new_findings = _points_from_buckets(
        list(new_results) + list(runtime_new.all()) + list(evidence_new.all()),
        "New Findings",
    )

    # Query resolved findings per day
    resolved_query = (
        db.query(
            func.date_trunc("day", RiskFinding.created_at).label("bucket"),
            func.count(RiskFinding.id).label("count"),
        )
        .join(RiskAssessment, RiskFinding.risk_assessment_id == RiskAssessment.id)
        .join(AISystem, RiskAssessment.ai_system_id == AISystem.id)
        .filter(
            RiskFinding.status.in_(["RESOLVED", "CLOSED"]),
            RiskFinding.created_at >= start,
            RiskFinding.created_at <= end,
        )
    )

    if filters.ai_system_id:
        resolved_query = resolved_query.filter(
            RiskAssessment.ai_system_id == filters.ai_system_id
        )

    resolved_query = resolved_query.group_by("bucket").order_by("bucket")
    resolved_results = resolved_query.all()

    runtime_resolved = (
        db.query(
            func.date_trunc("day", RuntimeRiskFinding.created_at).label("bucket"),
            func.count(RuntimeRiskFinding.id).label("count"),
        )
        .join(AISystem, RuntimeRiskFinding.ai_system_id == AISystem.id)
        .filter(
            func.upper(RuntimeRiskFinding.status).in_(
                ["RESOLVED", "CLOSED", "FALSE_POSITIVE"]
            ),
            RuntimeRiskFinding.created_at >= start,
            RuntimeRiskFinding.created_at <= end,
        )
    )
    if filters.ai_system_id:
        runtime_resolved = runtime_resolved.filter(
            RuntimeRiskFinding.ai_system_id == filters.ai_system_id
        )
    runtime_resolved = runtime_resolved.group_by("bucket").order_by("bucket")

    evidence_resolved = (
        db.query(
            func.date_trunc("day", EvidenceFinding.created_at).label("bucket"),
            func.count(EvidenceFinding.id).label("count"),
        )
        .join(RuntimeTrajectory, EvidenceFinding.trajectory_id == RuntimeTrajectory.id)
        .join(AISystem, RuntimeTrajectory.ai_system_id == AISystem.id)
        .filter(
            func.upper(EvidenceFinding.status).in_(["RESOLVED", "CLOSED", "DISMISSED"]),
            EvidenceFinding.created_at >= start,
            EvidenceFinding.created_at <= end,
        )
    )
    if filters.ai_system_id:
        evidence_resolved = evidence_resolved.filter(
            RuntimeTrajectory.ai_system_id == filters.ai_system_id
        )
    evidence_resolved = evidence_resolved.group_by("bucket").order_by("bucket")

    resolved_findings = _points_from_buckets(
        list(resolved_results)
        + list(runtime_resolved.all())
        + list(evidence_resolved.all()),
        "Resolved Findings",
    )

    # Open findings would require point-in-time snapshots, which we don't have yet
    # For now, return new and resolved

    return {
        "new_findings": new_findings,
        "resolved_findings": resolved_findings,
    }


def get_policy_evaluation_trends(
    db: Session,
    filters: ReportFilters,
    start: datetime,
    end: datetime,
) -> list[TimeSeriesPoint]:
    """Get policy evaluation trends over time."""
    query = (
        db.query(
            func.date_trunc("day", RuntimeEnforcementReceipt.started_at).label(
                "bucket"
            ),
            func.count(RuntimeEnforcementReceipt.id).label("count"),
        )
        .join(AISystem, RuntimeEnforcementReceipt.ai_system_id == AISystem.id)
        .filter(
            RuntimeEnforcementReceipt.started_at >= start,
            RuntimeEnforcementReceipt.started_at <= end,
        )
    )

    if filters.ai_system_id:
        query = query.filter(
            RuntimeEnforcementReceipt.ai_system_id == filters.ai_system_id
        )

    query = query.group_by("bucket").order_by("bucket")
    results = query.all()

    return [
        TimeSeriesPoint(
            timestamp=row.bucket, value=row.count, label="Policy Evaluations"
        )
        for row in results
    ]


def get_policy_trigger_trends(
    db: Session,
    filters: ReportFilters,
    start: datetime,
    end: datetime,
) -> list[TimeSeriesPoint]:
    """Get policy trigger trends over time."""
    query = (
        db.query(
            func.date_trunc("day", RuntimeEnforcementReceipt.started_at).label(
                "bucket"
            ),
            func.count(RuntimeEnforcementReceipt.id).label("count"),
        )
        .join(AISystem, RuntimeEnforcementReceipt.ai_system_id == AISystem.id)
        .filter(
            RuntimeEnforcementReceipt.started_at >= start,
            RuntimeEnforcementReceipt.started_at <= end,
            RuntimeEnforcementReceipt.policy_effect.in_(
                ["MONITOR", "REQUIRE_APPROVAL", "DENY", "SUSPEND"]
            ),
        )
    )

    if filters.ai_system_id:
        query = query.filter(
            RuntimeEnforcementReceipt.ai_system_id == filters.ai_system_id
        )

    query = query.group_by("bucket").order_by("bucket")
    results = query.all()

    return [
        TimeSeriesPoint(timestamp=row.bucket, value=row.count, label="Policy Triggers")
        for row in results
    ]


def get_execution_trends(
    db: Session,
    filters: ReportFilters,
    start: datetime,
    end: datetime,
) -> list[TimeSeriesPoint]:
    """Get execution trends over time."""
    query = (
        db.query(
            func.date_trunc("day", RuntimeTrajectory.started_at).label("bucket"),
            func.count(RuntimeTrajectory.id).label("count"),
        )
        .join(AISystem, RuntimeTrajectory.ai_system_id == AISystem.id)
        .filter(
            RuntimeTrajectory.started_at >= start, RuntimeTrajectory.started_at <= end
        )
    )

    if filters.ai_system_id:
        query = query.filter(RuntimeTrajectory.ai_system_id == filters.ai_system_id)

    query = query.group_by("bucket").order_by("bucket")
    results = query.all()

    return [
        TimeSeriesPoint(timestamp=row.bucket, value=row.count, label="Executions")
        for row in results
    ]
