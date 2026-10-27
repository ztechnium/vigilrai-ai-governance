"""Hierarchical budget scope + reservation reconciliation tests."""

from __future__ import annotations

from rai_gateway.risk_intelligence.budget_scope import (
    BudgetEvaluationContext,
    resolve_applicable_budgets,
)
from rai_gateway.risk_intelligence.budgets import BudgetService
from rai_gateway.risk_intelligence.domain import (
    BudgetEffect,
    BudgetMetric,
    BudgetReservationStatus,
    RiskScopeType,
)


def test_org_and_agent_budgets_both_apply(db_session, runtime_stack):
    system = runtime_stack["system"]
    identity = runtime_stack["identity"]
    agent = runtime_stack["agent"]
    svc = BudgetService(db_session)

    org_budget = svc.create_budget(
        name="Org monthly cost",
        scope_type=RiskScopeType.ORGANIZATION.value,
        scope_id="ORGANIZATION",
        metric=BudgetMetric.COST.value,
        limit_value=100.0,
        window_seconds=86400,
        effect_on_exceed=BudgetEffect.DENY.value,
        enforcement_mode="BEST_EFFORT",
        enabled=True,
    )
    agent_budget = svc.create_budget(
        ai_system_id=system.id,
        name="Agent cost",
        scope_type=RiskScopeType.AGENT.value,
        scope_id=str(agent.id),
        metric=BudgetMetric.COST.value,
        limit_value=10.0,
        window_seconds=86400,
        effect_on_exceed=BudgetEffect.DENY.value,
        enabled=True,
    )
    db_session.commit()

    ctx = BudgetEvaluationContext(
        ai_system_id=system.id,
        agent_id=agent.id,
        runtime_identity_id=identity.id,
    )
    applicable = resolve_applicable_budgets(db_session, ctx)
    ids = {b.id for b in applicable}
    assert org_budget.id in ids
    assert agent_budget.id in ids

    result = svc.check_and_consume(
        ai_system_id=system.id,
        agent_id=agent.id,
        runtime_identity_id=identity.id,
        cost=5.0,
        idempotency_key="corr-hier-1",
    )
    assert result["deny"] is False
    assert result["applicable_budget_count"] >= 2
    assert len(result["reservations"]) >= 2


def test_child_does_not_replace_parent_deny(db_session, runtime_stack):
    system = runtime_stack["system"]
    identity = runtime_stack["identity"]
    agent = runtime_stack["agent"]
    svc = BudgetService(db_session)

    svc.create_budget(
        name="Org tiny",
        scope_type=RiskScopeType.ORGANIZATION.value,
        scope_id="ORGANIZATION",
        metric=BudgetMetric.COST.value,
        limit_value=1.0,
        window_seconds=86400,
        effect_on_exceed=BudgetEffect.DENY.value,
        enabled=True,
    )
    svc.create_budget(
        ai_system_id=system.id,
        name="Agent generous",
        scope_type=RiskScopeType.AGENT.value,
        scope_id=str(agent.id),
        metric=BudgetMetric.COST.value,
        limit_value=1000.0,
        window_seconds=86400,
        effect_on_exceed=BudgetEffect.MONITOR.value,
        enabled=True,
    )
    db_session.commit()

    result = svc.check_and_consume(
        ai_system_id=system.id,
        agent_id=agent.id,
        runtime_identity_id=identity.id,
        cost=5.0,
        idempotency_key="corr-hier-deny",
    )
    assert result["deny"] is True
    assert result["dominant_effect"] == BudgetEffect.DENY.value


def test_cost_reservation_reconcile(db_session, runtime_stack):
    system = runtime_stack["system"]
    identity = runtime_stack["identity"]
    svc = BudgetService(db_session)
    svc.create_budget(
        ai_system_id=system.id,
        name="Cost cap",
        scope_type=RiskScopeType.AI_SYSTEM.value,
        scope_id=str(system.id),
        metric=BudgetMetric.COST.value,
        limit_value=50.0,
        window_seconds=86400,
        effect_on_exceed=BudgetEffect.DENY.value,
        enabled=True,
    )
    db_session.commit()

    key = "corr-reconcile-1"
    pre = svc.check_and_consume(
        ai_system_id=system.id,
        runtime_identity_id=identity.id,
        cost=10.0,
        idempotency_key=key,
    )
    assert pre["deny"] is False
    assert len(pre["reservations"]) == 1

    settled = svc.reconcile_reservations(idempotency_key=key, settled_cost=7.5)
    assert settled[0]["status"] == BudgetReservationStatus.SETTLED.value
    assert abs(settled[0]["settled_value"] - 7.5) < 1e-9
    assert abs(settled[0]["delta_value"] - (-2.5)) < 1e-9
