"""Client hook authorization orchestration."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from rai_gateway.approval.consumption import ApprovalConsumptionService
from rai_gateway.approval.domain import ProposedAction
from rai_gateway.client_hooks.adapters import GeminiCLIHookAdapter, get_adapter
from rai_gateway.client_hooks.domain import (
    BRIDGE_VERSION,
    DEFAULT_COVERAGE,
    PROTOCOL_VERSION,
    ClientType,
    HookAuthorizeResult,
    IntegrationStatus,
    NativeHookEvent,
)
from rai_gateway.client_hooks.payload import (
    extract_cursor_mcp_fields,
    extract_generic_tool_fields,
)
from rai_gateway.client_hooks.resource_mapping import HookResourceMapper
from rai_gateway.core.observability import generate_trace_id, log_admin_audit
from rai_gateway.identity.resolver import RuntimeAuthorityResolver
from rai_gateway.models.client_hooks import RuntimeClientIntegration
from rai_gateway.models.runtime_enforcement import RuntimeEnforcementReceipt
from rai_gateway.runtime_enforcement.domain import (
    ClientExecutionReport,
    EnforcementDecisionType,
    EnforcementMode,
    EnforcementResult,
    ExecutionStatus,
)
from rai_gateway.runtime_enforcement.service import RuntimeEnforcementService


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _hook_debug_enabled() -> bool:
    return os.environ.get("RAI_HOOK_DEBUG", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


class ClientIntegrationRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def list_for_identity(self, identity_id: UUID) -> list[RuntimeClientIntegration]:
        return (
            self._db.query(RuntimeClientIntegration)
            .filter(RuntimeClientIntegration.runtime_identity_id == identity_id)
            .order_by(RuntimeClientIntegration.client_type)
            .all()
        )

    def get(
        self, identity_id: UUID, client_type: str
    ) -> RuntimeClientIntegration | None:
        return (
            self._db.query(RuntimeClientIntegration)
            .filter(
                RuntimeClientIntegration.runtime_identity_id == identity_id,
                RuntimeClientIntegration.client_type == client_type,
            )
            .first()
        )

    def upsert(
        self,
        identity_id: UUID,
        client_type: str,
        *,
        enforcement_mode: str = EnforcementMode.HOOK_ENFORCED.value,
        status: str = IntegrationStatus.WAITING_FOR_HEARTBEAT.value,
        coverage: dict[str, str] | None = None,
    ) -> RuntimeClientIntegration:
        row = self.get(identity_id, client_type)
        if not row:
            row = RuntimeClientIntegration(
                runtime_identity_id=identity_id,
                client_type=client_type,
                enforcement_mode=enforcement_mode,
                deployment_control="LOCAL_HOOK",
                verification_status="DECLARED",
                status=status,
                coverage=coverage or DEFAULT_COVERAGE.get(client_type, {}),
                configuration_status="GENERATED",
            )
            self._db.add(row)
        else:
            row.enforcement_mode = enforcement_mode
            row.status = status
            row.configuration_status = "GENERATED"
            if coverage:
                row.coverage = coverage
        self._db.commit()
        self._db.refresh(row)
        return row

    def record_heartbeat(
        self,
        identity_id: UUID,
        client_type: str,
        *,
        client_version: str | None,
        bridge_version: str | None,
        protocol_version: str | None,
        coverage: dict[str, str] | None = None,
        deployment_control: str | None = None,
        verification_status: str | None = None,
        observed_bridge_hash: str | None = None,
    ) -> RuntimeClientIntegration:
        from rai_gateway.runtime_enforcement.domain import (
            MANAGED_HOOK_CONTROLS,
            DeploymentControl,
            VerificationStatus,
        )

        row = self.get(identity_id, client_type)
        if not row:
            row = self.upsert(identity_id, client_type)
        previous_coverage = dict(row.coverage or {})
        previous_assurance = (
            row.deployment_control,
            row.verification_status,
        )
        row.client_version = client_version
        row.bridge_version = bridge_version or BRIDGE_VERSION
        row.protocol_version = str(protocol_version or PROTOCOL_VERSION)
        row.last_seen_at = _utcnow()
        row.status = IntegrationStatus.CONNECTED.value
        if coverage:
            row.coverage = coverage
        if observed_bridge_hash:
            row.observed_bridge_hash = observed_bridge_hash

        # Clients may declare a managed profile label, but unregistered managed
        # claims are demoted to LOCAL_HOOK until admin registers expected hash.
        if deployment_control:
            if (
                deployment_control in MANAGED_HOOK_CONTROLS
                and not row.expected_bridge_hash
            ):
                row.deployment_control = DeploymentControl.LOCAL_HOOK.value
            else:
                row.deployment_control = deployment_control

        # Default: never accept client-claimed VERIFIED.
        if verification_status:
            if verification_status == VerificationStatus.VERIFIED.value:
                row.verification_status = VerificationStatus.DECLARED.value
            else:
                row.verification_status = verification_status

        # Server attestation: managed profile + matching hash/version → VERIFIED.
        control = row.deployment_control or DeploymentControl.LOCAL_HOOK.value
        if control in MANAGED_HOOK_CONTROLS and row.expected_bridge_hash:
            observed = (observed_bridge_hash or row.observed_bridge_hash or "").strip()
            expected = (row.expected_bridge_hash or "").strip()
            version_ok = True
            if row.expected_bridge_version:
                version_ok = (bridge_version or row.bridge_version or "") == (
                    row.expected_bridge_version
                )
            if observed and expected and observed == expected and version_ok:
                row.verification_status = VerificationStatus.VERIFIED.value
                row.last_attested_at = _utcnow()
            else:
                # Managed but attestation failed / missing → DECLARED (not VERIFIED).
                row.verification_status = VerificationStatus.DECLARED.value
        elif control == DeploymentControl.LOCAL_HOOK.value:
            if row.verification_status == VerificationStatus.VERIFIED.value:
                row.verification_status = VerificationStatus.DECLARED.value

        self._db.commit()
        self._db.refresh(row)
        if coverage and coverage != previous_coverage:
            log_admin_audit(
                trace_id=generate_trace_id(),
                actor_user_id="runtime",
                actor_role="runtime",
                action="client.integration.coverage_changed",
                target={
                    "runtime_identity_id": str(identity_id),
                    "client_type": client_type,
                },
            )
        if (row.deployment_control, row.verification_status) != previous_assurance:
            log_admin_audit(
                trace_id=generate_trace_id(),
                actor_user_id="runtime",
                actor_role="runtime",
                action="client.integration.assurance_changed",
                target={
                    "runtime_identity_id": str(identity_id),
                    "client_type": client_type,
                    "deployment_control": row.deployment_control,
                    "verification_status": row.verification_status,
                },
            )
        return row

    def register_managed_profile(
        self,
        identity_id: UUID,
        client_type: str,
        *,
        deployment_control: str,
        expected_bridge_hash: str,
        expected_bridge_version: str | None = None,
        managed_profile_key: str | None = None,
    ) -> RuntimeClientIntegration:
        """Admin-registered managed profile — required before VERIFIED attestation."""
        from rai_gateway.runtime_enforcement.domain import (
            MANAGED_HOOK_CONTROLS,
            VerificationStatus,
        )

        if deployment_control not in MANAGED_HOOK_CONTROLS:
            raise ValueError(
                f"deployment_control must be managed "
                f"({sorted(MANAGED_HOOK_CONTROLS)}), got {deployment_control!r}"
            )
        if not expected_bridge_hash or not expected_bridge_hash.strip():
            raise ValueError("expected_bridge_hash is required")

        row = self.get(identity_id, client_type)
        if not row:
            row = self.upsert(identity_id, client_type)
        row.deployment_control = deployment_control
        row.expected_bridge_hash = expected_bridge_hash.strip()
        row.expected_bridge_version = expected_bridge_version
        row.managed_profile_key = managed_profile_key
        # Profile registration alone is not attestation.
        row.verification_status = VerificationStatus.DECLARED.value
        self._db.commit()
        self._db.refresh(row)
        log_admin_audit(
            trace_id=generate_trace_id(),
            actor_user_id="admin",
            actor_role="admin",
            action="client.integration.managed_profile_registered",
            target={
                "runtime_identity_id": str(identity_id),
                "client_type": client_type,
                "deployment_control": deployment_control,
                "managed_profile_key": managed_profile_key,
            },
        )
        return row

    def record_decision(
        self,
        identity_id: UUID,
        client_type: str,
        effect: str,
    ) -> None:
        row = self.get(identity_id, client_type)
        if not row:
            return
        row.last_decision_at = _utcnow()
        row.last_decision_effect = effect
        self._db.commit()

    def disconnect(
        self, identity_id: UUID, client_type: str
    ) -> RuntimeClientIntegration | None:
        row = self.get(identity_id, client_type)
        if not row:
            return None
        row.status = IntegrationStatus.DISCONNECTED.value
        self._db.commit()
        self._db.refresh(row)
        return row


class ClientHookService:
    """Normalize native hook events and call WP4 authorize."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._mapper = HookResourceMapper(db)
        self._integrations = ClientIntegrationRepository(db)
        self._enforcement = RuntimeEnforcementService(db)
        self._resolver = RuntimeAuthorityResolver(db)

    def authorize_hook(
        self,
        event: NativeHookEvent,
        *,
        credential_secret: str,
    ) -> HookAuthorizeResult:
        adapter = get_adapter(event.client_type)
        trace_id = event.correlation_id or generate_trace_id()

        try:
            authority = self._resolver.resolve_from_credential(
                credential_secret,
                delegation_id=event.delegation_id,
            )
        except Exception as exc:
            return self._failure_block(
                adapter,
                reason=str(exc),
                reason_code="RUNTIME_AUTHENTICATION_FAILED",
                trace_id=trace_id,
            )

        runtime_identity_id = authority.runtime_identity.id

        if adapter.is_post_execution_event(event.hook_event):
            return self._report_execution(
                adapter=adapter,
                event=event,
                authority=authority,
                runtime_identity_id=runtime_identity_id,
                trace_id=trace_id,
            )

        if adapter.is_observation_event(event.hook_event):
            return self._observe_lifecycle(
                adapter=adapter,
                event=event,
                authority=authority,
                runtime_identity_id=runtime_identity_id,
                trace_id=trace_id,
            )

        if not adapter.is_enforced_event(event.hook_event):
            allow = adapter.translate_allow({})
            return HookAuthorizeResult(
                allowed=True,
                effect="ALLOW",
                reason_code=None,
                human_explanation="Non-enforced hook event; observe only",
                client_response=allow,
                enforcement_result={"effect": "ALLOW", "monitor": True},
                exit_code=0,
            )

        mapping = self._resolve_mapping(event, runtime_identity_id)
        debug_enabled = _hook_debug_enabled()
        debug_info = None
        if debug_enabled:
            native_mcp_name, native_tool_name, tool_input = self._debug_native_fields(
                event
            )
            debug_info = {
                "native_mcp": native_mcp_name,
                "native_tool": native_tool_name,
                "tool_input": tool_input,
                "mapped_mcp_id": str(mapping.integration_id)
                if mapping.integration_id
                else None,
                "mapped_tool_id": str(mapping.tool_id) if mapping.tool_id else None,
                "mapping_failure_reason": mapping.error_message
                if not mapping.ok
                else None,
            }
        if not mapping.ok:
            return self._failure_block(
                adapter,
                reason=mapping.error_message or "Resource mapping failed",
                reason_code=mapping.error_code or "RESOURCE_NOT_REGISTERED",
                trace_id=trace_id,
                debug=debug_info,
            )

        delegation_id = self._resolved_delegation_id(authority, event)
        try:
            normalized = adapter.normalize_event(
                event,
                mapping,
                runtime_identity_id=runtime_identity_id,
                delegation_id=delegation_id,
            )
        except ValueError as exc:
            return self._failure_block(
                adapter,
                reason=str(exc),
                reason_code="INVALID_HOOK_PAYLOAD",
                trace_id=trace_id,
                debug=debug_info,
            )

        # Attach safe observed client context; never authoritative identity.
        normalized.request.client_context = self._extract_client_context(event)
        if not normalized.request.correlation_id:
            normalized.request.correlation_id = trace_id

        try:
            result = self._enforcement.authorize(
                normalized.request,
                credential_secret=credential_secret,
            )
        except Exception as exc:
            return self._failure_block(
                adapter,
                reason=f"RAI authorization unavailable: {exc}",
                reason_code="DOWNSTREAM_UNAVAILABLE",
                trace_id=trace_id,
                debug=debug_info,
            )

        if (
            not result.allowed
            and result.effect == EnforcementDecisionType.REQUIRE_APPROVAL.value
        ):
            proposed = self._to_proposed_action(
                normalized.request, authority, runtime_identity_id
            )
            consumption = ApprovalConsumptionService(self._db).consume(
                authority,
                proposed,
                correlation_id=trace_id,
            )
            if consumption.allowed:
                result = EnforcementResult(
                    allowed=True,
                    effect=EnforcementDecisionType.ALLOW.value,
                    reason_code=None,
                    human_explanation="Approved action authorized for native execution",
                    runtime_identity_id=runtime_identity_id,
                    agent_version_id=authority.agent_version.id,
                    action_digest=result.action_digest,
                    policy_decision=result.policy_decision,
                    approval_request_id=consumption.approval_request_id,
                    approval_consumed=True,
                    enforcement_mode=EnforcementMode.HOOK_ENFORCED.value,
                    correlation_id=trace_id,
                    trace_id=trace_id,
                    receipt_id=result.receipt_id,
                )

        result_dict = result.to_dict()
        receipt_id = result.receipt_id
        approval_id = result.approval_request_id

        if result.allowed and result.effect in {"ALLOW", "MONITOR"}:
            client_response = adapter.translate_allow(result_dict)
            audit_action = "client_hook.authorized"
            exit_code = 0
        else:
            client_response = adapter.translate_deny(result_dict)
            audit_action = (
                "client_hook.approval_required"
                if result.effect == "REQUIRE_APPROVAL"
                else "client_hook.denied"
            )
            exit_code = 0

        self._integrations.record_decision(
            runtime_identity_id, event.client_type, result.effect
        )

        log_admin_audit(
            trace_id=trace_id,
            actor_user_id="runtime",
            actor_role="runtime",
            action=audit_action,
            target={
                "client_type": event.client_type,
                "hook_event": event.hook_event,
                "effect": result.effect,
                "runtime_identity_id": str(runtime_identity_id),
            },
        )

        return HookAuthorizeResult(
            allowed=result.allowed,
            effect=result.effect,
            reason_code=result.reason_code,
            human_explanation=result.human_explanation,
            client_response=client_response,
            enforcement_result=result_dict,
            debug=debug_info,
            receipt_id=receipt_id,
            approval_request_id=approval_id,
            exit_code=exit_code,
        )

    def test_connection(
        self,
        *,
        identity_id: UUID,
        client_type: str,
        credential_secret: str,
    ) -> dict[str, Any]:
        try:
            authority = self._resolver.resolve_from_credential(credential_secret)
        except Exception as exc:
            return {"ok": False, "message": str(exc), "checks": {"credential": False}}

        if authority.runtime_identity.id != identity_id:
            return {
                "ok": False,
                "message": "Credential does not match runtime identity",
                "checks": {"credential": False, "identity_match": False},
            }

        adapter = get_adapter(client_type)
        catalog_ok = bool(authority.agent_version_id)
        return {
            "ok": True,
            "message": "Connection test passed",
            "checks": {
                "credential": True,
                "identity_match": True,
                "identity_eligible": bool(
                    authority.eligibility and authority.eligibility.eligible
                ),
                "client_type": client_type,
                "adapter": adapter.client_type,
                "resource_catalog": catalog_ok,
                "protocol_version": PROTOCOL_VERSION,
            },
        }

    def generate_setup_config(
        self,
        identity_id: UUID,
        client_type: str,
    ) -> dict[str, Any]:
        integration = self._integrations.upsert(identity_id, client_type)
        log_admin_audit(
            trace_id=generate_trace_id(),
            actor_user_id="admin",
            actor_role="admin",
            action="client_integration.created",
            target={
                "runtime_identity_id": str(identity_id),
                "client_type": client_type,
            },
        )

        hook_cmd = f".cursor/hooks/rai-hook {client_type}"
        if client_type == ClientType.GEMINI_CLI.value:
            hook_cmd = "$GEMINI_PROJECT_DIR/.gemini/hooks/rai-hook gemini BeforeTool"
        elif client_type == ClientType.CLAUDE_CODE.value:
            hook_cmd = ".claude/hooks/rai-hook claude_code PreToolUse"

        configs = {
            ClientType.CURSOR.value: {
                "version": 1,
                "hooks": {
                    "beforeMCPExecution": [
                        {
                            "command": f"{hook_cmd} beforeMCPExecution",
                            "timeout": 10,
                            "failClosed": True,
                        }
                    ],
                    "beforeShellExecution": [
                        {
                            "command": f"{hook_cmd} beforeShellExecution",
                            "timeout": 10,
                            "failClosed": True,
                        }
                    ],
                    "afterMCPExecution": [
                        {
                            "command": f"{hook_cmd} afterMCPExecution",
                            "timeout": 10,
                        }
                    ],
                    "afterShellExecution": [
                        {
                            "command": f"{hook_cmd} afterShellExecution",
                            "timeout": 10,
                        }
                    ],
                    "beforeSubmitPrompt": [
                        {
                            "command": f"{hook_cmd} beforeSubmitPrompt",
                            "timeout": 10,
                        }
                    ],
                    "afterAgentResponse": [
                        {
                            "command": f"{hook_cmd} afterAgentResponse",
                            "timeout": 10,
                        }
                    ],
                    "afterAgentThought": [
                        {
                            "command": f"{hook_cmd} afterAgentThought",
                            "timeout": 10,
                        }
                    ],
                },
            },
            ClientType.CLAUDE_CODE.value: {
                "hooks": {
                    "PreToolUse": [
                        {
                            "command": hook_cmd,
                            "timeout": 10,
                        }
                    ],
                    "PostToolUse": [
                        {
                            "command": ".claude/hooks/rai-hook claude_code PostToolUse",
                            "timeout": 10,
                        }
                    ],
                    "UserPromptSubmit": [
                        {
                            "command": ".claude/hooks/rai-hook claude_code UserPromptSubmit",
                            "timeout": 10,
                        }
                    ],
                    "Stop": [
                        {
                            "command": ".claude/hooks/rai-hook claude_code Stop",
                            "timeout": 10,
                        }
                    ],
                }
            },
            ClientType.GEMINI_CLI.value: {
                "hooks": {
                    "BeforeTool": [
                        {
                            "matcher": "*",
                            "hooks": [
                                {
                                    "name": "rai-runtime-enforcement",
                                    "type": "command",
                                    "command": hook_cmd,
                                    "timeout": 10000,
                                }
                            ],
                        }
                    ],
                    "AfterTool": [
                        {
                            "matcher": "*",
                            "hooks": [
                                {
                                    "name": "rai-post-execution-report",
                                    "type": "command",
                                    "command": "$GEMINI_PROJECT_DIR/.gemini/hooks/rai-hook gemini AfterTool",
                                    "timeout": 10000,
                                }
                            ],
                        }
                    ],
                    "BeforeAgent": [
                        {
                            "matcher": "*",
                            "hooks": [
                                {
                                    "name": "rai-observe-prompt",
                                    "type": "command",
                                    "command": "$GEMINI_PROJECT_DIR/.gemini/hooks/rai-hook gemini BeforeAgent",
                                    "timeout": 10000,
                                }
                            ],
                        }
                    ],
                    "BeforeModel": [
                        {
                            "matcher": "*",
                            "hooks": [
                                {
                                    "name": "rai-observe-model-request",
                                    "type": "command",
                                    "command": "$GEMINI_PROJECT_DIR/.gemini/hooks/rai-hook gemini BeforeModel",
                                    "timeout": 10000,
                                }
                            ],
                        }
                    ],
                    "AfterModel": [
                        {
                            "matcher": "*",
                            "hooks": [
                                {
                                    "name": "rai-observe-model-response",
                                    "type": "command",
                                    "command": "$GEMINI_PROJECT_DIR/.gemini/hooks/rai-hook gemini AfterModel",
                                    "timeout": 10000,
                                }
                            ],
                        }
                    ],
                    "AfterAgent": [
                        {
                            "matcher": "*",
                            "hooks": [
                                {
                                    "name": "rai-observe-output",
                                    "type": "command",
                                    "command": "$GEMINI_PROJECT_DIR/.gemini/hooks/rai-hook gemini AfterAgent",
                                    "timeout": 10000,
                                }
                            ],
                        }
                    ],
                }
            },
        }

        env_template = {
            "RAI_BASE_URL": "http://localhost:8001",
            "RAI_AGENT_KEY": "<issue-runtime-credential-and-set-locally>",
        }

        return {
            "integration_id": str(integration.id),
            "client_type": client_type,
            "enforcement_mode": integration.enforcement_mode,
            "status": integration.status,
            "coverage": integration.coverage or DEFAULT_COVERAGE.get(client_type, {}),
            "protocol_version": PROTOCOL_VERSION,
            "bridge_version": BRIDGE_VERSION,
            "hook_config": configs.get(client_type, {}),
            "environment": env_template,
            "install_steps": [
                "Copy scripts/rai-hook to your project hook directory",
                "Set RAI_BASE_URL and RAI_AGENT_KEY in your environment",
                "Merge the generated hook config into your client settings",
                "Run Test Connection from the RAI control plane",
            ],
        }

    def _observe_lifecycle(
        self,
        *,
        adapter,
        event: NativeHookEvent,
        authority,
        runtime_identity_id: UUID,
        trace_id: str,
    ) -> HookAuthorizeResult:
        """Ingest prompt/model/output observations into WP5 trajectories (never block)."""
        from rai_gateway.client_hooks.observation import extract_observation_payload
        from rai_gateway.evidence.service import TrajectoryService

        allow = adapter.translate_allow({})
        event_type = adapter.observation_event_type(event.hook_event)
        if not event_type:
            return HookAuthorizeResult(
                allowed=True,
                effect="ALLOW",
                reason_code=None,
                human_explanation="Unrecognized observation hook; ignored",
                client_response=allow,
                enforcement_result={"effect": "ALLOW", "monitor": True},
                exit_code=0,
            )

        client_context = self._extract_client_context(event)
        observation = extract_observation_payload(
            event.client_type, event.hook_event, event.payload
        )
        integration = self._integrations.get(runtime_identity_id, event.client_type)
        delegation_id = self._resolved_delegation_id(authority, event)
        try:
            TrajectoryService(self._db).ingest_client_observation(
                ai_system_id=authority.ai_system.id,
                agent_id=authority.agent.id,
                agent_version_id=authority.agent_version.id,
                runtime_identity_id=runtime_identity_id,
                event_type=event_type,
                client_type=event.client_type,
                hook_event=event.hook_event,
                observation_payload=observation,
                client_integration_id=integration.id if integration else None,
                delegation_id=delegation_id,
                conversation_id=client_context.get("conversation_id"),
                client_session_id=client_context.get("session_id"),
                correlation_id=event.correlation_id or trace_id,
                generation_id=client_context.get("generation_id"),
                deployment_control=getattr(integration, "deployment_control", None)
                if integration
                else None,
                verification_status=getattr(integration, "verification_status", None)
                if integration
                else None,
            )
            self._db.commit()
            log_admin_audit(
                trace_id=trace_id,
                actor_user_id="runtime",
                actor_role="runtime",
                action="evidence.observation.ingested",
                target={
                    "event_type": event_type,
                    "hook_event": event.hook_event,
                    "client_type": event.client_type,
                    "runtime_identity_id": str(runtime_identity_id),
                },
            )
        except Exception:  # noqa: BLE001 — observation must never block the client
            self._db.rollback()
            log_admin_audit(
                trace_id=trace_id,
                actor_user_id="runtime",
                actor_role="runtime",
                action="evidence.observation.failed",
                target={
                    "hook_event": event.hook_event,
                    "client_type": event.client_type,
                    "runtime_identity_id": str(runtime_identity_id),
                },
            )
            try:
                from rai_gateway.evidence.domain import EvidenceFindingType
                from rai_gateway.evidence.service import TrajectoryService as _TS

                # Best-effort signal only — still never block the client.
                traj_svc = _TS(self._db)
                traj = traj_svc.get_or_create_trajectory(
                    ai_system_id=authority.ai_system.id,
                    agent_id=authority.agent.id,
                    agent_version_id=authority.agent_version.id,
                    runtime_identity_id=runtime_identity_id,
                    conversation_id=client_context.get("conversation_id"),
                    client_session_id=client_context.get("session_id"),
                    correlation_id=event.correlation_id or trace_id,
                    generation_id=client_context.get("generation_id"),
                )
                traj_svc.ensure_finding(
                    traj,
                    finding_type=EvidenceFindingType.CONTENT_CAPTURE_FAILED.value,
                    severity="MEDIUM",
                    title="Content capture failed",
                    description=(
                        f"Failed to ingest {event_type} from {event.client_type} "
                        f"hook {event.hook_event}."
                    ),
                )
                self._db.commit()
            except Exception:  # noqa: BLE001
                self._db.rollback()

        return HookAuthorizeResult(
            allowed=True,
            effect="ALLOW",
            reason_code=None,
            human_explanation="Observation recorded; not an enforcement boundary",
            client_response=allow,
            enforcement_result={"effect": "ALLOW", "monitor": True},
            exit_code=0,
        )

    def _report_execution(
        self,
        *,
        adapter,
        event: NativeHookEvent,
        authority,
        runtime_identity_id: UUID,
        trace_id: str,
    ) -> HookAuthorizeResult:
        """Observe-only post-execution reporting for afterMCPExecution / equivalents."""
        allow = adapter.translate_allow({})
        outcome = self._extract_execution_outcome(event)
        payload = event.payload or {}

        receipt_id_raw = (
            payload.get("enforcement_receipt_id")
            or payload.get("receipt_id")
            or payload.get("rai_receipt_id")
        )
        receipt_uuid = None
        if receipt_id_raw:
            try:
                receipt_uuid = UUID(str(receipt_id_raw))
            except (TypeError, ValueError):
                receipt_uuid = None

        status = (
            ExecutionStatus.SUCCEEDED.value
            if outcome["success"]
            else ExecutionStatus.FAILED.value
        )
        if outcome.get("unknown"):
            status = ExecutionStatus.UNKNOWN.value

        # Prefer server-issued receipt / correlation; fall back to heuristic digest match.
        if receipt_uuid or event.correlation_id or payload.get("correlation_id"):
            result = self._enforcement.report_execution_result(
                ClientExecutionReport(
                    enforcement_receipt_id=receipt_uuid,
                    correlation_id=event.correlation_id
                    or payload.get("correlation_id"),
                    client_type=event.client_type,
                    hook_event=event.hook_event,
                    status=status,
                    duration_ms=outcome.get("duration_ms"),
                    safe_result_metadata={
                        k: v
                        for k, v in {
                            "error": outcome.get("error"),
                            "downstream_reference": outcome.get("downstream_reference"),
                        }.items()
                        if v is not None
                    },
                    client_event_id=payload.get("client_event_id")
                    or payload.get("generation_id"),
                ),
                runtime_identity_id=runtime_identity_id,
            )
            if result.reason_code in {
                "EXECUTION_REPORT_UNKNOWN_RECEIPT",
                "EXECUTION_REPORT_IDENTITY_MISMATCH",
                "EXECUTION_REPORT_DENIED_RECEIPT",
                "EXECUTION_REPORT_INVALID",
            }:
                # Fall through to heuristic only for unknown receipt; hard-fail others.
                if result.reason_code != "EXECUTION_REPORT_UNKNOWN_RECEIPT":
                    return HookAuthorizeResult(
                        allowed=True,
                        effect="ALLOW",
                        reason_code=result.reason_code,
                        human_explanation=result.human_explanation,
                        client_response=allow,
                        enforcement_result=result.to_dict(),
                        receipt_id=result.receipt_id,
                        exit_code=0,
                    )
            else:
                self._integrations.record_decision(
                    runtime_identity_id, event.client_type, "ALLOW"
                )
                return HookAuthorizeResult(
                    allowed=True,
                    effect="ALLOW",
                    reason_code=None,
                    human_explanation="Post-execution outcome recorded",
                    client_response=allow,
                    enforcement_result=result.to_dict(),
                    receipt_id=result.receipt_id,
                    exit_code=0,
                )

        mapping = self._resolve_mapping(event, runtime_identity_id)
        if not mapping.ok or not mapping.tool_id:
            log_admin_audit(
                trace_id=trace_id,
                actor_user_id="runtime",
                actor_role="runtime",
                action="client_hook.execution_report_unmapped",
                target={
                    "client_type": event.client_type,
                    "hook_event": event.hook_event,
                    "reason": mapping.error_message,
                },
            )
            return HookAuthorizeResult(
                allowed=True,
                effect="ALLOW",
                reason_code=None,
                human_explanation="Post-execution event observed; tool mapping unavailable",
                client_response=allow,
                enforcement_result={"effect": "ALLOW", "monitor": True},
                exit_code=0,
            )

        delegation_id = self._resolved_delegation_id(authority, event)
        try:
            normalized = adapter.normalize_event(
                event,
                mapping,
                runtime_identity_id=runtime_identity_id,
                delegation_id=delegation_id,
            )
        except ValueError:
            from rai_gateway.runtime_enforcement.domain import RuntimeActionRequest

            class _Tmp:
                request = RuntimeActionRequest(
                    integration_type=mapping.integration_type,
                    integration_id=mapping.integration_id,
                    tool_id=mapping.tool_id,
                    parameters=mapping.parameters,
                    delegation_id=delegation_id,
                    correlation_id=event.correlation_id,
                )

            normalized = _Tmp()

        proposed = self._to_proposed_action(
            normalized.request, authority, runtime_identity_id
        )
        from rai_gateway.approval.canonicalizer import canonicalize_action

        _, action_digest = canonicalize_action(proposed)
        receipt = (
            self._db.query(RuntimeEnforcementReceipt)
            .filter(
                RuntimeEnforcementReceipt.runtime_identity_id == runtime_identity_id,
                RuntimeEnforcementReceipt.tool_id == mapping.tool_id,
                RuntimeEnforcementReceipt.action_digest == action_digest,
                RuntimeEnforcementReceipt.enforcement_decision.in_(
                    [
                        EnforcementDecisionType.ALLOW.value,
                        EnforcementDecisionType.MONITOR.value,
                    ]
                ),
                RuntimeEnforcementReceipt.execution_status.in_(
                    [
                        ExecutionStatus.PENDING_CLIENT_REPORT.value,
                        ExecutionStatus.NOT_ATTEMPTED.value,
                        ExecutionStatus.STARTED.value,
                        ExecutionStatus.IN_PROGRESS.value,
                    ]
                ),
            )
            .order_by(RuntimeEnforcementReceipt.started_at.desc())
            .first()
        )
        if not receipt:
            return HookAuthorizeResult(
                allowed=True,
                effect="ALLOW",
                reason_code=None,
                human_explanation="Post-execution event observed; no matching receipt",
                client_response=allow,
                enforcement_result={"effect": "ALLOW", "monitor": True},
                exit_code=0,
            )

        result = self._enforcement.report_execution_result(
            ClientExecutionReport(
                enforcement_receipt_id=receipt.id,
                client_type=event.client_type,
                hook_event=event.hook_event,
                status=status,
                duration_ms=outcome.get("duration_ms"),
                safe_result_metadata={
                    k: v
                    for k, v in {
                        "error": outcome.get("error"),
                        "downstream_reference": outcome.get("downstream_reference"),
                        "correlation_method": "heuristic_digest",
                    }.items()
                    if v is not None
                },
            ),
            runtime_identity_id=runtime_identity_id,
        )
        self._integrations.record_decision(
            runtime_identity_id, event.client_type, "ALLOW"
        )
        return HookAuthorizeResult(
            allowed=True,
            effect="ALLOW",
            reason_code=None,
            human_explanation="Post-execution outcome recorded",
            client_response=allow,
            enforcement_result=result.to_dict(),
            receipt_id=result.receipt_id,
            exit_code=0,
        )

    def _extract_client_context(self, event: NativeHookEvent) -> dict[str, Any]:
        payload = event.payload or {}
        context = {
            "client_type": event.client_type,
            "hook_event": event.hook_event,
            "client_version": payload.get("cursor_version")
            or payload.get("client_version")
            or payload.get("version"),
            "session_id": payload.get("session_id"),
            "conversation_id": payload.get("conversation_id"),
            "generation_id": payload.get("generation_id"),
            "workspace": None,
            "observed_model": payload.get("model"),
            "observed_client_user": payload.get("user_email") or payload.get("user"),
        }
        roots = payload.get("workspace_roots")
        if isinstance(roots, list) and roots:
            # Store only basename-level workspace labels, not full local paths when possible.
            context["workspace"] = [str(r) for r in roots[:5]]
        # Explicitly drop transcript paths and secrets.
        return {k: v for k, v in context.items() if v is not None}

    def _extract_execution_outcome(self, event: NativeHookEvent) -> dict[str, Any]:
        payload = event.payload or {}
        error = (
            payload.get("error")
            or payload.get("error_message")
            or payload.get("failure")
            or payload.get("stderr")
        )
        result = (
            payload.get("result")
            or payload.get("output")
            or payload.get("response")
            or payload.get("tool_output")
        )
        duration_ms = payload.get("duration_ms") or payload.get("duration")
        exit_code = payload.get("exit_code")
        success = True
        unknown = False
        if error:
            success = False
        if exit_code not in (None, 0, "0"):
            success = False
        if payload.get("success") is False or payload.get("ok") is False:
            success = False
        if payload.get("failed") is True:
            success = False
        if payload.get("status") in {"UNKNOWN", "unknown"}:
            unknown = True
        ref = None
        if isinstance(result, (str, int)):
            ref = str(result)[:200]
        elif isinstance(result, dict) and "id" in result:
            ref = str(result.get("id"))
        return {
            "success": success,
            "unknown": unknown,
            "duration_ms": duration_ms,
            "error": str(error)[:500] if error else None,
            "downstream_reference": ref,
        }

    @staticmethod
    def _resolved_delegation_id(authority, event: NativeHookEvent) -> UUID | None:
        """Prefer the resolved authority chain; fall back to the client-supplied id."""
        if authority.delegation_chain:
            return authority.delegation_chain[-1].delegation_id
        return event.delegation_id

    def _to_proposed_action(
        self,
        request,
        authority,
        runtime_identity_id: UUID,
    ) -> ProposedAction:
        delegation_id = request.delegation_id
        if authority.delegation_chain:
            delegation_id = authority.delegation_chain[-1].delegation_id
        return ProposedAction(
            ai_system_id=authority.ai_system.id,
            agent_id=authority.agent.id,
            agent_version_id=authority.agent_version.id,
            runtime_identity_id=runtime_identity_id,
            delegation_id=delegation_id,
            integration_type=request.integration_type,
            integration_id=request.integration_id,
            tool_id=request.tool_id,
            target=request.target,
            parameters=dict(request.parameters or {}),
            environment=request.environment,
        )

    def _debug_native_fields(
        self, event: NativeHookEvent
    ) -> tuple[str | None, str | None, dict[str, Any] | None]:
        if event.client_type == ClientType.CURSOR.value:
            if event.hook_event in {"beforeShellExecution", "afterShellExecution"}:
                return (
                    None,
                    event.payload.get("tool_name") or "shell",
                    {"command": event.payload.get("command", "")},
                )
            parsed = extract_cursor_mcp_fields(event.payload)
            return parsed.native_mcp_name, parsed.native_tool_name, parsed.parameters
        parsed = extract_generic_tool_fields(event.payload)
        return parsed.native_mcp_name, parsed.native_tool_name, parsed.parameters

    def _resolve_mapping(self, event: NativeHookEvent, runtime_identity_id: UUID):
        payload = event.payload
        if event.client_type == ClientType.CURSOR.value:
            if event.hook_event in {"beforeShellExecution", "afterShellExecution"}:
                tool_name = payload.get("tool_name") or "shell"
                return self._mapper.resolve_standalone_tool(
                    runtime_identity_id=runtime_identity_id,
                    native_tool_name=tool_name,
                    parameters={"command": payload.get("command", "")},
                )
            parsed = extract_cursor_mcp_fields(payload)
            if not parsed.ok:
                from rai_gateway.client_hooks.domain import ResourceMappingResult

                return ResourceMappingResult(
                    integration_type="mcp",
                    integration_id=None,
                    tool_id=None,
                    error_code=parsed.error_code or "INVALID_HOOK_PAYLOAD",
                    error_message=parsed.error_message or "Invalid hook payload",
                )
            return self._mapper.resolve_mcp_tool(
                runtime_identity_id=runtime_identity_id,
                native_mcp_name=parsed.native_mcp_name,
                native_tool_name=parsed.native_tool_name or "",
                parameters=parsed.parameters,
            )

        parsed = extract_generic_tool_fields(payload)
        if not parsed.ok:
            from rai_gateway.client_hooks.domain import ResourceMappingResult

            return ResourceMappingResult(
                integration_type="mcp",
                integration_id=None,
                tool_id=None,
                error_code=parsed.error_code or "INVALID_HOOK_PAYLOAD",
                error_message=parsed.error_message or "Invalid hook payload",
            )
        return self._mapper.resolve_mcp_tool(
            runtime_identity_id=runtime_identity_id,
            native_mcp_name=parsed.native_mcp_name,
            native_tool_name=parsed.native_tool_name or "",
            parameters=parsed.parameters,
        )

    def _failure_block(
        self,
        adapter,
        *,
        reason: str,
        reason_code: str,
        trace_id: str,
        debug: dict[str, Any] | None = None,
    ) -> HookAuthorizeResult:
        result = {
            "allowed": False,
            "effect": "DENY",
            "reason_code": reason_code,
            "human_explanation": reason,
        }
        client_response = adapter.translate_deny(result, blocked_by_failure=True)
        exit_code = 2 if isinstance(adapter, GeminiCLIHookAdapter) else 0

        log_admin_audit(
            trace_id=trace_id,
            actor_user_id="runtime",
            actor_role="runtime",
            action="client_hook.failure_blocked",
            target={"reason_code": reason_code},
        )

        return HookAuthorizeResult(
            allowed=False,
            effect="DENY",
            reason_code=reason_code,
            human_explanation=reason,
            client_response=client_response,
            enforcement_result=result,
            debug=debug,
            exit_code=exit_code,
        )
