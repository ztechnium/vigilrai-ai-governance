"""Live AGENT runner must bind to exact Agent Version endpoint + digest."""

from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, patch

from rai_gateway.evaluations.runners import AgentEvaluationRunner
from rai_gateway.evaluations.service import EvaluationService
from rai_gateway.registry.domain import AgentStatus, AgentVersionStatus, AISystemStatus
from rai_gateway.registry.service import RegistryService


def _stack(registry: RegistryService, *, endpoint: str | None = None) -> dict:
    suffix = uuid.uuid4().hex[:8]
    system = registry.create_ai_system(
        system_key=f"bind-sys-{suffix}",
        name="Bind Eval System",
        created_by="tester",
    )
    for status in (AISystemStatus.UNDER_REVIEW, AISystemStatus.APPROVED):
        registry.transition_ai_system(system.id, status.value, updated_by="tester")
    agent = registry.create_agent(
        system.id,
        agent_key=f"bind-agent-{suffix}",
        name="Bind Agent",
        created_by="tester",
    )
    for status in (AgentStatus.UNDER_REVIEW, AgentStatus.APPROVED):
        registry.transition_agent(agent.id, status.value, updated_by="tester")
    version = registry.create_agent_version(
        agent.id,
        created_by="tester",
        configuration_snapshot={"model": "bound-model", "model_provider": "test"},
        evaluation_endpoint_url=endpoint,
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


def test_bind_runner_config_prefers_version_endpoint(
    db_session, registry, test_organization
):
    stack = _stack(registry, endpoint="http://127.0.0.1:19090/version-agent")
    svc = EvaluationService(db_session)
    cfg = svc._bind_runner_config(
        "AGENT",
        {"endpoint_url": "http://127.0.0.1:19090/version-agent"},
        stack["version"],
    )
    assert cfg["endpoint_url"] == "http://127.0.0.1:19090/version-agent"
    assert cfg["agent_version_id"] == str(stack["version"].id)
    assert cfg["agent_config_digest"] == stack["version"].configuration_digest
    assert cfg["endpoint_binding_source"] == "agent_version"


def test_bind_runner_config_mismatch_errors(db_session, registry, test_organization):
    stack = _stack(registry, endpoint="http://127.0.0.1:19090/version-agent")
    svc = EvaluationService(db_session)
    cfg = svc._bind_runner_config(
        "AGENT",
        {"endpoint_url": "http://127.0.0.1:19091/other"},
        stack["version"],
    )
    assert "mismatch" in cfg["_binding_error"].lower()


def test_agent_runner_rejects_response_digest_mismatch():
    with patch(
        "rai_gateway.evaluations.runners.urllib.request.urlopen",
        return_value=_mock_http_json(
            {
                "output": "ok",
                "agent_config_digest": "digest-OTHER",
            }
        ),
    ):
        outcome = AgentEvaluationRunner().execute(
            cases=[
                {
                    "case_key": "live",
                    "input_fixture": {"prompt": "hello"},
                    "expected_behavior": {"value": "ok"},
                    "scoring_method": "exact_match",
                }
            ],
            agent_config={"model": "m1"},
            runner_config={
                "endpoint_url": "http://127.0.0.1:8080/eval",
                "agent_version_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                "agent_config_digest": "digest-expected",
            },
        )
    assert outcome.case_outcomes[0].status.value == "ERROR"
    assert "digest" in (outcome.case_outcomes[0].explanation or "").lower()


def test_run_now_binds_version_endpoint(db_session, registry, test_organization):
    endpoint = "http://127.0.0.1:19191/bound"
    stack = _stack(registry, endpoint=endpoint)
    eval_svc = EvaluationService(db_session)
    suite = eval_svc.create_suite(
        ai_system_id=stack["system"].id,
        suite_key="bound-agent",
        name="Bound Agent",
        category="SECURITY",
        created_by="tester",
        runner_type="AGENT",
        runner_config={},  # endpoint comes from Agent Version
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
    eval_svc.create_requirement(
        ai_system_id=stack["system"].id,
        name="bound security",
        category="SECURITY",
        evaluation_suite_id=published["id"],
        created_by="tester",
        environment_scope="PRODUCTION",
    )
    plan = eval_svc.create_plan(
        agent_version_id=stack["version"].id,
        created_by="tester",
        target_environment="PRODUCTION",
    )
    with patch(
        "rai_gateway.evaluations.runners.urllib.request.urlopen",
        return_value=_mock_http_json({"output": "pong"}),
    ) as mock_open:
        runs = eval_svc.start_runs_for_plan(
            uuid.UUID(plan["id"]),
            created_by="tester",
            idempotency_key="bind-1",
        )
    agent_run = next(r for r in runs if r["suite_id"] == published["id"])
    assert agent_run["status"] == "PASSED"
    assert agent_run["evidence"]["agent_version_id"] == str(stack["version"].id)
    assert (
        agent_run["evidence"]["config_digest"] == stack["version"].configuration_digest
    )
    assert agent_run["evidence"]["endpoint_binding_source"] == "agent_version"
    req = mock_open.call_args[0][0]
    body = json.loads(req.data.decode("utf-8"))
    assert body["agent_version_id"] == str(stack["version"].id)
    assert body["agent_config_digest"] == stack["version"].configuration_digest
