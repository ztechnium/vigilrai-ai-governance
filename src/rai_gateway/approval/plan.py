"""Multi-stage approval plan engine (Phase 2).

Stages are ordered. Within a stage:
- PARALLEL / quorum=len(roles): every required role must approve
- QUORUM: quorum_count distinct approvers whose role is in required_roles
- SEQUENTIAL: roles approve in required_roles order (one at a time)

The ApprovalRequest stays PENDING until the final stage completes, then becomes
APPROVED (consumable by WP3/WP4 ApprovalConsumptionService).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from rai_gateway.approval.authorization import (
    ApproverAuthorizationService,
    ApproverContext,
)
from rai_gateway.approval.domain import (
    ApprovalDecisionType,
    ApprovalDenialCode,
    ApprovalPlanStatus,
    ApprovalStageMode,
    ApprovalStageSpec,
    ApprovalStageStatus,
    ApprovalStatus,
)
from rai_gateway.approval.errors import (
    ApprovalConflictError,
    ApprovalDeniedError,
)
from rai_gateway.core.observability import generate_trace_id, log_admin_audit
from rai_gateway.models.approval import (
    ApprovalDecision,
    ApprovalPlan,
    ApprovalRequest,
    ApprovalStage,
    ApprovalStageDecision,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ApprovalPlanService:
    """Create and advance multi-stage approval plans."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._approver_auth = ApproverAuthorizationService(db)

    def attach_plan(
        self,
        request: ApprovalRequest,
        stage_specs: list[ApprovalStageSpec] | list[dict[str, Any]],
    ) -> ApprovalPlan:
        if not stage_specs:
            raise ApprovalDeniedError(
                "APPROVAL_PLAN_EMPTY",
                "Multi-stage plan requires at least one stage",
            )
        specs = [
            s if isinstance(s, ApprovalStageSpec) else ApprovalStageSpec.from_dict(s)
            for s in stage_specs
        ]
        now = _utcnow()
        plan = ApprovalPlan(
            approval_request_id=request.id,
            action_digest=request.action_digest,
            status=ApprovalPlanStatus.IN_PROGRESS.value,
            current_stage_index=0,
        )
        self._db.add(plan)
        self._db.flush()
        for idx, spec in enumerate(specs):
            stage = ApprovalStage(
                plan_id=plan.id,
                stage_index=idx,
                name=spec.name,
                mode=spec.mode,
                required_roles=list(spec.required_roles),
                quorum_count=spec.quorum_count,
                status=(
                    ApprovalStageStatus.ACTIVE.value
                    if idx == 0
                    else ApprovalStageStatus.PENDING.value
                ),
                activated_at=now if idx == 0 else None,
            )
            self._db.add(stage)
        self._db.flush()
        self._db.refresh(plan)
        return plan

    def get_plan_for_request(self, request_id: UUID) -> ApprovalPlan | None:
        return (
            self._db.query(ApprovalPlan)
            .filter(ApprovalPlan.approval_request_id == request_id)
            .first()
        )

    def approve_stage(
        self,
        request: ApprovalRequest,
        *,
        approver: ApproverContext,
        decision_reason: str | None = None,
        correlation_id: str | None = None,
    ) -> ApprovalRequest:
        """Record a stage approval. Promotes request to APPROVED only on final stage."""
        plan = self.get_plan_for_request(request.id)
        if plan is None:
            raise ApprovalDeniedError(
                "APPROVAL_PLAN_NOT_FOUND",
                "No multi-stage plan attached to this request",
            )
        if plan.status == ApprovalPlanStatus.INVALIDATED.value:
            raise ApprovalDeniedError(
                ApprovalDenialCode.APPROVAL_PLAN_INVALIDATED,
                "Approval plan was invalidated due to material action change",
            )
        if plan.status != ApprovalPlanStatus.IN_PROGRESS.value:
            raise ApprovalConflictError(
                f"Approval plan is not in progress: {plan.status}"
            )
        if plan.action_digest != request.action_digest:
            self._invalidate_plan(plan, reason="action digest mismatch")
            raise ApprovalDeniedError(
                ApprovalDenialCode.APPROVAL_PLAN_INVALIDATED,
                "Plan action digest no longer matches request",
            )

        self._approver_auth.authorize_approve(request, approver)
        stage = self._active_stage(plan)
        self._authorize_stage_role(stage, approver)
        self._check_cross_stage_sod(plan, approver.actor, current_stage_id=stage.id)

        existing = (
            self._db.query(ApprovalStageDecision)
            .filter(
                ApprovalStageDecision.stage_id == stage.id,
                ApprovalStageDecision.decided_by == approver.actor,
            )
            .first()
        )
        if existing:
            raise ApprovalDeniedError(
                ApprovalDenialCode.APPROVAL_DUPLICATE_STAGE_APPROVER,
                "Approver already recorded a decision on this stage",
            )

        if stage.mode == ApprovalStageMode.SEQUENTIAL.value:
            self._check_sequential_order(stage, approver.role)

        decision = ApprovalStageDecision(
            stage_id=stage.id,
            decision=ApprovalDecisionType.APPROVED.value,
            decided_by=approver.actor,
            approver_role=approver.role,
            decision_reason=decision_reason,
            authentication_assurance=approver.authentication_assurance,
            action_digest=request.action_digest,
            correlation_id=correlation_id,
        )
        self._db.add(decision)
        self._db.flush()

        if self._stage_quorum_met(stage):
            now = _utcnow()
            stage.status = ApprovalStageStatus.APPROVED.value
            stage.completed_at = now
            next_index = stage.stage_index + 1
            next_stage = next(
                (s for s in plan.stages if s.stage_index == next_index), None
            )
            if next_stage is None:
                # Final stage — request becomes consumable APPROVED
                plan.status = ApprovalPlanStatus.APPROVED.value
                plan.completed_at = now
                request.status = ApprovalStatus.APPROVED.value
                request.decided_at = now
                self._db.add(
                    ApprovalDecision(
                        approval_request_id=request.id,
                        decision=ApprovalDecisionType.APPROVED.value,
                        decided_by=approver.actor,
                        decision_reason=decision_reason
                        or f"Final stage '{stage.name}' approved",
                        authentication_assurance=approver.authentication_assurance,
                        correlation_id=correlation_id,
                    )
                )
            else:
                plan.current_stage_index = next_index
                next_stage.status = ApprovalStageStatus.ACTIVE.value
                next_stage.activated_at = now

        if request.status == ApprovalStatus.APPROVED.value:
            from rai_gateway.events.outbox import enqueue_approval_event

            enqueue_approval_event(self._db, request, "approval.approved")

        self._db.commit()
        self._db.refresh(request)

        log_admin_audit(
            trace_id=correlation_id or generate_trace_id(),
            actor_user_id=approver.actor,
            actor_role=approver.role,
            action="approval.stage.approved",
            target={
                "approval_request_id": str(request.id),
                "plan_id": str(plan.id),
                "stage_index": stage.stage_index,
                "stage_name": stage.name,
                "request_status": request.status,
                "action_digest": request.action_digest,
            },
            auth_strength=approver.authentication_assurance,
            reason=decision_reason,
        )
        return request

    def reject_stage(
        self,
        request: ApprovalRequest,
        *,
        approver: ApproverContext,
        decision_reason: str | None = None,
        correlation_id: str | None = None,
    ) -> ApprovalRequest:
        plan = self.get_plan_for_request(request.id)
        if plan is None:
            raise ApprovalDeniedError(
                "APPROVAL_PLAN_NOT_FOUND",
                "No multi-stage plan attached to this request",
            )
        if plan.status != ApprovalPlanStatus.IN_PROGRESS.value:
            raise ApprovalConflictError(
                f"Approval plan is not in progress: {plan.status}"
            )
        self._approver_auth.authorize_reject(request, approver)
        stage = self._active_stage(plan)
        self._authorize_stage_role(stage, approver)

        now = _utcnow()
        self._db.add(
            ApprovalStageDecision(
                stage_id=stage.id,
                decision=ApprovalDecisionType.REJECTED.value,
                decided_by=approver.actor,
                approver_role=approver.role,
                decision_reason=decision_reason,
                authentication_assurance=approver.authentication_assurance,
                action_digest=request.action_digest,
                correlation_id=correlation_id,
            )
        )
        stage.status = ApprovalStageStatus.REJECTED.value
        stage.completed_at = now
        plan.status = ApprovalPlanStatus.REJECTED.value
        plan.completed_at = now
        request.status = ApprovalStatus.REJECTED.value
        request.decided_at = now
        self._db.add(
            ApprovalDecision(
                approval_request_id=request.id,
                decision=ApprovalDecisionType.REJECTED.value,
                decided_by=approver.actor,
                decision_reason=decision_reason,
                authentication_assurance=approver.authentication_assurance,
                correlation_id=correlation_id,
            )
        )
        from rai_gateway.events.outbox import enqueue_approval_event

        enqueue_approval_event(self._db, request, "approval.rejected")
        self._db.commit()
        self._db.refresh(request)
        return request

    def invalidate_plans_for_material_change(
        self,
        *,
        runtime_identity_id: UUID,
        action_digest: str,
        tool_id: UUID | None = None,
    ) -> int:
        """Invalidate in-progress plans whose digest no longer matches a new action."""
        q = (
            self._db.query(ApprovalPlan)
            .join(ApprovalRequest)
            .filter(
                ApprovalRequest.runtime_identity_id == runtime_identity_id,
                ApprovalRequest.status == ApprovalStatus.PENDING.value,
                ApprovalPlan.status == ApprovalPlanStatus.IN_PROGRESS.value,
                ApprovalPlan.action_digest != action_digest,
            )
        )
        if tool_id is not None:
            q = q.filter(ApprovalRequest.tool_id == tool_id)
        count = 0
        for plan in q.all():
            self._invalidate_plan(plan, reason="material action change")
            count += 1
        if count:
            self._db.commit()
        return count

    def serialize_plan(self, plan: ApprovalPlan | None) -> dict[str, Any] | None:
        if plan is None:
            return None
        return {
            "id": str(plan.id),
            "approval_request_id": str(plan.approval_request_id),
            "action_digest": plan.action_digest,
            "status": plan.status,
            "current_stage_index": plan.current_stage_index,
            "stages": [
                {
                    "id": str(s.id),
                    "stage_index": s.stage_index,
                    "name": s.name,
                    "mode": s.mode,
                    "required_roles": s.required_roles,
                    "quorum_count": s.quorum_count,
                    "status": s.status,
                    "decisions": [
                        {
                            "id": str(d.id),
                            "decision": d.decision,
                            "decided_by": d.decided_by,
                            "approver_role": d.approver_role,
                            "decision_reason": d.decision_reason,
                            "decided_at": d.decided_at.isoformat()
                            if d.decided_at
                            else None,
                        }
                        for d in (s.decisions or [])
                    ],
                }
                for s in (plan.stages or [])
            ],
        }

    def _active_stage(self, plan: ApprovalPlan) -> ApprovalStage:
        stages = sorted(plan.stages or [], key=lambda s: s.stage_index)
        for stage in stages:
            if stage.status == ApprovalStageStatus.ACTIVE.value:
                return stage
        raise ApprovalDeniedError(
            ApprovalDenialCode.APPROVAL_STAGE_NOT_ACTIVE,
            "No active approval stage",
        )

    def _normalize_stage_role(self, role: str) -> str:
        from rai_gateway.core.authorization import TENANT_ROLE_TO_RBAC_ROLE
        from rai_gateway.services.admin_console import _normalize_role

        mapped = TENANT_ROLE_TO_RBAC_ROLE.get(role, role)
        return _normalize_role(mapped) or mapped

    def _authorize_stage_role(
        self, stage: ApprovalStage, approver: ApproverContext
    ) -> None:
        roles = [str(r) for r in (stage.required_roles or [])]
        if not roles:
            return
        approver_role = self._normalize_stage_role(approver.role)
        allowed = {self._normalize_stage_role(r) for r in roles}
        if approver_role not in allowed:
            raise ApprovalDeniedError(
                ApprovalDenialCode.APPROVAL_STAGE_ROLE_MISMATCH,
                f"Stage '{stage.name}' requires one of roles {roles}",
            )

    def _check_cross_stage_sod(
        self, plan: ApprovalPlan, actor: str, *, current_stage_id: UUID
    ) -> None:
        """Same principal cannot approve more than one stage on a plan (SoD)."""
        prior = (
            self._db.query(ApprovalStageDecision)
            .join(ApprovalStage, ApprovalStageDecision.stage_id == ApprovalStage.id)
            .filter(
                ApprovalStage.plan_id == plan.id,
                ApprovalStage.id != current_stage_id,
                ApprovalStageDecision.decided_by == actor,
                ApprovalStageDecision.decision == ApprovalDecisionType.APPROVED.value,
            )
            .first()
        )
        if prior is not None:
            raise ApprovalDeniedError(
                ApprovalDenialCode.APPROVAL_CROSS_STAGE_SOD,
                "Approver already approved another stage on this plan "
                "(cross-stage separation of duties)",
            )

    def _check_sequential_order(self, stage: ApprovalStage, role: str) -> None:
        roles = [str(r) for r in (stage.required_roles or [])]
        if not roles:
            return
        approved_roles = {
            self._normalize_stage_role(d.approver_role)
            for d in (stage.decisions or [])
            if d.decision == ApprovalDecisionType.APPROVED.value
        }
        role_norm = self._normalize_stage_role(role)
        for expected in roles:
            expected_norm = self._normalize_stage_role(expected)
            if expected_norm in approved_roles:
                continue
            if role_norm != expected_norm:
                raise ApprovalDeniedError(
                    ApprovalDenialCode.APPROVAL_STAGE_ROLE_MISMATCH,
                    f"Sequential stage '{stage.name}' next requires role '{expected}'",
                )
            return

    def _stage_quorum_met(self, stage: ApprovalStage) -> bool:
        self._db.refresh(stage)
        # Reload decisions after flush
        approvals = (
            self._db.query(ApprovalStageDecision)
            .filter(
                ApprovalStageDecision.stage_id == stage.id,
                ApprovalStageDecision.decision == ApprovalDecisionType.APPROVED.value,
            )
            .all()
        )
        roles = [str(r) for r in (stage.required_roles or [])]
        mode = stage.mode
        if mode == ApprovalStageMode.PARALLEL.value:
            needed = (
                {self._normalize_stage_role(r) for r in roles}
                if roles
                else {self._normalize_stage_role(a.approver_role) for a in approvals}
            )
            have = {self._normalize_stage_role(a.approver_role) for a in approvals}
            return needed.issubset(have) and len(approvals) >= len(needed)
        if mode == ApprovalStageMode.SEQUENTIAL.value:
            if not roles:
                return len(approvals) >= stage.quorum_count
            return len(approvals) >= len(roles)
        # QUORUM
        return len(approvals) >= int(stage.quorum_count)

    def _invalidate_plan(self, plan: ApprovalPlan, *, reason: str) -> None:
        now = _utcnow()
        plan.status = ApprovalPlanStatus.INVALIDATED.value
        plan.completed_at = now
        request = self._db.get(ApprovalRequest, plan.approval_request_id)
        if request and request.status == ApprovalStatus.PENDING.value:
            request.status = ApprovalStatus.CANCELLED.value
        for stage in plan.stages or []:
            if stage.status in {
                ApprovalStageStatus.PENDING.value,
                ApprovalStageStatus.ACTIVE.value,
            }:
                stage.status = ApprovalStageStatus.SKIPPED.value
                stage.completed_at = now
        log_admin_audit(
            trace_id=generate_trace_id(),
            actor_user_id="system",
            actor_role="system",
            action="approval.plan.invalidated",
            target={"plan_id": str(plan.id), "reason": reason},
        )
