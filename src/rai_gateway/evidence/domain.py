"""Domain types for WP5 runtime trajectory evidence and audit graph."""

from __future__ import annotations

from enum import StrEnum


class TrajectoryStatus(StrEnum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    INCOMPLETE = "INCOMPLETE"
    FAILED = "FAILED"


class EvidenceEventType(StrEnum):
    SESSION_STARTED = "SESSION_STARTED"
    PROMPT_OBSERVED = "PROMPT_OBSERVED"
    MODEL_REQUEST_OBSERVED = "MODEL_REQUEST_OBSERVED"
    MODEL_RESPONSE_OBSERVED = "MODEL_RESPONSE_OBSERVED"
    TOOL_ATTEMPTED = "TOOL_ATTEMPTED"
    AUTHORITY_RESOLVED = "AUTHORITY_RESOLVED"
    POLICY_EVALUATED = "POLICY_EVALUATED"
    APPROVAL_REQUESTED = "APPROVAL_REQUESTED"
    APPROVAL_DECIDED = "APPROVAL_DECIDED"
    APPROVAL_CONSUMED = "APPROVAL_CONSUMED"
    ACTION_ALLOWED = "ACTION_ALLOWED"
    ACTION_DENIED = "ACTION_DENIED"
    TOOL_EXECUTION_STARTED = "TOOL_EXECUTION_STARTED"
    TOOL_EXECUTION_SUCCEEDED = "TOOL_EXECUTION_SUCCEEDED"
    TOOL_EXECUTION_FAILED = "TOOL_EXECUTION_FAILED"
    TOOL_RESULT_OBSERVED = "TOOL_RESULT_OBSERVED"
    AGENT_OUTPUT_OBSERVED = "AGENT_OUTPUT_OBSERVED"
    SESSION_COMPLETED = "SESSION_COMPLETED"
    EVIDENCE_MISSING = "EVIDENCE_MISSING"
    FINDING_CREATED = "FINDING_CREATED"
    DATA_SOURCE_ACCESSED = "DATA_SOURCE_ACCESSED"
    DATA_ACCESS_DENIED = "DATA_ACCESS_DENIED"
    CONTENT_EVALUATION_REQUESTED = "CONTENT_EVALUATION_REQUESTED"
    CONTENT_EVALUATION_RESULT = "CONTENT_EVALUATION_RESULT"
    BUDGET_WARNING = "BUDGET_WARNING"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    ANOMALY_DETECTED = "ANOMALY_DETECTED"
    MONITOR_STARTED = "MONITOR_STARTED"
    INTERVENTION_DECIDED = "INTERVENTION_DECIDED"
    RUNTIME_IDENTITY_SUSPENDED = "RUNTIME_IDENTITY_SUSPENDED"
    RUNTIME_IDENTITY_REACTIVATED = "RUNTIME_IDENTITY_REACTIVATED"


class EvidenceSourceType(StrEnum):
    RAI_AUTHORITATIVE = "RAI_AUTHORITATIVE"
    RAI_EXECUTED = "RAI_EXECUTED"
    CLIENT_REPORTED = "CLIENT_REPORTED"
    CLIENT_OBSERVED = "CLIENT_OBSERVED"
    EXTERNAL_PROVIDER = "EXTERNAL_PROVIDER"
    DERIVED = "DERIVED"


class AssuranceLevel(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class ContentHandlingMode(StrEnum):
    FULL = "FULL"
    REDACTED = "REDACTED"
    HASH_ONLY = "HASH_ONLY"
    METADATA_ONLY = "METADATA_ONLY"
    DO_NOT_STORE = "DO_NOT_STORE"


class ContentKind(StrEnum):
    """Independently configurable evidence content kinds."""

    PROMPT = "prompt"
    MODEL_REQUEST = "model_request"
    MODEL_RESPONSE = "model_response"
    AGENT_OUTPUT = "agent_output"
    TOOL_PARAMETERS = "tool_parameters"
    TOOL_RESULT = "tool_result"


class EvidenceArtifactType(StrEnum):
    USER_PROMPT = "USER_PROMPT"
    MODEL_REQUEST = "MODEL_REQUEST"
    MODEL_RESPONSE = "MODEL_RESPONSE"
    AGENT_OUTPUT = "AGENT_OUTPUT"
    TOOL_PARAMETERS = "TOOL_PARAMETERS"
    TOOL_RESULT = "TOOL_RESULT"


class RedactionStatus(StrEnum):
    NOT_REQUIRED = "NOT_REQUIRED"
    APPLIED = "APPLIED"
    PARTIAL = "PARTIAL"
    HASHED = "HASHED"
    OMITTED = "OMITTED"
    FAILED = "FAILED"


class EvidenceRelationType(StrEnum):
    INITIATED = "INITIATED"
    OBSERVED = "OBSERVED"
    CAUSED = "CAUSED"
    REQUESTED = "REQUESTED"
    EVALUATED_BY = "EVALUATED_BY"
    MATCHED_POLICY = "MATCHED_POLICY"
    REQUIRED_APPROVAL = "REQUIRED_APPROVAL"
    APPROVED_BY = "APPROVED_BY"
    REJECTED_BY = "REJECTED_BY"
    AUTHORIZED = "AUTHORIZED"
    DENIED_BY = "DENIED_BY"
    EXECUTED_AS = "EXECUTED_AS"
    PRODUCED = "PRODUCED"
    FOLLOWED_BY = "FOLLOWED_BY"
    RELATED_TO = "RELATED_TO"
    DERIVED_FROM = "DERIVED_FROM"


class EvidenceEntityType(StrEnum):
    TRAJECTORY = "TRAJECTORY"
    EVENT = "EVENT"
    ARTIFACT = "ARTIFACT"
    FINDING = "FINDING"
    RECEIPT = "RECEIPT"
    APPROVAL_REQUEST = "APPROVAL_REQUEST"
    APPROVAL_DECISION = "APPROVAL_DECISION"
    POLICY_RULE = "POLICY_RULE"
    RUNTIME_IDENTITY = "RUNTIME_IDENTITY"
    TOOL = "TOOL"
    DATA_SOURCE = "DATA_SOURCE"
    EXECUTION = "EXECUTION"


class EvidenceFindingType(StrEnum):
    EVIDENCE_GAP = "EVIDENCE_GAP"
    MISSING_EXECUTION_RESULT = "MISSING_EXECUTION_RESULT"
    UNVERIFIED_ENFORCEMENT = "UNVERIFIED_ENFORCEMENT"
    REPEATED_DENIED_ACTION = "REPEATED_DENIED_ACTION"
    AUTHORITY_DENIAL = "AUTHORITY_DENIAL"
    POLICY_DENIAL = "POLICY_DENIAL"
    APPROVAL_MISMATCH = "APPROVAL_MISMATCH"
    OBSERVED_MODEL_MISMATCH = "OBSERVED_MODEL_MISMATCH"
    CONTENT_CAPTURE_FAILED = "CONTENT_CAPTURE_FAILED"
    CONTENT_REDACTION_FAILED = "CONTENT_REDACTION_FAILED"


class FindingSeverity(StrEnum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class FindingStatus(StrEnum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"
    DISMISSED = "DISMISSED"


class CoverageState(StrEnum):
    COMPLETE = "COMPLETE"
    MISSING = "MISSING"
    NOT_REQUIRED = "NOT_REQUIRED"
    NOT_AVAILABLE = "NOT_AVAILABLE"  # legacy; prefer NOT_OBSERVED / policy modes
    OBSERVED = "OBSERVED"  # legacy synonym of CAPTURED when mode is FULL
    CAPTURED = "CAPTURED"
    REDACTED = "REDACTED"
    HASH_ONLY = "HASH_ONLY"
    METADATA_ONLY = "METADATA_ONLY"
    DO_NOT_STORE = "DO_NOT_STORE"
    NOT_OBSERVED = "NOT_OBSERVED"
    INTEGRATION_UNSUPPORTED = "INTEGRATION_UNSUPPORTED"
    CAPTURE_FAILED = "CAPTURE_FAILED"
    NOT_VERIFIED = "NOT_VERIFIED"
    UNKNOWN = "UNKNOWN"


# Fallback when no organization/demo defaults and no overrides are configured.
DEFAULT_CONTENT_HANDLING = ContentHandlingMode.METADATA_ONLY

# Payload keys treated as inspectable content (omitted under METADATA_ONLY / HASH_ONLY).
CONTENT_PAYLOAD_FIELDS = frozenset(
    {
        "prompt",
        "output",
        "content",
        "text",
        "parameters",
        "result",
        "result_payload",
        "raw",
    }
)

_EVENT_TO_CONTENT_KIND: dict[str, ContentKind] = {
    EvidenceEventType.PROMPT_OBSERVED.value: ContentKind.PROMPT,
    EvidenceEventType.MODEL_REQUEST_OBSERVED.value: ContentKind.MODEL_REQUEST,
    EvidenceEventType.MODEL_RESPONSE_OBSERVED.value: ContentKind.MODEL_RESPONSE,
    EvidenceEventType.AGENT_OUTPUT_OBSERVED.value: ContentKind.AGENT_OUTPUT,
    EvidenceEventType.TOOL_ATTEMPTED.value: ContentKind.TOOL_PARAMETERS,
    EvidenceEventType.TOOL_RESULT_OBSERVED.value: ContentKind.TOOL_RESULT,
    EvidenceEventType.TOOL_EXECUTION_SUCCEEDED.value: ContentKind.TOOL_RESULT,
    EvidenceEventType.TOOL_EXECUTION_FAILED.value: ContentKind.TOOL_RESULT,
}

_EVENT_TO_ARTIFACT_TYPE: dict[str, EvidenceArtifactType] = {
    EvidenceEventType.PROMPT_OBSERVED.value: EvidenceArtifactType.USER_PROMPT,
    EvidenceEventType.MODEL_REQUEST_OBSERVED.value: EvidenceArtifactType.MODEL_REQUEST,
    EvidenceEventType.MODEL_RESPONSE_OBSERVED.value: EvidenceArtifactType.MODEL_RESPONSE,
    EvidenceEventType.AGENT_OUTPUT_OBSERVED.value: EvidenceArtifactType.AGENT_OUTPUT,
    EvidenceEventType.TOOL_ATTEMPTED.value: EvidenceArtifactType.TOOL_PARAMETERS,
    EvidenceEventType.TOOL_RESULT_OBSERVED.value: EvidenceArtifactType.TOOL_RESULT,
}


def content_kind_for_event(event_type: str | EvidenceEventType) -> ContentKind | None:
    value = (
        event_type.value
        if isinstance(event_type, EvidenceEventType)
        else str(event_type)
    )
    return _EVENT_TO_CONTENT_KIND.get(value)


def artifact_type_for_event(
    event_type: str | EvidenceEventType,
) -> EvidenceArtifactType | None:
    value = (
        event_type.value
        if isinstance(event_type, EvidenceEventType)
        else str(event_type)
    )
    return _EVENT_TO_ARTIFACT_TYPE.get(value)


def assurance_for_source(source_type: str | EvidenceSourceType) -> AssuranceLevel:
    """Derive assurance level from evidence source type."""
    value = (
        source_type.value
        if isinstance(source_type, EvidenceSourceType)
        else str(source_type)
    )
    mapping = {
        EvidenceSourceType.RAI_AUTHORITATIVE.value: AssuranceLevel.HIGH,
        EvidenceSourceType.RAI_EXECUTED.value: AssuranceLevel.HIGH,
        EvidenceSourceType.EXTERNAL_PROVIDER.value: AssuranceLevel.MEDIUM,
        EvidenceSourceType.CLIENT_REPORTED.value: AssuranceLevel.LOW,
        EvidenceSourceType.CLIENT_OBSERVED.value: AssuranceLevel.LOW,
        EvidenceSourceType.DERIVED.value: AssuranceLevel.MEDIUM,
    }
    return mapping.get(value, AssuranceLevel.UNKNOWN)


def assurance_for_deployment(
    *,
    source_type: str | EvidenceSourceType,
    deployment_control: str | None = None,
    verification_status: str | None = None,
) -> AssuranceLevel:
    """Refine assurance using WP4 deployment/verification metadata when present."""
    value = (
        source_type.value
        if isinstance(source_type, EvidenceSourceType)
        else str(source_type)
    )
    base = assurance_for_source(value)
    if base == AssuranceLevel.HIGH:
        return base

    # Client-observed metadata never rises above LOW — observation ≠ verification.
    if value == EvidenceSourceType.CLIENT_OBSERVED.value:
        return AssuranceLevel.LOW

    if value == EvidenceSourceType.CLIENT_REPORTED.value:
        if deployment_control == "LOCAL_HOOK":
            return AssuranceLevel.LOW
        if verification_status == "VERIFIED" and deployment_control in {
            "ENTERPRISE_MANAGED_HOOK",
            "TEAM_MANAGED_HOOK",
            "MDM_MANAGED",
        }:
            return AssuranceLevel.MEDIUM
        if deployment_control in {
            "ENTERPRISE_MANAGED_HOOK",
            "TEAM_MANAGED_HOOK",
            "MDM_MANAGED",
        }:
            return AssuranceLevel.MEDIUM
        return AssuranceLevel.LOW

    if verification_status == "VERIFIED" and deployment_control in {
        "ENTERPRISE_MANAGED_HOOK",
        "TEAM_MANAGED_HOOK",
        "MDM_MANAGED",
        "PROXY_CONTROLLED",
    }:
        return AssuranceLevel.MEDIUM

    return base
