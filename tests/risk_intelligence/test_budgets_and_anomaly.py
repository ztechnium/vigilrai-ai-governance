"""WP6 remaining work — budgets, anomaly detectors, kill-switch evidence."""

from __future__ import annotations

from datetime import datetime, timezone

from rai_gateway.risk_intelligence.anomaly import (
    REPEATED_DENY_THRESHOLD,
    AnomalyDetector,
)
from rai_gateway.risk_intelligence.budgets import BudgetService
from rai_gateway.risk_intelligence.domain import (
    MONITOR_WINDOW_PRESETS,
    AnomalyType,
    BudgetEffect,
    BudgetMetric,
    BudgetStatus,
    resolve_window_seconds,
)
from rai_gateway.risk_intelligence.repository import RiskIntelligenceRepository
from rai_gateway.risk_intelligence.service import RiskIntelligenceService


def test_window_presets():
    assert resolve_window_seconds("5m") == 300
    assert resolve_window_seconds("15m") == 900
    assert resolve_window_seconds("1h") == 3600
    assert resolve_window_seconds("24h") == 86400
    assert resolve_window_seconds(120) == 120
    assert set(MONITOR_WINDOW_PRESETS) == {"5m", "15m", "1h", "24h"}


def test_budget_action_count_warning_and_exceed(db_session, runtime_stack):
    system = runtime_stack["system"]
    identity = runtime_stack["identity"]
    svc = BudgetService(db_session)
    budget = svc.create_budget(
        ai_system_id=system.id,
        name="create_order daily",
        scope_type="RUNTIME_IDENTITY",
        metric=BudgetMetric.ACTION_COUNT.value,
        tool_name="create_order",
        limit_value=3,
        window_seconds=86400,
        warning_threshold=0.66,
        effect_on_exceed=BudgetEffect.DENY.value,
        enabled=True,
    )
    db_session.commit()

    r1 = svc.check_and_consume(
        ai_system_id=system.id,
        runtime_identity_id=identity.id,
        tool_name="create_order",
    )
    assert r1["deny"] is False
    assert r1["checks"][0]["status"] == BudgetStatus.OK.value

    r2 = svc.check_and_consume(
        ai_system_id=system.id,
        runtime_identity_id=identity.id,
        tool_name="create_order",
    )
    assert r2["checks"][0]["status"] == BudgetStatus.WARNING.value

    r3 = svc.check_and_consume(
        ai_system_id=system.id,
        runtime_identity_id=identity.id,
        tool_name="create_order",
    )
    # projected 3 == limit is OK/warning depending on >; exceed when projected > limit
    # 3rd call: usage was 2, projected 3, limit 3 → still not > limit
    assert r3["deny"] is False

    r4 = svc.check_and_consume(
        ai_system_id=system.id,
        runtime_identity_id=identity.id,
        tool_name="create_order",
    )
    assert r4["deny"] is True
    assert r4["checks"][0]["status"] == BudgetStatus.EXCEEDED.value
    assert budget.id is not None


def test_budget_amount_sum_and_unavailable_tokens(db_session, runtime_stack):
    system = runtime_stack["system"]
    identity = runtime_stack["identity"]
    svc = BudgetService(db_session)
    svc.create_budget(
        ai_system_id=system.id,
        name="order amount hour",
        scope_type="RUNTIME_IDENTITY",
        metric=BudgetMetric.AMOUNT.value,
        tool_name="create_order",
        limit_value=1000,
        window_seconds=3600,
        warning_threshold=0.8,
        effect_on_exceed=BudgetEffect.REQUIRE_APPROVAL.value,
        amount_parameter_path="amount",
        enabled=True,
    )
    svc.create_budget(
        ai_system_id=system.id,
        name="token daily",
        scope_type="RUNTIME_IDENTITY",
        metric=BudgetMetric.TOKEN_USAGE.value,
        limit_value=10000,
        window_seconds=86400,
        warning_threshold=0.8,
        effect_on_exceed=BudgetEffect.MONITOR.value,
        enabled=True,
    )
    db_session.commit()

    result = svc.check_and_consume(
        ai_system_id=system.id,
        runtime_identity_id=identity.id,
        tool_name="create_order",
        amount=900,
        parameters={"amount": 900},
        # token_usage omitted → UNAVAILABLE, never invented
    )
    statuses = {c["metric"]: c["status"] for c in result["checks"]}
    assert statuses[BudgetMetric.AMOUNT.value] == BudgetStatus.WARNING.value
    assert statuses[BudgetMetric.TOKEN_USAGE.value] == BudgetStatus.UNAVAILABLE.value
    assert result["require_approval"] is False

    result2 = svc.check_and_consume(
        ai_system_id=system.id,
        runtime_identity_id=identity.id,
        tool_name="create_order",
        amount=200,
        parameters={"amount": 200},
    )
    assert result2["require_approval"] is True
    assert any(c["status"] == BudgetStatus.EXCEEDED.value for c in result2["checks"])


def test_budget_concurrency_boundary(db_session, runtime_stack):
    """Two checks at usage=limit-1 must not both allow past limit for DENY budgets."""
    system = runtime_stack["system"]
    identity = runtime_stack["identity"]
    svc = BudgetService(db_session)
    svc.create_budget(
        ai_system_id=system.id,
        name="race limit",
        scope_type="RUNTIME_IDENTITY",
        metric=BudgetMetric.ACTION_COUNT.value,
        limit_value=2,
        window_seconds=3600,
        warning_threshold=1.0,
        effect_on_exceed=BudgetEffect.DENY.value,
        enabled=True,
    )
    db_session.commit()

    first = svc.check_and_consume(
        ai_system_id=system.id, runtime_identity_id=identity.id
    )
    second = svc.check_and_consume(
        ai_system_id=system.id, runtime_identity_id=identity.id
    )
    third = svc.check_and_consume(
        ai_system_id=system.id, runtime_identity_id=identity.id
    )
    assert first["deny"] is False
    assert second["deny"] is False
    assert third["deny"] is True


def test_repeated_deny_anomaly(db_session, runtime_stack):
    system = runtime_stack["system"]
    identity = runtime_stack["identity"]
    repo = RiskIntelligenceRepository(db_session)
    now = datetime.now(timezone.utc)
    for _ in range(REPEATED_DENY_THRESHOLD):
        repo.create_signal(
            ai_system_id=system.id,
            runtime_identity_id=identity.id,
            signal_type="REPEATED_DENIAL",
            source_type="RAI_AUTHORITATIVE",
            confidence=1.0,
            severity="MEDIUM",
            sensitivity="NORMAL",
            payload={"decision": "DENY"},
            occurred_at=now,
        )
    db_session.flush()
    findings = AnomalyDetector(db_session).detect_after_enforcement(
        ai_system_id=system.id,
        runtime_identity_id=identity.id,
    )
    types = [f.finding_type for f in findings if f]
    assert AnomalyType.REPEATED_DENIED_ACTION.value in types


def test_high_value_burst_anomaly(db_session, runtime_stack):
    system = runtime_stack["system"]
    identity = runtime_stack["identity"]
    repo = RiskIntelligenceRepository(db_session)
    now = datetime.now(timezone.utc)
    repo.create_signal(
        ai_system_id=system.id,
        runtime_identity_id=identity.id,
        signal_type="HIGH_VALUE_ACTION",
        source_type="RAI_AUTHORITATIVE",
        confidence=1.0,
        severity="HIGH",
        sensitivity="HIGH",
        payload={"amount": 500_000, "tool_name": "create_order"},
        occurred_at=now,
    )
    db_session.flush()
    findings = AnomalyDetector(db_session).detect_after_enforcement(
        ai_system_id=system.id,
        runtime_identity_id=identity.id,
        tool_name="create_order",
    )
    assert any(
        f and f.finding_type == AnomalyType.HIGH_VALUE_BURST.value for f in findings
    )


def test_risk_score_spike_explains_drivers(db_session, runtime_stack):
    system = runtime_stack["system"]
    identity = runtime_stack["identity"]
    findings = AnomalyDetector(db_session).detect_after_enforcement(
        ai_system_id=system.id,
        runtime_identity_id=identity.id,
        previous_risk_level="LOW",
        current_risk_level="HIGH",
        previous_score=10,
        current_score=60,
        score_drivers=["+ HIGH CONTENT_POLICY_VIOLATION", "+ HIGH REPEATED_DENIAL"],
    )
    spike = next(
        (
            f
            for f in findings
            if f and f.finding_type == AnomalyType.RISK_SCORE_SPIKE.value
        ),
        None,
    )
    assert spike is not None
    assert "LOW" in (spike.description or "")
    assert "HIGH" in (spike.description or "")
    assert spike.explanation["drivers"]


def test_monitor_max_aggregation(db_session, runtime_stack):
    system = runtime_stack["system"]
    identity = runtime_stack["identity"]
    risk = RiskIntelligenceService(db_session)
    rule = risk.create_monitor_rule(
        ai_system_id=system.id,
        name="max amount",
        scope="RUNTIME_IDENTITY",
        aggregation="MAX",
        threshold=1000,
        window="1h",
        tool_name="create_order",
        effect="REQUIRE_APPROVAL",
        enabled=True,
    )
    assert rule["window_seconds"] == 3600
    assert rule["aggregation"] == "MAX"

    repo = RiskIntelligenceRepository(db_session)
    now = datetime.now(timezone.utc)
    repo.create_signal(
        ai_system_id=system.id,
        runtime_identity_id=identity.id,
        signal_type="HIGH_VALUE_ACTION",
        source_type="RAI_AUTHORITATIVE",
        confidence=1.0,
        severity="HIGH",
        sensitivity="HIGH",
        payload={"amount": 1500, "tool_name": "create_order"},
        occurred_at=now,
    )
    db_session.flush()
    from rai_gateway.risk_intelligence.risk_engine import RiskEngine

    triggered = RiskEngine(db_session).evaluate_monitor_rules(
        ai_system_id=system.id,
        runtime_identity_id=identity.id,
        tool_name="create_order",
        amount=1500,
    )
    assert len(triggered) >= 1


def test_overview_includes_budget_and_anomaly_kpis(db_session, runtime_stack):
    overview = RiskIntelligenceService(db_session).overview(runtime_stack["system"].id)
    assert "budgets_near_limit" in overview
    assert "budgets_exceeded" in overview
    assert "recent_anomalies" in overview
    assert "suspended_runtime_identities" in overview
    assert "window_presets" in overview


def test_budget_service_serialize(db_session, runtime_stack):
    svc = BudgetService(db_session)
    row = svc.create_budget(
        ai_system_id=runtime_stack["system"].id,
        name="serialize",
        scope_type="AI_SYSTEM",
        metric=BudgetMetric.TOOL_COUNT.value,
        limit_value=10,
        window_seconds=900,
        warning_threshold=0.8,
        effect_on_exceed=BudgetEffect.MONITOR.value,
        enabled=True,
    )
    db_session.commit()
    data = svc.serialize_budget(row)
    assert data["id"] == str(row.id)
    assert data["status"] == BudgetStatus.OK.value
    assert data["remaining"] == 10
