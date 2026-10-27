"""Test doubles for WP4 runtime enforcement."""

from __future__ import annotations

from dataclasses import dataclass

from rai_gateway.approval.domain import ProposedAction
from rai_gateway.identity.resolver import RuntimeAuthorityContext
from rai_gateway.runtime_enforcement.adapters.base import RuntimeActionAdapter
from rai_gateway.runtime_enforcement.domain import DownstreamExecutionResult


@dataclass
class FakeAdapter(RuntimeActionAdapter):
    invocation_count: int = 0
    should_fail: bool = False
    fail_message: str = "Simulated downstream failure"

    def supports(self, action: ProposedAction) -> bool:
        return bool(action.tool_id)

    def execute(
        self,
        action: ProposedAction,
        authority: RuntimeAuthorityContext,
    ) -> DownstreamExecutionResult:
        self.invocation_count += 1
        if self.should_fail:
            return DownstreamExecutionResult(
                success=False,
                error_message=self.fail_message,
            )
        return DownstreamExecutionResult(
            success=True,
            downstream_reference=f"fake-{self.invocation_count}",
            result_payload={"tool_id": str(action.tool_id)},
        )
