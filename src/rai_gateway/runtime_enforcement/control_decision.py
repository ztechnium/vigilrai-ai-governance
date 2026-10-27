"""Canonical control-decision types for Enforcement Receipt V2."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class DecisionPhase(StrEnum):
    AUTHORIZE = "AUTHORIZE"
    EXECUTE = "EXECUTE"
    RESUME = "RESUME"


class ControlType(StrEnum):
    AUTHORITY = "AUTHORITY"
    POLICY = "POLICY"
    BUDGET = "BUDGET"
    RISK = "RISK"
    APPROVAL = "APPROVAL"
    EMERGENCY = "EMERGENCY"
    REVALIDATION = "REVALIDATION"


class ControlDecisionStatus(StrEnum):
    EVALUATED = "EVALUATED"
    SKIPPED = "SKIPPED"
    UNAVAILABLE = "UNAVAILABLE"
    ERROR = "ERROR"


# Fields frozen after decision_finalized_at is set.
FINALIZED_IMMUTABLE_FIELDS: frozenset[str] = frozenset(
    {
        "authority_snapshot",
        "authority_digest",
        "effective_scope_digest",
        "action_digest",
        "enforcement_decision",
        "reason_code",
        "human_explanation",
        "policy_effect",
        "matched_rule_ids",
        "policy_decision",
        "approval_request_id",
        "approval_consumed",
        "decision_digest",
        "decision_phase",
        "control_summary",
        "policy_bundle_digest",
        "receipt_schema_version",
        "runtime_identity_id",
        "ai_system_id",
        "agent_id",
        "agent_version_id",
        "delegation_id",
        "resume_of_receipt_id",
        "decision_chain_id",
    }
)

EXECUTION_MUTABLE_FIELDS: frozenset[str] = frozenset(
    {
        "execution_attempted",
        "execution_status",
        "execution_source",
        "downstream_reference",
        "execution_report",
        "reported_at",
        "completed_at",
        "duration_ms",
        "revalidated_at",
        "revalidation_count",
    }
)


@dataclass
class ControlDecisionInput:
    control_type: str
    status: str = ControlDecisionStatus.EVALUATED.value
    effect: str | None = None
    reason_code: str | None = None
    human_explanation: str | None = None
    policy_domain: str | None = None
    phase: str | None = None
    source_type: str | None = None
    source_id: str | None = None
    source_version: str | None = None
    matched_rule_ids: list[str] = field(default_factory=list)
    control_snapshot: dict[str, Any] | None = None
    evidence_refs: list[str] = field(default_factory=list)
    latency_ms: int | None = None

    def to_row_fields(self, *, sequence: int) -> dict[str, Any]:
        return {
            "sequence": sequence,
            "phase": self.phase,
            "control_type": self.control_type,
            "policy_domain": self.policy_domain,
            "status": self.status,
            "effect": self.effect,
            "reason_code": self.reason_code,
            "human_explanation": self.human_explanation,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "source_version": self.source_version,
            "matched_rule_ids": self.matched_rule_ids or None,
            "control_snapshot": self.control_snapshot,
            "evidence_refs": self.evidence_refs or None,
            "latency_ms": self.latency_ms,
        }


def skipped_controls_after_deny(
    *,
    after_types: list[str],
    phase: str | None = None,
    reason_code: str = "SHORT_CIRCUITED",
) -> list[ControlDecisionInput]:
    return [
        ControlDecisionInput(
            control_type=control_type,
            status=ControlDecisionStatus.SKIPPED.value,
            effect=None,
            reason_code=reason_code,
            human_explanation="Skipped because an earlier control denied the action",
            phase=phase,
        )
        for control_type in after_types
    ]
