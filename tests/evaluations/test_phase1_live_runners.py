"""Phase 1 assurance — live runners + production rejects fixture-only."""

from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, patch

from rai_gateway.evaluations.domain import (
    LIVE_ASSURANCE_RUNNER_TYPES,
    GateConditionType,
    GateDecision,
    RunnerType,
)
from rai_gateway.evaluations.gates import (
    default_conditions_from_requirements,
    evaluate_gate_conditions,
)
from rai_gateway.evaluations.runners import (
    AgentEvaluationRunner,
    DeterministicRunner,
    HumanReviewRunner,
    ModelJudgeRunner,
    ToolSandboxRunner,
    get_runner,
)
from rai_gateway.evaluations.service import EvaluationService
from rai_gateway.models.evaluations import EvaluationRequirement, EvaluationRun
from rai_gateway.registry.domain import AgentStatus, AgentVersionStatus, AISystemStatus
from rai_gateway.registry.service import RegistryService


def _stack(registry: RegistryService) -> dict:
    suffix = uuid.uuid4().hex[:8]
    system = registry.create_ai_system(
        system_key=f"p1-sys-{suffix}",
        name="P1 Eval System",
        created_by="tester",
    )
    for status in (AISystemStatus.UNDER_REVIEW, AISystemStatus.APPROVED):
        registry.transition_ai_system(system.id, status.value, updated_by="tester")
    agent = registry.create_agent(
        system.id,
        agent_key=f"p1-agent-{suffix}",
        name="P1 Agent",
        created_by="tester",
    )
    for status in (AgentStatus.UNDER_REVIEW, AgentStatus.APPROVED):
        registry.transition_agent(agent.id, status.value, updated_by="tester")
    version = registry.create_agent_version(
        agent.id,
        created_by="tester",
        configuration_snapshot={"model": "test-model", "model_provider": "test"},
    )
    for status in (AgentVersionStatus.UNDER_REVIEW, AgentVersionStatus.APPROVED):
        registry.transition_agent_version(version.id, status.value, updated_by="tester")
    return {"system": system, "agent": agent, "version": version}


def _mock_http_json(payload: dict):
    raw = json.dumps(payload).encode("utf-8")
    resp = MagicMock()
    resp.read.return_value = raw
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    return resp


def test_get_runner_registers_live_types():
    assert isinstance(get_runner(RunnerType.AGENT.value), AgentEvaluationRunner)
    assert isinstance(get_runner(RunnerType.TOOL_SANDBOX.value), ToolSandboxRunner)
    assert isinstance(get_runner(RunnerType.MODEL_JUDGE.value), ModelJudgeRunner)
    assert isinstance(get_runner(RunnerType.HUMAN_REVIEW.value), HumanReviewRunner)
    assert isinstance(get_runner(RunnerType.DETERMINISTIC.value), DeterministicRunner)


def test_agent_runner_requires_endpoint():
    outcome = AgentEvaluationRunner().execute(cases=[], runner_config={})
    assert outcome.status.value == "ERROR"
    assert "endpoint_url" in (outcome.error or "")


def test_agent_runner_rejects_simulate_only_cases():
    outcome = AgentEvaluationRunner().execute(
        cases=[
            {
                "case_key": "sim",
                "input_fixture": {"simulate": "ok"},
                "expected_behavior": {"value": "ok"},
                "scoring_method": "exact_match",
            }
        ],
        runner_config={"endpoint_url": "http://127.0.0.1:9/agent"},
    )
    assert outcome.case_outcomes[0].status.value == "ERROR"
    assert "simulate" in (outcome.case_outcomes[0].explanation or "").lower()


def test_agent_runner_invokes_endpoint_and_scores():
    with patch(
        "rai_gateway.evaluations.runners.urllib.request.urlopen",
        return_value=_mock_http_json(
            {
                "output": "safe-reply",
                "tool_proposals": [],
                "policy_decisions": [{"effect": "ALLOW"}],
            }
        ),
    ):
        outcome = AgentEvaluationRunner().execute(
            cases=[
                {
                    "case_key": "live",
                    "input_fixture": {"prompt": "hello"},
                    "expected_behavior": {"value": "safe-reply"},
                    "scoring_method": "exact_match",
                }
            ],
            agent_config={"model": "m1"},
            runner_config={"endpoint_url": "http://127.0.0.1:8080/eval"},
        )
    assert outcome.status.value == "PASSED"
    assert outcome.evidence["assurance_class"] == "LIVE_AGENT"
    assert outcome.case_outcomes[0].evidence.get("tool_proposals") == []


def test_tool_sandbox_runner_executes_tool():
    with patch(
        "rai_gateway.evaluations.runners.urllib.request.urlopen",
        return_value=_mock_http_json({"result": {"status": "ok"}}),
    ):
        outcome = ToolSandboxRunner().execute(
            cases=[
                {
                    "case_key": "po",
                    "input_fixture": {
                        "tool": "create_order",
                        "parameters": {"amount": 10},
                    },
                    "expected_behavior": {"paths": {"status": "ok"}},
                    "scoring_method": "json_path_equals",
                }
            ],
            runner_config={"endpoint_url": "http://localhost:9000/sandbox"},
        )
    assert outcome.status.value == "PASSED"
    assert outcome.evidence["assurance_class"] == "TOOL_SANDBOX"


def test_model_judge_runner_uses_rubric_response():
    with patch(
        "rai_gateway.evaluations.runners.urllib.request.urlopen",
        return_value=_mock_http_json(
            {"pass": True, "score": 0.95, "explanation": "on rubric"}
        ),
    ):
        outcome = ModelJudgeRunner().execute(
            cases=[
                {
                    "case_key": "tone",
                    "input_fixture": {"output": "Thanks for shopping"},
                    "expected_behavior": {"rubric": {"polite": True}},
                }
            ],
            runner_config={
                "endpoint_url": "http://127.0.0.1:8081/judge",
                "provider": "openai",
                "model": "judge-v1",
                "rubric_digest": "abc",
            },
        )
    assert outcome.status.value == "PASSED"
    assert outcome.evidence["assurance_class"] == "MODEL_JUDGE"


def test_human_review_runner_requires_decision():
    outcome = HumanReviewRunner().execute(
        cases=[{"case_key": "h1", "input_fixture": {}, "failure_severity": "HIGH"}]
    )
    assert outcome.status.value == "FAILED"
    assert outcome.case_outcomes[0].status.value == "ERROR"


def test_human_review_runner_accepts_decision():
    outcome = HumanReviewRunner().execute(
        cases=[
            {
                "case_key": "h1",
                "input_fixture": {
                    "human_decision": {
                        "pass": True,
                        "score": 1.0,
                        "reviewer": "alice",
                    }
                },
            }
        ]
    )
    assert outcome.status.value == "PASSED"
    assert outcome.evidence["assurance_class"] == "HUMAN_REVIEW"


def test_production_default_conditions_reject_deterministic(
    db_session, registry, test_organization
) -> None:
    stack = _stack(registry)
    eval_svc = EvaluationService(db_session)
    suite = eval_svc.create_suite(
        ai_system_id=stack["system"].id,
        suite_key="sec-live",
        name="Security Live",
        category="SECURITY",
        created_by="tester",
        runner_type="DETERMINISTIC",
    )
    eval_svc.add_case(
        suite["id"],
        case_key="c1",
        name="c1",
        input_fixture={"simulate": {"violated": False}},
        expected_behavior={"flag": "violated"},
        scoring_method="assert_false",
        failure_severity="CRITICAL",
    )
    published = eval_svc.publish_suite(suite["id"])
    # No accepted_runner_types override → PRODUCTION SECURITY requires live runners
    req = eval_svc.create_requirement(
        ai_system_id=stack["system"].id,
        name="prod security",
        category="SECURITY",
        evaluation_suite_id=published["id"],
        created_by="tester",
        environment_scope="PRODUCTION",
        minimum_score=1.0,
    )
    conditions = default_conditions_from_requirements(
        [db_session.get(EvaluationRequirement, uuid.UUID(req["id"]))]
    )
    runner_conds = [
        c
        for c in conditions
        if c["type"] == GateConditionType.ACCEPTABLE_RUNNER_TYPE.value
    ]
    assert len(runner_conds) == 1
    assert set(runner_conds[0]["allowed_runner_types"]) == set(
        LIVE_ASSURANCE_RUNNER_TYPES
    )

    plan = eval_svc.create_plan(
        agent_version_id=stack["version"].id,
        created_by="tester",
        target_environment="PRODUCTION",
    )
    runs = eval_svc.start_runs_for_plan(
        uuid.UUID(plan["id"]), created_by="tester", idempotency_key="k1"
    )
    det_run = next(r for r in runs if r["suite_id"] == published["id"])
    assert det_run["runner_type"] == "DETERMINISTIC"
    assert det_run["status"] == "PASSED"  # fixture suite itself can pass

    result = evaluate_gate_conditions(
        db_session,
        ai_system_id=stack["system"].id,
        agent_version_id=stack["version"].id,
        environment="PRODUCTION",
        conditions=conditions,
        requirements=[db_session.get(EvaluationRequirement, uuid.UUID(req["id"]))],
        runs=[db_session.get(EvaluationRun, uuid.UUID(det_run["id"]))],
    )
    assert result.decision == GateDecision.FAIL
    assert any(
        c.condition_type == GateConditionType.ACCEPTABLE_RUNNER_TYPE.value
        and c.result.value == "FAIL"
        for c in result.conditions
    )


def test_production_gate_accepts_agent_runner(
    db_session, registry, test_organization
) -> None:
    stack = _stack(registry)
    eval_svc = EvaluationService(db_session)
    suite = eval_svc.create_suite(
        ai_system_id=stack["system"].id,
        suite_key="sec-agent",
        name="Security Agent",
        category="SECURITY",
        created_by="tester",
        runner_type="AGENT",
        runner_config={"endpoint_url": "http://127.0.0.1:18080/agent"},
    )
    eval_svc.add_case(
        suite["id"],
        case_key="live",
        name="live",
        input_fixture={"prompt": "ping"},
        expected_behavior={"value": "pong"},
        scoring_method="exact_match",
        failure_severity="CRITICAL",
    )
    published = eval_svc.publish_suite(suite["id"])
    req = eval_svc.create_requirement(
        ai_system_id=stack["system"].id,
        name="prod security agent",
        category="SECURITY",
        evaluation_suite_id=published["id"],
        created_by="tester",
        environment_scope="PRODUCTION",
    )
    conditions = default_conditions_from_requirements(
        [db_session.get(EvaluationRequirement, uuid.UUID(req["id"]))],
        include_risk=False,
    )
    plan = eval_svc.create_plan(
        agent_version_id=stack["version"].id,
        created_by="tester",
        target_environment="PRODUCTION",
    )
    with patch(
        "rai_gateway.evaluations.runners.urllib.request.urlopen",
        return_value=_mock_http_json({"output": "pong"}),
    ):
        runs = eval_svc.start_runs_for_plan(
            uuid.UUID(plan["id"]),
            created_by="tester",
            idempotency_key="agent-1",
        )
    agent_run = next(r for r in runs if r["suite_id"] == published["id"])
    assert agent_run["runner_type"] == "AGENT"
    assert agent_run["status"] == "PASSED"
    assert agent_run["evidence"]["assurance_class"] == "LIVE_AGENT"

    result = evaluate_gate_conditions(
        db_session,
        ai_system_id=stack["system"].id,
        agent_version_id=stack["version"].id,
        environment="PRODUCTION",
        conditions=conditions,
        requirements=[db_session.get(EvaluationRequirement, uuid.UUID(req["id"]))],
        runs=[db_session.get(EvaluationRun, uuid.UUID(agent_run["id"]))],
    )
    assert result.decision == GateDecision.PASS
    assert all(
        c.result.value == "PASS"
        for c in result.conditions
        if c.condition_type == GateConditionType.ACCEPTABLE_RUNNER_TYPE.value
    )
