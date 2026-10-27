"""Metric calculation helpers for reporting."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rai_gateway.reporting.filters import calculate_change_pct, get_trend_direction
from rai_gateway.reporting.schemas import ComparisonMetric, KpiMetric

if TYPE_CHECKING:
    pass


def build_comparison_metric(
    current: int | float,
    previous: int | float | None = None,
) -> ComparisonMetric:
    """Build a comparison metric with change calculation."""
    change_pct = calculate_change_pct(current, previous)
    trend_direction = get_trend_direction(change_pct)

    return ComparisonMetric(
        value=current,
        previous_value=previous,
        change_pct=round(change_pct, 2) if change_pct is not None else None,
        trend_direction=trend_direction,
    )


def build_kpi_metric(
    title: str,
    current: int | float,
    previous: int | float | None = None,
    status_tone: str | None = None,
    link: str | None = None,
) -> KpiMetric:
    """Build a KPI metric with comparison."""
    change_pct = calculate_change_pct(current, previous)
    trend_direction = get_trend_direction(change_pct)

    return KpiMetric(
        title=title,
        value=current,
        previous_value=previous,
        change_pct=round(change_pct, 2) if change_pct is not None else None,
        trend_direction=trend_direction,
        status_tone=status_tone,
        link=link,
    )


def calculate_rate(numerator: int, denominator: int) -> float:
    """Calculate a rate percentage."""
    if denominator == 0:
        return 0.0
    return (numerator / denominator) * 100


def calculate_utilization_pct(current: float, limit: float) -> float:
    """Calculate budget/resource utilization percentage."""
    if limit == 0:
        return 0.0
    return (current / limit) * 100


def determine_status_tone(
    value: float,
    warning_threshold: float | None = None,
    critical_threshold: float | None = None,
    higher_is_worse: bool = True,
) -> str:
    """Determine status tone based on thresholds.

    Args:
        value: Current value
        warning_threshold: Warning threshold
        critical_threshold: Critical/danger threshold
        higher_is_worse: If True, higher values are worse (e.g., risk). If False, lower is worse.

    Returns:
        Status tone: "neutral", "success", "warn", or "danger"
    """
    if critical_threshold is not None:
        if higher_is_worse and value >= critical_threshold:
            return "danger"
        elif not higher_is_worse and value <= critical_threshold:
            return "danger"

    if warning_threshold is not None:
        if higher_is_worse and value >= warning_threshold:
            return "warn"
        elif not higher_is_worse and value <= warning_threshold:
            return "warn"

    # Value is within acceptable range
    if value == 0 and higher_is_worse:
        return "success"

    return "neutral"


def calculate_intervention_rate(
    monitors: int,
    approvals: int,
    denies: int,
    suspends: int,
    total_actions: int,
) -> float:
    """Calculate policy intervention rate.

    Intervention rate = (MONITOR + REQUIRE_APPROVAL + DENY + SUSPEND) / total actions
    """
    if total_actions == 0:
        return 0.0

    interventions = monitors + approvals + denies + suspends
    return (interventions / total_actions) * 100


def calculate_assurance_coverage(
    systems_with_valid_assurance: int,
    total_systems: int,
) -> float:
    """Calculate assurance coverage percentage."""
    if total_systems == 0:
        return 0.0
    return (systems_with_valid_assurance / total_systems) * 100
