"""Domain types for Phase 2 data-access governance."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import UUID


class DataAccessMode(StrEnum):
    READ = "READ"
    WRITE = "WRITE"
    DELETE = "DELETE"
    EXPORT = "EXPORT"


class DataAccessDecisionType(StrEnum):
    ALLOW = "ALLOW"
    MASK = "MASK"
    DENY = "DENY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    FILTER = "FILTER"


class DataSensitivity(StrEnum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    RESTRICTED = "RESTRICTED"
    PII = "PII"
    SENSITIVE_PII = "SENSITIVE_PII"


@dataclass
class DataAccessRequest:
    """Request to access structured data before it reaches the model/agent."""

    runtime_identity_id: UUID
    agent_version_id: UUID
    principal: str | None
    data_source_id: UUID | None
    resource: str  # table / index / collection
    fields: list[str] = field(default_factory=list)
    row_filter: dict[str, Any] = field(default_factory=dict)
    purpose: str | None = None
    access_mode: str = DataAccessMode.READ.value
    tool_id: UUID | None = None
    target: str | None = None
    ai_system_id: UUID | None = None
    agent_id: UUID | None = None
    payload: dict[str, Any] | list[Any] | None = None  # sample rows to transform


@dataclass
class FieldTransform:
    field: str
    action: str  # ALLOW | MASK | DROP | HASH
    mask_style: str = "REDACT"  # REDACT | HASH | LAST4


@dataclass
class DataAccessDecision:
    decision: DataAccessDecisionType
    reason_code: str
    human_explanation: str
    allowed_fields: list[str] = field(default_factory=list)
    denied_fields: list[str] = field(default_factory=list)
    masked_fields: list[str] = field(default_factory=list)
    transforms: list[FieldTransform] = field(default_factory=list)
    row_filter: dict[str, Any] = field(default_factory=dict)
    transformed_payload: dict[str, Any] | list[Any] | None = None
    policy_rule_ids: list[str] = field(default_factory=list)
    receipt_id: UUID | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "reason_code": self.reason_code,
            "human_explanation": self.human_explanation,
            "allowed_fields": self.allowed_fields,
            "denied_fields": self.denied_fields,
            "masked_fields": self.masked_fields,
            "transforms": [
                {
                    "field": t.field,
                    "action": t.action,
                    "mask_style": t.mask_style,
                }
                for t in self.transforms
            ],
            "row_filter": self.row_filter,
            "policy_rule_ids": self.policy_rule_ids,
            "receipt_id": str(self.receipt_id) if self.receipt_id else None,
        }


# Default field sensitivity catalog (can be overridden by DataAccessPolicy rules).
DEFAULT_FIELD_SENSITIVITY: dict[str, str] = {
    "national_id": DataSensitivity.SENSITIVE_PII.value,
    "ssn": DataSensitivity.SENSITIVE_PII.value,
    "passport_number": DataSensitivity.SENSITIVE_PII.value,
    "email": DataSensitivity.PII.value,
    "phone": DataSensitivity.PII.value,
    "full_name": DataSensitivity.PII.value,
    "date_of_birth": DataSensitivity.PII.value,
    "iban": DataSensitivity.RESTRICTED.value,
    "card_number": DataSensitivity.RESTRICTED.value,
}
# Purposes that may receive unmasked PII (narrow allow-list).
PII_ALLOWED_PURPOSES: frozenset[str] = frozenset(
    {
        "identity_verification",
        "kyc",
        "legal_hold",
        "security_investigation",
    }
)
