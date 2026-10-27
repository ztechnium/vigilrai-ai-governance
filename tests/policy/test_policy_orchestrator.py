"""Policy orchestrator and control provider tests."""

from __future__ import annotations

import uuid

from rai_gateway.approval.consumption import ApprovalConsumptionService
from rai_gateway.approval.domain import ProposedAction
from rai_gateway.policy.context import (
    PolicyEvaluationContext,
    RuntimePolicyCapabilities,
)
from rai_gateway.policy.domain import (
    PolicyControlDomain,
    PolicyEffect,
    PolicyInterventionPoint,
)
from rai_gateway.policy.evaluation import PolicyEvaluationService
from rai_gateway.policy.orchestrator import PolicyOrchestrator
from rai_gateway.policy.providers.access import AuthorityControlProvider
from rai_gateway.policy.providers.action import ActionPolicyControlProvider
from rai_gateway.policy.service import PolicyCollectionService


def _authority(db_session, stack):
    return ApprovalConsumptionService(db_session).resolve_authority_for_identity(
        stack["identity"].id,
        stack["delegation"].id,
    )


def _action(
    stack, *, tool_key: str = "tool", parameters: dict | None = None
) -> ProposedAction:
    tool = stack["tool"] if tool_key == "tool" else stack["deny_tool"]
    return ProposedAction(
        ai_system_id=stack["system"].id,
        agent_id=stack["agent"].id,
        agent_version_id=stack["version"].id,
        runtime_identity_id=stack["identity"].id,
        delegation_id=stack["delegation"].id,
        integration_type="mcp",
        integration_id=stack["mcp"].id,
        tool_id=tool.id,
        parameters=parameters or {},
    )


def _pre_tool_ctx(stack, authority, action) -> PolicyEvaluationContext:
    return PolicyEvaluationContext(
        intervention_point=PolicyInterventionPoint.PRE_TOOL.value,
        ai_system_id=stack["system"].id,
        agent_id=stack["agent"].id,
        agent_version_id=stack["version"].id,
        runtime_identity_id=stack["identity"].id,
        delegation_id=stack["delegation"].id,
        mcp_server_id=stack["mcp"].id,
        tool_id=action.tool_id,
        parameters=dict(action.parameters or {}),
        capabilities=RuntimePolicyCapabilities(
            intervention_points={PolicyInterventionPoint.PRE_TOOL.value},
            can_block_tool_call=True,
        ),
        authority=authority,
        proposed_action=action,
    )


def test_action_provider_parity_with_evaluation_service(
    db_session, policy_stack
) -> None:
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
    action = _action(policy_stack, parameters={"amount": 150000})

    legacy = PolicyEvaluationService(db_session).evaluate(authority, action)
    provider = ActionPolicyControlProvider(db_session)
    ctx = _pre_tool_ctx(policy_stack, authority, action)
    control = provider.evaluate(ctx)

    assert control.domain == PolicyControlDomain.ACTION.value
    assert control.effect == legacy.effect == PolicyEffect.REQUIRE_APPROVAL.value
    assert control.matched_rule_ids == legacy.matched_tool_rule_ids
    assert control.required_approver_role == legacy.required_approver_role


def test_orchestrator_access_deny_short_circuits(db_session, policy_stack) -> None:
    svc = PolicyCollectionService(db_session)
    svc.create_tool_rule(
        policy_stack["system"].id,
        title="Would require approval",
        tool_id=policy_stack["tool"].id,
        mcp_server_id=policy_stack["mcp"].id,
        effect=PolicyEffect.REQUIRE_APPROVAL.value,
        required_approver_role="business_approver",
        actor="tester",
    )

    authority = _authority(db_session, policy_stack)
    # Mismatched tool/system identity triggers ACCESS DENY.
    bad_action = ProposedAction(
        ai_system_id=uuid.uuid4(),
        agent_id=policy_stack["agent"].id,
        agent_version_id=policy_stack["version"].id,
        runtime_identity_id=policy_stack["identity"].id,
        delegation_id=policy_stack["delegation"].id,
        integration_type="mcp",
        integration_id=policy_stack["mcp"].id,
        tool_id=policy_stack["tool"].id,
        parameters={},
    )
    ctx = _pre_tool_ctx(policy_stack, authority, bad_action)
    ctx.ai_system_id = bad_action.ai_system_id

    orch = PolicyOrchestrator(
        [
            AuthorityControlProvider(db_session),
            ActionPolicyControlProvider(db_session),
        ]
    )
    envelope = orch.evaluate(ctx)
    assert envelope.effect == PolicyEffect.DENY.value
    assert len(envelope.decisions) == 1
    assert envelope.decisions[0].domain == PolicyControlDomain.ACCESS.value
    assert "ACTION" not in {d.domain for d in envelope.decisions}


def test_orchestrator_action_dominance(db_session, policy_stack) -> None:
    svc = PolicyCollectionService(db_session)
    svc.create_tool_rule(
        policy_stack["system"].id,
        title="Deny delete",
        tool_id=policy_stack["deny_tool"].id,
        mcp_server_id=policy_stack["mcp"].id,
        effect=PolicyEffect.DENY.value,
        actor="tester",
    )

    authority = _authority(db_session, policy_stack)
    action = _action(policy_stack, tool_key="deny", parameters={"doctype": "Supplier"})
    # No condition on this rule — matches any params for deny tool.
    ctx = _pre_tool_ctx(policy_stack, authority, action)

    orch = PolicyOrchestrator(
        [
            AuthorityControlProvider(db_session),
            ActionPolicyControlProvider(db_session),
        ]
    )
    envelope = orch.evaluate(ctx)
    assert envelope.effect == PolicyEffect.DENY.value
    domains = [d.domain for d in envelope.decisions]
    assert domains == [
        PolicyControlDomain.ACCESS.value,
        PolicyControlDomain.ACTION.value,
    ]
    action_decision = envelope.decisions[1]
    assert action_decision.effect == PolicyEffect.DENY.value


def test_orchestrator_not_wired_into_runtime_path() -> None:
    """Smoke: runtime enforcement module must not import PolicyOrchestrator."""
    import inspect

    import rai_gateway.runtime_enforcement.service as runtime_mod

    source = inspect.getsource(runtime_mod)
    assert "PolicyOrchestrator" not in source
    assert "policy.orchestrator" not in source
