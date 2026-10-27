"""WP10 public SDK contract domain types."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Final
from uuid import UUID

SDK_API_VERSION: Final[str] = "v1"
SDK_COMPATIBILITY_RANGE: Final[str] = ">=1.0.0,<2.0.0"
SDK_PROTOCOL_VERSION: Final[int] = 1


class IntegrationType(StrEnum):
    SDK = "SDK"
    API_PROXY = "API_PROXY"
    CLIENT_HOOK = "CLIENT_HOOK"
    MCP_GATEWAY = "MCP_GATEWAY"
    VENDOR_CONNECTOR = "VENDOR_CONNECTOR"
    CUSTOM = "CUSTOM"


class IntegrationStatus(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    REVOKED = "REVOKED"


class EnforcementMode(StrEnum):
    PROXY_ENFORCED = "PROXY_ENFORCED"
    HOOK_ENFORCED = "HOOK_ENFORCED"
    EXTERNAL_PROVIDER_ENFORCED = "EXTERNAL_PROVIDER_ENFORCED"
    OBSERVE_ONLY = "OBSERVE_ONLY"


class AuthMethod(StrEnum):
    API_KEY = "API_KEY"
    OIDC = "OIDC"
    MTLS = "MTLS"


class AdapterCertification(StrEnum):
    EXPERIMENTAL = "EXPERIMENTAL"
    SUPPORTED = "SUPPORTED"
    CERTIFIED = "CERTIFIED"
    DEPRECATED = "DEPRECATED"


class SdkDecision(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    MONITOR = "MONITOR"
    UNAVAILABLE = "UNAVAILABLE"


class SdkErrorCode(StrEnum):
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    TENANT_SUSPENDED = "TENANT_SUSPENDED"
    RUNTIME_IDENTITY_INACTIVE = "RUNTIME_IDENTITY_INACTIVE"
    AGENT_VERSION_INELIGIBLE = "AGENT_VERSION_INELIGIBLE"
    RESOURCE_OUT_OF_SCOPE = "RESOURCE_OUT_OF_SCOPE"
    POLICY_DENIED = "POLICY_DENIED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    RUNTIME_SUSPENDED = "RUNTIME_SUSPENDED"
    CONTENT_DENIED = "CONTENT_DENIED"
    DATA_ACCESS_DENIED = "DATA_ACCESS_DENIED"
    ASSURANCE_INVALID = "ASSURANCE_INVALID"
    RATE_LIMITED = "RATE_LIMITED"
    RAI_UNAVAILABLE = "RAI_UNAVAILABLE"
    INVALID_REQUEST = "INVALID_REQUEST"
    SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
    INTEGRATION_NOT_FOUND = "INTEGRATION_NOT_FOUND"
    DECISION_NOT_FOUND = "DECISION_NOT_FOUND"


class SessionStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ENDED = "ENDED"


class WebhookEventType(StrEnum):
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_APPROVED = "approval.approved"
    APPROVAL_REJECTED = "approval.rejected"
    APPROVAL_CANCELLED = "approval.cancelled"
    APPROVAL_EXPIRED = "approval.expired"
    APPROVAL_CONSUMED = "approval.consumed"
    # Legacy alias — treat as approved/rejected bucket for older subscriptions
    APPROVAL_DECIDED = "approval.decided"
    RUNTIME_SUSPENDED = "runtime.suspended"
    RUNTIME_REACTIVATED = "runtime.reactivated"
    RISK_CRITICAL = "risk.critical"
    INCIDENT_CREATED = "incident.created"
    ASSURANCE_EXPIRING = "assurance.expiring"
    ASSURANCE_INVALIDATED = "assurance.invalidated"
    EVALUATION_COMPLETED = "evaluation.completed"


class WebhookDeliveryStatus(StrEnum):
    PENDING = "PENDING"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    DEAD_LETTER = "DEAD_LETTER"


class BackgroundJobStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    DEAD_LETTER = "DEAD_LETTER"


class BackgroundJobType(StrEnum):
    EVALUATION_RUN = "EVALUATION_RUN"
    EVIDENCE_EXPORT = "EVIDENCE_EXPORT"
    PORTFOLIO_REPORT = "PORTFOLIO_REPORT"
    RETENTION_PURGE = "RETENTION_PURGE"
    PERIODIC_REVIEW = "PERIODIC_REVIEW"
    WEBHOOK_DELIVERY = "WEBHOOK_DELIVERY"
    PROJECTION_REFRESH = "PROJECTION_REFRESH"


DEFAULT_CAPABILITY_MATRIX: dict[str, bool] = {
    "input_observation": True,
    "output_observation": True,
    "tool_authorization": True,
    "execution_reporting": True,
    "model_observation": True,
    "principal_observation": True,
    "approval_continuation": True,
    "heartbeat": True,
    "data_access_authorize": True,
    "managed_deployment": False,
}


REASON_CODE_MAP: dict[str, SdkErrorCode] = {
    "RUNTIME_AUTHENTICATION_FAILED": SdkErrorCode.AUTHENTICATION_FAILED,
    "RUNTIME_IDENTITY_INELIGIBLE": SdkErrorCode.RUNTIME_IDENTITY_INACTIVE,
    "AUTHORITY_SCOPE_EXCEEDED": SdkErrorCode.RESOURCE_OUT_OF_SCOPE,
    "RESOURCE_NOT_REGISTERED": SdkErrorCode.RESOURCE_OUT_OF_SCOPE,
    "POLICY_DENIED": SdkErrorCode.POLICY_DENIED,
    "APPROVAL_REQUIRED": SdkErrorCode.APPROVAL_REQUIRED,
    "APPROVAL_PENDING": SdkErrorCode.APPROVAL_REQUIRED,
    "BUDGET_EXCEEDED": SdkErrorCode.BUDGET_EXCEEDED,
    "RISK_INTERVENTION_DENIED": SdkErrorCode.RUNTIME_SUSPENDED,
    "AGENT_INELIGIBLE": SdkErrorCode.AGENT_VERSION_INELIGIBLE,
    "DATA_FIELD_DENIED": SdkErrorCode.DATA_ACCESS_DENIED,
    "DATA_ACCESS_APPROVAL_REQUIRED": SdkErrorCode.APPROVAL_REQUIRED,
}


@dataclass
class PublicDecision:
    """Stable external decision schema independent of WP internals."""

    decision: str
    decision_id: str | None = None
    reason_code: str | None = None
    human_message: str | None = None
    machine_reason: str | None = None
    approval_request_id: str | None = None
    approval: dict[str, Any] | None = None
    enforcement_receipt_id: str | None = None
    constraints: dict[str, Any] = field(default_factory=dict)
    evidence_reference: str | None = None
    retryable: bool = False
    expires_at: str | None = None
    policy_references: list[str] = field(default_factory=list)
    risk_references: list[str] = field(default_factory=list)

    @property
    def allowed(self) -> bool:
        return self.decision == SdkDecision.ALLOW.value

    def to_dict(self) -> dict[str, Any]:
        approval = self.approval
        if approval is None and self.approval_request_id:
            approval = {"approval_request_id": self.approval_request_id}
        return {
            "decision": self.decision,
            "decision_id": self.decision_id,
            "reason_code": self.reason_code,
            "human_message": self.human_message,
            "machine_reason": self.machine_reason,
            "approval": approval,
            "approval_request_id": self.approval_request_id,
            "enforcement_receipt_id": self.enforcement_receipt_id,
            "constraints": self.constraints,
            "evidence_reference": self.evidence_reference,
            "retryable": self.retryable,
            "expires_at": self.expires_at,
            "policy_references": self.policy_references,
            "risk_references": self.risk_references,
            "allowed": self.allowed,
        }


@dataclass
class SessionContext:
    integration_id: UUID
    runtime_identity_id: UUID
    external_session_id: str | None = None
    external_conversation_id: str | None = None
    principal: str | None = None
    channel: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
