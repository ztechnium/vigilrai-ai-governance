"""Domain types and invariants for the AI system/agent registry."""

from __future__ import annotations

from enum import StrEnum
from typing import Final

SCORE_MIN: Final[int] = 0
SCORE_MAX: Final[int] = 100


class AISystemStatus(StrEnum):
    DRAFT = "DRAFT"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    SUSPENDED = "SUSPENDED"
    STOPPED = "STOPPED"  # authoritative emergency stop
    RETIRED = "RETIRED"


class AgentStatus(StrEnum):
    DRAFT = "DRAFT"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    SUSPENDED = "SUSPENDED"
    RETIRED = "RETIRED"


class AgentVersionStatus(StrEnum):
    DRAFT = "DRAFT"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    REASSESSMENT_REQUIRED = "REASSESSMENT_REQUIRED"
    RETIRED = "RETIRED"


class MaterialChangeStatus(StrEnum):
    NONE = "NONE"
    PENDING = "PENDING"
    MATERIAL = "MATERIAL"
    NON_MATERIAL = "NON_MATERIAL"


class RiskTier(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RiskCategory(StrEnum):
    COMPLIANCE = "compliance"
    PRIVACY = "privacy"
    SECURITY = "security"
    FRAUD = "fraud"
    OPERATIONAL = "operational"
    FINANCIAL = "financial"
    SAFETY = "safety"
    REPUTATIONAL = "reputational"
    OTHER = "other"


class ResourceType(StrEnum):
    MODEL = "model"
    TOOL = "tool"
    MCP_SERVER = "mcp_server"
    EXTERNAL_SERVICE = "external_service"
    DATA_SOURCE = "data_source"


class ChangeCategory(StrEnum):
    MODEL = "MODEL"
    TOOL = "TOOL"
    MCP_SERVER = "MCP_SERVER"
    EXTERNAL_SERVICE = "EXTERNAL_SERVICE"
    DATA_SOURCE = "DATA_SOURCE"
    DATA_SENSITIVITY = "DATA_SENSITIVITY"
    PERMISSION = "PERMISSION"
    BUSINESS_PURPOSE = "BUSINESS_PURPOSE"
    RISK_TIER = "RISK_TIER"
    CONFIGURATION = "CONFIGURATION"


class ResourceStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    DEPRECATED = "DEPRECATED"


class CatalogScope(StrEnum):
    """Ownership scope for registry catalog resources."""

    PLATFORM = "PLATFORM"
    ORGANIZATION = "ORGANIZATION"


class AssessmentStatus(StrEnum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    SUPERSEDED = "SUPERSEDED"


class FindingStatus(StrEnum):
    OPEN = "OPEN"
    MITIGATED = "MITIGATED"
    ACCEPTED = "ACCEPTED"
    CLOSED = "CLOSED"


# Valid lifecycle transitions for AI systems.
AI_SYSTEM_TRANSITIONS: dict[AISystemStatus, set[AISystemStatus]] = {
    AISystemStatus.DRAFT: {AISystemStatus.UNDER_REVIEW, AISystemStatus.RETIRED},
    AISystemStatus.UNDER_REVIEW: {
        AISystemStatus.APPROVED,
        AISystemStatus.DRAFT,
        AISystemStatus.RETIRED,
    },
    AISystemStatus.APPROVED: {
        AISystemStatus.SUSPENDED,
        AISystemStatus.STOPPED,
        AISystemStatus.UNDER_REVIEW,
        AISystemStatus.RETIRED,
    },
    AISystemStatus.SUSPENDED: {
        AISystemStatus.APPROVED,
        AISystemStatus.STOPPED,
        AISystemStatus.RETIRED,
    },
    AISystemStatus.STOPPED: {
        AISystemStatus.APPROVED,
        AISystemStatus.SUSPENDED,
        AISystemStatus.RETIRED,
    },
    AISystemStatus.RETIRED: {AISystemStatus.DRAFT},
}

AGENT_TRANSITIONS: dict[AgentStatus, set[AgentStatus]] = {
    AgentStatus.DRAFT: {AgentStatus.UNDER_REVIEW, AgentStatus.RETIRED},
    AgentStatus.UNDER_REVIEW: {
        AgentStatus.APPROVED,
        AgentStatus.DRAFT,
        AgentStatus.RETIRED,
    },
    AgentStatus.APPROVED: {
        AgentStatus.SUSPENDED,
        AgentStatus.UNDER_REVIEW,
        AgentStatus.RETIRED,
    },
    AgentStatus.SUSPENDED: {AgentStatus.APPROVED, AgentStatus.RETIRED},
    AgentStatus.RETIRED: {AgentStatus.DRAFT},
}

ASSESSMENT_TRANSITIONS: dict[AssessmentStatus, set[AssessmentStatus]] = {
    AssessmentStatus.DRAFT: {
        AssessmentStatus.SUBMITTED,
        AssessmentStatus.SUPERSEDED,
    },
    AssessmentStatus.SUBMITTED: {
        AssessmentStatus.APPROVED,
        AssessmentStatus.DRAFT,
        AssessmentStatus.SUPERSEDED,
    },
    AssessmentStatus.APPROVED: {AssessmentStatus.SUPERSEDED},
    AssessmentStatus.SUPERSEDED: set(),
}

AGENT_VERSION_TRANSITIONS: dict[AgentVersionStatus, set[AgentVersionStatus]] = {
    AgentVersionStatus.DRAFT: {
        AgentVersionStatus.UNDER_REVIEW,
        AgentVersionStatus.RETIRED,
    },
    AgentVersionStatus.UNDER_REVIEW: {
        AgentVersionStatus.APPROVED,
        AgentVersionStatus.DRAFT,
        AgentVersionStatus.REASSESSMENT_REQUIRED,
        AgentVersionStatus.RETIRED,
    },
    AgentVersionStatus.REASSESSMENT_REQUIRED: {
        AgentVersionStatus.UNDER_REVIEW,
        AgentVersionStatus.DRAFT,
        AgentVersionStatus.RETIRED,
    },
    AgentVersionStatus.APPROVED: {
        AgentVersionStatus.REASSESSMENT_REQUIRED,
        AgentVersionStatus.RETIRED,
    },
    AgentVersionStatus.RETIRED: {AgentVersionStatus.DRAFT},
}

GOVERNANCE_ELIGIBLE_SYSTEM_STATUSES: frozenset[AISystemStatus] = frozenset(
    {AISystemStatus.APPROVED}
)
GOVERNANCE_ELIGIBLE_AGENT_STATUSES: frozenset[AgentStatus] = frozenset(
    {AgentStatus.APPROVED}
)
GOVERNANCE_ELIGIBLE_VERSION_STATUSES: frozenset[AgentVersionStatus] = frozenset(
    {AgentVersionStatus.APPROVED}
)


def validate_score(value: int | None, field_name: str) -> None:
    if value is None:
        return
    if not SCORE_MIN <= value <= SCORE_MAX:
        raise ValueError(
            f"{field_name} must be between {SCORE_MIN} and {SCORE_MAX}, got {value}"
        )


def validate_lifecycle_transition(
    current: str,
    target: str,
    transitions: dict[StrEnum, set[StrEnum]],
    enum_cls: type[StrEnum],
) -> None:
    try:
        current_status = enum_cls(current)
        target_status = enum_cls(target)
    except ValueError as exc:
        raise ValueError(f"Invalid status value: {exc}") from exc

    allowed = transitions.get(current_status, set())
    if target_status not in allowed:
        raise ValueError(
            f"Invalid lifecycle transition from {current_status.value} "
            f"to {target_status.value}"
        )
