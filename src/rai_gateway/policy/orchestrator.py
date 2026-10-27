"""Policy decision envelope and orchestrator."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from rai_gateway.policy.context import PolicyEvaluationContext
from rai_gateway.policy.domain import (
    PolicyControlDomain,
    PolicyEffect,
    PolicyEnforceability,
    dominant_effect,
)

if TYPE_CHECKING:
    from rai_gateway.policy.providers.base import PolicyControlProvider


@dataclass
class ControlDecision:
    """Decision from a single specialized control domain."""

    domain: str
    effect: str
    control_id: str | None = None
    matched_rule_ids: list[str] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)
    human_explanation: str = ""
    findings: list[dict[str, Any]] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    evaluator: str | None = None
    remediation: dict[str, Any] | None = None
    enforceability: str = PolicyEnforceability.INLINE.value
    required_approver_role: str | None = None
    monitoring_instruction: str | None = None
    condition_details: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "effect": self.effect,
            "control_id": self.control_id,
            "matched_rule_ids": self.matched_rule_ids,
            "reason_codes": self.reason_codes,
            "human_explanation": self.human_explanation,
            "findings": self.findings,
            "evidence_refs": self.evidence_refs,
            "evaluator": self.evaluator,
            "remediation": self.remediation,
            "enforceability": self.enforceability,
            "required_approver_role": self.required_approver_role,
            "monitoring_instruction": self.monitoring_instruction,
            "condition_details": self.condition_details,
        }


@dataclass
class PolicyDecisionEnvelope:
    """Aggregated orchestration result across control domains."""

    intervention_point: str
    effect: str
    decisions: list[ControlDecision] = field(default_factory=list)
    matched_rule_ids: list[str] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)
    required_approver_role: str | None = None
    content_security: dict[str, Any] | None = None
    remediation: dict[str, Any] | None = None
    enforcement_capability: str = PolicyEnforceability.INLINE.value
    latency_ms: int = 0
    human_explanation: str = ""
    monitoring_instruction: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "intervention_point": self.intervention_point,
            "effect": self.effect,
            "decisions": [d.to_dict() for d in self.decisions],
            "matched_rule_ids": self.matched_rule_ids,
            "reason_codes": self.reason_codes,
            "required_approver_role": self.required_approver_role,
            "content_security": self.content_security,
            "remediation": self.remediation,
            "enforcement_capability": self.enforcement_capability,
            "latency_ms": self.latency_ms,
            "human_explanation": self.human_explanation,
            "monitoring_instruction": self.monitoring_instruction,
        }


# Preferred evaluation order for PRE_TOOL (plan § decision ordering).
_DOMAIN_ORDER = (
    PolicyControlDomain.ACCESS.value,
    PolicyControlDomain.ACTION.value,
    PolicyControlDomain.CONTENT.value,
    PolicyControlDomain.BUDGET.value,
    PolicyControlDomain.RISK.value,
    PolicyControlDomain.DATA.value,
)


class PolicyOrchestrator:
    """Compose specialized control providers into a single decision envelope.

    PR1 registers ACCESS + ACTION only. Not wired into runtime enforcement.
    """

    def __init__(self, providers: list[PolicyControlProvider] | None = None) -> None:
        self._providers: list[PolicyControlProvider] = list(providers or [])

    def register(self, provider: PolicyControlProvider) -> None:
        self._providers.append(provider)

    def evaluate(self, ctx: PolicyEvaluationContext) -> PolicyDecisionEnvelope:
        started = time.perf_counter()
        ordered = sorted(
            self._providers,
            key=lambda p: (
                _DOMAIN_ORDER.index(p.domain)
                if p.domain in _DOMAIN_ORDER
                else len(_DOMAIN_ORDER)
            ),
        )

        decisions: list[ControlDecision] = []
        for provider in ordered:
            if not provider.applies_to(ctx):
                continue
            decision = provider.evaluate(ctx)
            decisions.append(decision)
            # Deterministic ACCESS DENY short-circuits remaining domains.
            if (
                decision.domain == PolicyControlDomain.ACCESS.value
                and decision.effect == PolicyEffect.DENY.value
            ):
                break

        effects = [d.effect for d in decisions]
        winning = dominant_effect(effects)
        matched: list[str] = []
        reasons: list[str] = []
        explanations: list[str] = []
        required_role: str | None = None
        monitoring: str | None = None
        for d in decisions:
            matched.extend(d.matched_rule_ids)
            reasons.extend(d.reason_codes)
            if d.human_explanation:
                explanations.append(d.human_explanation)
            if (
                winning == PolicyEffect.REQUIRE_APPROVAL.value
                and d.effect == PolicyEffect.REQUIRE_APPROVAL.value
                and d.required_approver_role
                and required_role is None
            ):
                required_role = d.required_approver_role
            if (
                winning == PolicyEffect.MONITOR.value
                and d.monitoring_instruction
                and monitoring is None
            ):
                monitoring = d.monitoring_instruction

        enforceability = PolicyEnforceability.INLINE.value
        if decisions:
            if any(
                d.enforceability == PolicyEnforceability.NOT_AVAILABLE.value
                for d in decisions
            ):
                enforceability = PolicyEnforceability.NOT_AVAILABLE.value
            elif any(
                d.enforceability == PolicyEnforceability.OBSERVE_ONLY.value
                for d in decisions
            ):
                enforceability = PolicyEnforceability.OBSERVE_ONLY.value

        latency_ms = int((time.perf_counter() - started) * 1000)
        return PolicyDecisionEnvelope(
            intervention_point=ctx.intervention_point,
            effect=winning if decisions else PolicyEffect.ALLOW.value,
            decisions=decisions,
            matched_rule_ids=matched,
            reason_codes=reasons if decisions else ["NO_APPLICABLE_CONTROL_PROVIDERS"],
            required_approver_role=required_role,
            enforcement_capability=enforceability,
            latency_ms=latency_ms,
            human_explanation="; ".join(explanations)
            if explanations
            else (
                "No applicable control providers; default allow."
                if not decisions
                else ""
            ),
            monitoring_instruction=monitoring,
        )
