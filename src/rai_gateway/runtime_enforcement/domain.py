"""Domain types for WP4 mandatory runtime enforcement gateway."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import UUID


class EnforcementMode(StrEnum):
    PROXY_ENFORCED = "PROXY_ENFORCED"
    HOOK_ENFORCED = "HOOK_ENFORCED"
    EXTERNAL_PROVIDER_ENFORCED = "EXTERNAL_PROVIDER_ENFORCED"
    OBSERVE_ONLY = "OBSERVE_ONLY"


class EnforcementDecisionType(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    MONITOR = "MONITOR"


class ExecutionStatus(StrEnum):
    NOT_ATTEMPTED = "NOT_ATTEMPTED"
    PENDING_CLIENT_REPORT = "PENDING_CLIENT_REPORT"
    STARTED = "STARTED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    # Legacy alias kept for reading older receipts / tests mid-migration.
    IN_PROGRESS = "IN_PROGRESS"


class ExecutionSource(StrEnum):
    RAI_EXECUTED = "RAI_EXECUTED"
    CLIENT_REPORTED = "CLIENT_REPORTED"


class DeploymentControl(StrEnum):
    LOCAL_HOOK = "LOCAL_HOOK"
    TEAM_MANAGED_HOOK = "TEAM_MANAGED_HOOK"
    ENTERPRISE_MANAGED_HOOK = "ENTERPRISE_MANAGED_HOOK"
    MDM_MANAGED = "MDM_MANAGED"
    PROXY_CONTROLLED = "PROXY_CONTROLLED"
    # Alias for plan wording — same assurance class as PROXY_CONTROLLED.
    GATEWAY_MEDIATED = "GATEWAY_MEDIATED"
    EXTERNAL_MANAGED = "EXTERNAL_MANAGED"


MANAGED_HOOK_CONTROLS = frozenset(
    {
        DeploymentControl.TEAM_MANAGED_HOOK.value,
        DeploymentControl.ENTERPRISE_MANAGED_HOOK.value,
        DeploymentControl.MDM_MANAGED.value,
        DeploymentControl.GATEWAY_MEDIATED.value,
        DeploymentControl.PROXY_CONTROLLED.value,
    }
)


class VerificationStatus(StrEnum):
    DECLARED = "DECLARED"
    VERIFIED = "VERIFIED"
    UNKNOWN = "UNKNOWN"


class ContentCaptureMode(StrEnum):
    """Future content-handling modes — WP4 must not store unsafe raw content."""

    FULL = "FULL"
    REDACTED = "REDACTED"
    HASH_ONLY = "HASH_ONLY"
    METADATA_ONLY = "METADATA_ONLY"
    DO_NOT_STORE = "DO_NOT_STORE"


class RuntimeEnforcementReasonCode(StrEnum):
    RUNTIME_AUTHENTICATION_FAILED = "RUNTIME_AUTHENTICATION_FAILED"
    RUNTIME_IDENTITY_INELIGIBLE = "RUNTIME_IDENTITY_INELIGIBLE"
    AUTHORITY_SCOPE_EXCEEDED = "AUTHORITY_SCOPE_EXCEEDED"
    RESOURCE_NOT_REGISTERED = "RESOURCE_NOT_REGISTERED"
    RESOURCE_RELATIONSHIP_INVALID = "RESOURCE_RELATIONSHIP_INVALID"
    POLICY_DENIED = "POLICY_DENIED"
    POLICY_EVALUATION_FAILED = "POLICY_EVALUATION_FAILED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    APPROVAL_PENDING = "APPROVAL_PENDING"
    APPROVAL_EXPIRED = "APPROVAL_EXPIRED"
    APPROVAL_ALREADY_CONSUMED = "APPROVAL_ALREADY_CONSUMED"
    APPROVAL_ACTION_MISMATCH = "APPROVAL_ACTION_MISMATCH"
    APPROVAL_NOT_FOUND = "APPROVAL_NOT_FOUND"
    APPROVAL_REJECTED = "APPROVAL_REJECTED"
    APPROVAL_CANCELLED = "APPROVAL_CANCELLED"
    DOWNSTREAM_CONFIGURATION_INVALID = "DOWNSTREAM_CONFIGURATION_INVALID"
    DOWNSTREAM_UNAVAILABLE = "DOWNSTREAM_UNAVAILABLE"
    RUNTIME_STATE_CHANGED = "RUNTIME_STATE_CHANGED"
    DUPLICATE_RUNTIME_ACTION = "DUPLICATE_RUNTIME_ACTION"
    ADAPTER_NOT_AVAILABLE = "ADAPTER_NOT_AVAILABLE"
    AGENT_INELIGIBLE = "AGENT_INELIGIBLE"
    EXECUTION_REPORT_INVALID = "EXECUTION_REPORT_INVALID"
    EXECUTION_REPORT_UNKNOWN_RECEIPT = "EXECUTION_REPORT_UNKNOWN_RECEIPT"
    EXECUTION_REPORT_IDENTITY_MISMATCH = "EXECUTION_REPORT_IDENTITY_MISMATCH"
    EXECUTION_REPORT_DENIED_RECEIPT = "EXECUTION_REPORT_DENIED_RECEIPT"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    BUDGET_MEASUREMENT_UNAVAILABLE = "BUDGET_MEASUREMENT_UNAVAILABLE"
    RISK_INTERVENTION_DENIED = "RISK_INTERVENTION_DENIED"
    RISK_CONTROL_UNAVAILABLE = "RISK_CONTROL_UNAVAILABLE"
    APPROVAL_CONTROL_UNAVAILABLE = "APPROVAL_CONTROL_UNAVAILABLE"
    EMERGENCY_STOPPED = "EMERGENCY_STOPPED"


POLICY_EFFECT_PRECEDENCE = "DENY > REQUIRE_APPROVAL > MONITOR > ALLOW"


def normalize_execution_status(status: str | None) -> str | None:
    """Map legacy IN_PROGRESS to STARTED for API responses."""
    if status == ExecutionStatus.IN_PROGRESS.value:
        return ExecutionStatus.STARTED.value
    return status


@dataclass
class RuntimeActionTarget:
    type: str
    id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "id": self.id}


@dataclass
class RuntimeActionRequest:
    """Provider-neutral runtime action request from an authenticated client."""

    integration_type: str
    integration_id: UUID | None
    tool_id: UUID | None
    target: RuntimeActionTarget | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    environment: str | None = None
    approval_request_id: UUID | None = None
    correlation_id: str | None = None
    trace_id: str | None = None
    idempotency_key: str | None = None
    delegation_id: UUID | None = None
    client_context: dict[str, Any] | None = None


@dataclass
class DownstreamExecutionResult:
    success: bool
    downstream_reference: str | None = None
    result_payload: dict[str, Any] | None = None
    error_message: str | None = None


@dataclass
class ClientExecutionReport:
    """Provider-neutral post-execution report for hook mode."""

    enforcement_receipt_id: UUID | None = None
    correlation_id: str | None = None
    client_type: str | None = None
    hook_event: str | None = None
    status: str = ExecutionStatus.SUCCEEDED.value
    duration_ms: int | None = None
    safe_result_metadata: dict[str, Any] = field(default_factory=dict)
    client_event_id: str | None = None


@dataclass
class EnforcementResult:
    allowed: bool
    effect: str
    reason_code: str | None
    human_explanation: str
    runtime_identity_id: UUID | None = None
    agent_version_id: UUID | None = None
    action_digest: str | None = None
    policy_decision: dict[str, Any] | None = None
    approval_request_id: UUID | None = None
    approval: dict[str, Any] | None = None
    approval_consumed: bool = False
    monitor: bool = False
    monitoring_instruction: str | None = None
    execution_attempted: bool = False
    execution_status: str = ExecutionStatus.NOT_ATTEMPTED.value
    execution_source: str | None = None
    correlation_id: str | None = None
    trace_id: str | None = None
    receipt_id: UUID | None = None
    downstream_reference: str | None = None
    enforcement_mode: str = EnforcementMode.PROXY_ENFORCED.value
    deployment_control: str | None = None
    verification_status: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "effect": self.effect,
            "reason_code": self.reason_code,
            "human_explanation": self.human_explanation,
            "runtime_identity_id": str(self.runtime_identity_id)
            if self.runtime_identity_id
            else None,
            "agent_version_id": str(self.agent_version_id)
            if self.agent_version_id
            else None,
            "action_digest": self.action_digest,
            "policy_decision": self.policy_decision,
            "approval_request_id": str(self.approval_request_id)
            if self.approval_request_id
            else None,
            "approval": self.approval,
            "approval_consumed": self.approval_consumed,
            "monitor": self.monitor,
            "monitoring_instruction": self.monitoring_instruction,
            "execution_attempted": self.execution_attempted,
            "execution_status": normalize_execution_status(self.execution_status),
            "execution_source": self.execution_source,
            "correlation_id": self.correlation_id,
            "trace_id": self.trace_id,
            "receipt_id": str(self.receipt_id) if self.receipt_id else None,
            "downstream_reference": self.downstream_reference,
            "enforcement_mode": self.enforcement_mode,
            "deployment_control": self.deployment_control,
            "verification_status": self.verification_status,
        }
