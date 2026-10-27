"""Deterministic approval requirement evaluation for WP3."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from rai_gateway.approval.domain import ApprovalRequirement, ProposedAction
from rai_gateway.identity.resolver import RuntimeAuthorityContext
from rai_gateway.models.registry import ToolResource
from rai_gateway.policy.domain import PolicyEffect
from rai_gateway.policy.evaluation import PolicyEvaluationService


@dataclass
class RequirementResult:
    requirement: ApprovalRequirement
    reason: str
    risk_tier: str | None = None
    policy_reference: str | None = None
    monitoring_instruction: str | None = None
    required_approver_role: str | None = None


class ApprovalRequirementService:
    """Decide whether a proposed action requires human approval."""

    HIGH_RISK_TIERS = frozenset({"HIGH", "CRITICAL"})

    def __init__(self, db: Session) -> None:
        self._db = db
        self._policy = PolicyEvaluationService(db)

    def evaluate(
        self,
        authority: RuntimeAuthorityContext,
        action: ProposedAction,
    ) -> RequirementResult:
        tool = None
        if action.tool_id:
            tool = (
                self._db.query(ToolResource)
                .filter(ToolResource.id == action.tool_id)
                .first()
            )

        version_risk = authority.agent_version.risk_tier
        tool_risk = getattr(tool, "sensitivity", None) if tool else None
        risk_tier = version_risk or tool_risk

        decision = self._policy.evaluate(authority, action)

        if decision.effect == PolicyEffect.DENY.value:
            return RequirementResult(
                requirement=ApprovalRequirement.DENIED,
                reason=decision.human_explanation or "Action denied by policy",
                risk_tier=risk_tier,
                policy_reference=",".join(decision.matched_rule_ids) or "policy.deny",
            )

        if decision.effect == PolicyEffect.REQUIRE_APPROVAL.value:
            return RequirementResult(
                requirement=ApprovalRequirement.REQUIRED,
                reason=decision.human_explanation
                or "Human approval required by policy",
                risk_tier=risk_tier,
                policy_reference=",".join(decision.matched_rule_ids)
                or "policy.require_approval",
                required_approver_role=decision.required_approver_role,
            )

        if decision.effect == PolicyEffect.MONITOR.value:
            return RequirementResult(
                requirement=ApprovalRequirement.NOT_REQUIRED,
                reason=decision.human_explanation or "Action allowed with monitoring",
                risk_tier=risk_tier,
                policy_reference=",".join(decision.matched_rule_ids)
                or "policy.monitor",
                monitoring_instruction=decision.monitoring_instruction,
            )

        # Platform controls (not organization-specific policies)
        if tool and tool.consequential_action:
            return RequirementResult(
                requirement=ApprovalRequirement.REQUIRED,
                reason="Tool marked as consequential (platform control)",
                risk_tier=risk_tier,
                policy_reference="platform.tool.consequential_action",
            )

        if risk_tier and risk_tier.upper() in self.HIGH_RISK_TIERS:
            return RequirementResult(
                requirement=ApprovalRequirement.REQUIRED,
                reason=f"Risk tier {risk_tier} requires human approval (platform control)",
                risk_tier=risk_tier,
                policy_reference="platform.risk_tier.threshold",
            )

        return RequirementResult(
            requirement=ApprovalRequirement.NOT_REQUIRED,
            reason=decision.human_explanation or "No approval policy matched",
            risk_tier=risk_tier,
            policy_reference=",".join(decision.matched_rule_ids) or None,
        )
