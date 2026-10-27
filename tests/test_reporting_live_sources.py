"""Reports must use the same findings and trajectory cost the product already shows."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from rai_gateway.finops.domain import CostState, MeteringSource
from rai_gateway.models.finops import UsageSettlement
from rai_gateway.models.metering import RuntimeMeteringSpan
from rai_gateway.models.registry import AISystem
from rai_gateway.models.risk_intelligence import RuntimeRiskFinding
from rai_gateway.reporting.reports import build_budget_report, build_risk_report
from rai_gateway.reporting.schemas import ReportFilters


def _system(db_session) -> AISystem:
    suffix = uuid4().hex[:8]
    system = AISystem(
        system_key=f"report-sys-{suffix}",
        name=f"Report System {suffix}",
        created_by="tester",
    )
    db_session.add(system)
    db_session.flush()
    return system


def test_reports_include_runtime_findings_and_trajectory_cost(db_session):
    system = _system(db_session)
    now = datetime.utcnow()
    db_session.add(
        RuntimeRiskFinding(
            ai_system_id=system.id,
            finding_type="CONTENT_POLICY_VIOLATION",
            title="Prompt injection",
            severity="high",
            status="open",
            created_at=now,
        )
    )
    estimated = RuntimeMeteringSpan(
        ai_system_id=system.id,
        span_type="MODEL_CALL",
        cost_state=CostState.ESTIMATED.value,
        estimated_cost=1.25,
        total_tokens=100,
        currency="USD",
        metering_source=MeteringSource.SDK_REPORTED.value,
        started_at=now,
    )
    metered = RuntimeMeteringSpan(
        ai_system_id=system.id,
        span_type="MODEL_CALL",
        cost_state=CostState.METERED.value,
        metered_cost=2.0,
        actual_cost=2.0,
        total_tokens=50,
        currency="USD",
        metering_source=MeteringSource.PROVIDER_RESPONSE.value,
        started_at=now,
    )
    db_session.add_all([estimated, metered])
    db_session.flush()
    db_session.add(
        UsageSettlement(
            ai_system_id=system.id,
            metering_span_id=metered.id,
            metering_source=MeteringSource.PROVIDER_RESPONSE.value,
            cost_state=CostState.METERED.value,
            metered_cost=2.0,
            actual_cost=2.0,
            total_tokens=50,
            currency="USD",
        )
    )
    db_session.add(
        UsageSettlement(
            ai_system_id=system.id,
            metering_source=MeteringSource.EXPLICIT_COST.value,
            cost_state=CostState.METERED.value,
            metered_cost=0.5,
            actual_cost=0.5,
            total_tokens=10,
            currency="USD",
        )
    )
    db_session.commit()

    risk = build_risk_report(db_session, ReportFilters())
    assert risk.open_findings >= 1
    assert risk.severity_distribution.high >= 1
    assert (risk.status_distribution.get("OPEN") or 0) >= 1
    system_row = next(
        item for item in risk.risk_by_ai_system if item.name == system.name
    )
    assert system_row.value == 1
    assert risk.finding_trends
    assert sum(point.value for point in risk.finding_trends) >= 1

    budget = build_budget_report(db_session, ReportFilters())
    assert budget.total_cost >= 3.75
    assert budget.total_tokens >= 160
    assert budget.cost_trends
    assert sum(point.value for point in budget.cost_trends) >= 3.75
    assert sum(point.value for point in budget.token_trends) >= 160
