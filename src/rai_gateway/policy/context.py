"""Common policy evaluation context and integration capabilities."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from rai_gateway.approval.domain import ProposedAction
from rai_gateway.identity.resolver import RuntimeAuthorityContext
from rai_gateway.policy.domain import PolicyInterventionPoint


@dataclass
class RuntimePolicyCapabilities:
    """What the calling integration can enforce at each intervention point."""

    intervention_points: set[str] = field(default_factory=set)
    can_block_input: bool = False
    can_block_model_call: bool = False
    can_block_tool_call: bool = False
    can_block_output: bool = False
    can_transform_input: bool = False
    can_transform_output: bool = False
    can_transform_tool_payload: bool = False
    can_report_after_fact: bool = True

    def supports_point(self, intervention_point: str) -> bool:
        return intervention_point in self.intervention_points


@dataclass
class PolicyEvaluationContext:
    """Unified context for policy orchestration across control domains."""

    intervention_point: str
    ai_system_id: UUID
    agent_id: UUID | None = None
    agent_version_id: UUID | None = None
    runtime_identity_id: UUID | None = None
    delegation_id: UUID | None = None
    trajectory_id: UUID | None = None
    enforcement_receipt_id: UUID | None = None
    model_id: UUID | None = None
    mcp_server_id: UUID | None = None
    tool_id: UUID | None = None
    data_source_id: UUID | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    content: str | None = None
    capabilities: RuntimePolicyCapabilities = field(
        default_factory=RuntimePolicyCapabilities
    )
    # Optional runtime attachments for ACCESS / ACTION providers (PR1).
    authority: RuntimeAuthorityContext | None = None
    proposed_action: ProposedAction | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.intervention_point not in {p.value for p in PolicyInterventionPoint}:
            raise ValueError(f"Invalid intervention_point: {self.intervention_point}")
