"""Central runtime enforcement service for WP4."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from rai_gateway.approval.authority_validator import ActionAuthorityValidator
from rai_gateway.approval.canonicalizer import canonicalize_action
from rai_gateway.approval.consumption import ApprovalConsumptionService
from rai_gateway.approval.domain import (
    ActionTarget,
    ApprovalDenialCode,
    ApprovalRequirement,
    ApprovalStatus,
    ProposedAction,
)
from rai_gateway.approval.errors import ApprovalDeniedError
from rai_gateway.approval.requirement import ApprovalRequirementService
from rai_gateway.approval.service import ApprovalService
from rai_gateway.core.observability import generate_trace_id, log_admin_audit
from rai_gateway.identity.domain import RuntimeIdentityStatus
from rai_gateway.identity.errors import AuthorityDeniedError
from rai_gateway.identity.resolver import (
    RuntimeAuthorityContext,
    RuntimeAuthorityResolver,
)
from rai_gateway.models.registry import MCPServer, ToolResource
from rai_gateway.policy.domain import PolicyEffect
from rai_gateway.policy.evaluation import PolicyEvaluationService
from rai_gateway.registry.eligibility import EligibilityService
from rai_gateway.runtime_enforcement.adapters.base import RuntimeAdapterRegistry
from rai_gateway.runtime_enforcement.adapters.mcp import MCPToolExecutionAdapter
from rai_gateway.runtime_enforcement.canonical_receipt import (
    build_allow_controls,
    classify_deny_controls,
    find_prior_approval_receipt,
    persist_canonical_receipt,
)
from rai_gateway.runtime_enforcement.control_decision import DecisionPhase
from rai_gateway.runtime_enforcement.domain import (
    ClientExecutionReport,
    DeploymentControl,
    EnforcementDecisionType,
    EnforcementMode,
    EnforcementResult,
    ExecutionSource,
    ExecutionStatus,
    RuntimeActionRequest,
    RuntimeEnforcementReasonCode,
    VerificationStatus,
)
from rai_gateway.runtime_enforcement.repository import RuntimeEnforcementRepository


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _redact_parameters(parameters: dict[str, Any]) -> dict[str, Any]:
    from rai_gateway.evidence.redaction import _key_is_sensitive

    redacted: dict[str, Any] = {}
    for key, value in parameters.items():
        if _key_is_sensitive(str(key)):
            redacted[key] = "[REDACTED]"
        elif isinstance(value, dict):
            redacted[key] = _redact_parameters(value)
        else:
            redacted[key] = value
    return redacted


class RuntimeEnforcementService:
    """Mandatory runtime decision/enforcement boundary before side effects."""

    def __init__(
        self,
        db: Session,
        *,
        adapter_registry: RuntimeAdapterRegistry | None = None,
    ) -> None:
        self._db = db
        self._resolver = RuntimeAuthorityResolver(db)
        self._authority_validator = ActionAuthorityValidator(db)
        self._policy = PolicyEvaluationService(db)
        self._requirement = ApprovalRequirementService(db)
        self._consumption = ApprovalConsumptionService(db)
        self._repo = RuntimeEnforcementRepository(db)
        self._adapters = adapter_registry or RuntimeAdapterRegistry(
            [MCPToolExecutionAdapter(db)]
        )

    def _project_evidence(self, receipt_id: UUID | None) -> None:
        """Best-effort WP5 trajectory projection; never fails the enforcement path."""
        if not receipt_id:
            return
        from rai_gateway.evidence.service import TrajectoryService

        trajectory = TrajectoryService(self._db).project_receipt_safe(receipt_id)
        self._project_risk(
            receipt_id,
            trajectory_id=trajectory.id if trajectory is not None else None,
        )

    def _project_risk(
        self, receipt_id: UUID, *, trajectory_id: UUID | None = None
    ) -> None:
        """Best-effort WP6 risk signal extraction from enforcement receipt."""
        try:
            from rai_gateway.models.evidence import RuntimeTrajectory
            from rai_gateway.models.registry import ToolResource
            from rai_gateway.models.runtime_enforcement import RuntimeEnforcementReceipt
            from rai_gateway.risk_intelligence.service import RiskIntelligenceService

            receipt = (
                self._db.query(RuntimeEnforcementReceipt)
                .filter(RuntimeEnforcementReceipt.id == receipt_id)
                .first()
            )
            if not receipt:
                return
            resolved_trajectory_id = trajectory_id
            if resolved_trajectory_id is None and receipt.correlation_id:
                traj = (
                    self._db.query(RuntimeTrajectory)
                    .filter(RuntimeTrajectory.correlation_id == receipt.correlation_id)
                    .order_by(RuntimeTrajectory.started_at.desc())
                    .first()
                )
                if traj:
                    resolved_trajectory_id = traj.id
            tool_name = None
            if receipt.tool_id:
                tool = (
                    self._db.query(ToolResource)
                    .filter(ToolResource.id == receipt.tool_id)
                    .first()
                )
                tool_name = tool.name if tool else None
            summary = receipt.action_summary or {}
            params = summary.get("parameters") if isinstance(summary, dict) else {}
            if not isinstance(params, dict):
                params = {}
            amount = None
            for key in ("amount", "total", "value"):
                if key in params:
                    try:
                        amount = float(params[key])
                    except (TypeError, ValueError):
                        amount = None
                    break
            decision = receipt.enforcement_decision or "ALLOW"
            RiskIntelligenceService(self._db).process_enforcement_safe(
                ai_system_id=receipt.ai_system_id,
                agent_id=receipt.agent_id,
                agent_version_id=receipt.agent_version_id,
                runtime_identity_id=receipt.runtime_identity_id,
                trajectory_id=resolved_trajectory_id,
                decision=decision,
                tool_name=tool_name,
                tool_id=str(receipt.tool_id) if receipt.tool_id else None,
                parameters=params,
                amount=amount,
            )
        except Exception:
            # Never fail the enforcement path
            pass

    def _risk_authorization_overlay(
        self, authority: Any, request: RuntimeActionRequest
    ) -> dict[str, Any]:
        try:
            from rai_gateway.risk_intelligence.service import RiskIntelligenceService

            agent = authority.agent
            identity = authority.runtime_identity
            if not agent or not identity:
                return {}
            return RiskIntelligenceService(self._db).authorization_overlay(
                ai_system_id=agent.ai_system_id,
                runtime_identity_id=identity.id,
                tool_id=request.tool_id,
            )
        except Exception as exc:
            from rai_gateway.core.config import settings

            if settings.fail_closed_on_rai_unavailable:
                return {
                    "deny": True,
                    "deny_reason": f"Risk control unavailable (fail-closed): {exc}",
                    "control_error": True,
                }
            return {}

    def _budget_authorization_check(
        self, authority: Any, request: RuntimeActionRequest
    ) -> dict[str, Any]:
        """WP6 pre-execution budget check — concurrency-safe via BudgetService.

        FinOps estimate/reserve fills cost/token measurements when caller omits them.
        """
        try:
            from rai_gateway.finops.service import FinOpsService
            from rai_gateway.models.registry import ToolResource
            from rai_gateway.risk_intelligence.service import RiskIntelligenceService

            agent = authority.agent
            identity = authority.runtime_identity
            version = authority.agent_version
            if not agent or not identity:
                return {}
            tool_name = None
            if request.tool_id:
                tool = (
                    self._db.query(ToolResource)
                    .filter(ToolResource.id == request.tool_id)
                    .first()
                )
                tool_name = tool.name if tool else None
            params = request.parameters if isinstance(request.parameters, dict) else {}
            amount = None
            for key in ("amount", "total", "value"):
                if key in params:
                    try:
                        amount = float(params[key])
                    except (TypeError, ValueError):
                        amount = None
                    break
            token_usage = None
            cost = None
            if "token_usage" in params:
                try:
                    token_usage = float(params["token_usage"])
                except (TypeError, ValueError):
                    token_usage = None
            if "cost" in params:
                try:
                    cost = float(params["cost"])
                except (TypeError, ValueError):
                    cost = None

            finops = FinOpsService(self._db)
            estimate = finops.estimate_from_parameters(params)
            if cost is None and estimate.get("estimated_cost") is not None:
                cost = float(estimate["estimated_cost"])
            if token_usage is None:
                tin = estimate.get("estimated_input_tokens") or 0
                tout = estimate.get("estimated_output_tokens") or 0
                if tin or tout:
                    token_usage = float(tin + tout)

            reservation_id = None
            if estimate.get("estimated_cost") is not None:
                pricing_id = estimate.get("pricing_entry_id")
                reservation = finops.reserve(
                    estimated_cost=float(estimate["estimated_cost"]),
                    currency=str(estimate.get("currency") or "USD"),
                    ai_system_id=agent.ai_system_id,
                    agent_id=agent.id,
                    agent_version_id=version.id if version else None,
                    runtime_identity_id=identity.id,
                    correlation_id=request.correlation_id,
                    provider=estimate.get("provider"),
                    model=estimate.get("model"),
                    estimated_input_tokens=estimate.get("estimated_input_tokens"),
                    estimated_output_tokens=estimate.get("estimated_output_tokens"),
                    pricing_entry_id=UUID(pricing_id) if pricing_id else None,
                    allocation={
                        "tool_id": str(request.tool_id) if request.tool_id else None,
                        "tool_name": tool_name,
                    },
                )
                reservation_id = str(reservation.id)

            overlay = RiskIntelligenceService(self._db).budget_authorization_check(
                ai_system_id=agent.ai_system_id,
                runtime_identity_id=identity.id,
                agent_id=agent.id,
                agent_version_id=version.id if version else None,
                delegation_id=getattr(request, "delegation_id", None),
                tool_name=tool_name,
                tool_id=request.tool_id,
                provider=estimate.get("provider"),
                model=estimate.get("model"),
                parameters=params,
                amount=amount,
                token_usage=token_usage,
                cost=cost,
                trajectory_id=None,
                idempotency_key=request.correlation_id
                or (f"receipt-pending:{agent.ai_system_id}:{identity.id}"),
                finops_usage_reservation_id=UUID(reservation_id)
                if reservation_id
                else None,
            )
            if reservation_id:
                overlay = dict(overlay or {})
                overlay["finops_reservation_id"] = reservation_id
                overlay["budget_idempotency_key"] = request.correlation_id
                overlay["finops_estimate"] = {
                    k: estimate.get(k)
                    for k in (
                        "estimated_cost",
                        "currency",
                        "provider",
                        "model",
                        "reason",
                    )
                }
                if overlay.get("deny") and reservation_id:
                    finops.release(UUID(reservation_id), reason="budget_denied")
                else:
                    # Stash for receipt attachment after ALLOW.
                    ctx = dict(request.client_context or {})
                    ctx["finops_reservation_id"] = reservation_id
                    if request.correlation_id:
                        ctx["budget_idempotency_key"] = request.correlation_id
                    request.client_context = ctx
            return overlay
        except Exception as exc:
            from rai_gateway.core.config import settings

            if settings.fail_closed_on_rai_unavailable:
                return {
                    "deny": True,
                    "deny_reason": f"Budget control unavailable (fail-closed): {exc}",
                    "control_error": True,
                }
            return {}

    def authorize(
        self,
        request: RuntimeActionRequest,
        *,
        credential_secret: str,
    ) -> EnforcementResult:
        """Decision-only enforcement without downstream execution."""
        return self._enforce(
            request,
            credential_secret=credential_secret,
            execute_downstream=False,
        )

    def enforce_and_execute(
        self,
        request: RuntimeActionRequest,
        *,
        credential_secret: str,
    ) -> EnforcementResult:
        """Full proxy enforcement including downstream execution when allowed."""
        return self._enforce(
            request,
            credential_secret=credential_secret,
            execute_downstream=True,
        )

    def _enforce(
        self,
        request: RuntimeActionRequest,
        *,
        credential_secret: str,
        execute_downstream: bool,
    ) -> EnforcementResult:
        correlation_id = request.correlation_id or generate_trace_id()
        trace_id = request.trace_id or correlation_id

        log_admin_audit(
            trace_id=trace_id,
            actor_user_id="runtime",
            actor_role="runtime",
            action="runtime.action.requested",
            target={
                "integration_type": request.integration_type,
                "integration_id": str(request.integration_id)
                if request.integration_id
                else None,
                "tool_id": str(request.tool_id) if request.tool_id else None,
                "correlation_id": correlation_id,
            },
        )

        try:
            authority = self._resolver.resolve_from_credential(
                credential_secret,
                delegation_id=request.delegation_id,
            )
        except AuthorityDeniedError as exc:
            return self._deny(
                request,
                authority=None,
                reason_code=self._map_authority_reason(exc.reason),
                human_explanation=str(exc),
                correlation_id=correlation_id,
                trace_id=trace_id,
                policy_decision=None,
                action_digest=None,
            )

        if not authority.credential:
            return self._deny(
                request,
                authority=authority,
                reason_code=RuntimeEnforcementReasonCode.RUNTIME_AUTHENTICATION_FAILED.value,
                human_explanation="Runtime credential authentication failed",
                correlation_id=correlation_id,
                trace_id=trace_id,
                policy_decision=None,
                action_digest=None,
            )

        resource_error = self._validate_registered_resources(request)
        if resource_error:
            return self._deny(
                request,
                authority=authority,
                reason_code=resource_error,
                human_explanation="Requested integration or tool is not registered",
                correlation_id=correlation_id,
                trace_id=trace_id,
                policy_decision=None,
                action_digest=None,
            )

        action = self._build_proposed_action(request, authority)
        _, action_digest = canonicalize_action(action)

        idempotent = self._check_idempotency(
            authority.runtime_identity.id,
            request.idempotency_key,
            action_digest,
        )
        if idempotent:
            return idempotent

        try:
            self._authority_validator.validate(authority, action)
        except ApprovalDeniedError as exc:
            return self._deny(
                request,
                authority=authority,
                reason_code=self._map_approval_reason(exc.reason),
                human_explanation=str(exc),
                correlation_id=correlation_id,
                trace_id=trace_id,
                policy_decision=None,
                action_digest=action_digest,
                action=action,
            )

        try:
            policy_decision = self._policy.evaluate(authority, action)
        except ApprovalDeniedError as exc:
            return self._deny(
                request,
                authority=authority,
                reason_code=self._map_approval_reason(exc.reason),
                human_explanation=str(exc),
                correlation_id=correlation_id,
                trace_id=trace_id,
                policy_decision=None,
                action_digest=action_digest,
                action=action,
            )
        except Exception as exc:
            return self._deny(
                request,
                authority=authority,
                reason_code=RuntimeEnforcementReasonCode.POLICY_EVALUATION_FAILED.value,
                human_explanation=f"Policy evaluation failed: {exc}",
                correlation_id=correlation_id,
                trace_id=trace_id,
                policy_decision=None,
                action_digest=action_digest,
                action=action,
            )

        policy_dict = policy_decision.to_dict()
        monitor = policy_decision.effect == PolicyEffect.MONITOR.value
        monitoring_instruction = policy_decision.monitoring_instruction

        if policy_decision.effect == PolicyEffect.DENY.value:
            return self._deny(
                request,
                authority=authority,
                reason_code=RuntimeEnforcementReasonCode.POLICY_DENIED.value,
                human_explanation=policy_decision.human_explanation
                or "Action denied by policy",
                correlation_id=correlation_id,
                trace_id=trace_id,
                policy_decision=policy_dict,
                action_digest=action_digest,
                action=action,
                monitor=monitor,
                monitoring_instruction=monitoring_instruction,
            )

        # WP6 dynamic risk / constraint overlay (does not replace WP4)
        risk_overlay = self._risk_authorization_overlay(authority, request)
        if risk_overlay.get("deny"):
            reason_code = RuntimeEnforcementReasonCode.RISK_INTERVENTION_DENIED.value
            if risk_overlay.get("control_error"):
                reason_code = (
                    RuntimeEnforcementReasonCode.RISK_CONTROL_UNAVAILABLE.value
                )
            elif "emergency" in (risk_overlay.get("deny_reason") or "").lower() or (
                "STOPPED" in (risk_overlay.get("deny_reason") or "")
            ):
                reason_code = RuntimeEnforcementReasonCode.EMERGENCY_STOPPED.value
            return self._deny(
                request,
                authority=authority,
                reason_code=reason_code,
                human_explanation=risk_overlay.get("deny_reason")
                or "Action denied by runtime risk constraint",
                correlation_id=correlation_id,
                trace_id=trace_id,
                policy_decision=policy_dict,
                action_digest=action_digest,
                action=action,
                monitor=True,
                monitoring_instruction="WP6 runtime constraint",
            )
        if risk_overlay.get("require_approval"):
            policy_dict = {
                **policy_dict,
                "risk_require_approval": True,
                "risk_state": risk_overlay.get("risk_state"),
            }

        # WP6 budget check before approval / execution
        budget_overlay = self._budget_authorization_check(authority, request)
        if budget_overlay.get("deny"):
            reason_code = RuntimeEnforcementReasonCode.BUDGET_EXCEEDED.value
            if budget_overlay.get("control_error"):
                reason_code = (
                    RuntimeEnforcementReasonCode.RISK_CONTROL_UNAVAILABLE.value
                )
            elif any(
                c.get("reason") == "BUDGET_MEASUREMENT_UNAVAILABLE"
                for c in (budget_overlay.get("checks") or [])
            ):
                reason_code = (
                    RuntimeEnforcementReasonCode.BUDGET_MEASUREMENT_UNAVAILABLE.value
                )
            return self._deny(
                request,
                authority=authority,
                reason_code=reason_code,
                human_explanation=budget_overlay.get("deny_reason")
                or "Action denied by runtime budget",
                correlation_id=correlation_id,
                trace_id=trace_id,
                policy_decision={
                    **policy_dict,
                    "budget_checks": budget_overlay.get("checks"),
                },
                action_digest=action_digest,
                action=action,
                monitor=True,
                monitoring_instruction="WP6 budget exceeded",
            )
        if budget_overlay.get("require_approval"):
            policy_dict = {
                **policy_dict,
                "budget_require_approval": True,
                "budget_checks": budget_overlay.get("checks"),
            }
        if (
            budget_overlay.get("monitor")
            or budget_overlay.get("dominant_effect") == "MONITOR"
        ):
            monitor = True
            monitoring_instruction = (
                monitoring_instruction or "WP6 budget MONITOR effect"
            )
            policy_dict = {
                **policy_dict,
                "budget_monitor": True,
                "budget_checks": budget_overlay.get("checks")
                or policy_dict.get("budget_checks"),
            }

        try:
            requirement = self._requirement.evaluate(authority, action)
        except Exception as exc:
            from rai_gateway.core.config import settings

            if settings.fail_closed_on_rai_unavailable:
                return self._deny(
                    request,
                    authority=authority,
                    reason_code=RuntimeEnforcementReasonCode.APPROVAL_CONTROL_UNAVAILABLE.value,
                    human_explanation=f"Approval control unavailable (fail-closed): {exc}",
                    correlation_id=correlation_id,
                    trace_id=trace_id,
                    policy_decision=policy_dict,
                    action_digest=action_digest,
                    action=action,
                    monitor=True,
                    monitoring_instruction="Approval control unavailable",
                )
            raise

        if requirement.requirement == ApprovalRequirement.DENIED:
            return self._deny(
                request,
                authority=authority,
                reason_code=RuntimeEnforcementReasonCode.POLICY_DENIED.value,
                human_explanation=requirement.reason,
                correlation_id=correlation_id,
                trace_id=trace_id,
                policy_decision=policy_dict,
                action_digest=action_digest,
                action=action,
            )

        needs_approval = (
            requirement.requirement == ApprovalRequirement.REQUIRED
            or policy_decision.effect == PolicyEffect.REQUIRE_APPROVAL.value
            or bool(risk_overlay.get("require_approval"))
            or bool(budget_overlay.get("require_approval"))
        )

        if needs_approval and not execute_downstream:
            consumed = self._consume_approved_match(
                authority,
                action,
                correlation_id=correlation_id,
            )
            if consumed is not None and consumed.allowed:
                return self._allowed_without_execution(
                    request,
                    authority=authority,
                    action=action,
                    action_digest=action_digest,
                    policy_decision=policy_dict,
                    correlation_id=correlation_id,
                    trace_id=trace_id,
                    monitor=monitor,
                    monitoring_instruction=monitoring_instruction
                    or requirement.monitoring_instruction,
                    approval_request_id=consumed.approval_request_id,
                    approval_consumed=True,
                )
            return self._approval_required(
                request,
                authority=authority,
                action=action,
                action_digest=action_digest,
                policy_decision=policy_dict,
                correlation_id=correlation_id,
                trace_id=trace_id,
                human_explanation=requirement.reason
                or policy_decision.human_explanation
                or "Human approval required before execution",
                monitor=monitor,
                monitoring_instruction=monitoring_instruction
                or requirement.monitoring_instruction,
                enforcement_mode=EnforcementMode.HOOK_ENFORCED.value,
            )

        approval_consumed = False
        approval_request_id = request.approval_request_id

        if needs_approval and execute_downstream:
            if not request.approval_request_id:
                return self._approval_required(
                    request,
                    authority=authority,
                    action=action,
                    action_digest=action_digest,
                    policy_decision=policy_dict,
                    correlation_id=correlation_id,
                    trace_id=trace_id,
                    human_explanation=requirement.reason
                    or policy_decision.human_explanation
                    or "Human approval required before execution",
                    monitor=monitor,
                    monitoring_instruction=monitoring_instruction
                    or requirement.monitoring_instruction,
                    enforcement_mode=EnforcementMode.PROXY_ENFORCED.value,
                )
            try:
                consumption = self._consumption.consume(
                    authority,
                    action,
                    approval_request_id=request.approval_request_id,
                    correlation_id=correlation_id,
                )
            except Exception as exc:
                from rai_gateway.core.config import settings

                if settings.fail_closed_on_rai_unavailable:
                    return self._deny(
                        request,
                        authority=authority,
                        reason_code=RuntimeEnforcementReasonCode.APPROVAL_CONTROL_UNAVAILABLE.value,
                        human_explanation=(
                            f"Approval control unavailable (fail-closed): {exc}"
                        ),
                        correlation_id=correlation_id,
                        trace_id=trace_id,
                        policy_decision=policy_dict,
                        action_digest=action_digest,
                        action=action,
                        monitor=True,
                        monitoring_instruction="Approval control unavailable",
                    )
                raise
            if not consumption.allowed:
                reason = consumption.reason or ApprovalDenialCode.APPROVAL_NOT_FOUND
                return self._deny(
                    request,
                    authority=authority,
                    reason_code=self._map_approval_reason(reason.value),
                    human_explanation=consumption.message,
                    correlation_id=correlation_id,
                    trace_id=trace_id,
                    policy_decision=policy_dict,
                    action_digest=action_digest,
                    action=action,
                    approval_request_id=consumption.approval_request_id,
                )
            approval_consumed = True
            approval_request_id = consumption.approval_request_id
            log_admin_audit(
                trace_id=trace_id,
                actor_user_id="runtime",
                actor_role="runtime",
                action="runtime.action.approval_consumed",
                target={
                    "approval_request_id": str(approval_request_id),
                    "action_digest": action_digest,
                },
            )

        state_error = self._revalidate_critical_state(authority)
        if state_error:
            return self._deny(
                request,
                authority=authority,
                reason_code=state_error,
                human_explanation="Governance state changed before execution",
                correlation_id=correlation_id,
                trace_id=trace_id,
                policy_decision=policy_dict,
                action_digest=action_digest,
                action=action,
                approval_request_id=approval_request_id,
                approval_consumed=approval_consumed,
                include_revalidation=True,
            )

        if not execute_downstream:
            return self._allowed_without_execution(
                request,
                authority=authority,
                action=action,
                action_digest=action_digest,
                policy_decision=policy_dict,
                correlation_id=correlation_id,
                trace_id=trace_id,
                monitor=monitor,
                monitoring_instruction=monitoring_instruction
                or requirement.monitoring_instruction,
            )

        adapter = self._adapters.resolve(action)
        if not adapter:
            return self._deny(
                request,
                authority=authority,
                reason_code=RuntimeEnforcementReasonCode.ADAPTER_NOT_AVAILABLE.value,
                human_explanation="No runtime adapter available for this action",
                correlation_id=correlation_id,
                trace_id=trace_id,
                policy_decision=policy_dict,
                action_digest=action_digest,
                action=action,
                approval_request_id=approval_request_id,
                approval_consumed=approval_consumed,
            )

        receipt = persist_canonical_receipt(
            self._repo,
            authority=authority,
            fields={
                "runtime_identity_id": authority.runtime_identity.id,
                "ai_system_id": authority.ai_system.id,
                "agent_id": authority.agent.id,
                "agent_version_id": authority.agent_version.id,
                "delegation_id": request.delegation_id,
                "enforcement_mode": EnforcementMode.PROXY_ENFORCED.value,
                "integration_type": request.integration_type,
                "integration_id": request.integration_id,
                "tool_id": request.tool_id,
                "action_digest": action_digest,
                "policy_effect": policy_decision.effect,
                "matched_rule_ids": policy_decision.matched_rule_ids,
                "approval_request_id": approval_request_id,
                "approval_consumed": approval_consumed,
                "enforcement_decision": EnforcementDecisionType.ALLOW.value,
                "execution_attempted": False,
                "execution_status": ExecutionStatus.STARTED.value,
                "execution_source": ExecutionSource.RAI_EXECUTED.value,
                "deployment_control": DeploymentControl.PROXY_CONTROLLED.value,
                "verification_status": VerificationStatus.VERIFIED.value,
                "client_context": request.client_context,
                "idempotency_key": request.idempotency_key,
                "policy_decision": policy_dict,
                "action_summary": self._action_summary(action),
                "monitor": monitor,
                "monitoring_instruction": monitoring_instruction
                or requirement.monitoring_instruction,
                "correlation_id": correlation_id,
                "trace_id": trace_id,
                "decision_phase": DecisionPhase.RESUME.value
                if approval_consumed
                else DecisionPhase.EXECUTE.value,
            },
            controls=build_allow_controls(
                policy_decision=policy_dict,
                phase=DecisionPhase.RESUME.value
                if approval_consumed
                else DecisionPhase.EXECUTE.value,
                include_approval=bool(approval_request_id or approval_consumed),
                approval_consumed=approval_consumed,
            ),
            finalize={
                "enforcement_decision": EnforcementDecisionType.ALLOW.value,
                "human_explanation": policy_decision.human_explanation
                or "Action allowed after governance checks",
                "policy_effect": policy_decision.effect,
                "matched_rule_ids": policy_decision.matched_rule_ids,
                "policy_decision": policy_dict,
                "approval_request_id": approval_request_id,
                "approval_consumed": approval_consumed,
                "monitor": monitor,
                "monitoring_instruction": monitoring_instruction
                or requirement.monitoring_instruction,
            },
            **self._approval_lineage_kwargs(approval_request_id, approval_consumed),
        )

        if request.idempotency_key:
            self._repo.create_idempotency_record(
                runtime_identity_id=authority.runtime_identity.id,
                idempotency_key=request.idempotency_key,
                action_digest=action_digest,
                receipt_id=receipt.id,
                execution_status=ExecutionStatus.STARTED.value,
            )
        self._attach_finops_reservation(request, receipt.id)
        self._db.commit()

        log_admin_audit(
            trace_id=trace_id,
            actor_user_id="runtime",
            actor_role="runtime",
            action="runtime.action.allowed",
            target={"receipt_id": str(receipt.id), "action_digest": action_digest},
        )
        log_admin_audit(
            trace_id=trace_id,
            actor_user_id="runtime",
            actor_role="runtime",
            action="runtime.execution.reported_started",
            target={"receipt_id": str(receipt.id)},
        )

        downstream = adapter.execute(action, authority)
        execution_status = (
            ExecutionStatus.SUCCEEDED.value
            if downstream.success
            else ExecutionStatus.FAILED.value
        )

        self._repo.update_execution_outcome(
            receipt,
            execution_attempted=True,
            execution_status=execution_status,
            execution_source=ExecutionSource.RAI_EXECUTED.value,
            downstream_reference=downstream.downstream_reference,
        )
        if request.idempotency_key:
            record = self._repo.get_idempotency_record(
                authority.runtime_identity.id, request.idempotency_key
            )
            if record:
                record.execution_status = execution_status
        self._db.commit()
        self._project_evidence(receipt.id)

        audit_action = (
            "runtime.execution.reported_succeeded"
            if downstream.success
            else "runtime.execution.reported_failed"
        )
        log_admin_audit(
            trace_id=trace_id,
            actor_user_id="runtime",
            actor_role="runtime",
            action=audit_action,
            target={
                "receipt_id": str(receipt.id),
                "execution_status": execution_status,
                "execution_source": ExecutionSource.RAI_EXECUTED.value,
            },
        )

        explanation = (
            "Action executed successfully"
            if downstream.success
            else (downstream.error_message or "Downstream execution failed")
        )

        return EnforcementResult(
            allowed=True,
            effect=EnforcementDecisionType.ALLOW.value,
            reason_code=None,
            human_explanation=explanation,
            runtime_identity_id=authority.runtime_identity.id,
            agent_version_id=authority.agent_version.id,
            action_digest=action_digest,
            policy_decision=policy_dict,
            approval_request_id=approval_request_id,
            approval_consumed=approval_consumed,
            monitor=monitor,
            monitoring_instruction=monitoring_instruction
            or requirement.monitoring_instruction,
            execution_attempted=True,
            execution_status=execution_status,
            execution_source=ExecutionSource.RAI_EXECUTED.value,
            correlation_id=correlation_id,
            trace_id=trace_id,
            receipt_id=receipt.id,
            downstream_reference=downstream.downstream_reference,
            enforcement_mode=EnforcementMode.PROXY_ENFORCED.value,
            deployment_control=DeploymentControl.PROXY_CONTROLLED.value,
            verification_status=VerificationStatus.VERIFIED.value,
        )

    def _validate_registered_resources(
        self, request: RuntimeActionRequest
    ) -> str | None:
        if request.integration_type == "mcp":
            if not request.integration_id:
                return RuntimeEnforcementReasonCode.RESOURCE_NOT_REGISTERED.value
            mcp = (
                self._db.query(MCPServer)
                .filter(MCPServer.id == request.integration_id)
                .first()
            )
            if not mcp or mcp.status != "ACTIVE":
                return RuntimeEnforcementReasonCode.RESOURCE_NOT_REGISTERED.value
        if not request.tool_id:
            return RuntimeEnforcementReasonCode.RESOURCE_NOT_REGISTERED.value
        tool = (
            self._db.query(ToolResource)
            .filter(ToolResource.id == request.tool_id)
            .first()
        )
        if not tool or tool.status != "ACTIVE":
            return RuntimeEnforcementReasonCode.RESOURCE_NOT_REGISTERED.value
        if request.integration_type == "mcp" and request.integration_id:
            if tool.mcp_server_id and tool.mcp_server_id != request.integration_id:
                return RuntimeEnforcementReasonCode.RESOURCE_RELATIONSHIP_INVALID.value
        return None

    def _build_proposed_action(
        self,
        request: RuntimeActionRequest,
        authority: RuntimeAuthorityContext,
    ) -> ProposedAction:
        target = None
        if request.target:
            target = ActionTarget(type=request.target.type, id=request.target.id)
        delegation_id = request.delegation_id
        if authority.delegation_chain:
            delegation_id = authority.delegation_chain[-1].delegation_id
        return ProposedAction(
            ai_system_id=authority.ai_system.id,
            agent_id=authority.agent.id,
            agent_version_id=authority.agent_version.id,
            runtime_identity_id=authority.runtime_identity.id,
            delegation_id=delegation_id,
            integration_type=request.integration_type,
            integration_id=request.integration_id,
            tool_id=request.tool_id,
            target=target,
            parameters=dict(request.parameters or {}),
            environment=request.environment or authority.runtime_identity.environment,
        )

    def _revalidate_critical_state(
        self, authority: RuntimeAuthorityContext
    ) -> str | None:
        identity = authority.runtime_identity
        self._db.refresh(identity)
        if identity.status != RuntimeIdentityStatus.ACTIVE.value:
            return RuntimeEnforcementReasonCode.RUNTIME_STATE_CHANGED.value
        eligibility = EligibilityService(self._db).evaluate(
            system_id=authority.ai_system.id,
            agent_id=authority.agent.id,
            version_id=authority.agent_version.id,
        )
        if not eligibility.eligible:
            return RuntimeEnforcementReasonCode.RUNTIME_STATE_CHANGED.value
        # Re-resolve optional delegation chain for TOCTOU revocation/suspension.
        if authority.delegation_chain:
            try:
                leaf_id = authority.delegation_chain[-1].delegation_id
                self._resolver._delegation_service.resolve_active_chain(leaf_id)
            except Exception:
                return RuntimeEnforcementReasonCode.RUNTIME_STATE_CHANGED.value
        return None

    def _approval_lineage_kwargs(
        self,
        approval_request_id: UUID | None,
        approval_consumed: bool,
    ) -> dict[str, Any]:
        if not approval_consumed or not approval_request_id:
            return {}
        prior = find_prior_approval_receipt(self._repo, approval_request_id)
        if not prior:
            return {}
        return {
            "resume_of_receipt_id": prior.id,
            "decision_chain_id": prior.decision_chain_id or prior.id,
        }

    def _check_idempotency(
        self,
        runtime_identity_id: UUID,
        idempotency_key: str | None,
        action_digest: str,
    ) -> EnforcementResult | None:
        if not idempotency_key:
            return None
        record = self._repo.get_idempotency_record(runtime_identity_id, idempotency_key)
        if not record:
            return None
        if record.action_digest != action_digest:
            return EnforcementResult(
                allowed=False,
                effect=EnforcementDecisionType.DENY.value,
                reason_code=RuntimeEnforcementReasonCode.DUPLICATE_RUNTIME_ACTION.value,
                human_explanation="Idempotency key reused with a different action digest",
                runtime_identity_id=runtime_identity_id,
                action_digest=action_digest,
                execution_attempted=False,
                execution_status=ExecutionStatus.NOT_ATTEMPTED.value,
                receipt_id=record.receipt_id,
            )
        receipt = self._repo.get_receipt(record.receipt_id)
        if not receipt:
            return None
        return EnforcementResult(
            allowed=receipt.enforcement_decision == EnforcementDecisionType.ALLOW.value,
            effect=receipt.enforcement_decision,
            reason_code=receipt.reason_code,
            human_explanation=receipt.human_explanation or "Idempotent replay",
            runtime_identity_id=receipt.runtime_identity_id,
            agent_version_id=receipt.agent_version_id,
            action_digest=receipt.action_digest,
            policy_decision=receipt.policy_decision,
            approval_request_id=receipt.approval_request_id,
            approval_consumed=receipt.approval_consumed,
            monitor=receipt.monitor,
            monitoring_instruction=receipt.monitoring_instruction,
            execution_attempted=receipt.execution_attempted,
            execution_status=receipt.execution_status,
            correlation_id=receipt.correlation_id,
            trace_id=receipt.trace_id,
            receipt_id=receipt.id,
            downstream_reference=receipt.downstream_reference,
        )

    def _deny(
        self,
        request: RuntimeActionRequest,
        *,
        authority: RuntimeAuthorityContext | None,
        reason_code: str,
        human_explanation: str,
        correlation_id: str,
        trace_id: str,
        policy_decision: dict[str, Any] | None,
        action_digest: str | None,
        action: ProposedAction | None = None,
        approval_request_id: UUID | None = None,
        approval_consumed: bool = False,
        monitor: bool = False,
        monitoring_instruction: str | None = None,
        include_revalidation: bool = False,
    ) -> EnforcementResult:
        receipt_id = None
        if authority and action_digest:
            phase = DecisionPhase.EXECUTE.value
            controls = classify_deny_controls(
                reason_code=reason_code,
                policy_decision=policy_decision,
                phase=phase,
            )
            if include_revalidation and not any(
                c.control_type == "REVALIDATION" for c in controls
            ):
                from rai_gateway.runtime_enforcement.control_decision import (
                    ControlDecisionInput,
                    ControlDecisionStatus,
                    ControlType,
                )

                controls.append(
                    ControlDecisionInput(
                        control_type=ControlType.REVALIDATION.value,
                        status=ControlDecisionStatus.EVALUATED.value,
                        effect="DENY",
                        reason_code=reason_code,
                        phase=phase,
                    )
                )
            receipt = persist_canonical_receipt(
                self._repo,
                authority=authority,
                fields={
                    "runtime_identity_id": authority.runtime_identity.id,
                    "ai_system_id": authority.ai_system.id,
                    "agent_id": authority.agent.id,
                    "agent_version_id": authority.agent_version.id,
                    "delegation_id": request.delegation_id,
                    "enforcement_mode": EnforcementMode.PROXY_ENFORCED.value,
                    "integration_type": request.integration_type,
                    "integration_id": request.integration_id,
                    "tool_id": request.tool_id,
                    "action_digest": action_digest,
                    "policy_effect": policy_decision.get("effect")
                    if policy_decision
                    else None,
                    "matched_rule_ids": policy_decision.get("matched_rule_ids")
                    if policy_decision
                    else None,
                    "approval_request_id": approval_request_id,
                    "approval_consumed": approval_consumed,
                    "enforcement_decision": EnforcementDecisionType.DENY.value,
                    "execution_attempted": False,
                    "execution_status": ExecutionStatus.NOT_ATTEMPTED.value,
                    "deployment_control": DeploymentControl.PROXY_CONTROLLED.value,
                    "verification_status": VerificationStatus.VERIFIED.value,
                    "client_context": request.client_context,
                    "idempotency_key": request.idempotency_key,
                    "policy_decision": policy_decision,
                    "action_summary": self._action_summary(action) if action else None,
                    "monitor": monitor,
                    "monitoring_instruction": monitoring_instruction,
                    "correlation_id": correlation_id,
                    "trace_id": trace_id,
                    "decision_phase": phase,
                    "revalidation_count": 1 if include_revalidation else 0,
                },
                controls=controls,
                finalize={
                    "enforcement_decision": EnforcementDecisionType.DENY.value,
                    "reason_code": reason_code,
                    "human_explanation": human_explanation,
                    "policy_effect": policy_decision.get("effect")
                    if policy_decision
                    else None,
                    "matched_rule_ids": policy_decision.get("matched_rule_ids")
                    if policy_decision
                    else None,
                    "policy_decision": policy_decision,
                    "approval_request_id": approval_request_id,
                    "approval_consumed": approval_consumed,
                    "monitor": monitor,
                    "monitoring_instruction": monitoring_instruction,
                },
            )
            receipt_id = receipt.id
            self._db.commit()
            self._project_evidence(receipt_id)

        log_admin_audit(
            trace_id=trace_id,
            actor_user_id="runtime",
            actor_role="runtime",
            action="runtime.action.denied",
            target={
                "reason_code": reason_code,
                "receipt_id": str(receipt_id) if receipt_id else None,
            },
        )

        return EnforcementResult(
            allowed=False,
            effect=EnforcementDecisionType.DENY.value,
            reason_code=reason_code,
            human_explanation=human_explanation,
            runtime_identity_id=authority.runtime_identity.id if authority else None,
            agent_version_id=authority.agent_version.id if authority else None,
            action_digest=action_digest,
            policy_decision=policy_decision,
            approval_request_id=approval_request_id,
            approval_consumed=approval_consumed,
            monitor=monitor,
            monitoring_instruction=monitoring_instruction,
            execution_attempted=False,
            execution_status=ExecutionStatus.NOT_ATTEMPTED.value,
            correlation_id=correlation_id,
            trace_id=trace_id,
            receipt_id=receipt_id,
        )

    def _consume_approved_match(
        self,
        authority: RuntimeAuthorityContext,
        action: ProposedAction,
        *,
        correlation_id: str,
    ):
        """Consume an already-approved exact action, if one is still valid.

        Hook clients retry authorize on the next turn without sending
        ``approval_request_id``. Digest match is enough; a missing match must
        not write an approval-denied audit.
        """
        from rai_gateway.models.approval import ApprovalRequest

        _, digest = canonicalize_action(action)
        existing = (
            self._db.query(ApprovalRequest)
            .filter(
                ApprovalRequest.action_digest == digest,
                ApprovalRequest.runtime_identity_id == action.runtime_identity_id,
                ApprovalRequest.status == ApprovalStatus.APPROVED.value,
                ApprovalRequest.expires_at > _utcnow(),
            )
            .order_by(ApprovalRequest.created_at.desc())
            .first()
        )
        if existing is None:
            return None
        return self._consumption.consume(
            authority,
            action,
            approval_request_id=existing.id,
            correlation_id=correlation_id,
        )

    def _approval_required(
        self,
        request: RuntimeActionRequest,
        *,
        authority: RuntimeAuthorityContext,
        action: ProposedAction,
        action_digest: str,
        policy_decision: dict[str, Any],
        correlation_id: str,
        trace_id: str,
        human_explanation: str,
        monitor: bool,
        monitoring_instruction: str | None,
        enforcement_mode: str = EnforcementMode.PROXY_ENFORCED.value,
    ) -> EnforcementResult:
        approval_request_id = request.approval_request_id
        if not approval_request_id:
            try:
                apr = ApprovalService(self._db).find_or_create_pending_request(
                    authority,
                    integration_type=action.integration_type,
                    integration_id=action.integration_id,
                    tool_id=action.tool_id,
                    model_id=action.model_id,
                    data_source_id=action.data_source_id,
                    target_type=action.target.type if action.target else None,
                    target_identifier=action.target.id if action.target else None,
                    parameters=dict(action.parameters or {}),
                    business_reason=human_explanation,
                    environment=action.environment,
                    created_by="runtime",
                    correlation_id=correlation_id,
                    runtime_idempotency_key=request.idempotency_key,
                )
                approval_request_id = apr.id
            except Exception as exc:
                from rai_gateway.core.config import settings

                if settings.fail_closed_on_rai_unavailable:
                    return self._deny(
                        request,
                        authority=authority,
                        reason_code=RuntimeEnforcementReasonCode.APPROVAL_CONTROL_UNAVAILABLE.value,
                        human_explanation=(
                            f"Approval control unavailable (fail-closed): {exc}"
                        ),
                        correlation_id=correlation_id,
                        trace_id=trace_id,
                        policy_decision=policy_decision,
                        action_digest=action_digest,
                        action=action,
                        monitor=True,
                        monitoring_instruction="Approval control unavailable",
                    )
                raise

        receipt = persist_canonical_receipt(
            self._repo,
            authority=authority,
            fields={
                "runtime_identity_id": authority.runtime_identity.id,
                "ai_system_id": authority.ai_system.id,
                "agent_id": authority.agent.id,
                "agent_version_id": authority.agent_version.id,
                "delegation_id": request.delegation_id,
                "enforcement_mode": enforcement_mode,
                "deployment_control": (
                    DeploymentControl.PROXY_CONTROLLED.value
                    if enforcement_mode == EnforcementMode.PROXY_ENFORCED.value
                    else DeploymentControl.LOCAL_HOOK.value
                ),
                "verification_status": (
                    VerificationStatus.VERIFIED.value
                    if enforcement_mode == EnforcementMode.PROXY_ENFORCED.value
                    else VerificationStatus.DECLARED.value
                ),
                "integration_type": request.integration_type,
                "integration_id": request.integration_id,
                "tool_id": request.tool_id,
                "action_digest": action_digest,
                "policy_effect": policy_decision.get("effect"),
                "matched_rule_ids": policy_decision.get("matched_rule_ids"),
                "approval_request_id": approval_request_id,
                "approval_consumed": False,
                "enforcement_decision": EnforcementDecisionType.REQUIRE_APPROVAL.value,
                "execution_attempted": False,
                "execution_status": ExecutionStatus.NOT_ATTEMPTED.value,
                "client_context": request.client_context,
                "idempotency_key": request.idempotency_key,
                "policy_decision": policy_decision,
                "action_summary": self._action_summary(action),
                "monitor": monitor,
                "monitoring_instruction": monitoring_instruction,
                "correlation_id": correlation_id,
                "trace_id": trace_id,
                "decision_phase": DecisionPhase.AUTHORIZE.value,
            },
            controls=build_allow_controls(
                policy_decision=policy_decision,
                phase=DecisionPhase.AUTHORIZE.value,
                include_approval=True,
                approval_consumed=False,
            ),
            finalize={
                "enforcement_decision": EnforcementDecisionType.REQUIRE_APPROVAL.value,
                "reason_code": RuntimeEnforcementReasonCode.APPROVAL_REQUIRED.value,
                "human_explanation": human_explanation,
                "policy_effect": policy_decision.get("effect"),
                "matched_rule_ids": policy_decision.get("matched_rule_ids"),
                "policy_decision": policy_decision,
                "approval_request_id": approval_request_id,
                "approval_consumed": False,
                "monitor": monitor,
                "monitoring_instruction": monitoring_instruction,
            },
        )
        self._db.commit()
        self._project_evidence(receipt.id)

        log_admin_audit(
            trace_id=trace_id,
            actor_user_id="runtime",
            actor_role="runtime",
            action="runtime.action.approval_required",
            target={
                "receipt_id": str(receipt.id),
                "approval_request_id": str(approval_request_id),
                "action_digest": action_digest,
            },
        )

        approval_payload = None
        if approval_request_id:
            from rai_gateway.approval.resume import build_approval_resume
            from rai_gateway.models.approval import ApprovalRequest as APRModel

            apr_row = (
                self._db.query(APRModel)
                .filter(APRModel.id == approval_request_id)
                .first()
            )
            if apr_row is not None:
                approval_payload = build_approval_resume(apr_row)

        return EnforcementResult(
            allowed=False,
            effect=EnforcementDecisionType.REQUIRE_APPROVAL.value,
            reason_code=RuntimeEnforcementReasonCode.APPROVAL_REQUIRED.value,
            human_explanation=human_explanation,
            runtime_identity_id=authority.runtime_identity.id,
            agent_version_id=authority.agent_version.id,
            action_digest=action_digest,
            policy_decision=policy_decision,
            approval_request_id=approval_request_id,
            approval=approval_payload,
            approval_consumed=False,
            monitor=monitor,
            monitoring_instruction=monitoring_instruction,
            execution_attempted=False,
            execution_status=ExecutionStatus.NOT_ATTEMPTED.value,
            correlation_id=correlation_id,
            trace_id=trace_id,
            receipt_id=receipt.id,
        )

    def _allowed_without_execution(
        self,
        request: RuntimeActionRequest,
        *,
        authority: RuntimeAuthorityContext,
        action: ProposedAction,
        action_digest: str,
        policy_decision: dict[str, Any],
        correlation_id: str,
        trace_id: str,
        monitor: bool,
        monitoring_instruction: str | None,
        approval_request_id: UUID | None = None,
        approval_consumed: bool = False,
    ) -> EnforcementResult:
        decision = (
            EnforcementDecisionType.MONITOR.value
            if monitor
            else EnforcementDecisionType.ALLOW.value
        )
        receipt = persist_canonical_receipt(
            self._repo,
            authority=authority,
            fields={
                "runtime_identity_id": authority.runtime_identity.id,
                "ai_system_id": authority.ai_system.id,
                "agent_id": authority.agent.id,
                "agent_version_id": authority.agent_version.id,
                "delegation_id": request.delegation_id,
                "enforcement_mode": EnforcementMode.HOOK_ENFORCED.value,
                "deployment_control": DeploymentControl.LOCAL_HOOK.value,
                "verification_status": VerificationStatus.DECLARED.value,
                "integration_type": request.integration_type,
                "integration_id": request.integration_id,
                "tool_id": request.tool_id,
                "action_digest": action_digest,
                "policy_effect": policy_decision.get("effect"),
                "matched_rule_ids": policy_decision.get("matched_rule_ids"),
                "approval_request_id": approval_request_id,
                "approval_consumed": approval_consumed,
                "enforcement_decision": decision,
                "execution_attempted": False,
                "execution_status": ExecutionStatus.PENDING_CLIENT_REPORT.value,
                "execution_source": ExecutionSource.CLIENT_REPORTED.value,
                "client_context": request.client_context,
                "idempotency_key": request.idempotency_key,
                "policy_decision": policy_decision,
                "action_summary": self._action_summary(action),
                "monitor": monitor,
                "monitoring_instruction": monitoring_instruction,
                "correlation_id": correlation_id,
                "trace_id": trace_id,
                "decision_phase": DecisionPhase.AUTHORIZE.value,
            },
            controls=build_allow_controls(
                policy_decision=policy_decision,
                phase=DecisionPhase.AUTHORIZE.value,
                include_approval=approval_consumed,
                approval_consumed=approval_consumed,
            ),
            finalize={
                "enforcement_decision": decision,
                "human_explanation": (
                    "Approved action consumed"
                    if approval_consumed
                    else policy_decision.get("human_explanation")
                    or "Action authorized without execution"
                ),
                "policy_effect": policy_decision.get("effect"),
                "matched_rule_ids": policy_decision.get("matched_rule_ids"),
                "policy_decision": policy_decision,
                "monitor": monitor,
                "monitoring_instruction": monitoring_instruction,
            },
        )
        self._attach_finops_reservation(request, receipt.id)
        self._db.commit()
        self._project_evidence(receipt.id)

        audit_action = (
            "runtime.action.allowed" if not monitor else "runtime.action.allowed"
        )
        log_admin_audit(
            trace_id=trace_id,
            actor_user_id="runtime",
            actor_role="runtime",
            action=audit_action,
            target={"receipt_id": str(receipt.id), "action_digest": action_digest},
        )

        effect = (
            EnforcementDecisionType.MONITOR.value
            if monitor
            else EnforcementDecisionType.ALLOW.value
        )
        return EnforcementResult(
            allowed=True,
            effect=effect,
            reason_code=None,
            human_explanation=receipt.human_explanation or "",
            runtime_identity_id=authority.runtime_identity.id,
            agent_version_id=authority.agent_version.id,
            action_digest=action_digest,
            policy_decision=policy_decision,
            approval_request_id=approval_request_id,
            approval_consumed=approval_consumed,
            monitor=monitor,
            monitoring_instruction=monitoring_instruction,
            execution_attempted=False,
            execution_status=ExecutionStatus.PENDING_CLIENT_REPORT.value,
            execution_source=ExecutionSource.CLIENT_REPORTED.value,
            correlation_id=correlation_id,
            trace_id=trace_id,
            receipt_id=receipt.id,
            enforcement_mode=EnforcementMode.HOOK_ENFORCED.value,
            deployment_control=DeploymentControl.LOCAL_HOOK.value,
            verification_status=VerificationStatus.DECLARED.value,
        )

    def report_execution_result(
        self,
        report: ClientExecutionReport,
        *,
        runtime_identity_id: UUID,
    ) -> EnforcementResult:
        """Record client-reported post-execution outcome for an existing receipt.

        Does not mutate original governance facts (decision, identity, action, policy).
        """
        receipt = None
        if report.enforcement_receipt_id:
            receipt = self._repo.get_receipt(report.enforcement_receipt_id)
        elif report.correlation_id:
            receipt = self._repo.find_by_correlation(
                runtime_identity_id=runtime_identity_id,
                correlation_id=report.correlation_id,
            )

        if not receipt:
            return EnforcementResult(
                allowed=False,
                effect=EnforcementDecisionType.DENY.value,
                reason_code=RuntimeEnforcementReasonCode.EXECUTION_REPORT_UNKNOWN_RECEIPT.value,
                human_explanation="Unknown enforcement receipt for execution report",
                runtime_identity_id=runtime_identity_id,
                execution_status=ExecutionStatus.NOT_ATTEMPTED.value,
            )

        if receipt.runtime_identity_id != runtime_identity_id:
            return EnforcementResult(
                allowed=False,
                effect=EnforcementDecisionType.DENY.value,
                reason_code=RuntimeEnforcementReasonCode.EXECUTION_REPORT_IDENTITY_MISMATCH.value,
                human_explanation="Execution report runtime identity does not match receipt",
                runtime_identity_id=runtime_identity_id,
                receipt_id=receipt.id,
                execution_status=receipt.execution_status,
            )

        if receipt.enforcement_decision == EnforcementDecisionType.DENY.value:
            return EnforcementResult(
                allowed=False,
                effect=EnforcementDecisionType.DENY.value,
                reason_code=RuntimeEnforcementReasonCode.EXECUTION_REPORT_DENIED_RECEIPT.value,
                human_explanation="Client-reported success cannot overwrite a DENY receipt",
                runtime_identity_id=runtime_identity_id,
                receipt_id=receipt.id,
                execution_status=receipt.execution_status,
                enforcement_mode=receipt.enforcement_mode,
            )

        if receipt.enforcement_decision not in (
            EnforcementDecisionType.ALLOW.value,
            EnforcementDecisionType.MONITOR.value,
        ):
            return EnforcementResult(
                allowed=False,
                effect=receipt.enforcement_decision,
                reason_code=RuntimeEnforcementReasonCode.EXECUTION_REPORT_INVALID.value,
                human_explanation="Execution reports are only accepted for ALLOW/MONITOR receipts",
                runtime_identity_id=runtime_identity_id,
                receipt_id=receipt.id,
                execution_status=receipt.execution_status,
            )

        status = (report.status or "").upper()
        if status not in {
            ExecutionStatus.SUCCEEDED.value,
            ExecutionStatus.FAILED.value,
            ExecutionStatus.UNKNOWN.value,
            ExecutionStatus.STARTED.value,
        }:
            return EnforcementResult(
                allowed=False,
                effect=EnforcementDecisionType.DENY.value,
                reason_code=RuntimeEnforcementReasonCode.EXECUTION_REPORT_INVALID.value,
                human_explanation=f"Invalid execution status: {report.status}",
                runtime_identity_id=runtime_identity_id,
                receipt_id=receipt.id,
                execution_status=receipt.execution_status,
            )

        # Idempotent replay of the same terminal status.
        if (
            receipt.execution_status
            in {
                ExecutionStatus.SUCCEEDED.value,
                ExecutionStatus.FAILED.value,
                ExecutionStatus.UNKNOWN.value,
            }
            and receipt.execution_status == status
        ):
            return EnforcementResult(
                allowed=True,
                effect=receipt.enforcement_decision,
                reason_code=None,
                human_explanation="Idempotent execution report replay",
                runtime_identity_id=receipt.runtime_identity_id,
                agent_version_id=receipt.agent_version_id,
                action_digest=receipt.action_digest,
                policy_decision=receipt.policy_decision,
                approval_request_id=receipt.approval_request_id,
                approval_consumed=receipt.approval_consumed,
                execution_attempted=receipt.execution_attempted,
                execution_status=receipt.execution_status,
                execution_source=receipt.execution_source,
                correlation_id=receipt.correlation_id,
                trace_id=receipt.trace_id,
                receipt_id=receipt.id,
                downstream_reference=receipt.downstream_reference,
                enforcement_mode=receipt.enforcement_mode,
                deployment_control=receipt.deployment_control,
                verification_status=receipt.verification_status,
            )

        now = _utcnow()
        safe_meta = _redact_parameters(dict(report.safe_result_metadata or {}))
        if report.client_event_id:
            safe_meta["client_event_id"] = report.client_event_id
        if report.hook_event:
            safe_meta["hook_event"] = report.hook_event
        if report.client_type:
            safe_meta["client_type"] = report.client_type

        self._repo.update_execution_outcome(
            receipt,
            execution_attempted=True,
            execution_status=status,
            execution_source=ExecutionSource.CLIENT_REPORTED.value,
            duration_ms=report.duration_ms,
            execution_report=safe_meta,
            reported_at=now,
            completed_at=now
            if status
            in {
                ExecutionStatus.SUCCEEDED.value,
                ExecutionStatus.FAILED.value,
                ExecutionStatus.UNKNOWN.value,
            }
            else receipt.completed_at,
        )
        # FinOps settlement from trusted usage (prefer provider/gateway over agent).
        if status in {
            ExecutionStatus.SUCCEEDED.value,
            ExecutionStatus.FAILED.value,
            ExecutionStatus.UNKNOWN.value,
        }:
            self._settle_finops_from_report(receipt, safe_meta)
        self._db.commit()
        self._project_evidence(receipt.id)

        audit_map = {
            ExecutionStatus.STARTED.value: "runtime.execution.reported_started",
            ExecutionStatus.SUCCEEDED.value: "runtime.execution.reported_succeeded",
            ExecutionStatus.FAILED.value: "runtime.execution.reported_failed",
            ExecutionStatus.UNKNOWN.value: "runtime.execution.report_missing",
        }
        log_admin_audit(
            trace_id=receipt.trace_id or generate_trace_id(),
            actor_user_id="runtime",
            actor_role="runtime",
            action=audit_map.get(status, "runtime.execution.reported_succeeded"),
            target={
                "receipt_id": str(receipt.id),
                "execution_status": status,
                "execution_source": ExecutionSource.CLIENT_REPORTED.value,
            },
        )

        return EnforcementResult(
            allowed=True,
            effect=receipt.enforcement_decision,
            reason_code=None,
            human_explanation="Client execution outcome recorded",
            runtime_identity_id=receipt.runtime_identity_id,
            agent_version_id=receipt.agent_version_id,
            action_digest=receipt.action_digest,
            policy_decision=receipt.policy_decision,
            approval_request_id=receipt.approval_request_id,
            approval_consumed=receipt.approval_consumed,
            execution_attempted=True,
            execution_status=status,
            execution_source=ExecutionSource.CLIENT_REPORTED.value,
            correlation_id=receipt.correlation_id,
            trace_id=receipt.trace_id,
            receipt_id=receipt.id,
            downstream_reference=receipt.downstream_reference,
            enforcement_mode=receipt.enforcement_mode,
            deployment_control=receipt.deployment_control,
            verification_status=receipt.verification_status,
        )

    def mark_stale_pending_reports(
        self,
        *,
        older_than_seconds: int = 3600,
        limit: int = 500,
    ) -> int:
        """PENDING_CLIENT_REPORT past threshold → UNKNOWN (not FAILED)."""
        from datetime import timedelta

        from rai_gateway.models.runtime_enforcement import RuntimeEnforcementReceipt

        cutoff = _utcnow() - timedelta(seconds=older_than_seconds)
        rows = (
            self._db.query(RuntimeEnforcementReceipt)
            .filter(
                RuntimeEnforcementReceipt.execution_status
                == ExecutionStatus.PENDING_CLIENT_REPORT.value,
                RuntimeEnforcementReceipt.started_at < cutoff,
            )
            .limit(limit)
            .all()
        )
        for receipt in rows:
            receipt.execution_status = ExecutionStatus.UNKNOWN.value
            receipt.reported_at = _utcnow()
            receipt.completed_at = _utcnow()
            log_admin_audit(
                trace_id=receipt.trace_id or generate_trace_id(),
                actor_user_id="runtime",
                actor_role="runtime",
                action="runtime.execution.report_missing",
                target={"receipt_id": str(receipt.id)},
            )
        if rows:
            self._db.commit()
            for receipt in rows:
                self._project_evidence(receipt.id)
        return len(rows)

    def _attach_finops_reservation(
        self, request: RuntimeActionRequest, receipt_id: UUID
    ) -> None:
        ctx = request.client_context or {}
        raw = ctx.get("finops_reservation_id")
        if not raw:
            return
        try:
            from rai_gateway.finops.service import FinOpsService

            FinOpsService(self._db).attach_receipt(UUID(str(raw)), receipt_id)
        except Exception:
            # FinOps attachment must not fail the authorize path.
            pass

    def _settle_finops_from_report(
        self, receipt: Any, safe_meta: dict[str, Any]
    ) -> None:
        try:
            from rai_gateway.finops.service import FinOpsService

            usage = (
                safe_meta.get("usage")
                if isinstance(safe_meta.get("usage"), dict)
                else None
            )
            cost = (
                safe_meta.get("cost")
                if isinstance(safe_meta.get("cost"), dict)
                else None
            )
            # Also accept top-level token fields from SDK/provider reports.
            if usage is None:
                token_keys = (
                    "input_tokens",
                    "output_tokens",
                    "prompt_tokens",
                    "completion_tokens",
                    "cached_input_tokens",
                    "reasoning_tokens",
                    "total_tokens",
                    "provider",
                    "model",
                )
                extracted = {k: safe_meta[k] for k in token_keys if k in safe_meta}
                if extracted:
                    usage = extracted
            if not usage and not cost:
                return
            settlement = FinOpsService(self._db).settle(
                usage=usage,
                cost=cost,
                enforcement_receipt_id=receipt.id,
                correlation_id=receipt.correlation_id,
                ai_system_id=receipt.ai_system_id,
                agent_id=receipt.agent_id,
                agent_version_id=receipt.agent_version_id,
                runtime_identity_id=receipt.runtime_identity_id,
                delegation_id=receipt.delegation_id,
            )
            self._record_compatible_metering_span(receipt, settlement, usage, cost)
            # Reconcile hierarchical COST/TOKEN budget reservations.
            if receipt.correlation_id:
                from rai_gateway.risk_intelligence.budgets import BudgetService

                BudgetService(self._db).reconcile_reservations(
                    idempotency_key=receipt.correlation_id,
                    settled_cost=settlement.metered_cost
                    or settlement.billed_cost
                    or settlement.actual_cost,
                    settled_tokens=float(settlement.total_tokens)
                    if settlement.total_tokens is not None
                    else None,
                    metering_span_id=settlement.metering_span_id,
                )
        except Exception:
            pass

    def _record_compatible_metering_span(
        self,
        receipt: Any,
        settlement: Any,
        usage: dict[str, Any] | None,
        cost: dict[str, Any] | None,
    ) -> None:
        from rai_gateway.finops.metering import RuntimeMeteringService
        from rai_gateway.models.evidence import RuntimeTrajectory

        trajectory = None
        if receipt.correlation_id:
            matches = (
                self._db.query(RuntimeTrajectory)
                .filter(
                    RuntimeTrajectory.correlation_id == receipt.correlation_id,
                    RuntimeTrajectory.ai_system_id == receipt.ai_system_id,
                )
                .all()
            )
            if len(matches) == 1:
                trajectory = matches[0]
        span_type = "TOOL_CALL" if getattr(receipt, "tool_id", None) else "MODEL_CALL"
        span = RuntimeMeteringService(self._db).record_span(
            ai_system_id=receipt.ai_system_id,
            agent_id=receipt.agent_id,
            agent_version_id=receipt.agent_version_id,
            runtime_identity_id=receipt.runtime_identity_id,
            delegation_id=receipt.delegation_id,
            runtime_conversation_id=trajectory.runtime_conversation_id
            if trajectory
            else None,
            trajectory_id=trajectory.id if trajectory else None,
            enforcement_receipt_id=receipt.id,
            correlation_id=receipt.correlation_id,
            span_type=span_type,
            tool_id=getattr(receipt, "tool_id", None),
            provider=(usage or {}).get("provider") or settlement.provider,
            model=(usage or {}).get("model") or settlement.model,
            usage=usage,
            cost=cost,
            external_span_id=f"receipt:{receipt.id}",
        )
        settlement.metering_span_id = span.id
        if trajectory and not settlement.trajectory_id:
            settlement.trajectory_id = trajectory.id
            settlement.runtime_conversation_id = trajectory.runtime_conversation_id

    def _action_summary(self, action: ProposedAction) -> dict[str, Any]:
        return {
            "integration_type": action.integration_type,
            "integration_id": str(action.integration_id)
            if action.integration_id
            else None,
            "tool_id": str(action.tool_id) if action.tool_id else None,
            "target": action.target.to_dict() if action.target else None,
            "parameters": _redact_parameters(action.parameters or {}),
            "environment": action.environment,
        }

    def _map_authority_reason(self, reason: str | None) -> str:
        mapping = {
            "RUNTIME_IDENTITY_INELIGIBLE": RuntimeEnforcementReasonCode.RUNTIME_IDENTITY_INELIGIBLE.value,
            "AUTHORITY_SCOPE_EXCEEDED": RuntimeEnforcementReasonCode.AUTHORITY_SCOPE_EXCEEDED.value,
            "AGENT_VERSION_INELIGIBLE": RuntimeEnforcementReasonCode.AGENT_INELIGIBLE.value,
            "CREDENTIAL_REVOKED": RuntimeEnforcementReasonCode.RUNTIME_AUTHENTICATION_FAILED.value,
            "CREDENTIAL_EXPIRED": RuntimeEnforcementReasonCode.RUNTIME_AUTHENTICATION_FAILED.value,
            "UNAUTHENTICATED": RuntimeEnforcementReasonCode.RUNTIME_AUTHENTICATION_FAILED.value,
        }
        return mapping.get(
            reason or "",
            RuntimeEnforcementReasonCode.RUNTIME_AUTHENTICATION_FAILED.value,
        )

    def _map_approval_reason(self, reason: str | None) -> str:
        mapping = {
            ApprovalDenialCode.AUTHORITY_SCOPE_EXCEEDED.value: RuntimeEnforcementReasonCode.AUTHORITY_SCOPE_EXCEEDED.value,
            ApprovalDenialCode.AGENT_INELIGIBLE.value: RuntimeEnforcementReasonCode.AGENT_INELIGIBLE.value,
            ApprovalDenialCode.RUNTIME_IDENTITY_INELIGIBLE.value: RuntimeEnforcementReasonCode.RUNTIME_IDENTITY_INELIGIBLE.value,
            ApprovalDenialCode.APPROVAL_REQUIRED.value: RuntimeEnforcementReasonCode.APPROVAL_REQUIRED.value,
            ApprovalDenialCode.APPROVAL_PENDING.value: RuntimeEnforcementReasonCode.APPROVAL_PENDING.value,
            ApprovalDenialCode.APPROVAL_EXPIRED.value: RuntimeEnforcementReasonCode.APPROVAL_EXPIRED.value,
            ApprovalDenialCode.APPROVAL_ALREADY_CONSUMED.value: RuntimeEnforcementReasonCode.APPROVAL_ALREADY_CONSUMED.value,
            ApprovalDenialCode.APPROVAL_ACTION_MISMATCH.value: RuntimeEnforcementReasonCode.APPROVAL_ACTION_MISMATCH.value,
            ApprovalDenialCode.APPROVAL_NOT_FOUND.value: RuntimeEnforcementReasonCode.APPROVAL_NOT_FOUND.value,
            ApprovalDenialCode.APPROVAL_REJECTED.value: RuntimeEnforcementReasonCode.APPROVAL_REJECTED.value,
            ApprovalDenialCode.APPROVAL_CANCELLED.value: RuntimeEnforcementReasonCode.APPROVAL_CANCELLED.value,
            ApprovalDenialCode.APPROVAL_AUTHORITY_CHANGED.value: RuntimeEnforcementReasonCode.RUNTIME_STATE_CHANGED.value,
        }
        return mapping.get(
            reason or "", RuntimeEnforcementReasonCode.RUNTIME_STATE_CHANGED.value
        )
