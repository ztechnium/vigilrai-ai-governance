"""Provider-neutral runtime action adapter boundary."""

from __future__ import annotations

from abc import ABC, abstractmethod

from rai_gateway.approval.domain import ProposedAction
from rai_gateway.identity.resolver import RuntimeAuthorityContext
from rai_gateway.runtime_enforcement.domain import DownstreamExecutionResult


class RuntimeActionAdapter(ABC):
    """Decides how an allowed action is executed downstream."""

    @abstractmethod
    def supports(self, action: ProposedAction) -> bool:
        """Return True when this adapter can execute the action."""

    @abstractmethod
    def execute(
        self,
        action: ProposedAction,
        authority: RuntimeAuthorityContext,
    ) -> DownstreamExecutionResult:
        """Invoke downstream integration for an already-governed action."""


class RuntimeAdapterRegistry:
    """Select the first adapter that supports a proposed action."""

    def __init__(self, adapters: list[RuntimeActionAdapter] | None = None) -> None:
        self._adapters = adapters or []

    def register(self, adapter: RuntimeActionAdapter) -> None:
        self._adapters.append(adapter)

    def resolve(self, action: ProposedAction) -> RuntimeActionAdapter | None:
        for adapter in self._adapters:
            if adapter.supports(action):
                return adapter
        return None
