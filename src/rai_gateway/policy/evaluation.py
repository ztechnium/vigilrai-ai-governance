"""Policy evaluation engine."""

from __future__ import annotations

from sqlalchemy.orm import Session, joinedload

from rai_gateway.approval.authority_validator import ActionAuthorityValidator
from rai_gateway.approval.domain import ProposedAction
from rai_gateway.identity.resolver import RuntimeAuthorityContext
from rai_gateway.models.policy_engine import ToolRule
from rai_gateway.policy.conditions import evaluate_condition
from rai_gateway.policy.domain import (
    MatchMode,
    PolicyDecision,
    PolicyEffect,
    dominant_effect,
)
from rai_gateway.policy.service import PolicyCollectionService


class PolicyEvaluationService:
    """Evaluate proposed actions against AI System policy collections."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._collections = PolicyCollectionService(db)
        self._authority = ActionAuthorityValidator(db)

    def evaluate(
        self,
        authority: RuntimeAuthorityContext,
        action: ProposedAction,
    ) -> PolicyDecision:
        self._authority.validate(authority, action)
        return self.evaluate_tool_rules(action)

    def evaluate_tool_rules(self, action: ProposedAction) -> PolicyDecision:
        """Match ToolRules only (no authority validation).

        Used by ActionPolicyControlProvider when ACCESS already validated authority.
        """
        collection = self._collections.get_collection_for_system(action.ai_system_id)
        if not collection:
            return PolicyDecision(
                effect=PolicyEffect.ALLOW.value,
                human_explanation="No policy collection configured; default allow after authority validation.",
                reason_codes=["NO_POLICY_COLLECTION"],
            )

        tool_rules = (
            self._db.query(ToolRule)
            .options(joinedload(ToolRule.conditions))
            .filter(
                ToolRule.policy_collection_id == collection.id,
                ToolRule.enabled.is_(True),
                ToolRule.archived_at.is_(None),
            )
            .all()
        )

        matched_rules: list[ToolRule] = []
        condition_details: list[dict] = []

        for rule in tool_rules:
            if not self._rule_applies(rule, action):
                continue
            if self._conditions_match(rule, action.parameters or {}, condition_details):
                matched_rules.append(rule)

        if not matched_rules:
            return PolicyDecision(
                effect=PolicyEffect.ALLOW.value,
                matched_policy_ids=[str(collection.id)],
                human_explanation="No matching tool rules; default allow after authority validation.",
                reason_codes=["NO_MATCHING_TOOL_RULE"],
            )

        effects = [rule.effect for rule in matched_rules]
        winning_effect = dominant_effect(effects)
        dominant_rule = next(r for r in matched_rules if r.effect == winning_effect)

        explanations = [
            f"{r.title}: {r.effect}" + (f" ({r.description})" if r.description else "")
            for r in matched_rules
        ]
        monitoring = None
        if winning_effect == PolicyEffect.MONITOR.value:
            monitoring = f"Monitor action per rule '{dominant_rule.title}'"

        return PolicyDecision(
            effect=winning_effect,
            matched_policy_ids=[str(collection.id)],
            matched_rule_ids=[str(r.id) for r in matched_rules],
            matched_tool_rule_ids=[str(r.id) for r in matched_rules],
            reason_codes=[f"MATCHED:{r.id}" for r in matched_rules],
            human_explanation="; ".join(explanations),
            monitoring_instruction=monitoring,
            required_approver_role=dominant_rule.required_approver_role
            if winning_effect == PolicyEffect.REQUIRE_APPROVAL.value
            else None,
            condition_details=condition_details,
        )

    def _rule_applies(self, rule: ToolRule, action: ProposedAction) -> bool:
        if action.tool_id != rule.tool_id:
            return False
        if rule.mcp_server_id and action.integration_id != rule.mcp_server_id:
            return False
        return True

    def _conditions_match(
        self,
        rule: ToolRule,
        parameters: dict,
        condition_details: list[dict],
    ) -> bool:
        conditions = list(rule.conditions or [])
        if not conditions:
            return True

        results: list[bool] = []
        for cond in conditions:
            ok, detail = evaluate_condition(
                parameters=parameters,
                parameter_path=cond.parameter_path,
                operator=cond.operator,
                value_type=cond.value_type,
                expected=cond.value_json,
            )
            condition_details.append(
                {
                    "rule_id": str(rule.id),
                    "parameter_path": cond.parameter_path,
                    "operator": cond.operator,
                    "matched": ok,
                    "detail": detail,
                }
            )
            results.append(ok)

        if rule.match_mode == MatchMode.ANY.value:
            return any(results)
        return all(results)
