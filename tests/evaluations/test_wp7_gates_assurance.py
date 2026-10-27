"""WP7 evaluation, deployment gates, assurance, and eligibility integration."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from rai_gateway.evaluations.domain import (
    AssuranceStatus,
    GateDecision,
    WaiverStatus,
)
from rai_gateway.evaluations.errors import SuiteImmutableError, WaiverDeniedError
from rai_gateway.evaluations.runners import DeterministicRunner
from rai_gateway.evaluations.service import EvaluationService
from rai_gateway.identity.domain import DelegatorType
from rai_gateway.identity.errors import AuthorityDeniedError
from rai_gateway.identity.resolver import RuntimeAuthorityResolver
from rai_gateway.identity.service import (
    CredentialService,
    DelegationService,
    RuntimeIdentityService,
)
from rai_gateway.registry.domain import AgentStatus, AgentVersionStatus, AISystemStatus
from rai_gateway.registry.eligibility import EligibilityService
from rai_gateway.registry.service import RegistryService
from rai_gateway.runtime_enforcement.adapters.base import RuntimeAdapterRegistry
from rai_gateway.runtime_enforcement.service import RuntimeEnforcementService
from runtime_enforcement.fakes import FakeAdapter


@pytest.fixture()
def registry(db_session) -> RegistryService:
    return RegistryService(db_session)


@pytest.fixture()
def eval_svc(db_session) -> EvaluationService:
    return EvaluationService(db_session)


def _approve_system_agent(registry: RegistryService, suffix: str) -> dict:
    system = registry.create_ai_system(
        system_key=f"wp7-sys-{suffix}",
        name="WhatsApp Sales AI",
        created_by="tester",
    )
    for status in (AISystemStatus.UNDER_REVIEW, AISystemStatus.APPROVED):
        registry.transition_ai_system(system.id, status.value, updated_by="tester")
    agent = registry.create_agent(
        system.id,
        agent_key=f"sales-bot-{suffix}",
        name="WhatsApp Sales Agent",
        created_by="tester",
    )
    for status in (AgentStatus.UNDER_REVIEW, AgentStatus.APPROVED):
        registry.transition_agent(agent.id, status.value, updated_by="tester")
    return {"system": system, "agent": agent}


def _setup_suites_and_requirements(
    eval_svc: EvaluationService,
    *,
    ai_system_id,
    business_fail: bool = True,
    quality_score_case: bool = False,
) -> dict:
    """Create published Security/Privacy/Tool/Business suites + PRODUCTION requirements."""
    suites = {}

    def _suite(key: str, category: str, cases: list[dict]) -> None:
        suite = eval_svc.create_suite(
            ai_system_id=ai_system_id,
            suite_key=key,
            name=f"{key} Suite",
            category=category,
            created_by="tester",
        )
        for case in cases:
            eval_svc.add_case(suite["id"], **case)
        suites[key] = eval_svc.publish_suite(suite["id"])

    _suite(
        "security",
        "SECURITY",
        [
            {
                "case_key": "no_cred_leak",
                "name": "No credential leak",
                "input_fixture": {"simulate": {"violated": False}},
                "expected_behavior": {"flag": "violated"},
                "scoring_method": "assert_false",
                "failure_severity": "CRITICAL",
            },
            {
                "case_key": "auth_required",
                "name": "Auth required",
                "input_fixture": {"simulate": "token-required"},
                "expected_behavior": {"value": "token-required"},
                "scoring_method": "exact_match",
                "failure_severity": "HIGH",
            },
        ],
    )
    _suite(
        "privacy",
        "PRIVACY",
        [
            {
                "case_key": "no_pii",
                "name": "No PII disclosure",
                "input_fixture": {"simulate": {"violated": False}},
                "expected_behavior": {"flag": "violated"},
                "scoring_method": "assert_false",
                "failure_severity": "CRITICAL",
            }
        ],
    )
    _suite(
        "tool_safety",
        "TOOL_USE",
        [
            {
                "case_key": "tool_sandbox",
                "name": "Tool uses sandbox",
                "input_fixture": {"simulate": "SANDBOX"},
                "expected_behavior": {"value": "SANDBOX"},
                "scoring_method": "exact_match",
                "failure_severity": "HIGH",
            }
        ],
    )
    if quality_score_case:
        _suite(
            "quality",
            "QUALITY",
            [
                {
                    "case_key": "quality_score",
                    "name": "Quality threshold",
                    "input_fixture": {"simulate": 0.88},
                    "expected_behavior": {},
                    "scoring_method": "threshold",
                    "threshold": 0.90,
                    "failure_severity": "MEDIUM",
                }
            ],
        )
    else:
        discount = 30 if business_fail else 15
        _suite(
            "business_rules",
            "BUSINESS_RULE",
            [
                {
                    "case_key": "max_discount",
                    "name": "Maximum authorized discount",
                    "input_fixture": {
                        "simulate": discount,
                    },
                    "expected_behavior": {"max": 15},
                    "scoring_method": "max_value",
                    "failure_severity": "HIGH",
                }
            ],
        )

    reqs = {}
    mapping = [
        ("security", "SECURITY", 0.95),
        ("privacy", "PRIVACY", 1.0),
        ("tool_safety", "TOOL_USE", 0.95),
    ]
    if quality_score_case:
        mapping.append(("quality", "QUALITY", 0.90))
    else:
        mapping.append(("business_rules", "BUSINESS_RULE", 1.0))

    for key, category, minimum in mapping:
        reqs[key] = eval_svc.create_requirement(
            ai_system_id=ai_system_id,
            name=f"{key} requirement",
            category=category,
            evaluation_suite_id=suites[key]["id"],
            created_by="tester",
            minimum_score=minimum,
            maximum_failed_critical_cases=0,
            validity_days=30,
            environment_scope="PRODUCTION",
            # Hermetic WP7 regression: opt into fixture runner assurance.
            # Production default (no override) rejects DETERMINISTIC for SECURITY/etc.
            accepted_runner_types=["DETERMINISTIC"],
        )

    gate = eval_svc.create_gate(
        ai_system_id=ai_system_id,
        name="Production Gate",
        created_by="tester",
        environment="PRODUCTION",
        auto_from_requirements=True,
    )
    return {"suites": suites, "requirements": reqs, "gate": gate}


def test_deterministic_runner_max_value():
    runner = DeterministicRunner()
    outcome = runner.execute(
        cases=[
            {
                "case_key": "discount",
                "enabled": True,
                "input_fixture": {"simulate": 30},
                "expected_behavior": {"max": 15},
                "scoring_method": "max_value",
                "threshold": 1.0,
                "failure_severity": "HIGH",
            }
        ]
    )
    assert outcome.status.value == "FAILED"
    assert outcome.case_outcomes[0].status.value == "FAIL"
    assert "exceeds" in (outcome.case_outcomes[0].explanation or "")


def test_suite_immutability_after_publish(
    db_session, registry, eval_svc, test_organization
):
    stack = _approve_system_agent(registry, uuid.uuid4().hex[:8])
    suite = eval_svc.create_suite(
        ai_system_id=stack["system"].id,
        suite_key="sec",
        name="Security",
        category="SECURITY",
        created_by="tester",
    )
    eval_svc.add_case(
        suite["id"],
        case_key="c1",
        name="Case 1",
        input_fixture={"simulate": True},
        expected_behavior={"value": True},
    )
    eval_svc.publish_suite(suite["id"])
    with pytest.raises(SuiteImmutableError):
        eval_svc.add_case(
            suite["id"],
            case_key="c2",
            name="Case 2",
            input_fixture={},
            expected_behavior={},
        )


def test_saas_sales_bot_failed_gate_blocks_eligibility_and_runtime(
    db_session, registry, eval_svc, test_organization
):
    """Reference acceptance: business rule FAIL → gate FAIL → WP2/WP4 DENY."""
    suffix = uuid.uuid4().hex[:8]
    stack = _approve_system_agent(registry, suffix)
    setup = _setup_suites_and_requirements(
        eval_svc, ai_system_id=stack["system"].id, business_fail=True
    )

    mcp = registry.create_mcp_server(
        server_key=f"sales-mcp-{suffix}",
        name="Sales MCP",
    )
    tool = registry.create_tool_resource(
        tool_key=f"create_order_{suffix}",
        name="Create Order",
        mcp_server_id=mcp.id,
        consequential_action=False,
    )

    version = registry.create_agent_version(
        stack["agent"].id,
        created_by="tester",
        change_summary="v2 new model + create_order + discount",
        configuration_snapshot={
            "model": "gpt-new",
            "max_discount_percent": 30,
            "tools": ["create_order"],
        },
        risk_tier="HIGH",
    )
    registry.add_version_dependency(
        version.id, resource_type="mcp_server", resource_id=mcp.id
    )
    registry.add_version_dependency(
        version.id, resource_type="tool", resource_id=tool.id
    )
    for status in (AgentVersionStatus.UNDER_REVIEW, AgentVersionStatus.APPROVED):
        registry.transition_agent_version(version.id, status.value, updated_by="tester")

    registry.create_risk_assessment(
        ai_system_id=stack["system"].id,
        agent_version_id=version.id,
        assessed_by="tester",
        risk_tier="HIGH",
        overall_score=70,
    )

    plan = eval_svc.create_plan(
        agent_version_id=version.id,
        target_environment="PRODUCTION",
        created_by="tester",
    )
    runs = eval_svc.start_runs_for_plan(plan["id"], created_by="tester")
    by_req = {r["requirement_id"]: r for r in runs}
    assert by_req[setup["requirements"]["security"]["id"]]["status"] == "PASSED"
    assert by_req[setup["requirements"]["privacy"]["id"]]["status"] == "PASSED"
    assert by_req[setup["requirements"]["tool_safety"]["id"]]["status"] == "PASSED"
    assert by_req[setup["requirements"]["business_rules"]["id"]]["status"] == "FAILED"

    gate = eval_svc.evaluate_deployment_gate(
        agent_version_id=version.id,
        environment="PRODUCTION",
        evaluated_by="tester",
    )
    assert gate["decision"] == GateDecision.FAIL.value
    assert gate["assurance"]["status"] == AssuranceStatus.FAILED.value

    eligibility = EligibilityService(db_session).evaluate(
        system_id=stack["system"].id,
        agent_id=stack["agent"].id,
        version_id=version.id,
    )
    assert eligibility.eligible is False
    assert "assurance" in eligibility.reason.lower() or "WP7" in eligibility.reason

    identity = RuntimeIdentityService(db_session).create_runtime_identity(
        agent_id=stack["agent"].id,
        agent_version_id=version.id,
        name="Sales Runtime",
        created_by="tester",
    )
    issued = CredentialService(db_session).issue_credential(
        identity.id, created_by="tester"
    )
    delegation = DelegationService(db_session).create_delegation(
        delegator_type=DelegatorType.HUMAN.value,
        delegator_id="sales-owner",
        delegate_runtime_identity_id=identity.id,
        scope={
            "mcp_server_ids": [str(mcp.id)],
            "tool_ids": [str(tool.id)],
        },
        created_by="tester",
    )

    with pytest.raises(AuthorityDeniedError):
        RuntimeAuthorityResolver(db_session).resolve_from_credential(
            issued.plaintext_secret
        )

    fake = FakeAdapter()
    enforcement = RuntimeEnforcementService(
        db_session, adapter_registry=RuntimeAdapterRegistry([fake])
    )
    from rai_gateway.runtime_enforcement.domain import (
        RuntimeActionRequest,
        RuntimeActionTarget,
    )

    result = enforcement.enforce_and_execute(
        RuntimeActionRequest(
            integration_type="mcp",
            integration_id=mcp.id,
            tool_id=tool.id,
            target=RuntimeActionTarget(type="Order"),
            parameters={"discount": 30},
            delegation_id=delegation.id,
        ),
        credential_secret=issued.plaintext_secret,
    )
    assert result.allowed is False
    assert result.execution_attempted is False
    assert fake.invocation_count == 0
    assert "INELIGIBLE" in str(result.reason_code)


def test_saas_sales_bot_pass_path(db_session, registry, eval_svc, test_organization):
    """Corrected version passes gate → assurance VALID → eligibility TRUE."""
    suffix = uuid.uuid4().hex[:8]
    stack = _approve_system_agent(registry, suffix)
    _setup_suites_and_requirements(
        eval_svc, ai_system_id=stack["system"].id, business_fail=False
    )

    version = registry.create_agent_version(
        stack["agent"].id,
        created_by="tester",
        change_summary="v3 fixed discount",
        configuration_snapshot={"model": "gpt-new", "max_discount_percent": 15},
        risk_tier="MEDIUM",
    )
    for status in (AgentVersionStatus.UNDER_REVIEW, AgentVersionStatus.APPROVED):
        registry.transition_agent_version(version.id, status.value, updated_by="tester")
    registry.create_risk_assessment(
        ai_system_id=stack["system"].id,
        agent_version_id=version.id,
        assessed_by="tester",
        risk_tier="MEDIUM",
        overall_score=40,
    )

    plan = eval_svc.create_plan(
        agent_version_id=version.id,
        target_environment="PRODUCTION",
        created_by="tester",
    )
    eval_svc.start_runs_for_plan(plan["id"], created_by="tester")
    gate = eval_svc.evaluate_deployment_gate(
        agent_version_id=version.id,
        environment="PRODUCTION",
        evaluated_by="tester",
    )
    assert gate["decision"] == GateDecision.PASS.value
    assert gate["assurance"]["status"] == AssuranceStatus.VALID.value

    eligibility = EligibilityService(db_session).evaluate(
        system_id=stack["system"].id,
        agent_id=stack["agent"].id,
        version_id=version.id,
    )
    assert eligibility.eligible is True


def test_waiver_separation_of_duties_and_pass_with_conditions(
    db_session, registry, eval_svc, test_organization
):
    suffix = uuid.uuid4().hex[:8]
    stack = _approve_system_agent(registry, suffix)
    setup = _setup_suites_and_requirements(
        eval_svc,
        ai_system_id=stack["system"].id,
        quality_score_case=True,
    )
    version = registry.create_agent_version(
        stack["agent"].id,
        created_by="tester",
        configuration_snapshot={"model": "x"},
    )
    for status in (AgentVersionStatus.UNDER_REVIEW, AgentVersionStatus.APPROVED):
        registry.transition_agent_version(version.id, status.value, updated_by="tester")
    registry.create_risk_assessment(
        ai_system_id=stack["system"].id,
        agent_version_id=version.id,
        assessed_by="tester",
        risk_tier="LOW",
        overall_score=20,
    )
    plan = eval_svc.create_plan(
        agent_version_id=version.id,
        target_environment="PRODUCTION",
        created_by="tester",
    )
    eval_svc.start_runs_for_plan(plan["id"], created_by="tester")
    gate = eval_svc.evaluate_deployment_gate(
        agent_version_id=version.id,
        environment="PRODUCTION",
        evaluated_by="tester",
    )
    assert gate["decision"] == GateDecision.WAIVER_REQUIRED.value

    failed = next(
        c
        for c in gate["condition_results"]
        if c["result"] == "FAIL" and c.get("waivable")
    )
    waiver = eval_svc.request_waiver(
        agent_version_id=version.id,
        justification="Temporary quality dip with enhanced monitoring",
        failed_condition=failed,
        requester="owner-1",
        compensating_controls={"wp6": "enhanced_monitoring"},
        validity_days=14,
        gate_evaluation_id=gate["id"],
    )
    with pytest.raises(WaiverDeniedError):
        eval_svc.approve_waiver(waiver["id"], approver="owner-1")

    approved = eval_svc.approve_waiver(
        waiver["id"], approver="rai-officer-2", decision_reason="Accepted with controls"
    )
    assert approved["status"] == WaiverStatus.APPROVED.value

    # Re-evaluate after approval happens inside approve_waiver
    assurance = eval_svc.get_assurance(version.id)
    assert assurance["current"]["status"] == AssuranceStatus.CONDITIONAL.value
    assert assurance["deployment_eligible"] is True
    assert setup["gate"]["id"]


def test_assurance_expiry_requires_reassessment(
    db_session, registry, eval_svc, test_organization
):
    suffix = uuid.uuid4().hex[:8]
    stack = _approve_system_agent(registry, suffix)
    _setup_suites_and_requirements(
        eval_svc, ai_system_id=stack["system"].id, business_fail=False
    )
    version = registry.create_agent_version(
        stack["agent"].id,
        created_by="tester",
        configuration_snapshot={"model": "x", "max_discount_percent": 15},
    )
    for status in (AgentVersionStatus.UNDER_REVIEW, AgentVersionStatus.APPROVED):
        registry.transition_agent_version(version.id, status.value, updated_by="tester")
    registry.create_risk_assessment(
        ai_system_id=stack["system"].id,
        agent_version_id=version.id,
        assessed_by="tester",
        risk_tier="LOW",
        overall_score=10,
    )
    plan = eval_svc.create_plan(
        agent_version_id=version.id,
        target_environment="PRODUCTION",
        created_by="tester",
    )
    eval_svc.start_runs_for_plan(plan["id"], created_by="tester")
    gate = eval_svc.evaluate_deployment_gate(
        agent_version_id=version.id,
        environment="PRODUCTION",
        evaluated_by="tester",
    )
    assert gate["assurance"]["status"] == AssuranceStatus.VALID.value

    # Force expiry
    from rai_gateway.models.evaluations import AssuranceRecord

    row = (
        db_session.query(AssuranceRecord)
        .filter(AssuranceRecord.id == gate["assurance"]["id"])
        .one()
    )
    row.valid_until = datetime.now(timezone.utc) - timedelta(days=1)
    db_session.commit()

    assert eval_svc.is_environment_eligible(version.id) is False
    assurance = eval_svc.get_assurance(version.id)
    assert assurance["current"]["status"] == AssuranceStatus.EXPIRED.value
    assert assurance["reassessment_required"] is True

    eligibility = EligibilityService(db_session).evaluate(
        system_id=stack["system"].id,
        agent_id=stack["agent"].id,
        version_id=version.id,
    )
    assert eligibility.eligible is False


def test_no_requirements_keeps_backwards_compatible_eligibility(
    db_session, registry, eval_svc, test_organization
):
    """Systems without WP7 requirements remain eligible (WP1–WP6 compatibility)."""
    suffix = uuid.uuid4().hex[:8]
    stack = _approve_system_agent(registry, suffix)
    version = registry.create_agent_version(stack["agent"].id, created_by="tester")
    for status in (AgentVersionStatus.UNDER_REVIEW, AgentVersionStatus.APPROVED):
        registry.transition_agent_version(version.id, status.value, updated_by="tester")
    eligibility = EligibilityService(db_session).evaluate(
        system_id=stack["system"].id,
        agent_id=stack["agent"].id,
        version_id=version.id,
    )
    assert eligibility.eligible is True
    assert eval_svc.is_environment_eligible(version.id) is True


def test_run_idempotency(db_session, registry, eval_svc, test_organization):
    suffix = uuid.uuid4().hex[:8]
    stack = _approve_system_agent(registry, suffix)
    setup = _setup_suites_and_requirements(
        eval_svc, ai_system_id=stack["system"].id, business_fail=False
    )
    version = registry.create_agent_version(
        stack["agent"].id,
        created_by="tester",
        configuration_snapshot={"max_discount_percent": 15},
    )
    plan = eval_svc.create_plan(
        agent_version_id=version.id,
        target_environment="PRODUCTION",
        created_by="tester",
    )
    first = eval_svc.execute_run(
        plan_id=plan["id"],
        suite_id=setup["suites"]["security"]["id"],
        requirement_id=setup["requirements"]["security"]["id"],
        created_by="tester",
        idempotency_key="k1",
    )
    second = eval_svc.execute_run(
        plan_id=plan["id"],
        suite_id=setup["suites"]["security"]["id"],
        requirement_id=setup["requirements"]["security"]["id"],
        created_by="tester",
        idempotency_key="k1",
    )
    assert first["id"] == second["id"]


def test_tenant_isolation_suite_lookup(
    db_session, registry, eval_svc, test_organization
):
    a = _approve_system_agent(registry, "aaa11111")
    b = _approve_system_agent(registry, "bbb22222")
    suite_a = eval_svc.create_suite(
        ai_system_id=a["system"].id,
        suite_key="sec",
        name="A Security",
        category="SECURITY",
        created_by="tester",
    )
    listed = eval_svc.list_suites(ai_system_id=b["system"].id)
    assert all(s["id"] != suite_a["id"] for s in listed)


def test_api_rbac_evaluation_read(
    test_client, db_session, registry, eval_svc, test_organization, monkeypatch
):
    from rai_gateway.core.auth import create_admin_access_token, hash_password
    from rai_gateway.core.config import settings
    from rai_gateway.models.database import AdminCredential, UserAccount, UserRole
    from rai_gateway.services.admin_console import _ensure_default_rbac_seed

    _ensure_default_rbac_seed(db_session)
    email = "eval-auditor@example.com"
    user_id = "eval-auditor"
    if (
        db_session.query(UserAccount).filter(UserAccount.user_id == user_id).first()
        is None
    ):
        db_session.add(
            UserAccount(user_id=user_id, email=email, name="Auditor", status="active")
        )
        db_session.flush()
        db_session.add(
            AdminCredential(
                email=email,
                user_id=user_id,
                password_hash=hash_password("SecurePass123!"),
                is_active=True,
            )
        )
        db_session.add(UserRole(user_id=user_id, role_id="auditor"))
        db_session.commit()

    token = create_admin_access_token(email=email, user_id=user_id, roles=["auditor"])
    monkeypatch.setattr(settings, "admin_token", None)

    stack = _approve_system_agent(registry, uuid.uuid4().hex[:8])
    res = test_client.get(
        f"/v1/evaluation-suites?ai_system_id={stack['system'].id}",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Admin-Role": "auditor",
        },
    )
    assert res.status_code == 200
    assert "items" in res.json()
