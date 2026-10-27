"""Tests for WP6 content evaluator providers and risk engine."""

from __future__ import annotations

from uuid import uuid4

import pytest

from rai_gateway.policy.domain import PolicyEffect
from rai_gateway.policy.service import PolicyCollectionService
from rai_gateway.risk_intelligence.domain import InterventionEffect
from rai_gateway.risk_intelligence.providers import (
    ContentEvaluatorError,
    EvaluatorRequest,
    MockContentEvaluator,
    ProviderConfig,
    parse_structured_evaluator_output,
)
from rai_gateway.risk_intelligence.service import RiskIntelligenceService


@pytest.fixture
def risk_svc(db_session):
    return RiskIntelligenceService(db_session)


@pytest.fixture
def content_rule(db_session, runtime_stack):
    policy = PolicyCollectionService(db_session)
    return policy.create_content_rule(
        runtime_stack["system"].id,
        title="No bank account disclosure",
        content="Never disclose customer bank account or financial account numbers.",
        effect=PolicyEffect.DENY.value,
        enabled=True,
        applies_to="OUTPUT",
        category="financial_data_disclosure",
        severity="CRITICAL",
        actor="test",
    )


def test_parse_structured_output_valid():
    raw = {
        "evaluations": [
            {
                "rule_id": "RULE-1",
                "violated": True,
                "confidence": 0.96,
                "category": "financial_data_disclosure",
                "reason": "bank account",
                "evidence_spans": ["EG12"],
                "severity": "CRITICAL",
            }
        ]
    }
    out = parse_structured_evaluator_output(raw, expected_rule_ids={"RULE-1"})
    assert len(out.evaluations) == 1
    assert out.evaluations[0].violated is True
    assert out.evaluations[0].confidence == 0.96


def test_parse_structured_output_invalid_json():
    with pytest.raises(ContentEvaluatorError) as exc:
        parse_structured_evaluator_output("not-json")
    assert exc.value.failure_type == "EVALUATOR_INVALID_RESPONSE"


def test_parse_structured_output_unknown_rule():
    with pytest.raises(ContentEvaluatorError):
        parse_structured_evaluator_output(
            {
                "evaluations": [
                    {
                        "rule_id": "UNKNOWN",
                        "violated": False,
                        "confidence": 0.1,
                    }
                ]
            },
            expected_rule_ids={"RULE-1"},
        )


def test_mock_evaluator_detects_bank_account():
    provider = MockContentEvaluator()
    rules = [
        {
            "id": str(uuid4()),
            "title": "No bank disclosure",
            "content": "Do not disclose bank account information",
            "effect": "DENY",
            "category": "financial_data_disclosure",
        }
    ]
    result = provider.evaluate(
        EvaluatorRequest(
            content="Customer bank account is EG12 3456 7890",
            content_type="OUTPUT",
            applicable_rules=rules,
        ),
        ProviderConfig(provider="mock", model="mock"),
    )
    assert result.evaluations[0].violated is True
    assert result.evaluations[0].confidence >= 0.9


def test_content_deny_acceptance(db_session, risk_svc, runtime_stack, content_rule):
    system = runtime_stack["system"]
    identity = runtime_stack["identity"]
    risk_svc.upsert_evaluator_config(
        ai_system_id=system.id,
        provider="mock",
        model="mock-evaluator",
        enabled=True,
        minimum_confidence_to_intervene=0.9,
    )
    result = risk_svc.evaluate_content(
        ai_system_id=system.id,
        content="Customer bank account is EG12 3456 7890 1234",
        content_type="OUTPUT",
        runtime_identity_id=identity.id,
        apply_risk=True,
    )
    assert result["status"] in ("COMPLETED", "CACHED")
    assert result["intervention_hints"]
    assert result["intervention_hints"][0]["suggested_intervention"] == "DENY"
    assert result["risk"]["signals_created"] >= 1
    findings = risk_svc.list_findings(ai_system_id=system.id)
    assert findings
    interventions = risk_svc.list_interventions(ai_system_id=system.id)
    assert interventions
    assert interventions[0]["effect"] == InterventionEffect.DENY.value


def test_frequency_monitor_threshold(db_session, risk_svc, runtime_stack):
    system = runtime_stack["system"]
    identity = runtime_stack["identity"]
    agent = runtime_stack["agent"]
    version = runtime_stack["version"]
    risk_svc.create_monitor_rule(
        ai_system_id=system.id,
        name="PO frequency",
        scope="RUNTIME_IDENTITY",
        tool_name="submit_purchase_order",
        window_seconds=600,
        aggregation="COUNT",
        threshold=5,
        effect="MARK_AND_MONITOR",
        monitor_duration_seconds=1800,
        enabled=True,
    )
    for _ in range(5):
        risk_svc.process_enforcement_safe(
            ai_system_id=system.id,
            agent_id=agent.id,
            agent_version_id=version.id,
            runtime_identity_id=identity.id,
            trajectory_id=None,
            decision="ALLOW",
            tool_name="submit_purchase_order",
            tool_id=None,
            parameters={},
            amount=None,
        )
    monitors = risk_svc.list_monitors(ai_system_id=system.id, status="ACTIVE")
    assert monitors
    states = risk_svc.list_risk_states(ai_system_id=system.id, monitoring_only=True)
    assert states


def test_policy_monitor_decision_creates_active_monitor(
    db_session, risk_svc, runtime_stack
):
    """Tool-rule MONITOR must populate /risk/monitoring (RiskMonitor rows)."""
    system = runtime_stack["system"]
    identity = runtime_stack["identity"]
    agent = runtime_stack["agent"]
    version = runtime_stack["version"]
    risk_svc.process_enforcement_safe(
        ai_system_id=system.id,
        agent_id=agent.id,
        agent_version_id=version.id,
        runtime_identity_id=identity.id,
        trajectory_id=None,
        decision="MONITOR",
        tool_name="jira_create_issue",
        tool_id=None,
        parameters={},
        amount=None,
    )
    monitors = risk_svc.list_monitors(ai_system_id=system.id, status="ACTIVE")
    assert monitors
    assert monitors[0]["scope_id"] == str(identity.id)
    assert "jira_create_issue" in (monitors[0]["reason"] or "")
    states = risk_svc.list_risk_states(ai_system_id=system.id, monitoring_only=True)
    assert states
    findings = risk_svc.list_findings(ai_system_id=system.id)
    assert any(f.get("finding_type") == "POLICY_MONITOR" for f in findings)


def test_amount_sum_requires_approval(db_session, risk_svc, runtime_stack):
    system = runtime_stack["system"]
    identity = runtime_stack["identity"]
    agent = runtime_stack["agent"]
    version = runtime_stack["version"]
    risk_svc.create_monitor_rule(
        ai_system_id=system.id,
        name="PO amount sum",
        scope="RUNTIME_IDENTITY",
        tool_name="submit_purchase_order",
        window_seconds=3600,
        aggregation="SUM",
        threshold=500000,
        amount_parameter_path="amount",
        effect="REQUIRE_APPROVAL",
        enabled=True,
    )
    risk_svc.process_enforcement_safe(
        ai_system_id=system.id,
        agent_id=agent.id,
        agent_version_id=version.id,
        runtime_identity_id=identity.id,
        trajectory_id=None,
        decision="ALLOW",
        tool_name="submit_purchase_order",
        amount=500000,
        parameters={"amount": 500000},
    )
    overlay = risk_svc.authorization_overlay(
        ai_system_id=system.id,
        runtime_identity_id=identity.id,
    )
    assert overlay["require_approval"] is True


def test_recommendation_draft_not_activated(db_session, risk_svc, runtime_stack):
    from rai_gateway.risk_intelligence.recommendations import RecommendationService

    system = runtime_stack["system"]
    rec_svc = RecommendationService(db_session)
    rec = rec_svc.detect_content_refinement(
        ai_system_id=system.id,
        category="financial_data_disclosure",
        violation_count=5,
        evidence_refs=[],
        min_count=5,
    )
    assert rec is not None
    db_session.commit()
    accepted = risk_svc.accept_recommendation(rec.id, actor="test")
    assert accepted["enabled"] is False
    assert accepted["draft_rule_id"]


def test_evaluator_not_configured_does_not_silent_pass(
    db_session, risk_svc, runtime_stack
):
    result = risk_svc.evaluate_content(
        ai_system_id=runtime_stack["system"].id,
        content="anything",
        content_type="OUTPUT",
        apply_risk=False,
    )
    assert result["status"] == "FAILED"
    assert result["failure_type"] == "EVALUATOR_NOT_CONFIGURED"


def test_confidence_thresholds_mark_vs_intervene(
    db_session, risk_svc, runtime_stack, content_rule
):
    system = runtime_stack["system"]
    risk_svc.upsert_evaluator_config(
        ai_system_id=system.id,
        provider="mock",
        model="mock-evaluator",
        enabled=True,
        minimum_confidence_to_mark=0.5,
        minimum_confidence_to_monitor=0.7,
        minimum_confidence_to_intervene=0.99,
    )
    result = risk_svc.evaluate_content(
        ai_system_id=system.id,
        content="Customer bank account is EG12",
        content_type="OUTPUT",
        apply_risk=True,
    )
    assert result["intervention_hints"]
    assert (
        result["intervention_hints"][0]["suggested_intervention"] == "MARK_AND_MONITOR"
    )
