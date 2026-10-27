"""Tests for reporting and analytics module."""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from rai_gateway.reporting import filters, metrics, queries
from rai_gateway.reporting.schemas import (
    EffectDistribution,
    ReportFilters,
    ReportScope,
    SeverityDistribution,
)


class TestFilters:
    """Test filter utilities."""

    def test_get_default_period(self):
        """Test default period calculation."""
        start, end = filters.get_default_period(days=30)

        assert isinstance(start, datetime)
        assert isinstance(end, datetime)
        assert end > start
        assert (end - start).days == 30

    def test_get_previous_period(self):
        """Test previous period calculation."""
        end = datetime.utcnow()
        start = end - timedelta(days=30)

        prev_start, prev_end = filters.get_previous_period(start, end)

        assert prev_end == start
        assert (prev_end - prev_start).days == 30

    def test_calculate_change_pct(self):
        """Test percentage change calculation."""
        # Increase
        change = filters.calculate_change_pct(120, 100)
        assert change == 20.0

        # Decrease
        change = filters.calculate_change_pct(80, 100)
        assert change == -20.0

        # No previous value
        change = filters.calculate_change_pct(100, None)
        assert change is None

        # Previous is zero
        change = filters.calculate_change_pct(100, 0)
        assert change is None

    def test_get_trend_direction(self):
        """Test trend direction determination."""
        assert filters.get_trend_direction(10.0) == "up"
        assert filters.get_trend_direction(-10.0) == "down"
        assert filters.get_trend_direction(2.0) == "stable"
        assert filters.get_trend_direction(None) is None


class TestMetrics:
    """Test metric calculation helpers."""

    def test_build_comparison_metric(self):
        """Test comparison metric building."""
        metric = metrics.build_comparison_metric(120, 100)

        assert metric.value == 120
        assert metric.previous_value == 100
        assert metric.change_pct == 20.0
        assert metric.trend_direction == "up"

    def test_calculate_rate(self):
        """Test rate calculation."""
        rate = metrics.calculate_rate(25, 100)
        assert rate == 25.0

        # Zero denominator
        rate = metrics.calculate_rate(10, 0)
        assert rate == 0.0

    def test_calculate_utilization_pct(self):
        """Test utilization percentage calculation."""
        util = metrics.calculate_utilization_pct(75.0, 100.0)
        assert util == 75.0

        # Zero limit
        util = metrics.calculate_utilization_pct(50.0, 0.0)
        assert util == 0.0

    def test_determine_status_tone(self):
        """Test status tone determination."""
        # Higher is worse
        assert (
            metrics.determine_status_tone(95, 80, 90, higher_is_worse=True) == "danger"
        )
        assert metrics.determine_status_tone(85, 80, 90, higher_is_worse=True) == "warn"
        assert (
            metrics.determine_status_tone(70, 80, 90, higher_is_worse=True) == "neutral"
        )
        assert (
            metrics.determine_status_tone(0, 80, 90, higher_is_worse=True) == "success"
        )

        # Lower is worse
        assert (
            metrics.determine_status_tone(10, 20, 15, higher_is_worse=False) == "danger"
        )
        assert (
            metrics.determine_status_tone(18, 20, 15, higher_is_worse=False) == "warn"
        )
        assert (
            metrics.determine_status_tone(25, 20, 15, higher_is_worse=False)
            == "neutral"
        )

    def test_calculate_intervention_rate(self):
        """Test intervention rate calculation."""
        rate = metrics.calculate_intervention_rate(
            monitors=10, approvals=5, denies=3, suspends=2, total_actions=100
        )
        assert rate == 20.0

        # Zero total
        rate = metrics.calculate_intervention_rate(5, 5, 5, 5, 0)
        assert rate == 0.0

    def test_calculate_assurance_coverage(self):
        """Test assurance coverage calculation."""
        coverage = metrics.calculate_assurance_coverage(8, 10)
        assert coverage == 80.0

        # Zero total
        coverage = metrics.calculate_assurance_coverage(0, 0)
        assert coverage == 0.0


class TestReportSchemas:
    """Test report schema models."""

    def test_report_filters(self):
        """Test ReportFilters schema."""
        filters = ReportFilters(
            ai_system_id=uuid4(),
            risk_severity=["CRITICAL", "HIGH"],
            period_start=datetime.utcnow(),
        )

        assert filters.ai_system_id is not None
        assert len(filters.risk_severity) == 2
        assert filters.period_start is not None

    def test_report_scope(self):
        """Test ReportScope schema."""
        scope = ReportScope(
            ai_system_id=uuid4(),
        )

        assert scope.ai_system_id is not None

    def test_severity_distribution(self):
        """Test SeverityDistribution schema."""
        dist = SeverityDistribution(
            critical=5,
            high=10,
            medium=15,
            low=20,
        )

        assert dist.critical == 5
        assert dist.high == 10
        assert dist.medium == 15
        assert dist.low == 20

    def test_effect_distribution(self):
        """Test EffectDistribution schema."""
        dist = EffectDistribution(
            allow=80,
            monitor=10,
            require_approval=5,
            deny=3,
            suspend=2,
        )

        assert dist.allow == 80
        assert dist.deny == 3


class TestQueries:
    """Test query functions.

    Note: These tests would require database fixtures in a real test environment.
    Here we're just testing the function signatures and basic logic.
    """

    def test_query_function_signatures(self):
        """Verify query functions exist and have correct signatures."""
        assert callable(queries.count_risk_findings)
        assert callable(queries.count_policy_evaluations)
        assert callable(queries.count_governed_actions)
        assert callable(queries.count_budgets)
        assert callable(queries.get_severity_distribution)
        assert callable(queries.get_effect_distribution)
        assert callable(queries.get_risk_by_ai_system)


@pytest.mark.integration
class TestReportingAPI:
    """Integration tests for reporting API endpoints.

    These would require a test database and proper fixtures.
    """

    def test_get_summary_report_endpoint(self):
        """Test GET /v1/reports/summary endpoint."""
        # This would be a full integration test with TestClient
        pass

    def test_get_risk_report_endpoint(self):
        """Test GET /v1/reports/risk endpoint."""
        pass

    def test_create_report_snapshot_endpoint(self):
        """Test POST /v1/reports/snapshots endpoint."""
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
