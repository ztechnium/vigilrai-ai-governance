"""Shared report filter normalization and period utilities."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy.orm import Query

if TYPE_CHECKING:
    from rai_gateway.reporting.schemas import ReportFilters


def get_default_period(days: int = 30) -> tuple[datetime, datetime]:
    """Get default reporting period (last N days)."""
    end = datetime.utcnow()
    start = end - timedelta(days=days)
    return start, end


def get_previous_period(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    """Calculate equivalent previous period for comparison."""
    duration = end - start
    previous_end = start
    previous_start = previous_end - duration
    return previous_start, previous_end


def calculate_change_pct(
    current: int | float, previous: int | float | None
) -> float | None:
    """Calculate percentage change from previous period."""
    if previous is None or previous == 0:
        return None
    return ((current - previous) / previous) * 100


def get_trend_direction(change_pct: float | None) -> str | None:
    """Determine trend direction from change percentage."""
    if change_pct is None:
        return None
    if abs(change_pct) < 5:
        return "stable"
    return "up" if change_pct > 0 else "down"


def apply_time_filter(query: Query, time_column, filters: ReportFilters) -> Query:
    """Apply time period filters to a query."""
    if filters.period_start:
        query = query.filter(time_column >= filters.period_start)
    if filters.period_end:
        query = query.filter(time_column <= filters.period_end)
    return query


def apply_ai_system_filter(
    query: Query, system_column, filters: ReportFilters
) -> Query:
    """Apply AI system filter if specified."""
    if filters.ai_system_id:
        query = query.filter(system_column == filters.ai_system_id)
    return query


def apply_agent_filter(query: Query, agent_column, filters: ReportFilters) -> Query:
    """Apply agent filter if specified."""
    if filters.agent_id:
        query = query.filter(agent_column == filters.agent_id)
    if filters.agent_version_id:
        query = query.filter(
            query._entities[0].entity_zero.mapper.class_.agent_version_id
            == filters.agent_version_id
        )
    return query


def apply_runtime_identity_filter(
    query: Query, identity_column, filters: ReportFilters
) -> Query:
    """Apply runtime identity filter if specified."""
    if filters.runtime_identity_id:
        query = query.filter(identity_column == filters.runtime_identity_id)
    return query


def apply_conversation_filter(
    query: Query, conversation_column, filters: ReportFilters
) -> Query:
    """Apply conversation filter if specified."""
    if filters.conversation_id:
        query = query.filter(conversation_column == filters.conversation_id)
    if filters.trajectory_id:
        query = query.filter(
            query._entities[0].entity_zero.mapper.class_.id == filters.trajectory_id
        )
    return query


def apply_risk_filters(query: Query, filters: ReportFilters) -> Query:
    """Apply risk-related filters."""
    model_class = query._entities[0].entity_zero.mapper.class_

    if filters.risk_severity:
        query = query.filter(model_class.severity.in_(filters.risk_severity))
    if filters.risk_category:
        query = query.filter(model_class.category.in_(filters.risk_category))
    if filters.finding_status:
        query = query.filter(model_class.status.in_(filters.finding_status))

    return query


def apply_policy_filters(query: Query, filters: ReportFilters) -> Query:
    """Apply policy-related filters."""
    model_class = query._entities[0].entity_zero.mapper.class_

    if filters.policy_type:
        query = query.filter(model_class.policy_type == filters.policy_type)
    if filters.policy_id:
        query = query.filter(model_class.policy_id == filters.policy_id)
    if filters.effect:
        query = query.filter(model_class.effect == filters.effect)
    if filters.decision:
        query = query.filter(model_class.enforcement_decision == filters.decision)

    return query


def apply_resource_filters(query: Query, filters: ReportFilters) -> Query:
    """Apply resource-related filters (model, tool, data source)."""
    model_class = query._entities[0].entity_zero.mapper.class_

    if filters.model_id:
        if hasattr(model_class, "model_id"):
            query = query.filter(model_class.model_id == filters.model_id)
    if filters.tool_id:
        if hasattr(model_class, "tool_id"):
            query = query.filter(model_class.tool_id == filters.tool_id)
    if filters.mcp_server_id:
        if hasattr(model_class, "mcp_server_id"):
            query = query.filter(model_class.mcp_server_id == filters.mcp_server_id)
    if filters.data_source_id:
        if hasattr(model_class, "data_source_id"):
            query = query.filter(model_class.data_source_id == filters.data_source_id)

    return query


def apply_budget_filters(query: Query, filters: ReportFilters) -> Query:
    """Apply budget-related filters."""
    model_class = query._entities[0].entity_zero.mapper.class_

    if filters.budget_id:
        if hasattr(model_class, "budget_id"):
            query = query.filter(model_class.budget_id == filters.budget_id)
    if filters.budget_metric:
        if hasattr(model_class, "metric"):
            query = query.filter(model_class.metric == filters.budget_metric)

    return query


def apply_common_filters(
    query: Query,
    filters: ReportFilters,
    time_column=None,
    system_column=None,
) -> Query:
    """Apply common filters to a query.

    This is a convenience function that applies the most common filter combinations.
    Individual filter functions can be used for more fine-grained control.
    """
    # Time filter
    if time_column is not None:
        query = apply_time_filter(query, time_column, filters)

    # AI system filter
    if system_column is not None:
        query = apply_ai_system_filter(query, system_column, filters)

    # Other filters
    model_class = query._entities[0].entity_zero.mapper.class_

    if hasattr(model_class, "agent_id"):
        query = apply_agent_filter(query, model_class.agent_id, filters)
    if hasattr(model_class, "runtime_identity_id"):
        query = apply_runtime_identity_filter(
            query, model_class.runtime_identity_id, filters
        )

    return query
