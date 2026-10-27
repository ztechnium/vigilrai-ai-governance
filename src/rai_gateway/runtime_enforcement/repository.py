"""Persistence helpers for WP4 / Canonical Enforcement V2 receipts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from rai_gateway.identity.authority_snapshot import digest_payload
from rai_gateway.models.runtime_enforcement import (
    RuntimeControlDecision,
    RuntimeEnforcementReceipt,
    RuntimeIdempotencyRecord,
)
from rai_gateway.runtime_enforcement.control_decision import (
    EXECUTION_MUTABLE_FIELDS,
    FINALIZED_IMMUTABLE_FIELDS,
    ControlDecisionInput,
)


class FinalizedDecisionMutationError(RuntimeError):
    """Raised when attempting to mutate immutable decision fields after finalize."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RuntimeEnforcementRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def _owned_query(self):
        return self._db.query(RuntimeEnforcementReceipt)

    def create_receipt(self, **fields: Any) -> RuntimeEnforcementReceipt:
        """Legacy create path — prefer create_decision_receipt for V2 flows."""
        receipt = RuntimeEnforcementReceipt(**fields)
        self._db.add(receipt)
        self._db.flush()
        return receipt

    def create_decision_receipt(self, **fields: Any) -> RuntimeEnforcementReceipt:
        """Create a schema-v2 decision receipt (not yet finalized)."""
        fields.setdefault("receipt_schema_version", 2)
        fields.setdefault("revalidation_count", 0)
        if not fields.get("decision_chain_id"):
            fields["decision_chain_id"] = uuid4()
        return self.create_receipt(**fields)

    def append_control_decision(
        self,
        receipt: RuntimeEnforcementReceipt,
        decision: ControlDecisionInput | dict[str, Any],
    ) -> RuntimeControlDecision:
        if receipt.decision_finalized_at is not None:
            raise FinalizedDecisionMutationError(
                "Cannot append control decisions after finalize"
            )
        existing = (
            self._db.query(RuntimeControlDecision)
            .filter(RuntimeControlDecision.receipt_id == receipt.id)
            .count()
        )
        if isinstance(decision, ControlDecisionInput):
            row_fields = decision.to_row_fields(sequence=existing + 1)
        else:
            row_fields = dict(decision)
            row_fields.setdefault("sequence", existing + 1)
        row = RuntimeControlDecision(receipt_id=receipt.id, **row_fields)
        self._db.add(row)
        self._db.flush()
        return row

    def list_control_decisions(self, receipt_id: UUID) -> list[RuntimeControlDecision]:
        return (
            self._db.query(RuntimeControlDecision)
            .filter(RuntimeControlDecision.receipt_id == receipt_id)
            .order_by(RuntimeControlDecision.sequence.asc())
            .all()
        )

    def finalize_decision(
        self,
        receipt: RuntimeEnforcementReceipt,
        *,
        enforcement_decision: str,
        reason_code: str | None = None,
        human_explanation: str | None = None,
        policy_effect: str | None = None,
        matched_rule_ids: list[str] | None = None,
        policy_decision: dict[str, Any] | None = None,
        approval_request_id: UUID | None = None,
        approval_consumed: bool | None = None,
        control_summary: dict[str, Any] | None = None,
        monitor: bool | None = None,
        monitoring_instruction: str | None = None,
    ) -> RuntimeEnforcementReceipt:
        if receipt.decision_finalized_at is not None:
            raise FinalizedDecisionMutationError("Decision already finalized")

        receipt.enforcement_decision = enforcement_decision
        if reason_code is not None:
            receipt.reason_code = reason_code
        if human_explanation is not None:
            receipt.human_explanation = human_explanation
        if policy_effect is not None:
            receipt.policy_effect = policy_effect
        if matched_rule_ids is not None:
            receipt.matched_rule_ids = matched_rule_ids
        if policy_decision is not None:
            receipt.policy_decision = policy_decision
        if approval_request_id is not None:
            receipt.approval_request_id = approval_request_id
        if approval_consumed is not None:
            receipt.approval_consumed = approval_consumed
        if control_summary is not None:
            receipt.control_summary = control_summary
        if monitor is not None:
            receipt.monitor = monitor
        if monitoring_instruction is not None:
            receipt.monitoring_instruction = monitoring_instruction

        controls = self.list_control_decisions(receipt.id)
        receipt.decision_digest = self.compute_decision_digest(receipt, controls)
        receipt.decision_finalized_at = _utcnow()
        self._db.flush()
        return receipt

    def compute_decision_digest(
        self,
        receipt: RuntimeEnforcementReceipt,
        controls: list[RuntimeControlDecision] | None = None,
    ) -> str:
        controls = (
            controls
            if controls is not None
            else self.list_control_decisions(receipt.id)
        )
        payload = {
            "receipt_schema_version": receipt.receipt_schema_version,
            "runtime_identity_id": str(receipt.runtime_identity_id),
            "agent_version_id": str(receipt.agent_version_id),
            "action_digest": receipt.action_digest,
            "authority_digest": receipt.authority_digest,
            "effective_scope_digest": receipt.effective_scope_digest,
            "enforcement_decision": receipt.enforcement_decision,
            "reason_code": receipt.reason_code,
            "policy_effect": receipt.policy_effect,
            "matched_rule_ids": receipt.matched_rule_ids,
            "approval_request_id": str(receipt.approval_request_id)
            if receipt.approval_request_id
            else None,
            "decision_phase": receipt.decision_phase,
            "decision_chain_id": str(receipt.decision_chain_id)
            if receipt.decision_chain_id
            else None,
            "resume_of_receipt_id": str(receipt.resume_of_receipt_id)
            if receipt.resume_of_receipt_id
            else None,
            "controls": [
                {
                    "sequence": c.sequence,
                    "control_type": c.control_type,
                    "policy_domain": c.policy_domain,
                    "status": c.status,
                    "effect": c.effect,
                    "reason_code": c.reason_code,
                    "matched_rule_ids": c.matched_rule_ids,
                }
                for c in controls
            ],
        }
        return digest_payload(payload)

    def update_execution_outcome(
        self, receipt: RuntimeEnforcementReceipt, **fields: Any
    ) -> None:
        illegal = set(fields) - EXECUTION_MUTABLE_FIELDS
        if illegal and receipt.decision_finalized_at is not None:
            # Allow only execution fields after finalize.
            raise FinalizedDecisionMutationError(
                f"Cannot mutate non-execution fields after finalize: {sorted(illegal)}"
            )
        for key, value in fields.items():
            setattr(receipt, key, value)
        if "completed_at" not in fields and fields.get("execution_status") in {
            "SUCCEEDED",
            "FAILED",
            "UNKNOWN",
        }:
            receipt.completed_at = _utcnow()
        self._db.flush()

    def update_receipt(self, receipt: RuntimeEnforcementReceipt, **fields: Any) -> None:
        """Legacy updater — blocks finalized decision field mutation."""
        if receipt.decision_finalized_at is not None:
            blocked = set(fields) & FINALIZED_IMMUTABLE_FIELDS
            if blocked:
                raise FinalizedDecisionMutationError(
                    f"Cannot mutate finalized decision fields: {sorted(blocked)}"
                )
            # Prefer execution-only updates after finalize.
            non_exec = set(fields) - EXECUTION_MUTABLE_FIELDS - {"idempotency_key"}
            if non_exec:
                raise FinalizedDecisionMutationError(
                    f"Cannot mutate fields after finalize: {sorted(non_exec)}"
                )
        for key, value in fields.items():
            setattr(receipt, key, value)
        if "completed_at" not in fields and fields.get("execution_status") in {
            "SUCCEEDED",
            "FAILED",
            "UNKNOWN",
        }:
            receipt.completed_at = _utcnow()
        self._db.flush()

    def get_receipt(self, receipt_id: UUID) -> RuntimeEnforcementReceipt | None:
        return (
            self._owned_query()
            .filter(RuntimeEnforcementReceipt.id == receipt_id)
            .first()
        )

    def find_by_correlation(
        self,
        *,
        runtime_identity_id: UUID,
        correlation_id: str,
    ) -> RuntimeEnforcementReceipt | None:
        return (
            self._db.query(RuntimeEnforcementReceipt)
            .filter(
                RuntimeEnforcementReceipt.runtime_identity_id == runtime_identity_id,
                RuntimeEnforcementReceipt.correlation_id == correlation_id,
            )
            .order_by(RuntimeEnforcementReceipt.started_at.desc())
            .first()
        )

    def list_receipts_for_approval(
        self, approval_request_id: UUID, *, limit: int = 50
    ) -> list[RuntimeEnforcementReceipt]:
        return (
            self._db.query(RuntimeEnforcementReceipt)
            .filter(
                RuntimeEnforcementReceipt.approval_request_id == approval_request_id
            )
            .order_by(RuntimeEnforcementReceipt.started_at.desc())
            .limit(limit)
            .all()
        )

    def list_receipts(
        self,
        *,
        ai_system_id: UUID | None = None,
        agent_id: UUID | None = None,
        runtime_identity_id: UUID | None = None,
        tool_id: UUID | None = None,
        enforcement_decision: str | None = None,
        execution_status: str | None = None,
        enforcement_mode: str | None = None,
        approval_request_id: UUID | None = None,
        client_type: str | None = None,
        started_after: datetime | None = None,
        started_before: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[RuntimeEnforcementReceipt]:
        query = self._owned_query().order_by(
            RuntimeEnforcementReceipt.started_at.desc()
        )
        if ai_system_id:
            query = query.filter(RuntimeEnforcementReceipt.ai_system_id == ai_system_id)
        if agent_id:
            query = query.filter(RuntimeEnforcementReceipt.agent_id == agent_id)
        if runtime_identity_id:
            query = query.filter(
                RuntimeEnforcementReceipt.runtime_identity_id == runtime_identity_id
            )
        if tool_id:
            query = query.filter(RuntimeEnforcementReceipt.tool_id == tool_id)
        if enforcement_decision:
            query = query.filter(
                RuntimeEnforcementReceipt.enforcement_decision == enforcement_decision
            )
        if execution_status:
            if execution_status == "STARTED":
                query = query.filter(
                    RuntimeEnforcementReceipt.execution_status.in_(
                        ["STARTED", "IN_PROGRESS"]
                    )
                )
            else:
                query = query.filter(
                    RuntimeEnforcementReceipt.execution_status == execution_status
                )
        if enforcement_mode:
            query = query.filter(
                RuntimeEnforcementReceipt.enforcement_mode == enforcement_mode
            )
        if approval_request_id:
            query = query.filter(
                RuntimeEnforcementReceipt.approval_request_id == approval_request_id
            )
        if client_type:
            query = query.filter(
                RuntimeEnforcementReceipt.client_context["client_type"].as_string()
                == client_type
            )
        if started_after:
            query = query.filter(RuntimeEnforcementReceipt.started_at >= started_after)
        if started_before:
            query = query.filter(RuntimeEnforcementReceipt.started_at <= started_before)
        return query.offset(offset).limit(limit).all()

    def get_idempotency_record(
        self,
        runtime_identity_id: UUID,
        idempotency_key: str,
    ) -> RuntimeIdempotencyRecord | None:
        return (
            self._db.query(RuntimeIdempotencyRecord)
            .filter(
                RuntimeIdempotencyRecord.runtime_identity_id == runtime_identity_id,
                RuntimeIdempotencyRecord.idempotency_key == idempotency_key,
            )
            .with_for_update()
            .first()
        )

    def create_idempotency_record(
        self,
        *,
        runtime_identity_id: UUID,
        idempotency_key: str,
        action_digest: str,
        receipt_id: UUID,
        execution_status: str,
    ) -> RuntimeIdempotencyRecord:
        record = RuntimeIdempotencyRecord(
            runtime_identity_id=runtime_identity_id,
            idempotency_key=idempotency_key,
            action_digest=action_digest,
            receipt_id=receipt_id,
            execution_status=execution_status,
        )
        self._db.add(record)
        self._db.flush()
        return record
