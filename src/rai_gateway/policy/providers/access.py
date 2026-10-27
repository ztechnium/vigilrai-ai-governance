"""ACCESS control provider — wraps ActionAuthorityValidator."""

from __future__ import annotations

from sqlalchemy.orm import Session

from rai_gateway.approval.authority_validator import ActionAuthorityValidator
from rai_gateway.approval.errors import ApprovalDeniedError
from rai_gateway.policy.context import PolicyEvaluationContext
from rai_gateway.policy.domain import (
    PolicyControlDomain,
    PolicyEffect,
    PolicyEnforceability,
    PolicyInterventionPoint,
)
from rai_gateway.policy.orchestrator import ControlDecision

_ACCESS_POINTS = frozenset(
    {
        PolicyInterventionPoint.PRE_TOOL.value,
        PolicyInterventionPoint.POST_TOOL.value,
    }
)


class AuthorityControlProvider:
    """Map runtime authority validation into a ControlDecision."""

    def __init__(self, db: Session) -> None:
        self._validator = ActionAuthorityValidator(db)

    @property
    def domain(self) -> str:
        return PolicyControlDomain.ACCESS.value

    def applies_to(self, ctx: PolicyEvaluationContext) -> bool:
        return (
            ctx.intervention_point in _ACCESS_POINTS
            and ctx.authority is not None
            and ctx.proposed_action is not None
        )

    def evaluate(self, ctx: PolicyEvaluationContext) -> ControlDecision:
        assert ctx.authority is not None
        assert ctx.proposed_action is not None
        try:
            self._validator.validate(ctx.authority, ctx.proposed_action)
        except ApprovalDeniedError as exc:
            reason = getattr(exc, "reason", None) or "AUTHORITY_DENIED"
            return ControlDecision(
                domain=self.domain,
                effect=PolicyEffect.DENY.value,
                reason_codes=[str(reason)],
                human_explanation=exc.message,
                enforceability=PolicyEnforceability.INLINE.value,
            )
        return ControlDecision(
            domain=self.domain,
            effect=PolicyEffect.ALLOW.value,
            reason_codes=["AUTHORITY_VALID"],
            human_explanation="Runtime authority validated.",
            enforceability=PolicyEnforceability.INLINE.value,
        )
