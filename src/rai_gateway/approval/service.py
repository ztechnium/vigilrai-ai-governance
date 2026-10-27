"""Application services for WP3 durable approval requests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from rai_gateway.approval.authority_validator import ActionAuthorityValidator
from rai_gateway.approval.authorization import (
    ApproverAuthorizationService,
    ApproverContext,
)
from rai_gateway.approval.canonicalizer import canonicalize_action
from rai_gateway.approval.domain import (
    DEFAULT_APPROVAL_TTL_MINUTES,
    ActionTarget,
    ApprovalDecisionType,
    ApprovalRequirement,
    ApprovalStageSpec,
    ApprovalStatus,
    ProposedAction,
)
from rai_gateway.approval.errors import (
    ApprovalConflictError,
    ApprovalDeniedError,
    ApprovalNotFoundError,
    InvalidApprovalTransitionError,
)
from rai_gateway.approval.plan import ApprovalPlanService
from rai_gateway.approval.requirement import ApprovalRequirementService
from rai_gateway.core.observability import generate_trace_id, log_admin_audit
from rai_gateway.identity.resolver import RuntimeAuthorityContext
from rai_gateway.models.approval import ApprovalDecision, ApprovalRequest


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ApprovalService:
    """Manage durable approval request lifecycle."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._validator = ActionAuthorityValidator(db)
        self._requirement = ApprovalRequirementService(db)
        self._approver_auth = ApproverAuthorizationService(db)
        self._plans = ApprovalPlanService(db)

    def _owned_query(self):
        return self._db.query(ApprovalRequest)

    def _project_evidence(self, approval_request_id: UUID | None) -> None:
        if not approval_request_id:
            return
        from rai_gateway.evidence.service import TrajectoryService

        TrajectoryService(self._db).project_approval_safe(approval_request_id)

    def create_request(
        self,
        authority: RuntimeAuthorityContext,
        *,
        integration_type: str,
        integration_id: UUID | None,
        tool_id: UUID | None,
        model_id: UUID | None = None,
        data_source_id: UUID | None = None,
        target_type: str | None = None,
        target_identifier: str | None = None,
        parameters: dict[str, Any] | None = None,
        business_reason: str | None = None,
        environment: str | None = None,
        created_by: str,
        correlation_id: str | None = None,
        ttl_minutes: int = DEFAULT_APPROVAL_TTL_MINUTES,
        force: bool = False,
        stages: list[ApprovalStageSpec] | list[dict[str, Any]] | None = None,
        runtime_idempotency_key: str | None = None,
    ) -> ApprovalRequest:
        delegation_id = (
            authority.delegation_chain[-1].delegation_id
            if authority.delegation_chain
            else None
        )
        action = ProposedAction(
            ai_system_id=authority.ai_system.id,
            agent_id=authority.agent.id,
            agent_version_id=authority.agent_version.id,
            runtime_identity_id=authority.runtime_identity.id,
            delegation_id=delegation_id,
            integration_type=integration_type,
            integration_id=integration_id,
            tool_id=tool_id,
            model_id=model_id,
            data_source_id=data_source_id,
            target=ActionTarget(type=target_type, id=target_identifier)
            if target_type
            else None,
            parameters=parameters or {},
            environment=environment or authority.runtime_identity.environment,
        )

        self._validator.validate(authority, action)
        requirement = self._requirement.evaluate(authority, action)
        if requirement.requirement == ApprovalRequirement.DENIED:
            raise ApprovalDeniedError(
                requirement.reason,
                "Action denied by approval requirement policy",
            )
        if requirement.requirement == ApprovalRequirement.NOT_REQUIRED and not force:
            raise ApprovalDeniedError(
                "APPROVAL_NOT_REQUIRED",
                "Action does not require human approval",
            )

        canonical_payload, digest = canonicalize_action(action)
        # Material change: invalidate in-flight multi-stage plans with other digests
        self._plans.invalidate_plans_for_material_change(
            runtime_identity_id=authority.runtime_identity.id,
            action_digest=digest,
            tool_id=tool_id,
        )
        now = _utcnow()
        request = ApprovalRequest(
            ai_system_id=authority.ai_system.id,
            agent_id=authority.agent.id,
            agent_version_id=authority.agent_version.id,
            runtime_identity_id=authority.runtime_identity.id,
            delegation_id=delegation_id,
            initiating_principal=authority.initiating_principal,
            action_type="tool_invoke",
            integration_type=integration_type,
            integration_id=integration_id,
            tool_id=tool_id,
            model_id=model_id,
            data_source_id=data_source_id,
            target_type=target_type,
            target_identifier=target_identifier,
            canonical_action_payload=canonical_payload,
            action_digest=digest,
            business_reason=business_reason,
            risk_tier=requirement.risk_tier,
            approval_policy_reference=requirement.policy_reference,
            requirement_reason=requirement.reason,
            status=ApprovalStatus.PENDING.value,
            expires_at=now + timedelta(minutes=ttl_minutes),
            correlation_id=correlation_id,
            created_by=created_by,
            runtime_idempotency_key=runtime_idempotency_key,
        )
        self._db.add(request)
        self._db.flush()
        if stages:
            self._plans.attach_plan(request, stages)
        from rai_gateway.events.outbox import enqueue_approval_event

        enqueue_approval_event(self._db, request, "approval.requested")
        self._db.commit()
        self._db.refresh(request)
        self._project_evidence(request.id)

        log_admin_audit(
            trace_id=correlation_id or generate_trace_id(),
            actor_user_id=created_by,
            actor_role="admin",
            action="approval.requested",
            target={
                "approval_request_id": str(request.id),
                "action_digest": digest,
                "runtime_identity_id": str(request.runtime_identity_id),
                "agent_version_id": str(request.agent_version_id),
                "multi_stage": bool(stages),
            },
        )
        return request

    def find_or_create_pending_request(
        self,
        authority: RuntimeAuthorityContext,
        *,
        integration_type: str,
        integration_id: UUID | None,
        tool_id: UUID | None,
        model_id: UUID | None = None,
        data_source_id: UUID | None = None,
        target_type: str | None = None,
        target_identifier: str | None = None,
        parameters: dict[str, Any] | None = None,
        business_reason: str | None = None,
        environment: str | None = None,
        created_by: str,
        correlation_id: str | None = None,
        ttl_minutes: int = DEFAULT_APPROVAL_TTL_MINUTES,
        runtime_idempotency_key: str | None = None,
    ) -> ApprovalRequest:
        """Return matching APPROVED/PENDING request, or create a new PENDING APR.

        Used by hook/proxy REQUIRE_APPROVAL paths so clients always receive a real
        ``approval_request_id`` (never a receipt id stand-in).

        When ``runtime_idempotency_key`` is supplied, correlation prefers that key
        over digest-only matching so legitimate identical actions can coexist.
        """
        delegation_id = (
            authority.delegation_chain[-1].delegation_id
            if authority.delegation_chain
            else None
        )
        action = ProposedAction(
            ai_system_id=authority.ai_system.id,
            agent_id=authority.agent.id,
            agent_version_id=authority.agent_version.id,
            runtime_identity_id=authority.runtime_identity.id,
            delegation_id=delegation_id,
            integration_type=integration_type,
            integration_id=integration_id,
            tool_id=tool_id,
            model_id=model_id,
            data_source_id=data_source_id,
            target=ActionTarget(type=target_type, id=target_identifier)
            if target_type
            else None,
            parameters=parameters or {},
            environment=environment or authority.runtime_identity.environment,
        )
        _, digest = canonicalize_action(action)
        now = _utcnow()

        if runtime_idempotency_key:
            keyed = (
                self._db.query(ApprovalRequest)
                .filter(
                    ApprovalRequest.runtime_identity_id
                    == authority.runtime_identity.id,
                    ApprovalRequest.runtime_idempotency_key == runtime_idempotency_key,
                )
                .order_by(ApprovalRequest.created_at.desc())
                .first()
            )
            if keyed is not None:
                self._expire_if_needed(keyed)
                if keyed.action_digest != digest:
                    raise ApprovalConflictError(
                        "runtime_idempotency_key reused with a different action digest"
                    )
                if (
                    keyed.status
                    in {
                        ApprovalStatus.APPROVED.value,
                        ApprovalStatus.PENDING.value,
                    }
                    and keyed.expires_at > now
                ):
                    return keyed
                # Free the key so a fresh request can reuse it after terminal/expired.
                keyed.runtime_idempotency_key = None
                self._db.flush()

        candidates = (
            self._db.query(ApprovalRequest)
            .filter(
                ApprovalRequest.action_digest == digest,
                ApprovalRequest.runtime_identity_id == authority.runtime_identity.id,
                ApprovalRequest.status.in_(
                    [
                        ApprovalStatus.APPROVED.value,
                        ApprovalStatus.PENDING.value,
                    ]
                ),
            )
            .order_by(ApprovalRequest.created_at.desc())
            .all()
        )
        for existing in candidates:
            self._expire_if_needed(existing)
            if (
                existing.status
                in {
                    ApprovalStatus.APPROVED.value,
                    ApprovalStatus.PENDING.value,
                }
                and existing.expires_at > now
            ):
                return existing

        return self.create_request(
            authority,
            integration_type=integration_type,
            integration_id=integration_id,
            tool_id=tool_id,
            model_id=model_id,
            data_source_id=data_source_id,
            target_type=target_type,
            target_identifier=target_identifier,
            parameters=parameters,
            business_reason=business_reason,
            environment=environment,
            created_by=created_by,
            correlation_id=correlation_id,
            ttl_minutes=ttl_minutes,
            force=True,
            runtime_idempotency_key=runtime_idempotency_key,
        )

    def get_request(
        self,
        request_id: UUID,
    ) -> ApprovalRequest:
        request = self._owned_query().filter(ApprovalRequest.id == request_id).first()
        if not request:
            raise ApprovalNotFoundError(str(request_id))
        self._expire_if_needed(request)
        return request

    def list_requests(
        self,
        *,
        status: str | None = None,
        ai_system_id: UUID | None = None,
        agent_id: UUID | None = None,
        agent_version_id: UUID | None = None,
        runtime_identity_id: UUID | None = None,
        risk_tier: str | None = None,
        search: str | None = None,
    ) -> list[ApprovalRequest]:
        query = self._owned_query()
        if status:
            query = query.filter(ApprovalRequest.status == status)
        if ai_system_id:
            query = query.filter(ApprovalRequest.ai_system_id == ai_system_id)
        if agent_id:
            query = query.filter(ApprovalRequest.agent_id == agent_id)
        if agent_version_id:
            query = query.filter(ApprovalRequest.agent_version_id == agent_version_id)
        if runtime_identity_id:
            query = query.filter(
                ApprovalRequest.runtime_identity_id == runtime_identity_id
            )
        if risk_tier:
            query = query.filter(ApprovalRequest.risk_tier == risk_tier)
        if search:
            like = f"%{search}%"
            query = query.filter(
                (ApprovalRequest.business_reason.ilike(like))
                | (ApprovalRequest.target_identifier.ilike(like))
                | (ApprovalRequest.target_type.ilike(like))
            )
        results = query.order_by(ApprovalRequest.created_at.desc()).all()
        for request in results:
            self._expire_if_needed(request)
        return results

    def approve(
        self,
        request_id: UUID,
        *,
        approver: ApproverContext,
        decision_reason: str | None = None,
        correlation_id: str | None = None,
    ) -> ApprovalRequest:
        request = self._lock_request(request_id)
        plan = self._plans.get_plan_for_request(request.id)
        if plan is not None:
            updated = self._plans.approve_stage(
                request,
                approver=approver,
                decision_reason=decision_reason,
                correlation_id=correlation_id,
            )
            self._project_evidence(updated.id)
            return updated

        self._approver_auth.authorize_approve(request, approver)
        self._transition(request, ApprovalStatus.APPROVED)
        now = _utcnow()
        request.decided_at = now
        decision = ApprovalDecision(
            approval_request_id=request.id,
            decision=ApprovalDecisionType.APPROVED.value,
            decided_by=approver.actor,
            decision_reason=decision_reason,
            authentication_assurance=approver.authentication_assurance,
            correlation_id=correlation_id,
        )
        self._db.add(decision)
        from rai_gateway.events.outbox import enqueue_approval_event

        enqueue_approval_event(self._db, request, "approval.approved")
        self._db.commit()
        self._db.refresh(request)
        self._project_evidence(request.id)

        log_admin_audit(
            trace_id=correlation_id or generate_trace_id(),
            actor_user_id=approver.actor,
            actor_role=approver.role,
            action="approval.approved",
            target={
                "approval_request_id": str(request.id),
                "action_digest": request.action_digest,
            },
            auth_strength=approver.authentication_assurance,
            reason=decision_reason,
        )
        return request

    def reject(
        self,
        request_id: UUID,
        *,
        approver: ApproverContext,
        decision_reason: str | None = None,
        correlation_id: str | None = None,
    ) -> ApprovalRequest:
        request = self._lock_request(request_id)
        if request.risk_tier and request.risk_tier.upper() in {"HIGH", "CRITICAL"}:
            if not decision_reason:
                raise ApprovalDeniedError(
                    "DECISION_REASON_REQUIRED",
                    "Decision reason is required for HIGH/CRITICAL risk approvals",
                )
        plan = self._plans.get_plan_for_request(request.id)
        if plan is not None:
            updated = self._plans.reject_stage(
                request,
                approver=approver,
                decision_reason=decision_reason,
                correlation_id=correlation_id,
            )
            self._project_evidence(updated.id)
            return updated

        self._approver_auth.authorize_reject(request, approver)
        self._transition(request, ApprovalStatus.REJECTED)
        now = _utcnow()
        request.decided_at = now
        decision = ApprovalDecision(
            approval_request_id=request.id,
            decision=ApprovalDecisionType.REJECTED.value,
            decided_by=approver.actor,
            decision_reason=decision_reason,
            authentication_assurance=approver.authentication_assurance,
            correlation_id=correlation_id,
        )
        self._db.add(decision)
        from rai_gateway.events.outbox import enqueue_approval_event

        enqueue_approval_event(self._db, request, "approval.rejected")
        self._db.commit()
        self._db.refresh(request)
        self._project_evidence(request.id)

        log_admin_audit(
            trace_id=correlation_id or generate_trace_id(),
            actor_user_id=approver.actor,
            actor_role=approver.role,
            action="approval.rejected",
            target={
                "approval_request_id": str(request.id),
                "action_digest": request.action_digest,
            },
            auth_strength=approver.authentication_assurance,
            reason=decision_reason,
        )
        return request

    def cancel(
        self,
        request_id: UUID,
        *,
        actor: str,
        correlation_id: str | None = None,
    ) -> ApprovalRequest:
        request = self._lock_request(request_id)
        self._transition(request, ApprovalStatus.CANCELLED)
        from rai_gateway.events.outbox import enqueue_approval_event

        enqueue_approval_event(self._db, request, "approval.cancelled")
        self._db.commit()
        self._db.refresh(request)

        log_admin_audit(
            trace_id=correlation_id or generate_trace_id(),
            actor_user_id=actor,
            actor_role="member",
            action="approval.cancelled",
            target={"approval_request_id": str(request.id)},
        )
        return request

    def _lock_request(
        self,
        request_id: UUID,
    ) -> ApprovalRequest:
        query = self._owned_query().filter(ApprovalRequest.id == request_id)
        request = query.with_for_update().first()
        if not request:
            raise ApprovalNotFoundError(str(request_id))
        self._expire_if_needed(request)
        if request.status != ApprovalStatus.PENDING.value:
            raise ApprovalConflictError(
                f"Approval request is already in terminal state: {request.status}"
            )
        return request

    def _transition(self, request: ApprovalRequest, target: ApprovalStatus) -> None:
        current = ApprovalStatus(request.status)
        allowed = {
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
        }
        if target not in allowed.get(current, set()):
            raise InvalidApprovalTransitionError(current.value, target.value)
        request.status = target.value

    def _expire_if_needed(self, request: ApprovalRequest) -> None:
        now = _utcnow()
        if request.expires_at > now:
            return
        if request.status in {
            ApprovalStatus.PENDING.value,
            ApprovalStatus.APPROVED.value,
        }:
            previous = request.status
            request.status = ApprovalStatus.EXPIRED.value
            from rai_gateway.events.outbox import enqueue_approval_event

            enqueue_approval_event(self._db, request, "approval.expired")
            self._db.commit()
            if previous == ApprovalStatus.PENDING.value:
                log_admin_audit(
                    trace_id=generate_trace_id(),
                    actor_user_id="system",
                    actor_role="system",
                    action="approval.expired",
                    target={"approval_request_id": str(request.id)},
                )

    def expire_due_approvals(self, *, limit: int = 100) -> int:
        """Active expiration sweep — durable without requiring API traffic."""
        now = _utcnow()
        rows = (
            self._db.query(ApprovalRequest)
            .filter(
                ApprovalRequest.status.in_(
                    [ApprovalStatus.PENDING.value, ApprovalStatus.APPROVED.value]
                ),
                ApprovalRequest.expires_at <= now,
            )
            .order_by(ApprovalRequest.expires_at.asc())
            .limit(limit)
        )
        try:
            rows = rows.with_for_update(skip_locked=True).all()
        except Exception:  # noqa: BLE001 — SQLite / dialects without SKIP LOCKED
            rows = rows.all()

        from rai_gateway.events.outbox import enqueue_approval_event

        expired = 0
        for request in rows:
            if request.status not in {
                ApprovalStatus.PENDING.value,
                ApprovalStatus.APPROVED.value,
            }:
                continue
            request.status = ApprovalStatus.EXPIRED.value
            enqueue_approval_event(self._db, request, "approval.expired")
            log_admin_audit(
                trace_id=generate_trace_id(),
                actor_user_id="system",
                actor_role="system",
                action="approval.expired",
                target={"approval_request_id": str(request.id)},
            )
            self._project_evidence(request.id)
            expired += 1
        if expired:
            self._db.commit()
        return expired
