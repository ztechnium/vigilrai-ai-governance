"""Policy evaluation and CRUD tests."""

from __future__ import annotations

import pytest

from rai_gateway.approval.consumption import ApprovalConsumptionService
from rai_gateway.approval.domain import ApprovalRequirement, ProposedAction
from rai_gateway.approval.errors import ApprovalDeniedError
from rai_gateway.approval.requirement import ApprovalRequirementService
from rai_gateway.approval.service import ApprovalService
from rai_gateway.policy.domain import PolicyEffect
from rai_gateway.policy.errors import PolicyValidationError
from rai_gateway.policy.evaluation import PolicyEvaluationService
from rai_gateway.policy.service import PolicyCollectionService


def _authority(db_session, stack):
    return ApprovalConsumptionService(db_session).resolve_authority_for_identity(
        stack["identity"].id,
        stack["delegation"].id,
    )


def test_content_rule_crud(db_session, policy_stack) -> None:
    svc = PolicyCollectionService(db_session)
    rule = svc.create_content_rule(
        policy_stack["system"].id,
        title="No supplier secrets",
        content="Do not disclose supplier banking data.",
        effect=PolicyEffect.MONITOR.value,
        actor="tester",
    )
    assert rule.enabled is True

    updated = svc.update_content_rule(rule.id, actor="tester", enabled=False)
    assert updated.enabled is False

    detail = svc.get_collection_detail(policy_stack["system"].id)
    assert len(detail["content_rules"]) == 1
    svc.delete_content_rule(rule.id, actor="tester")
    detail = svc.get_collection_detail(policy_stack["system"].id)
    assert detail["content_rules"] == []


def test_tool_rule_mcp_validation(db_session, policy_stack) -> None:
    svc = PolicyCollectionService(db_session)
    with pytest.raises(PolicyValidationError):
        svc.create_tool_rule(
            policy_stack["system"].id,
            title="Bad MCP",
            tool_id=policy_stack["tool"].id,
            mcp_server_id=None,
            effect=PolicyEffect.DENY.value,
            actor="tester",
        )


def test_require_approval_on_amount(db_session, policy_stack) -> None:
    svc = PolicyCollectionService(db_session)
    svc.create_tool_rule(
        policy_stack["system"].id,
        title="High Value PO",
        tool_id=policy_stack["tool"].id,
        mcp_server_id=policy_stack["mcp"].id,
        effect=PolicyEffect.REQUIRE_APPROVAL.value,
        required_approver_role="business_approver",
        conditions=[
            {
                "parameter_path": "amount",
                "operator": "gte",
                "value_type": "number",
                "value": 100000,
            }
        ],
        actor="tester",
    )

    authority = _authority(db_session, policy_stack)
    action = ProposedAction(
        ai_system_id=policy_stack["system"].id,
        agent_id=policy_stack["agent"].id,
        agent_version_id=policy_stack["version"].id,
        runtime_identity_id=policy_stack["identity"].id,
        delegation_id=policy_stack["delegation"].id,
        integration_type="mcp",
        integration_id=policy_stack["mcp"].id,
        tool_id=policy_stack["tool"].id,
        parameters={"amount": 150000},
    )

    decision = PolicyEvaluationService(db_session).evaluate(authority, action)
    assert decision.effect == PolicyEffect.REQUIRE_APPROVAL.value

    req = ApprovalRequirementService(db_session).evaluate(authority, action)
    assert req.requirement == ApprovalRequirement.REQUIRED


def test_deny_rule_blocks_approval(db_session, policy_stack) -> None:
    svc = PolicyCollectionService(db_session)
    svc.create_tool_rule(
        policy_stack["system"].id,
        title="Deny delete",
        tool_id=policy_stack["deny_tool"].id,
        mcp_server_id=policy_stack["mcp"].id,
        effect=PolicyEffect.DENY.value,
        conditions=[
            {
                "parameter_path": "doctype",
                "operator": "eq",
                "value_type": "string",
                "value": "Supplier",
            }
        ],
        actor="tester",
    )

    authority = _authority(db_session, policy_stack)
    with pytest.raises(ApprovalDeniedError):
        ApprovalService(db_session).create_request(
            authority,
            integration_type="mcp",
            integration_id=policy_stack["mcp"].id,
            tool_id=policy_stack["deny_tool"].id,
            parameters={"doctype": "Supplier"},
            created_by="tester",
            force=True,
        )


def test_no_matching_rule_defaults_allow(db_session, policy_stack) -> None:
    authority = _authority(db_session, policy_stack)
    action = ProposedAction(
        ai_system_id=policy_stack["system"].id,
        agent_id=policy_stack["agent"].id,
        agent_version_id=policy_stack["version"].id,
        runtime_identity_id=policy_stack["identity"].id,
        delegation_id=policy_stack["delegation"].id,
        integration_type="mcp",
        integration_id=policy_stack["mcp"].id,
        tool_id=policy_stack["tool"].id,
        parameters={"amount": 10},
    )
    decision = PolicyEvaluationService(db_session).evaluate(authority, action)
    assert decision.effect == PolicyEffect.ALLOW.value


def test_effect_precedence_deny_wins(db_session, policy_stack) -> None:
    svc = PolicyCollectionService(db_session)
    for effect, title in (
        (PolicyEffect.REQUIRE_APPROVAL.value, "Require"),
        (PolicyEffect.DENY.value, "Deny"),
    ):
        svc.create_tool_rule(
            policy_stack["system"].id,
            title=title,
            tool_id=policy_stack["tool"].id,
            mcp_server_id=policy_stack["mcp"].id,
            effect=effect,
            required_approver_role="business_approver"
            if effect == PolicyEffect.REQUIRE_APPROVAL.value
            else None,
            conditions=[
                {
                    "parameter_path": "amount",
                    "operator": "gte",
                    "value_type": "number",
                    "value": 1,
                }
            ],
            actor="tester",
        )

    authority = _authority(db_session, policy_stack)
    action = ProposedAction(
        ai_system_id=policy_stack["system"].id,
        agent_id=policy_stack["agent"].id,
        agent_version_id=policy_stack["version"].id,
        runtime_identity_id=policy_stack["identity"].id,
        delegation_id=policy_stack["delegation"].id,
        integration_type="mcp",
        integration_id=policy_stack["mcp"].id,
        tool_id=policy_stack["tool"].id,
        parameters={"amount": 100},
    )
    decision = PolicyEvaluationService(db_session).evaluate(authority, action)
    assert decision.effect == PolicyEffect.DENY.value


def test_any_match_mode(db_session, policy_stack) -> None:
    svc = PolicyCollectionService(db_session)
    svc.create_tool_rule(
        policy_stack["system"].id,
        title="Currency or amount",
        tool_id=policy_stack["tool"].id,
        mcp_server_id=policy_stack["mcp"].id,
        match_mode="ANY",
        effect=PolicyEffect.MONITOR.value,
        conditions=[
            {
                "parameter_path": "amount",
                "operator": "gte",
                "value_type": "number",
                "value": 100000,
            },
            {
                "parameter_path": "currency",
                "operator": "eq",
                "value_type": "string",
                "value": "USD",
            },
        ],
        actor="tester",
    )

    authority = _authority(db_session, policy_stack)
    action = ProposedAction(
        ai_system_id=policy_stack["system"].id,
        agent_id=policy_stack["agent"].id,
        agent_version_id=policy_stack["version"].id,
        runtime_identity_id=policy_stack["identity"].id,
        delegation_id=policy_stack["delegation"].id,
        integration_type="mcp",
        integration_id=policy_stack["mcp"].id,
        tool_id=policy_stack["tool"].id,
        parameters={"amount": 1, "currency": "USD"},
    )
    decision = PolicyEvaluationService(db_session).evaluate(authority, action)
    assert decision.effect == PolicyEffect.MONITOR.value
