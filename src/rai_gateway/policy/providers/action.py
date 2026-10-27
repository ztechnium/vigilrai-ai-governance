"""ACTION control provider — wraps ToolRule evaluation without re-validating authority."""

from __future__ import annotations

from sqlalchemy.orm import Session

from rai_gateway.policy.context import PolicyEvaluationContext
from rai_gateway.policy.domain import (
    PolicyControlDomain,
    PolicyEnforceability,
    PolicyInterventionPoint,
)
from rai_gateway.policy.evaluation import PolicyEvaluationService
from rai_gateway.policy.orchestrator import ControlDecision

_ACTION_POINTS = frozenset({PolicyInterventionPoint.PRE_TOOL.value})


class ActionPolicyControlProvider:
    """Map ToolRule matching into a ControlDecision.

    Uses tool-rule evaluation only so ACCESS can own authority validation
    when both providers run under the orchestrator.
    """

    def __init__(self, db: Session) -> None:
        self._evaluation = PolicyEvaluationService(db)

    @property
    def domain(self) -> str:
        return PolicyControlDomain.ACTION.value

    def applies_to(self, ctx: PolicyEvaluationContext) -> bool:
        return (
            ctx.intervention_point in _ACTION_POINTS and ctx.proposed_action is not None
        )

    def evaluate(self, ctx: PolicyEvaluationContext) -> ControlDecision:
        assert ctx.proposed_action is not None
        decision = self._evaluation.evaluate_tool_rules(ctx.proposed_action)
        return ControlDecision(
            domain=self.domain,
            effect=decision.effect,
            control_id=(
                decision.matched_policy_ids[0] if decision.matched_policy_ids else None
            ),
            matched_rule_ids=list(
                decision.matched_tool_rule_ids or decision.matched_rule_ids
            ),
            reason_codes=list(decision.reason_codes),
            human_explanation=decision.human_explanation,
            enforceability=PolicyEnforceability.INLINE.value,
            required_approver_role=decision.required_approver_role,
            monitoring_instruction=decision.monitoring_instruction,
            condition_details=list(decision.condition_details),
        )
