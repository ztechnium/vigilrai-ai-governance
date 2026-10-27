"""Policy control provider protocol."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from rai_gateway.policy.context import PolicyEvaluationContext
from rai_gateway.policy.orchestrator import ControlDecision


@runtime_checkable
class PolicyControlProvider(Protocol):
    """Specialized control engine adapter for the policy orchestrator."""

    @property
    def domain(self) -> str: ...

    def applies_to(self, ctx: PolicyEvaluationContext) -> bool: ...

    def evaluate(self, ctx: PolicyEvaluationContext) -> ControlDecision: ...
