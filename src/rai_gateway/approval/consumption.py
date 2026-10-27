"""Atomic approval consumption for WP4 runtime enforcement."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from rai_gateway.approval.authority_validator import ActionAuthorityValidator
from rai_gateway.approval.canonicalizer import canonicalize_action
from rai_gateway.approval.domain import (
    ApprovalDenialCode,
    ApprovalStatus,
    ConsumptionResult,
    ProposedAction,
)
from rai_gateway.approval.errors import ApprovalDeniedError
from rai_gateway.core.observability import generate_trace_id, log_admin_audit
from rai_gateway.identity.domain import RuntimeIdentityStatus
from rai_gateway.identity.errors import AuthorityDeniedError
from rai_gateway.identity.resolver import (
    AuthenticatedRuntimeContext,
    RuntimeAuthorityContext,
    RuntimeAuthorityResolver,
)
from rai_gateway.models.approval import ApprovalRequest


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ApprovalConsumptionService:
    """Central service for exact action-bound approval consumption."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._resolver = RuntimeAuthorityResolver(db)
        self._validator = ActionAuthorityValidator(db)

    def _project_evidence(self, approval_request_id: UUID | None) -> None:
        if not approval_request_id:
            return
        from rai_gateway.evidence.service import TrajectoryService

        TrajectoryService(self._db).project_approval_safe(approval_request_id)

    def consume(
        self,
        authority: RuntimeAuthorityContext,
        action: ProposedAction,
        *,
        approval_request_id: UUID | None = None,
        correlation_id: str | None = None,
    ) -> ConsumptionResult:
        try:
            self._revalidate_governance_state(authority)
            self._validator.validate(authority, action)
        except (ApprovalDeniedError, AuthorityDeniedError) as exc:
            reason = getattr(
                exc, "reason", ApprovalDenialCode.APPROVAL_AUTHORITY_CHANGED.value
            )
            self._audit_denied(
                None,
                str(reason),
                correlation_id,
                authority,
                action,
            )
            return ConsumptionResult(
                allowed=False,
                reason=ApprovalDenialCode(str(reason))
                if str(reason) in ApprovalDenialCode._value2member_map_
                else ApprovalDenialCode.APPROVAL_AUTHORITY_CHANGED,
                message=str(exc),
            )

        _, digest = canonicalize_action(action)
        now = _utcnow()
        request = self._lock_matching_request(
            action_digest=digest,
            runtime_identity_id=action.runtime_identity_id,
            approval_request_id=approval_request_id,
        )
        if not request:
            self._audit_denied(
                None,
                ApprovalDenialCode.APPROVAL_NOT_FOUND.value,
                correlation_id,
                authority,
                action,
            )
            return ConsumptionResult(
                allowed=False,
                reason=ApprovalDenialCode.APPROVAL_NOT_FOUND,
                message="No matching approved request found",
            )

        if request.status == ApprovalStatus.CONSUMED.value:
            self._db.rollback()
            return ConsumptionResult(
                allowed=False,
                reason=ApprovalDenialCode.APPROVAL_ALREADY_CONSUMED,
                message="Approval has already been consumed",
                approval_request_id=request.id,
            )
        if request.status != ApprovalStatus.APPROVED.value:
            self._db.rollback()
            code = self._status_denial_code(request.status)
            return ConsumptionResult(
                allowed=False,
                reason=code,
                message=f"Approval is in state {request.status}",
                approval_request_id=request.id,
            )
        if request.expires_at <= now:
            self._db.rollback()
            return ConsumptionResult(
                allowed=False,
                reason=ApprovalDenialCode.APPROVAL_EXPIRED,
                message="Approval has expired",
                approval_request_id=request.id,
            )

        if request.action_digest != digest:
            self._db.rollback()
            return ConsumptionResult(
                allowed=False,
                reason=ApprovalDenialCode.APPROVAL_ACTION_MISMATCH,
                message="Action digest does not match approved action",
                approval_request_id=request.id,
            )

        request.status = ApprovalStatus.CONSUMED.value
        request.consumed_at = now
        from rai_gateway.events.outbox import enqueue_approval_event

        enqueue_approval_event(self._db, request, "approval.consumed")
        self._db.commit()
        self._project_evidence(request.id)
        log_admin_audit(
            trace_id=correlation_id or generate_trace_id(),
            actor_user_id="runtime",
            actor_role="runtime",
            action="approval.consumed",
            target={
                "approval_request_id": str(request.id),
                "action_digest": digest,
                "runtime_identity_id": str(action.runtime_identity_id),
            },
        )
        return ConsumptionResult(
            allowed=True,
            approval_request_id=request.id,
            message="Approval consumed",
        )

    def resolve_authority_for_identity(
        self,
        runtime_identity_id: UUID,
        delegation_id: UUID | None = None,
    ) -> RuntimeAuthorityContext:
        from rai_gateway.identity.service import RuntimeIdentityService

        identity = RuntimeIdentityService(self._db).get_runtime_identity(
            runtime_identity_id
        )
        return self._resolver.resolve(
            AuthenticatedRuntimeContext(
                credential=None,
                runtime_identity=identity,
                delegation_id=delegation_id,
            )
        )

    def _lock_matching_request(
        self,
        *,
        action_digest: str,
        runtime_identity_id: UUID,
        approval_request_id: UUID | None,
    ) -> ApprovalRequest | None:
        query = (
            self._db.query(ApprovalRequest)
            .filter(ApprovalRequest.action_digest == action_digest)
            .filter(ApprovalRequest.runtime_identity_id == runtime_identity_id)
            .filter(ApprovalRequest.status == ApprovalStatus.APPROVED.value)
            .order_by(ApprovalRequest.created_at.desc())
        )
        if approval_request_id:
            query = query.filter(ApprovalRequest.id == approval_request_id)
        return query.with_for_update().first()

    def _expire_request(self, request: ApprovalRequest) -> None:
        if request.status == ApprovalStatus.PENDING.value:
            request.status = ApprovalStatus.EXPIRED.value
        elif request.status == ApprovalStatus.APPROVED.value:
            request.status = ApprovalStatus.EXPIRED.value
        self._db.commit()

    def _revalidate_governance_state(self, authority: RuntimeAuthorityContext) -> None:
        from rai_gateway.registry.eligibility import EligibilityService

        identity = authority.runtime_identity
        if identity.status != RuntimeIdentityStatus.ACTIVE.value:
            raise ApprovalDeniedError(
                ApprovalDenialCode.RUNTIME_IDENTITY_INELIGIBLE,
                f"Runtime identity is {identity.status}",
            )
        eligibility = EligibilityService(self._db).evaluate(
            system_id=authority.ai_system.id,
            agent_id=authority.agent.id,
            version_id=authority.agent_version.id,
        )
        if not eligibility.eligible:
            raise ApprovalDeniedError(
                ApprovalDenialCode.AGENT_INELIGIBLE,
                eligibility.reason,
            )

    def _status_denial_code(self, status: str) -> ApprovalDenialCode:
        mapping = {
            ApprovalStatus.PENDING.value: ApprovalDenialCode.APPROVAL_PENDING,
            ApprovalStatus.REJECTED.value: ApprovalDenialCode.APPROVAL_REJECTED,
            ApprovalStatus.CANCELLED.value: ApprovalDenialCode.APPROVAL_CANCELLED,
            ApprovalStatus.EXPIRED.value: ApprovalDenialCode.APPROVAL_EXPIRED,
            ApprovalStatus.CONSUMED.value: ApprovalDenialCode.APPROVAL_ALREADY_CONSUMED,
        }
        return mapping.get(status, ApprovalDenialCode.APPROVAL_AUTHORITY_CHANGED)

    def _audit_denied(
        self,
        request_id: UUID | None,
        reason: str,
        correlation_id: str | None,
        authority: RuntimeAuthorityContext,
        action: ProposedAction,
    ) -> None:
        _, digest = canonicalize_action(action)
        log_admin_audit(
            trace_id=correlation_id or generate_trace_id(),
            actor_user_id="runtime",
            actor_role="runtime",
            action="approval.consumption_denied",
            target={
                "approval_request_id": str(request_id) if request_id else None,
                "denial_reason": reason,
                "action_digest": digest,
                "runtime_identity_id": str(action.runtime_identity_id),
            },
        )
