"""WP10 public SDK facade over WP2–WP6 authoritative domains."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from rai_gateway.core.observability import generate_trace_id, log_siem_event
from rai_gateway.evidence.domain import EvidenceEventType, TrajectoryStatus
from rai_gateway.evidence.service import TrajectoryService
from rai_gateway.identity.domain import DelegationStatus, RuntimeIdentityStatus
from rai_gateway.identity.errors import NotFoundError, RelationshipError
from rai_gateway.identity.resolver import RuntimeAuthorityResolver
from rai_gateway.identity.service import DelegationService
from rai_gateway.models.identity import DelegationGrant
from rai_gateway.models.productization import (
    OidcRuntimeBinding,
    SdkDecisionRecord,
    SdkIntegration,
    SdkSession,
)
from rai_gateway.models.registry import Agent, ToolResource
from rai_gateway.runtime_enforcement.domain import (
    ClientExecutionReport,
    EnforcementDecisionType,
    EnforcementMode,
    ExecutionStatus,
    RuntimeActionRequest,
    RuntimeActionTarget,
)
from rai_gateway.runtime_enforcement.service import RuntimeEnforcementService
from rai_gateway.sdk.auth import (
    AuthenticatedRuntime,
    CompositeRuntimeAuthenticator,
)
from rai_gateway.sdk.domain import (
    DEFAULT_CAPABILITY_MATRIX,
    REASON_CODE_MAP,
    SDK_API_VERSION,
    SDK_COMPATIBILITY_RANGE,
    SDK_PROTOCOL_VERSION,
    AuthMethod,
    IntegrationStatus,
    IntegrationType,
    PublicDecision,
    SdkDecision,
    SdkErrorCode,
    SessionStatus,
)
from rai_gateway.sdk.errors import SdkError
from rai_gateway.sdk.rate_limit import (
    DEFAULT_SDK_LIMIT,
    sdk_rate_limiter,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SdkService:
    """Stable external integration contract — wraps WP1–WP9 without exposing internals."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._auth = CompositeRuntimeAuthenticator(db)
        self._enforcement = RuntimeEnforcementService(db)
        self._evidence = TrajectoryService(db)
        self._resolver = RuntimeAuthorityResolver(db)

    # ------------------------------------------------------------------
    # Auth + tenant guards
    # ------------------------------------------------------------------

    def authenticate(
        self,
        *,
        secret: str | None,
        token: str | None,
        mtls_identity: str | None = None,
        mtls_proxy_authorization: str | None = None,
        integration_id: UUID | None = None,
    ) -> AuthenticatedRuntime:
        if integration_id:
            integration = self._get_integration(integration_id)
            auth = self._auth.authenticate_for_integration(
                integration,
                secret=secret,
                token=token,
                mtls_identity=mtls_identity,
                mtls_proxy_authorization=mtls_proxy_authorization,
            )
        else:
            auth = self._auth.authenticate(
                secret=secret,
                token=token,
                mtls_identity=mtls_identity,
                mtls_proxy_authorization=mtls_proxy_authorization,
            )
        self._assert_identity_active(auth.runtime_identity)
        self._rate_limit(f"sdk:{auth.runtime_identity.id}")
        return auth

    def _assert_identity_active(self, identity: Any) -> None:
        if identity.status != RuntimeIdentityStatus.ACTIVE.value:
            code = (
                SdkErrorCode.RUNTIME_SUSPENDED
                if identity.status == RuntimeIdentityStatus.SUSPENDED.value
                else SdkErrorCode.RUNTIME_IDENTITY_INACTIVE
            )
            raise SdkError(code, f"Runtime identity is {identity.status}")

    def _rate_limit(self, key: str) -> None:
        result = sdk_rate_limiter.check(key, limit=DEFAULT_SDK_LIMIT, window_seconds=60)
        if not result.allowed:
            raise SdkError(
                SdkErrorCode.RATE_LIMITED,
                "SDK rate limit exceeded",
                retryable=True,
                details={
                    "limit": result.limit,
                    "reset_at": result.reset_at,
                },
            )

    # ------------------------------------------------------------------
    # Integration registry
    # ------------------------------------------------------------------

    def create_integration(
        self,
        *,
        integration_key: str,
        name: str,
        runtime_identity_id: UUID,
        created_by: str,
        integration_type: str = IntegrationType.SDK.value,
        environment: str = "production",
        auth_method: str = AuthMethod.API_KEY.value,
        enforcement_mode: str = EnforcementMode.HOOK_ENFORCED.value,
        fail_closed: bool = True,
        capability_matrix: dict[str, bool] | None = None,
        oidc_issuer: str | None = None,
        oidc_audience: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        existing = (
            self._db.query(SdkIntegration)
            .filter(SdkIntegration.integration_key == integration_key)
            .first()
        )
        if existing:
            raise SdkError(
                SdkErrorCode.INVALID_REQUEST,
                f"Integration key already exists: {integration_key}",
            )
        row = SdkIntegration(
            integration_key=integration_key,
            name=name,
            integration_type=integration_type,
            runtime_identity_id=runtime_identity_id,
            environment=environment,
            auth_method=auth_method,
            protocol_version=SDK_PROTOCOL_VERSION,
            enforcement_mode=enforcement_mode,
            verification_status="DECLARED",
            certification_status="SUPPORTED",
            capability_matrix=capability_matrix or dict(DEFAULT_CAPABILITY_MATRIX),
            fail_closed=fail_closed,
            status=IntegrationStatus.ACTIVE.value,
            oidc_issuer=oidc_issuer,
            oidc_audience=oidc_audience,
            metadata_json=metadata,
            created_by=created_by,
        )
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        log_siem_event(
            trace_id=str(row.id),
            event_type="sdk.integration.created",
            decision="allow",
            metadata={
                "integration_id": str(row.id),
                "integration_key": integration_key,
            },
        )
        return self._serialize_integration(row)

    def list_integrations(self) -> list[dict[str, Any]]:
        rows = (
            self._db.query(SdkIntegration)
            .order_by(SdkIntegration.created_at.desc())
            .all()
        )
        return [self._serialize_integration(r) for r in rows]

    def get_integration(self, integration_id: UUID) -> dict[str, Any]:
        row = self._get_integration(integration_id)
        return self._serialize_integration(row)

    def heartbeat(
        self,
        auth: AuthenticatedRuntime,
        *,
        integration_id: UUID,
        sdk_version: str | None = None,
        protocol_version: int | None = None,
        capability_matrix: dict[str, bool] | None = None,
    ) -> dict[str, Any]:
        integration = self._require_integration_for_auth(auth, integration_id)
        integration.last_heartbeat_at = _utcnow()
        if sdk_version:
            integration.last_sdk_version = sdk_version
            integration.sdk_version = sdk_version
        if protocol_version is not None:
            integration.protocol_version = protocol_version
        if capability_matrix:
            integration.capability_matrix = {
                **(integration.capability_matrix or {}),
                **capability_matrix,
            }
        self._db.commit()
        self._db.refresh(integration)
        return {
            "ok": True,
            "integration_id": str(integration.id),
            "server_api_version": SDK_API_VERSION,
            "compatibility_range": SDK_COMPATIBILITY_RANGE,
            "protocol_version": integration.protocol_version,
            "enforcement_mode": integration.enforcement_mode,
            "fail_closed": integration.fail_closed,
            "status": integration.status,
            "last_heartbeat_at": integration.last_heartbeat_at.isoformat(),
        }

    def bind_oidc(
        self,
        *,
        runtime_identity_id: UUID,
        issuer: str,
        audience: str,
        subject: str,
        created_by: str,
    ) -> dict[str, Any]:
        row = OidcRuntimeBinding(
            runtime_identity_id=runtime_identity_id,
            issuer=issuer,
            audience=audience,
            subject=subject,
            status="ACTIVE",
            created_by=created_by,
        )
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        return {
            "id": str(row.id),
            "runtime_identity_id": str(runtime_identity_id),
            "issuer": issuer,
            "audience": audience,
            "subject": subject,
            "status": row.status,
        }

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def start_session(
        self,
        auth: AuthenticatedRuntime,
        *,
        integration_id: UUID,
        external_session_id: str | None = None,
        external_conversation_id: str | None = None,
        principal: str | None = None,
        channel: str | None = None,
        metadata: dict[str, Any] | None = None,
        delegation_id: UUID | None = None,
        allow_ended_session_reuse: bool = False,
    ) -> dict[str, Any]:
        integration = self._require_integration_for_auth(auth, integration_id)
        identity = auth.runtime_identity
        self._ensure_sdk_client_integration(integration, identity.id)
        resolved_delegation_id = self._validate_session_delegation(
            auth,
            delegation_id=delegation_id,
        )

        if external_session_id and (
            existing := (
                self._db.query(SdkSession)
                .filter(
                    SdkSession.integration_id == integration.id,
                    SdkSession.external_session_id == external_session_id,
                )
                .first()
            )
        ):
            # Idempotent replay of an ACTIVE turn/session.
            if existing.status == SessionStatus.ACTIVE.value:
                if (
                    resolved_delegation_id is not None
                    and existing.delegation_id is not None
                    and existing.delegation_id != resolved_delegation_id
                ):
                    raise SdkError(
                        SdkErrorCode.INVALID_REQUEST,
                        "delegation_id does not match the existing active session",
                        details={
                            "external_session_id": external_session_id,
                            "session_delegation_id": str(existing.delegation_id),
                            "requested_delegation_id": str(resolved_delegation_id),
                        },
                    )
                if resolved_delegation_id and not existing.delegation_id:
                    existing.delegation_id = resolved_delegation_id
                    if existing.trajectory_id:
                        trajectory = self._evidence.get_trajectory(
                            existing.trajectory_id
                        )
                        if trajectory and not trajectory.delegation_id:
                            trajectory.delegation_id = resolved_delegation_id
                    self._db.commit()
                    self._db.refresh(existing)
                return self._serialize_session(existing)

            # ENDED sessions must not silently reopen as a new lifecycle.
            # Opt-in reuse creates a fresh trajectory on the same external turn id
            # for migration of hosts that previously reused conversation ids.
            if not allow_ended_session_reuse:
                raise SdkError(
                    SdkErrorCode.INVALID_REQUEST,
                    "SDK session already ended; use a unique external_session_id "
                    "per AI turn (conversation id is for grouping only)",
                    details={
                        "external_session_id": external_session_id,
                        "session_id": str(existing.id),
                        "status": existing.status,
                        "hint": "Pass allow_ended_session_reuse=true only for "
                        "explicit migration of legacy hosts",
                    },
                )

            correlation_id = generate_trace_id()
            agent = self._db.query(Agent).filter(Agent.id == identity.agent_id).first()
            if not agent:
                raise SdkError(
                    SdkErrorCode.AGENT_VERSION_INELIGIBLE,
                    "Agent not found for runtime identity",
                )
            trajectory = self._evidence.get_or_create_trajectory(
                ai_system_id=agent.ai_system_id,
                agent_id=identity.agent_id,
                agent_version_id=identity.agent_version_id,
                runtime_identity_id=identity.id,
                client_integration_id=integration.client_integration_id,
                delegation_id=resolved_delegation_id or existing.delegation_id,
                conversation_id=external_conversation_id
                or existing.external_conversation_id,
                client_session_id=external_session_id,
                correlation_id=correlation_id,
                enforcement_mode=integration.enforcement_mode,
                deployment_control=integration.deployment_control,
            )
            existing.status = SessionStatus.ACTIVE.value
            existing.ended_at = None
            existing.correlation_id = correlation_id
            existing.trajectory_id = trajectory.id
            if resolved_delegation_id is not None:
                existing.delegation_id = resolved_delegation_id
            if channel is not None:
                existing.channel = channel
            if principal is not None:
                existing.principal = principal
            if metadata is not None:
                existing.metadata_json = metadata
            if external_conversation_id is not None:
                existing.external_conversation_id = external_conversation_id
            self._db.commit()
            self._db.refresh(existing)
            return self._serialize_session(existing)

        correlation_id = generate_trace_id()
        agent = self._db.query(Agent).filter(Agent.id == identity.agent_id).first()
        if not agent:
            raise SdkError(
                SdkErrorCode.AGENT_VERSION_INELIGIBLE,
                "Agent not found for runtime identity",
            )
        trajectory = self._evidence.get_or_create_trajectory(
            ai_system_id=agent.ai_system_id,
            agent_id=identity.agent_id,
            agent_version_id=identity.agent_version_id,
            runtime_identity_id=identity.id,
            client_integration_id=integration.client_integration_id,
            delegation_id=resolved_delegation_id,
            conversation_id=external_conversation_id,
            client_session_id=external_session_id,
            correlation_id=correlation_id,
            enforcement_mode=integration.enforcement_mode,
            deployment_control=integration.deployment_control,
        )
        session = SdkSession(
            integration_id=integration.id,
            runtime_identity_id=identity.id,
            trajectory_id=trajectory.id,
            delegation_id=resolved_delegation_id,
            correlation_id=correlation_id,
            external_session_id=external_session_id,
            external_conversation_id=external_conversation_id,
            principal=principal,
            channel=channel,
            status=SessionStatus.ACTIVE.value,
            metadata_json=metadata,
        )
        self._db.add(session)
        self._db.commit()
        self._db.refresh(session)
        return self._serialize_session(session)

    def _ensure_sdk_client_integration(
        self, integration: SdkIntegration, runtime_identity_id: UUID
    ) -> None:
        """Link/create a RuntimeClientIntegration so trajectory Client is not blank."""
        from rai_gateway.models.client_hooks import RuntimeClientIntegration

        if integration.client_integration_id:
            return
        row = (
            self._db.query(RuntimeClientIntegration)
            .filter(
                RuntimeClientIntegration.runtime_identity_id == runtime_identity_id,
                RuntimeClientIntegration.client_type == "sdk",
            )
            .first()
        )
        if row is None:
            row = RuntimeClientIntegration(
                runtime_identity_id=runtime_identity_id,
                client_type="sdk",
                enforcement_mode=integration.enforcement_mode
                or EnforcementMode.HOOK_ENFORCED.value,
                deployment_control=integration.deployment_control or "LOCAL_HOOK",
                verification_status=integration.verification_status or "DECLARED",
                status="CONNECTED",
            )
            self._db.add(row)
            self._db.flush()
        integration.client_integration_id = row.id
        self._db.flush()

    def _validate_session_delegation(
        self,
        auth: AuthenticatedRuntime,
        *,
        delegation_id: UUID | None,
    ) -> UUID | None:
        """Validate and return an active delegation for this runtime."""
        if delegation_id is None:
            # Default to the most recent ACTIVE grant for this runtime identity.
            identity = auth.runtime_identity
            grants = DelegationService(self._db).list_delegations(
                delegate_runtime_identity_id=identity.id,
                status=DelegationStatus.ACTIVE.value,
            )
            return grants[0].id if grants else None

        identity = auth.runtime_identity
        delegation_svc = DelegationService(self._db)
        try:
            chain = delegation_svc.resolve_active_chain(delegation_id)
        except NotFoundError as exc:
            raise SdkError(
                SdkErrorCode.INVALID_REQUEST,
                "delegation_id not found",
                details={"delegation_id": str(delegation_id)},
            ) from exc
        except RelationshipError as exc:
            raise SdkError(
                SdkErrorCode.INVALID_REQUEST,
                f"delegation_id is not usable: {exc}",
                details={"delegation_id": str(delegation_id)},
            ) from exc

        if not chain:
            raise SdkError(
                SdkErrorCode.INVALID_REQUEST,
                "delegation_id could not be resolved",
                details={"delegation_id": str(delegation_id)},
            )

        leaf = chain[-1]
        if leaf.status != DelegationStatus.ACTIVE.value:
            raise SdkError(
                SdkErrorCode.INVALID_REQUEST,
                "delegation_id is not ACTIVE",
                details={
                    "delegation_id": str(delegation_id),
                    "status": leaf.status,
                },
            )
        if leaf.delegate_runtime_identity_id != identity.id:
            raise SdkError(
                SdkErrorCode.INVALID_REQUEST,
                "delegation leaf runtime identity does not match authenticated runtime",
                details={
                    "delegation_id": str(delegation_id),
                    "delegate_runtime_identity_id": str(
                        leaf.delegate_runtime_identity_id
                    ),
                    "authenticated_runtime_identity_id": str(identity.id),
                },
            )

        # Confirm grant is visible in org scope (defense in depth).
        grant = (
            self._db.query(DelegationGrant)
            .filter(DelegationGrant.id == delegation_id)
            .first()
        )
        if grant is None:
            raise SdkError(
                SdkErrorCode.INVALID_REQUEST,
                "delegation_id not found",
                details={"delegation_id": str(delegation_id)},
            )
        return grant.id

    @staticmethod
    def _configuration_provenance_from_session(
        session: SdkSession,
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Merge session + call metadata configuration provenance keys.

        Call-level metadata wins over session metadata. RAI records identifiers
        and digests only — never the application persona/system prompt body.
        """
        keys = (
            "configuration_id",
            "configuration_version",
            "configuration_digest",
            "configuration_source",
            "configuration_environment",
            "deployment_id",
            "release_id",
            "generation_id",
            "turn_id",
        )
        merged: dict[str, Any] = {}
        session_meta = (
            session.metadata_json if isinstance(session.metadata_json, dict) else {}
        )
        for source in (session_meta, metadata or {}):
            for key in keys:
                value = source.get(key)
                if isinstance(value, str) and value.strip():
                    merged[key] = value.strip()
                elif value is not None and key in ("generation_id", "turn_id"):
                    merged[key] = value
        return merged

    def observe_input(
        self,
        auth: AuthenticatedRuntime,
        *,
        session_id: UUID,
        content: str | None = None,
        content_type: str = "text",
        observed_model: str | None = None,
        principal: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        session, integration = self._require_session(auth, session_id)
        identity = auth.runtime_identity
        agent = self._db.query(Agent).filter(Agent.id == identity.agent_id).first()
        if not agent:
            raise SdkError(SdkErrorCode.AGENT_VERSION_INELIGIBLE, "Agent not found")

        provenance = self._configuration_provenance_from_session(session, metadata)
        payload: dict[str, Any] = {
            "content_type": content_type,
            "prompt": content,
            "observed_model": observed_model,
            "principal": principal,
            **provenance,
            **{k: v for k, v in (metadata or {}).items() if k not in provenance},
        }
        payload = {k: v for k, v in payload.items() if v is not None}

        decision = SdkDecision.ALLOW.value
        reason_code = None
        findings: list[dict[str, Any]] = []
        intervention = None

        try:
            self._evidence.ingest_client_observation(
                ai_system_id=agent.ai_system_id,
                agent_id=identity.agent_id,
                agent_version_id=identity.agent_version_id,
                runtime_identity_id=identity.id,
                event_type=EvidenceEventType.PROMPT_OBSERVED.value,
                client_type="sdk",
                hook_event="observe_input",
                observation_payload=payload,
                client_integration_id=integration.client_integration_id,
                delegation_id=session.delegation_id,
                conversation_id=session.external_conversation_id,
                client_session_id=session.external_session_id,
                correlation_id=session.correlation_id,
                deployment_control=integration.deployment_control,
                verification_status=integration.verification_status,
            )
            # Content evaluation overlay (WP6) — best-effort
            try:
                from rai_gateway.risk_intelligence.service import (
                    RiskIntelligenceService,
                )

                overlay = RiskIntelligenceService(self._db).authorization_overlay(
                    ai_system_id=agent.ai_system_id,
                    runtime_identity_id=identity.id,
                    tool_id=None,
                )
                if overlay.get("deny"):
                    decision = SdkDecision.DENY.value
                    reason_code = SdkErrorCode.CONTENT_DENIED.value
                    intervention = overlay
            except Exception:
                if integration.fail_closed and integration.enforcement_mode != (
                    EnforcementMode.OBSERVE_ONLY.value
                ):
                    raise
        except SdkError:
            raise
        except Exception as exc:
            if integration.fail_closed and integration.enforcement_mode != (
                EnforcementMode.OBSERVE_ONLY.value
            ):
                raise SdkError(
                    SdkErrorCode.RAI_UNAVAILABLE,
                    "RAI unavailable during input observation",
                    retryable=True,
                    details={"cause": str(exc)},
                ) from exc
            decision = SdkDecision.MONITOR.value
            reason_code = SdkErrorCode.RAI_UNAVAILABLE.value

        return {
            "decision": decision,
            "reason_code": reason_code,
            "risk_findings": findings,
            "content_policy_findings": findings,
            "intervention": intervention,
            "evidence_reference": str(session.trajectory_id)
            if session.trajectory_id
            else None,
            "session_id": str(session.id),
            "enforcement_mode": integration.enforcement_mode,
        }

    def authorize_action(
        self,
        auth: AuthenticatedRuntime,
        *,
        session_id: UUID,
        credential_secret: str | None = None,
        tool: str | None = None,
        tool_id: UUID | None = None,
        target: dict[str, Any] | None = None,
        parameters: dict[str, Any] | None = None,
        amount: float | None = None,
        currency: str | None = None,
        idempotency_key: str | None = None,
        metadata: dict[str, Any] | None = None,
        approval_request_id: UUID | None = None,
    ) -> dict[str, Any]:
        session, integration = self._require_session(auth, session_id)

        resolved_tool_id = tool_id
        if not resolved_tool_id and tool:
            resolved_tool_id = self._resolve_tool_id(tool)

        params = dict(parameters or {})
        if amount is not None:
            params.setdefault("amount", amount)
        if currency is not None:
            params.setdefault("currency", currency)
        if metadata:
            params.setdefault("_sdk_metadata", metadata)

        action_digest = self._sdk_action_digest(
            tool=tool,
            tool_id=resolved_tool_id,
            target=target,
            parameters=params,
        )

        if idempotency_key:
            existing = (
                self._db.query(SdkDecisionRecord)
                .filter(
                    SdkDecisionRecord.integration_id == integration.id,
                    SdkDecisionRecord.idempotency_key == idempotency_key,
                )
                .first()
            )
            if existing and self._release_expired_approval_idempotency(existing):
                existing = None
            if existing:
                if existing.action_digest and existing.action_digest != action_digest:
                    raise SdkError(
                        SdkErrorCode.INVALID_REQUEST,
                        "Idempotency key reused with a different action digest",
                        details={
                            "idempotency_key": idempotency_key,
                            "stored_digest": existing.action_digest,
                            "request_digest": action_digest,
                        },
                    )
                return self._decision_from_record(existing)

        action_target = None
        if target:
            action_target = RuntimeActionTarget(
                type=str(target.get("type", "resource")),
                id=target.get("id"),
            )

        # OBSERVE_ONLY never invents enforcement
        if integration.enforcement_mode == EnforcementMode.OBSERVE_ONLY.value:
            decision = PublicDecision(
                decision=SdkDecision.MONITOR.value,
                decision_id=str(uuid4()),
                reason_code=None,
                human_message="Observation-only integration; no enforcement applied",
                machine_reason="OBSERVE_ONLY",
                retryable=False,
            )
            record = self._persist_decision(
                session=session,
                integration=integration,
                decision=decision,
                tool_key=tool,
                idempotency_key=idempotency_key,
                action_digest=action_digest,
                receipt_id=None,
            )
            decision.decision_id = str(record.id)
            return decision.to_dict()

        if not credential_secret:
            raise SdkError(
                SdkErrorCode.AUTHENTICATION_FAILED,
                "Runtime credential required for authorize_action "
                "(OIDC authenticates identity; WP2 API key still gates enforcement)",
            )

        try:
            request = RuntimeActionRequest(
                integration_type="sdk",
                integration_id=integration.client_integration_id or integration.id,
                tool_id=resolved_tool_id,
                target=action_target,
                parameters=params,
                environment=integration.environment,
                approval_request_id=approval_request_id,
                idempotency_key=idempotency_key,
                correlation_id=session.correlation_id,
                delegation_id=session.delegation_id,
                client_context={
                    "sdk_session_id": str(session.id),
                    "client_type": "sdk",
                    "channel": session.channel,
                    "principal": session.principal,
                    "tool_key": tool,
                    "conversation_id": session.external_conversation_id,
                    "session_id": session.external_session_id,
                },
            )
            result = self._enforcement.authorize(
                request,
                credential_secret=credential_secret,
            )
        except SdkError:
            raise
        except Exception as exc:
            if integration.fail_closed:
                decision = PublicDecision(
                    decision=SdkDecision.DENY.value,
                    decision_id=str(uuid4()),
                    reason_code=SdkErrorCode.RAI_UNAVAILABLE.value,
                    human_message="RAI unavailable; fail-closed deny",
                    machine_reason=str(exc),
                    retryable=True,
                )
                record = self._persist_decision(
                    session=session,
                    integration=integration,
                    decision=decision,
                    tool_key=tool,
                    idempotency_key=idempotency_key,
                    action_digest=action_digest,
                    receipt_id=None,
                )
                decision.decision_id = str(record.id)
                return decision.to_dict()
            raise SdkError(
                SdkErrorCode.RAI_UNAVAILABLE,
                "RAI unavailable",
                retryable=True,
            ) from exc

        public = self._map_enforcement_result(result)
        record = self._persist_decision(
            session=session,
            integration=integration,
            decision=public,
            tool_key=tool,
            idempotency_key=idempotency_key,
            action_digest=action_digest,
            receipt_id=result.receipt_id,
            approval_request_id=result.approval_request_id,
        )
        public.decision_id = str(record.id)
        return public.to_dict()

    def report_execution(
        self,
        auth: AuthenticatedRuntime,
        *,
        decision_id: UUID,
        status: str,
        external_execution_id: str | None = None,
        started_at: str | None = None,
        completed_at: str | None = None,
        result_metadata: dict[str, Any] | None = None,
        error_metadata: dict[str, Any] | None = None,
        usage: dict[str, Any] | None = None,
        cost: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        record = (
            self._db.query(SdkDecisionRecord)
            .filter(SdkDecisionRecord.id == decision_id)
            .first()
        )
        if not record:
            raise SdkError(SdkErrorCode.DECISION_NOT_FOUND, "Decision not found")
        session = (
            self._db.query(SdkSession)
            .filter(SdkSession.id == record.session_id)
            .first()
        )
        if not session or session.runtime_identity_id != auth.runtime_identity.id:
            raise SdkError(SdkErrorCode.DECISION_NOT_FOUND, "Decision not found")

        mapped_status = self._map_execution_status(status)
        if not record.enforcement_receipt_id:
            return {
                "ok": True,
                "decision_id": str(decision_id),
                "status": mapped_status,
                "note": "No enforcement receipt (observe-only or unavailable)",
            }

        safe_meta = {
            **(result_metadata or {}),
            "external_execution_id": external_execution_id,
            "started_at": started_at,
            "completed_at": completed_at,
            "error": error_metadata,
            "usage": usage,
            "cost": cost,
        }
        result = self._enforcement.report_execution_result(
            ClientExecutionReport(
                enforcement_receipt_id=record.enforcement_receipt_id,
                correlation_id=session.correlation_id,
                client_type="sdk",
                hook_event="report_execution",
                status=mapped_status,
                safe_result_metadata={
                    k: v for k, v in safe_meta.items() if v is not None
                },
                client_event_id=external_execution_id,
            ),
            runtime_identity_id=auth.runtime_identity.id,
        )
        return {
            "ok": True,
            "decision_id": str(decision_id),
            "status": mapped_status,
            "receipt": result.to_dict() if hasattr(result, "to_dict") else result,
        }

    def record_metering_span(
        self,
        auth: AuthenticatedRuntime,
        *,
        session_id: UUID,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        from rai_gateway.finops.domain import reject_foreign_trajectory
        from rai_gateway.finops.metering import RuntimeMeteringService
        from rai_gateway.finops.metrics import inc

        session, integration = self._require_session(auth, session_id, allow_ended=True)
        requested = body.get("trajectory_id")
        try:
            reject_foreign_trajectory(
                str(session.trajectory_id) if session.trajectory_id else None,
                str(requested) if requested else None,
            )
        except PermissionError as exc:
            inc("finops_metering_ingest_errors_total")
            raise SdkError(SdkErrorCode.RESOURCE_OUT_OF_SCOPE, str(exc)) from exc
        trajectory = self._trajectory_for_session(session)
        try:
            span = RuntimeMeteringService(self._db).record_span(
                ai_system_id=trajectory.ai_system_id if trajectory else None,
                agent_id=trajectory.agent_id if trajectory else None,
                agent_version_id=trajectory.agent_version_id if trajectory else None,
                runtime_identity_id=session.runtime_identity_id,
                delegation_id=session.delegation_id
                or (trajectory.delegation_id if trajectory else None),
                runtime_conversation_id=trajectory.runtime_conversation_id
                if trajectory
                else None,
                trajectory_id=session.trajectory_id,
                correlation_id=session.correlation_id,
                integration_id=integration.id,
                environment=integration.environment,
                span_type=body.get("span_type"),
                operation=body.get("operation"),
                provider=body.get("provider"),
                model=body.get("model"),
                usage=body.get("usage"),
                cost=body.get("cost"),
                started_at=body.get("started_at"),
                completed_at=body.get("completed_at"),
                external_span_id=body.get("external_span_id"),
                parent_span_id=body.get("parent_span_id"),
                metadata=body.get("metadata"),
                tokens_are_estimated=body.get("tokens_are_estimated"),
            )
        except PermissionError as exc:
            inc("finops_metering_ingest_errors_total")
            raise SdkError(SdkErrorCode.RESOURCE_OUT_OF_SCOPE, str(exc)) from exc
        self._db.commit()
        payload = RuntimeMeteringService(self._db).serialize_span(span)
        payload["metering_span_id"] = payload["id"]
        payload["conversation_id"] = payload.get("runtime_conversation_id")
        return payload

    def complete_metering_span(
        self,
        auth: AuthenticatedRuntime,
        *,
        session_id: UUID,
        span_id: UUID,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        from rai_gateway.finops.metering import RuntimeMeteringService

        session, _integration = self._require_session(
            auth, session_id, allow_ended=True
        )
        try:
            span = RuntimeMeteringService(self._db).complete_span(
                span_id,
                usage=body.get("usage"),
                cost=body.get("cost"),
                provider=body.get("provider"),
                model=body.get("model"),
                completed_at=body.get("completed_at"),
            )
        except LookupError as exc:
            raise SdkError(SdkErrorCode.INVALID_REQUEST, str(exc)) from exc
        if (
            span.trajectory_id
            and session.trajectory_id
            and span.trajectory_id != session.trajectory_id
        ):
            raise SdkError(
                SdkErrorCode.RESOURCE_OUT_OF_SCOPE,
                "Metering span belongs to another session",
            )
        self._db.commit()
        payload = RuntimeMeteringService(self._db).serialize_span(span)
        payload["metering_span_id"] = payload["id"]
        return payload

    def _trajectory_for_session(self, session: SdkSession):
        if not session.trajectory_id:
            return None
        from rai_gateway.models.evidence import RuntimeTrajectory

        return (
            self._db.query(RuntimeTrajectory)
            .filter(RuntimeTrajectory.id == session.trajectory_id)
            .first()
        )

    def authorize_data_access(
        self,
        auth: AuthenticatedRuntime,
        *,
        session_id: UUID,
        resource: str,
        fields: list[str] | None = None,
        payload: dict[str, Any] | list[Any] | None = None,
        purpose: str | None = None,
        access_mode: str = "READ",
        data_source_id: UUID | None = None,
        tool_id: UUID | None = None,
        target: str | None = None,
        row_filter: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Authorize/mask structured data *before* it reaches the model.

        Call this from the data gateway / retrieval / tool adapter path. The
        returned ``transformed_payload`` is the only payload safe to pass to
        the agent/model.
        """
        from rai_gateway.data_access.domain import (
            DataAccessDecisionType,
            DataAccessRequest,
        )
        from rai_gateway.data_access.service import DataAccessService

        session, integration = self._require_session(auth, session_id)
        identity = auth.runtime_identity
        agent = self._db.query(Agent).filter(Agent.id == identity.agent_id).first()
        if not agent:
            raise SdkError(SdkErrorCode.AGENT_VERSION_INELIGIBLE, "Agent not found")

        if integration.enforcement_mode == EnforcementMode.OBSERVE_ONLY.value:
            result = {
                "decision": "MONITOR",
                "reason_code": "OBSERVE_ONLY",
                "human_explanation": (
                    "Observation-only integration; data-access not enforced"
                ),
                "allowed_fields": list(fields or []),
                "denied_fields": [],
                "masked_fields": [],
                "transforms": [],
                "row_filter": row_filter or {},
                "transformed_payload": payload,
                "receipt_id": None,
                "session_id": str(session.id),
                "allowed": True,
            }
            self._record_data_access_evidence(
                session=session,
                integration=integration,
                resource=resource,
                purpose=purpose,
                access_mode=access_mode,
                data_source_id=data_source_id,
                tool_id=tool_id,
                decision="MONITOR",
                reason_code="OBSERVE_ONLY",
                receipt_id=None,
                payload=payload if isinstance(payload, (dict, list)) else None,
            )
            return result

        request = DataAccessRequest(
            runtime_identity_id=identity.id,
            agent_version_id=identity.agent_version_id,
            principal=session.principal,
            data_source_id=data_source_id,
            resource=resource,
            fields=list(fields or []),
            row_filter=dict(row_filter or {}),
            purpose=purpose,
            access_mode=access_mode,
            tool_id=tool_id,
            target=target,
            ai_system_id=agent.ai_system_id,
            agent_id=identity.agent_id,
            payload=payload if isinstance(payload, (dict, list)) else None,
        )
        decision = DataAccessService(self._db).authorize(
            request,
            persist_receipt=True,
            correlation_id=session.correlation_id,
        )

        result = decision.to_dict()
        result["transformed_payload"] = decision.transformed_payload
        result["session_id"] = str(session.id)
        result["allowed"] = decision.decision in {
            DataAccessDecisionType.ALLOW,
            DataAccessDecisionType.MASK,
            DataAccessDecisionType.FILTER,
        }

        if decision.decision == DataAccessDecisionType.DENY:
            # Fail closed for the model path: no raw payload.
            result["transformed_payload"] = None
        elif decision.decision == DataAccessDecisionType.REQUIRE_APPROVAL:
            result["transformed_payload"] = None

        self._record_data_access_evidence(
            session=session,
            integration=integration,
            resource=resource,
            purpose=purpose,
            access_mode=access_mode,
            data_source_id=data_source_id,
            tool_id=tool_id,
            decision=decision.decision.value
            if hasattr(decision.decision, "value")
            else str(decision.decision),
            reason_code=decision.reason_code,
            receipt_id=str(decision.receipt_id) if decision.receipt_id else None,
            payload=payload if isinstance(payload, (dict, list)) else None,
        )

        return result

    def _record_data_access_evidence(
        self,
        *,
        session: Any,
        integration: Any,
        resource: str,
        purpose: str | None,
        access_mode: str,
        data_source_id: UUID | None,
        tool_id: UUID | None,
        decision: str,
        reason_code: str | None,
        receipt_id: str | None,
        payload: dict[str, Any] | list[Any] | None,
    ) -> None:
        """Project data-access decisions onto the session trajectory for Investigation."""
        if not session.trajectory_id:
            return
        import hashlib

        from rai_gateway.evidence.domain import (
            EvidenceEntityType,
            EvidenceEventType,
            EvidenceRelationType,
            EvidenceSourceType,
        )
        from rai_gateway.models.registry import DataSource

        trajectory = self._evidence.get_trajectory(session.trajectory_id)
        if trajectory is None:
            return

        data_source_name = None
        if data_source_id:
            ds = (
                self._db.query(DataSource)
                .filter(DataSource.id == data_source_id)
                .first()
            )
            data_source_name = ds.name if ds else None

        decision_upper = str(decision).upper()
        denied = decision_upper in {"DENY", "REQUIRE_APPROVAL"}
        event_type = (
            EvidenceEventType.DATA_ACCESS_DENIED.value
            if denied
            else EvidenceEventType.DATA_SOURCE_ACCESSED.value
        )

        summary_bits = [
            data_source_name or (str(data_source_id)[:8] if data_source_id else None),
            resource,
            purpose,
        ]
        human_explanation = " · ".join(bit for bit in summary_bits if bit) or resource

        # Keep payload metadata only — never store retrieved KB text bodies.
        meta_payload: dict[str, Any] = {
            "resource": resource,
            "purpose": purpose,
            "access_mode": access_mode,
            "decision": decision_upper,
            "reason_code": reason_code,
            "receipt_id": receipt_id,
            "data_source_id": str(data_source_id) if data_source_id else None,
            "data_source_name": data_source_name,
            "tool_id": str(tool_id) if tool_id else None,
            "human_explanation": human_explanation,
        }
        idempotency_tail = receipt_id or "na"
        if isinstance(payload, dict):
            for key in (
                "document_ids",
                "documentIds",
                "chunk_ids",
                "chunkIds",
                "source_ids",
                "sourceIds",
                "hit_count",
                "hitCount",
                "query",
            ):
                if key in payload and payload[key] is not None:
                    meta_payload[key] = payload[key]
            docs = payload.get("documentIds") or payload.get("document_ids") or []
            if docs:
                idempotency_tail = hashlib.sha256(
                    str(docs).encode("utf-8")
                ).hexdigest()[:16]

        event, _ = self._evidence.append_event(
            trajectory,
            event_type=event_type,
            source_type=EvidenceSourceType.RAI_AUTHORITATIVE.value,
            source_reference=(
                f"data-access:{session.id}:{resource}:{idempotency_tail}"
            ),
            payload=meta_payload,
            correlation_id=session.correlation_id,
            deployment_control=integration.deployment_control,
            verification_status=integration.verification_status,
        )
        if data_source_id:
            self._evidence.ensure_relation(
                trajectory,
                source_entity_type=EvidenceEntityType.EVENT.value,
                source_entity_id=str(event.id),
                relation_type=EvidenceRelationType.RELATED_TO.value,
                target_entity_type=EvidenceEntityType.DATA_SOURCE.value,
                target_entity_id=str(data_source_id),
            )

    def observe_output(
        self,
        auth: AuthenticatedRuntime,
        *,
        session_id: UUID,
        content: str | None = None,
        content_type: str = "text",
        observed_model: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        session, integration = self._require_session(auth, session_id)
        identity = auth.runtime_identity
        agent = self._db.query(Agent).filter(Agent.id == identity.agent_id).first()
        if not agent:
            raise SdkError(SdkErrorCode.AGENT_VERSION_INELIGIBLE, "Agent not found")

        provenance = self._configuration_provenance_from_session(session, metadata)
        payload: dict[str, Any] = {
            "content_type": content_type,
            "output": content,
            "observed_model": observed_model,
            **provenance,
            **{k: v for k, v in (metadata or {}).items() if k not in provenance},
        }
        payload = {k: v for k, v in payload.items() if v is not None}

        try:
            self._evidence.ingest_client_observation(
                ai_system_id=agent.ai_system_id,
                agent_id=identity.agent_id,
                agent_version_id=identity.agent_version_id,
                runtime_identity_id=identity.id,
                event_type=EvidenceEventType.AGENT_OUTPUT_OBSERVED.value,
                client_type="sdk",
                hook_event="observe_output",
                observation_payload=payload,
                client_integration_id=integration.client_integration_id,
                delegation_id=session.delegation_id,
                conversation_id=session.external_conversation_id,
                client_session_id=session.external_session_id,
                correlation_id=session.correlation_id,
                deployment_control=integration.deployment_control,
                verification_status=integration.verification_status,
            )
        except Exception as exc:
            if integration.fail_closed and integration.enforcement_mode != (
                EnforcementMode.OBSERVE_ONLY.value
            ):
                raise SdkError(
                    SdkErrorCode.RAI_UNAVAILABLE,
                    "RAI unavailable during output observation",
                    retryable=True,
                ) from exc

        return {
            "ok": True,
            "session_id": str(session.id),
            "evidence_reference": str(session.trajectory_id)
            if session.trajectory_id
            else None,
        }

    def end_session(
        self,
        auth: AuthenticatedRuntime,
        *,
        session_id: UUID,
    ) -> dict[str, Any]:
        session, _integration = self._require_session(
            auth, session_id, allow_ended=True
        )
        if session.status == SessionStatus.ENDED.value:
            return self._serialize_session(session)
        session.status = SessionStatus.ENDED.value
        session.ended_at = _utcnow()
        if session.trajectory_id:
            trajectory = self._evidence.get_trajectory(session.trajectory_id)
            if trajectory is not None:
                if not trajectory.ended_at:
                    trajectory.ended_at = session.ended_at
                if trajectory.status == TrajectoryStatus.ACTIVE.value:
                    trajectory.status = TrajectoryStatus.COMPLETED.value
        self._db.commit()
        self._db.refresh(session)
        return self._serialize_session(session)

    def get_decision(
        self,
        auth: AuthenticatedRuntime,
        *,
        decision_id: UUID,
    ) -> dict[str, Any]:
        record = (
            self._db.query(SdkDecisionRecord)
            .filter(SdkDecisionRecord.id == decision_id)
            .first()
        )
        if not record:
            raise SdkError(SdkErrorCode.DECISION_NOT_FOUND, "Decision not found")
        session = (
            self._db.query(SdkSession)
            .filter(SdkSession.id == record.session_id)
            .first()
        )
        if not session or session.runtime_identity_id != auth.runtime_identity.id:
            raise SdkError(SdkErrorCode.DECISION_NOT_FOUND, "Decision not found")
        return self._decision_from_record(record)

    def get_approval_status(
        self,
        auth: AuthenticatedRuntime,
        *,
        approval_request_id: UUID,
    ) -> dict[str, Any]:
        from rai_gateway.approval.resume import build_approval_status_response
        from rai_gateway.approval.service import ApprovalService
        from rai_gateway.models.approval import ApprovalRequest

        row = (
            self._db.query(ApprovalRequest)
            .filter(ApprovalRequest.id == approval_request_id)
            .first()
        )
        if not row:
            raise SdkError(SdkErrorCode.INVALID_REQUEST, "Approval request not found")
        if row.runtime_identity_id != auth.runtime_identity.id:
            raise SdkError(SdkErrorCode.INVALID_REQUEST, "Approval request not found")
        ApprovalService(self._db)._expire_if_needed(row)  # noqa: SLF001
        self._db.refresh(row)
        return build_approval_status_response(row)

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "api_version": SDK_API_VERSION,
            "compatibility_range": SDK_COMPATIBILITY_RANGE,
            "protocol_version": SDK_PROTOCOL_VERSION,
        }

    def onboarding_checklist(self) -> dict[str, Any]:
        """Product onboarding status for this instance."""
        from rai_gateway.public_product.onboarding import (
            OnboardingError,
            OnboardingService,
        )

        try:
            return OnboardingService(self._db).build_checklist()
        except OnboardingError as exc:
            raise SdkError(SdkErrorCode.INVALID_REQUEST, exc.message) from exc

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _get_integration(self, integration_id: UUID) -> SdkIntegration:
        row = (
            self._db.query(SdkIntegration)
            .filter(SdkIntegration.id == integration_id)
            .first()
        )
        if not row:
            raise SdkError(SdkErrorCode.INTEGRATION_NOT_FOUND, "Integration not found")
        return row

    def _require_integration_for_auth(
        self, auth: AuthenticatedRuntime, integration_id: UUID
    ) -> SdkIntegration:
        integration = self._get_integration(integration_id)
        if integration.runtime_identity_id != auth.runtime_identity.id:
            raise SdkError(
                SdkErrorCode.AUTHENTICATION_FAILED,
                "Integration does not match authenticated runtime identity",
            )
        if integration.status != IntegrationStatus.ACTIVE.value:
            raise SdkError(
                SdkErrorCode.INVALID_REQUEST,
                f"Integration is {integration.status}",
            )
        return integration

    def _require_session(
        self,
        auth: AuthenticatedRuntime,
        session_id: UUID,
        *,
        allow_ended: bool = False,
    ) -> tuple[SdkSession, SdkIntegration]:
        session = self._db.query(SdkSession).filter(SdkSession.id == session_id).first()
        if not session or session.runtime_identity_id != auth.runtime_identity.id:
            raise SdkError(SdkErrorCode.SESSION_NOT_FOUND, "Session not found")
        if not allow_ended and session.status != SessionStatus.ACTIVE.value:
            raise SdkError(SdkErrorCode.INVALID_REQUEST, "Session is not active")
        integration = self._get_integration(session.integration_id)
        return session, integration

    def _resolve_tool_id(self, tool: str) -> UUID | None:
        row = (
            self._db.query(ToolResource)
            .filter((ToolResource.tool_key == tool) | (ToolResource.name == tool))
            .first()
        )
        return row.id if row else None

    def _map_enforcement_result(self, result: Any) -> PublicDecision:
        effect = result.effect or (
            EnforcementDecisionType.ALLOW.value
            if result.allowed
            else EnforcementDecisionType.DENY.value
        )
        reason = result.reason_code
        public_reason = None
        if reason:
            mapped = REASON_CODE_MAP.get(reason)
            public_reason = mapped.value if mapped else reason

        retryable = public_reason in {
            SdkErrorCode.RAI_UNAVAILABLE.value,
            SdkErrorCode.RATE_LIMITED.value,
        }
        return PublicDecision(
            decision=effect,
            decision_id=None,
            reason_code=public_reason,
            human_message=result.human_explanation,
            machine_reason=reason,
            approval_request_id=str(result.approval_request_id)
            if result.approval_request_id
            else None,
            approval=getattr(result, "approval", None),
            enforcement_receipt_id=str(result.receipt_id)
            if result.receipt_id
            else None,
            evidence_reference=str(result.receipt_id) if result.receipt_id else None,
            retryable=retryable,
            expires_at=(
                (result.approval or {}).get("expires_at")
                if getattr(result, "approval", None)
                else None
            ),
            constraints={
                "monitor": result.monitor,
                "monitoring_instruction": result.monitoring_instruction,
            },
        )

    def _persist_decision(
        self,
        *,
        session: SdkSession,
        integration: SdkIntegration,
        decision: PublicDecision,
        tool_key: str | None,
        idempotency_key: str | None,
        receipt_id: UUID | None,
        approval_request_id: UUID | None = None,
        action_digest: str | None = None,
    ) -> SdkDecisionRecord:
        record = SdkDecisionRecord(
            session_id=session.id,
            integration_id=integration.id,
            enforcement_receipt_id=receipt_id,
            decision=decision.decision,
            reason_code=decision.reason_code,
            tool_key=tool_key,
            idempotency_key=idempotency_key,
            action_digest=action_digest,
            approval_request_id=approval_request_id
            or (
                UUID(decision.approval_request_id)
                if decision.approval_request_id
                else None
            ),
            payload=decision.to_dict(),
        )
        self._db.add(record)
        self._db.commit()
        self._db.refresh(record)
        return record

    def _release_expired_approval_idempotency(
        self, existing: SdkDecisionRecord
    ) -> bool:
        """Drop the idempotency binding when its approval can no longer be used.

        A live PENDING or APPROVED request stays bound so a different action
        digest cannot replace it. Once that request is expired, rejected, or
        cancelled, the same key may authorize again and open a new approval.
        """
        if not existing.approval_request_id:
            return False
        from rai_gateway.approval.domain import ApprovalStatus
        from rai_gateway.approval.errors import ApprovalNotFoundError
        from rai_gateway.approval.service import ApprovalService

        try:
            request = ApprovalService(self._db).get_request(
                existing.approval_request_id
            )
        except ApprovalNotFoundError:
            return False
        if request.status not in {
            ApprovalStatus.EXPIRED.value,
            ApprovalStatus.REJECTED.value,
            ApprovalStatus.CANCELLED.value,
        }:
            return False
        existing.idempotency_key = None
        self._db.flush()
        return True

    def _sdk_action_digest(
        self,
        *,
        tool: str | None,
        tool_id: UUID | None,
        target: dict[str, Any] | None,
        parameters: dict[str, Any],
    ) -> str:
        payload = {
            "tool": tool,
            "tool_id": str(tool_id) if tool_id else None,
            "target": target or {},
            "parameters": parameters,
        }
        canonical = json.dumps(
            payload, sort_keys=True, default=str, separators=(",", ":")
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _decision_from_record(self, record: SdkDecisionRecord) -> dict[str, Any]:
        if record.payload:
            data = dict(record.payload)
            data["decision_id"] = str(record.id)
            return data
        return PublicDecision(
            decision=record.decision,
            decision_id=str(record.id),
            reason_code=record.reason_code,
            approval_request_id=str(record.approval_request_id)
            if record.approval_request_id
            else None,
            enforcement_receipt_id=str(record.enforcement_receipt_id)
            if record.enforcement_receipt_id
            else None,
        ).to_dict()

    def _map_execution_status(self, status: str) -> str:
        mapping = {
            "succeeded": ExecutionStatus.SUCCEEDED.value,
            "success": ExecutionStatus.SUCCEEDED.value,
            "SUCCEEDED": ExecutionStatus.SUCCEEDED.value,
            "failed": ExecutionStatus.FAILED.value,
            "FAILED": ExecutionStatus.FAILED.value,
            "started": ExecutionStatus.STARTED.value,
            "STARTED": ExecutionStatus.STARTED.value,
            "pending": ExecutionStatus.PENDING_CLIENT_REPORT.value,
        }
        return mapping.get(status, status)

    def _serialize_integration(self, row: SdkIntegration) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "integration_key": row.integration_key,
            "name": row.name,
            "integration_type": row.integration_type,
            "runtime_identity_id": str(row.runtime_identity_id),
            "environment": row.environment,
            "auth_method": row.auth_method,
            "protocol_version": row.protocol_version,
            "sdk_version": row.sdk_version,
            "enforcement_mode": row.enforcement_mode,
            "deployment_control": row.deployment_control,
            "verification_status": row.verification_status,
            "certification_status": row.certification_status,
            "capability_matrix": row.capability_matrix or DEFAULT_CAPABILITY_MATRIX,
            "fail_closed": row.fail_closed,
            "status": row.status,
            "last_heartbeat_at": row.last_heartbeat_at.isoformat()
            if row.last_heartbeat_at
            else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    def _serialize_session(self, session: SdkSession) -> dict[str, Any]:
        return {
            "rai_session_id": str(session.id),
            "session_id": str(session.id),
            "trajectory_id": str(session.trajectory_id)
            if session.trajectory_id
            else None,
            "delegation_id": str(session.delegation_id)
            if session.delegation_id
            else None,
            "correlation_id": session.correlation_id,
            "integration_id": str(session.integration_id),
            "external_session_id": session.external_session_id,
            "external_conversation_id": session.external_conversation_id,
            "status": session.status,
            "started_at": session.started_at.isoformat()
            if session.started_at
            else None,
            "ended_at": session.ended_at.isoformat() if session.ended_at else None,
        }
