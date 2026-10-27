"""Domain types and invariants for WP3 durable action-bound human approval."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Final
from uuid import UUID

DEFAULT_APPROVAL_TTL_MINUTES: Final[int] = 15


class ApprovalStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    CONSUMED = "CONSUMED"


class ApprovalDecisionType(StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ApprovalRequirement(StrEnum):
    NOT_REQUIRED = "NOT_REQUIRED"
    REQUIRED = "REQUIRED"
    DENIED = "DENIED"


class IntegrationType(StrEnum):
    MCP = "mcp"
    EXTERNAL_SERVICE = "external_service"


APPROVAL_TRANSITIONS: dict[ApprovalStatus, set[ApprovalStatus]] = {
    ApprovalStatus.PENDING: {
        ApprovalStatus.APPROVED,
        ApprovalStatus.REJECTED,
        ApprovalStatus.CANCELLED,
        ApprovalStatus.EXPIRED,
    },
    ApprovalStatus.APPROVED: {
        ApprovalStatus.CONSUMED,
        ApprovalStatus.EXPIRED,
    },
    ApprovalStatus.REJECTED: set(),
    ApprovalStatus.EXPIRED: set(),
    ApprovalStatus.CANCELLED: set(),
    ApprovalStatus.CONSUMED: set(),
}


class ApprovalDenialCode(StrEnum):
    APPROVAL_NOT_FOUND = "APPROVAL_NOT_FOUND"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    APPROVAL_PENDING = "APPROVAL_PENDING"
    APPROVAL_REJECTED = "APPROVAL_REJECTED"
    APPROVAL_CANCELLED = "APPROVAL_CANCELLED"
    APPROVAL_EXPIRED = "APPROVAL_EXPIRED"
    APPROVAL_ALREADY_CONSUMED = "APPROVAL_ALREADY_CONSUMED"
    APPROVAL_ACTION_MISMATCH = "APPROVAL_ACTION_MISMATCH"
    APPROVAL_AGENT_VERSION_MISMATCH = "APPROVAL_AGENT_VERSION_MISMATCH"
    APPROVAL_RUNTIME_IDENTITY_MISMATCH = "APPROVAL_RUNTIME_IDENTITY_MISMATCH"
    APPROVAL_AUTHORITY_CHANGED = "APPROVAL_AUTHORITY_CHANGED"
    APPROVER_NOT_AUTHORIZED = "APPROVER_NOT_AUTHORIZED"
    APPROVAL_STEP_UP_REQUIRED = "APPROVAL_STEP_UP_REQUIRED"
    AUTHORITY_SCOPE_EXCEEDED = "AUTHORITY_SCOPE_EXCEEDED"
    AGENT_INELIGIBLE = "AGENT_INELIGIBLE"
    RUNTIME_IDENTITY_INELIGIBLE = "RUNTIME_IDENTITY_INELIGIBLE"
    SELF_APPROVAL_DENIED = "SELF_APPROVAL_DENIED"
    INVALID_TRANSITION = "INVALID_TRANSITION"
    APPROVAL_STAGE_ROLE_MISMATCH = "APPROVAL_STAGE_ROLE_MISMATCH"
    APPROVAL_STAGE_ALREADY_DECIDED = "APPROVAL_STAGE_ALREADY_DECIDED"
    APPROVAL_DUPLICATE_STAGE_APPROVER = "APPROVAL_DUPLICATE_STAGE_APPROVER"
    APPROVAL_CROSS_STAGE_SOD = "APPROVAL_CROSS_STAGE_SOD"
    APPROVAL_PLAN_INVALIDATED = "APPROVAL_PLAN_INVALIDATED"
    APPROVAL_STAGE_NOT_ACTIVE = "APPROVAL_STAGE_NOT_ACTIVE"


class ApprovalStageMode(StrEnum):
    """How approvals within a stage are counted."""

    SEQUENTIAL = "SEQUENTIAL"  # one required role at a time (order in required_roles)
    PARALLEL = "PARALLEL"  # all required_roles must approve
    QUORUM = "QUORUM"  # quorum_count of distinct approvers from required_roles


class ApprovalStageStatus(StrEnum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SKIPPED = "SKIPPED"


class ApprovalPlanStatus(StrEnum):
    IN_PROGRESS = "IN_PROGRESS"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    INVALIDATED = "INVALIDATED"


@dataclass
class ApprovalStageSpec:
    """Declarative stage definition supplied at request creation."""

    name: str
    mode: str = ApprovalStageMode.QUORUM.value
    required_roles: list[str] = field(default_factory=list)
    quorum_count: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "mode": self.mode,
            "required_roles": list(self.required_roles),
            "quorum_count": self.quorum_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ApprovalStageSpec:
        roles = data.get("required_roles") or []
        if isinstance(roles, str):
            roles = [roles]
        mode = str(data.get("mode") or ApprovalStageMode.QUORUM.value).upper()
        quorum = int(data.get("quorum_count") or data.get("quorum") or 1)
        if mode == ApprovalStageMode.PARALLEL.value:
            quorum = max(quorum, len(roles) or 1)
        return cls(
            name=str(data.get("name") or "stage"),
            mode=mode,
            required_roles=[str(r) for r in roles],
            quorum_count=max(1, quorum),
        )


@dataclass
class ActionTarget:
    type: str
    id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "id": self.id}


@dataclass
class ProposedAction:
    """Provider-neutral proposed consequential action."""

    ai_system_id: UUID
    agent_id: UUID
    agent_version_id: UUID
    runtime_identity_id: UUID
    delegation_id: UUID | None
    integration_type: str
    integration_id: UUID | None
    tool_id: UUID | None
    model_id: UUID | None = None
    data_source_id: UUID | None = None
    target: ActionTarget | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    environment: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ai_system_id": str(self.ai_system_id),
            "agent_id": str(self.agent_id),
            "agent_version_id": str(self.agent_version_id),
            "runtime_identity_id": str(self.runtime_identity_id),
            "delegation_id": str(self.delegation_id) if self.delegation_id else None,
            "integration_type": self.integration_type,
            "integration_id": str(self.integration_id) if self.integration_id else None,
            "tool_id": str(self.tool_id) if self.tool_id else None,
            "model_id": str(self.model_id) if self.model_id else None,
            "data_source_id": str(self.data_source_id) if self.data_source_id else None,
            "target": self.target.to_dict() if self.target else None,
            "parameters": self.parameters,
            "environment": self.environment,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProposedAction:
        target_data = data.get("target")
        target = None
        if target_data:
            target = ActionTarget(
                type=str(target_data.get("type", "")),
                id=target_data.get("id"),
            )
        return cls(
            ai_system_id=UUID(str(data["ai_system_id"])),
            agent_id=UUID(str(data["agent_id"])),
            agent_version_id=UUID(str(data["agent_version_id"])),
            runtime_identity_id=UUID(str(data["runtime_identity_id"])),
            delegation_id=UUID(str(data["delegation_id"]))
            if data.get("delegation_id")
            else None,
            integration_type=str(data["integration_type"]),
            integration_id=UUID(str(data["integration_id"]))
            if data.get("integration_id")
            else None,
            tool_id=UUID(str(data["tool_id"])) if data.get("tool_id") else None,
            model_id=UUID(str(data["model_id"])) if data.get("model_id") else None,
            data_source_id=UUID(str(data["data_source_id"]))
            if data.get("data_source_id")
            else None,
            target=target,
            parameters=dict(data.get("parameters") or {}),
            environment=data.get("environment"),
        )


@dataclass
class ConsumptionResult:
    allowed: bool
    reason: ApprovalDenialCode | None = None
    message: str = ""
    approval_request_id: UUID | None = None
