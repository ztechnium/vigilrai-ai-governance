"""Helpers to persist Canonical Enforcement Receipt V2 control stacks."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from rai_gateway.identity.authority_snapshot import digest_payload
from rai_gateway.identity.resolver import RuntimeAuthorityContext
from rai_gateway.models.runtime_enforcement import RuntimeEnforcementReceipt
from rai_gateway.runtime_enforcement.control_decision import (
    ControlDecisionInput,
    ControlDecisionStatus,
    ControlType,
    DecisionPhase,
    skipped_controls_after_deny,
)
from rai_gateway.runtime_enforcement.domain import RuntimeEnforcementReasonCode
from rai_gateway.runtime_enforcement.repository import RuntimeEnforcementRepository

AUTHORITY_DENY_SKIP_REST = [
    ControlType.POLICY.value,
    ControlType.BUDGET.value,
    ControlType.RISK.value,
    ControlType.APPROVAL.value,
]


def build_authority_fields(authority: RuntimeAuthorityContext) -> dict[str, Any]:
    snapshot = authority.authority_snapshot
    digest = authority.authority_digest
    scope_digest = None
    if authority.effective_scope is not None:
        scope_digest = digest_payload(authority.effective_scope.to_dict())
    return {
        "authority_snapshot": snapshot,
        "authority_digest": digest,
        "effective_scope_digest": scope_digest,
        "receipt_schema_version": 2,
    }


def classify_deny_controls(
    *,
    reason_code: str,
    policy_decision: dict[str, Any] | None,
    phase: str = DecisionPhase.EXECUTE.value,
) -> list[ControlDecisionInput]:
    """Map a deny outcome into ordered control children with SKIPPED trailing controls."""
    controls: list[ControlDecisionInput] = []

    authority_reasons = {
        RuntimeEnforcementReasonCode.RUNTIME_AUTHENTICATION_FAILED.value,
        RuntimeEnforcementReasonCode.RUNTIME_IDENTITY_INELIGIBLE.value,
        RuntimeEnforcementReasonCode.AUTHORITY_SCOPE_EXCEEDED.value,
        "AUTHORITY_SCOPE_EXCEEDED",
        "IDENTITY_SUSPENDED",
        "IDENTITY_REVOKED",
        "IDENTITY_EXPIRED",
        "DELEGATION_REVOKED",
        "DELEGATION_EXPIRED",
        "DELEGATION_CYCLE",
        "DELEGATION_DEPTH_EXCEEDED",
        "BROKEN_DELEGATION_CHAIN",
        "AGENT_INELIGIBLE",
        "AGENT_VERSION_INELIGIBLE",
    }

    if reason_code in authority_reasons or reason_code.startswith("IDENTITY_"):
        controls.append(
            ControlDecisionInput(
                control_type=ControlType.AUTHORITY.value,
                status=ControlDecisionStatus.EVALUATED.value,
                effect="DENY",
                reason_code=reason_code,
                phase=phase,
            )
        )
        controls.extend(
            skipped_controls_after_deny(
                after_types=AUTHORITY_DENY_SKIP_REST, phase=phase
            )
        )
        return controls

    if reason_code == RuntimeEnforcementReasonCode.RUNTIME_STATE_CHANGED.value:
        controls.append(
            ControlDecisionInput(
                control_type=ControlType.REVALIDATION.value,
                status=ControlDecisionStatus.EVALUATED.value,
                effect="DENY",
                reason_code=reason_code,
                phase=phase,
            )
        )
        return controls

    if reason_code in {
        RuntimeEnforcementReasonCode.EMERGENCY_STOPPED.value,
        RuntimeEnforcementReasonCode.RISK_INTERVENTION_DENIED.value,
    }:
        controls.append(
            ControlDecisionInput(
                control_type=ControlType.AUTHORITY.value,
                status=ControlDecisionStatus.EVALUATED.value,
                effect="ALLOW",
                phase=phase,
            )
        )
        controls.append(
            ControlDecisionInput(
                control_type=ControlType.POLICY.value,
                policy_domain="ACTION",
                status=ControlDecisionStatus.EVALUATED.value,
                effect=(policy_decision or {}).get("effect") or "ALLOW",
                matched_rule_ids=(policy_decision or {}).get("matched_rule_ids") or [],
                control_snapshot=policy_decision,
                phase=phase,
            )
        )
        controls.append(
            ControlDecisionInput(
                control_type=ControlType.EMERGENCY.value
                if reason_code == RuntimeEnforcementReasonCode.EMERGENCY_STOPPED.value
                else ControlType.RISK.value,
                policy_domain="RISK",
                status=ControlDecisionStatus.EVALUATED.value,
                effect="DENY",
                reason_code=reason_code,
                phase=phase,
            )
        )
        controls.extend(
            skipped_controls_after_deny(
                after_types=[ControlType.BUDGET.value, ControlType.APPROVAL.value],
                phase=phase,
            )
        )
        return controls

    if reason_code in {
        RuntimeEnforcementReasonCode.BUDGET_EXCEEDED.value,
        RuntimeEnforcementReasonCode.BUDGET_MEASUREMENT_UNAVAILABLE.value,
    }:
        controls.append(
            ControlDecisionInput(
                control_type=ControlType.AUTHORITY.value,
                status=ControlDecisionStatus.EVALUATED.value,
                effect="ALLOW",
                phase=phase,
            )
        )
        controls.append(
            ControlDecisionInput(
                control_type=ControlType.POLICY.value,
                policy_domain="ACTION",
                status=ControlDecisionStatus.EVALUATED.value,
                effect=(policy_decision or {}).get("effect") or "ALLOW",
                matched_rule_ids=(policy_decision or {}).get("matched_rule_ids") or [],
                control_snapshot=policy_decision,
                phase=phase,
            )
        )
        controls.append(
            ControlDecisionInput(
                control_type=ControlType.BUDGET.value,
                policy_domain="BUDGET",
                status=ControlDecisionStatus.EVALUATED.value,
                effect="DENY",
                reason_code=reason_code,
                phase=phase,
            )
        )
        controls.extend(
            skipped_controls_after_deny(
                after_types=[ControlType.APPROVAL.value],
                phase=phase,
            )
        )
        return controls

    # Default: policy (or approval) deny after authority allow
    controls.append(
        ControlDecisionInput(
            control_type=ControlType.AUTHORITY.value,
            status=ControlDecisionStatus.EVALUATED.value,
            effect="ALLOW",
            phase=phase,
        )
    )
    controls.append(
        ControlDecisionInput(
            control_type=ControlType.POLICY.value,
            policy_domain="ACTION",
            status=ControlDecisionStatus.EVALUATED.value,
            effect="DENY",
            reason_code=reason_code,
            matched_rule_ids=(policy_decision or {}).get("matched_rule_ids") or [],
            control_snapshot=policy_decision,
            phase=phase,
        )
    )
    controls.extend(
        skipped_controls_after_deny(
            after_types=[
                ControlType.BUDGET.value,
                ControlType.RISK.value,
                ControlType.APPROVAL.value,
            ],
            phase=phase,
        )
    )
    return controls


def build_allow_controls(
    *,
    policy_decision: dict[str, Any] | None,
    phase: str = DecisionPhase.EXECUTE.value,
    include_approval: bool = False,
    approval_consumed: bool = False,
) -> list[ControlDecisionInput]:
    effect = (policy_decision or {}).get("effect") or "ALLOW"
    controls = [
        ControlDecisionInput(
            control_type=ControlType.AUTHORITY.value,
            status=ControlDecisionStatus.EVALUATED.value,
            effect="ALLOW",
            phase=phase,
        ),
        ControlDecisionInput(
            control_type=ControlType.POLICY.value,
            policy_domain="ACTION",
            status=ControlDecisionStatus.EVALUATED.value,
            effect=effect,
            matched_rule_ids=(policy_decision or {}).get("matched_rule_ids") or [],
            control_snapshot=policy_decision,
            phase=phase,
        ),
        ControlDecisionInput(
            control_type=ControlType.BUDGET.value,
            policy_domain="BUDGET",
            status=ControlDecisionStatus.EVALUATED.value,
            effect="ALLOW",
            phase=phase,
        ),
        ControlDecisionInput(
            control_type=ControlType.RISK.value,
            policy_domain="RISK",
            status=ControlDecisionStatus.EVALUATED.value,
            effect="ALLOW",
            phase=phase,
        ),
    ]
    if include_approval:
        controls.append(
            ControlDecisionInput(
                control_type=ControlType.APPROVAL.value,
                status=ControlDecisionStatus.EVALUATED.value,
                effect="ALLOW" if approval_consumed else "REQUIRE_APPROVAL",
                phase=phase,
            )
        )
    return controls


def persist_canonical_receipt(
    repo: RuntimeEnforcementRepository,
    *,
    authority: RuntimeAuthorityContext,
    fields: dict[str, Any],
    controls: list[ControlDecisionInput],
    finalize: dict[str, Any],
    resume_of_receipt_id: UUID | None = None,
    decision_chain_id: UUID | None = None,
) -> RuntimeEnforcementReceipt:
    base = build_authority_fields(authority)
    payload = {**base, **fields}
    if resume_of_receipt_id is not None:
        payload["resume_of_receipt_id"] = resume_of_receipt_id
    if decision_chain_id is not None:
        payload["decision_chain_id"] = decision_chain_id
    receipt = repo.create_decision_receipt(**payload)
    for control in controls:
        repo.append_control_decision(receipt, control)
    summary = {
        "control_count": len(controls),
        "control_types": [c.control_type for c in controls],
        "skipped": sum(
            1 for c in controls if c.status == ControlDecisionStatus.SKIPPED.value
        ),
    }
    finalize = {
        **finalize,
        "control_summary": finalize.get("control_summary") or summary,
    }
    repo.finalize_decision(receipt, **finalize)
    return receipt


def find_prior_approval_receipt(
    repo: RuntimeEnforcementRepository,
    approval_request_id: UUID,
) -> RuntimeEnforcementReceipt | None:
    receipts = repo.list_receipts_for_approval(approval_request_id, limit=20)
    for receipt in receipts:
        if receipt.enforcement_decision == "REQUIRE_APPROVAL":
            return receipt
    return None
