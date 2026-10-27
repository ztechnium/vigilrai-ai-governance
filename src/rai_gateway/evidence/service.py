"""Trajectory correlation, evidence ingestion, and WP4 projection."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from rai_gateway.evidence.correlation import (
    build_session_key,
    extract_client_session_fields,
)
from rai_gateway.evidence.domain import (
    DEFAULT_CONTENT_HANDLING,
    AssuranceLevel,
    ContentHandlingMode,
    CoverageState,
    EvidenceEntityType,
    EvidenceEventType,
    EvidenceFindingType,
    EvidenceRelationType,
    EvidenceSourceType,
    FindingSeverity,
    FindingStatus,
    TrajectoryStatus,
    artifact_type_for_event,
    assurance_for_deployment,
)
from rai_gateway.evidence.redaction import (
    apply_content_handling,
    content_preview,
    content_status_for_mode,
    extract_inline_content,
    sha256_digest,
)
from rai_gateway.evidence.repository import EvidenceRepository
from rai_gateway.models.evidence import (
    EvidenceEvent,
    EvidenceFinding,
    EvidenceRelation,
    RuntimeTrajectory,
)
from rai_gateway.models.runtime_enforcement import RuntimeEnforcementReceipt
from rai_gateway.runtime_enforcement.domain import (
    EnforcementDecisionType,
    ExecutionSource,
    ExecutionStatus,
)

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TrajectoryService:
    """Correlate runtime facts into ordered trajectories and evidence graphs."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._repo = EvidenceRepository(db)

    # ------------------------------------------------------------------
    # Public read API helpers
    # ------------------------------------------------------------------

    def get_trajectory(
        self,
        trajectory_id: UUID,
    ) -> RuntimeTrajectory | None:
        return self._repo.get_trajectory(trajectory_id)

    def list_trajectories(self, **filters: Any) -> list[RuntimeTrajectory]:
        return self._repo.list_trajectories(**filters)

    def count_trajectories(self, **filters: Any) -> int:
        return self._repo.count_trajectories(**filters)

    def list_events(
        self, trajectory_id: UUID, *, limit: int = 500, offset: int = 0
    ) -> list[EvidenceEvent]:
        return self._repo.list_events(trajectory_id, limit=limit, offset=offset)

    def list_relations(self, trajectory_id: UUID) -> list[EvidenceRelation]:
        return self._repo.list_relations(trajectory_id)

    def list_findings(self, trajectory_id: UUID) -> list[EvidenceFinding]:
        return self._repo.list_findings(trajectory_id)

    def list_artifacts(self, trajectory_id: UUID) -> list[Any]:
        return self._repo.list_artifacts(trajectory_id)

    def get_event(self, trajectory_id: UUID, event_id: UUID) -> EvidenceEvent | None:
        """Fetch an event scoped to its trajectory (tenant isolation)."""
        return self._repo.get_event(trajectory_id=trajectory_id, event_id=event_id)

    def get_artifact(self, trajectory_id: UUID, artifact_id: UUID) -> Any | None:
        """Fetch an artifact scoped to its trajectory (tenant isolation)."""
        return self._repo.get_artifact(
            trajectory_id=trajectory_id, artifact_id=artifact_id
        )

    # ------------------------------------------------------------------
    # Correlation / ingestion
    # ------------------------------------------------------------------

    def get_or_create_trajectory(
        self,
        *,
        ai_system_id: UUID,
        agent_id: UUID,
        agent_version_id: UUID,
        runtime_identity_id: UUID,
        client_integration_id: UUID | None = None,
        delegation_id: UUID | None = None,
        conversation_id: str | None = None,
        client_session_id: str | None = None,
        correlation_id: str | None = None,
        generation_id: str | None = None,
        enforcement_mode: str | None = None,
        deployment_control: str | None = None,
        occurred_at: datetime | None = None,
    ) -> RuntimeTrajectory:
        session_key = build_session_key(
            runtime_identity_id=runtime_identity_id,
            client_integration_id=client_integration_id,
            conversation_id=conversation_id,
            client_session_id=client_session_id,
            correlation_id=correlation_id,
            generation_id=generation_id,
        )
        existing = self._repo.find_trajectory_by_session(
            runtime_identity_id=runtime_identity_id,
            session_key=session_key,
        )
        if not existing and client_session_id:
            existing = self._repo.find_active_trajectory_for_session_fields(
                runtime_identity_id=runtime_identity_id,
                conversation_id=conversation_id,
                client_session_id=client_session_id,
            )
        if not existing and correlation_id:
            # Reuse approval/enforcement stubs that were keyed only by correlation.
            existing = self._repo.find_trajectory_by_correlation(
                runtime_identity_id=runtime_identity_id,
                correlation_id=correlation_id,
            )
        if existing:
            updates: dict[str, Any] = {}
            # Promote weaker keys when a stronger turn/session id arrives.
            if session_key != existing.session_key and (
                existing.session_key.startswith("corr:")
                or existing.session_key.startswith("gen:")
                or existing.session_key.startswith("ri:")
                or existing.session_key.startswith("conv:")
            ):
                conflict = self._repo.find_trajectory_by_session(
                    runtime_identity_id=runtime_identity_id,
                    session_key=session_key,
                )
                if conflict is None or conflict.id == existing.id:
                    updates["session_key"] = session_key
            if conversation_id and not existing.conversation_id:
                updates["conversation_id"] = conversation_id
            if client_session_id and not existing.client_session_id:
                updates["client_session_id"] = client_session_id
            if correlation_id and not existing.correlation_id:
                updates["correlation_id"] = correlation_id
            if client_integration_id and not existing.client_integration_id:
                updates["client_integration_id"] = client_integration_id
            if delegation_id and not existing.delegation_id:
                updates["delegation_id"] = delegation_id
            if enforcement_mode and not existing.enforcement_mode:
                updates["enforcement_mode"] = enforcement_mode
            if deployment_control and not existing.deployment_control:
                updates["deployment_control"] = deployment_control
            if updates:
                self._repo.update_trajectory(existing, **updates)
            self._project_conversation(existing)
            return existing

        now = occurred_at or _utcnow()
        from rai_gateway.evidence.retention import (
            DEFAULT_RETENTION_DAYS,
            EvidenceRetentionService,
        )

        eligible = EvidenceRetentionService(self._db).compute_eligible_for_purge_at(
            anchor=now, retention_days=DEFAULT_RETENTION_DAYS
        )
        trajectory = self._repo.create_trajectory(
            ai_system_id=ai_system_id,
            agent_id=agent_id,
            agent_version_id=agent_version_id,
            runtime_identity_id=runtime_identity_id,
            client_integration_id=client_integration_id,
            delegation_id=delegation_id,
            session_key=session_key,
            conversation_id=conversation_id,
            client_session_id=client_session_id,
            correlation_id=correlation_id,
            started_at=now,
            last_event_at=now,
            status=TrajectoryStatus.ACTIVE.value,
            enforcement_mode=enforcement_mode,
            deployment_control=deployment_control,
            assurance_summary={},
            coverage_summary={},
            event_count=0,
            finding_count=0,
            retention_days=DEFAULT_RETENTION_DAYS,
            eligible_for_purge_at=eligible,
            legal_hold=False,
            trajectory_semantics="TURN",
        )
        self._project_conversation(trajectory)
        return trajectory

    def _project_conversation(self, trajectory: RuntimeTrajectory) -> None:
        """Best-effort conversation projection; never raises into auth paths."""
        from rai_gateway.evidence.conversation_projection import (
            ConversationProjectionService,
        )

        ConversationProjectionService(self._db).project_trajectory(trajectory)

    def append_event(
        self,
        trajectory: RuntimeTrajectory,
        *,
        event_type: str,
        source_type: str,
        source_reference: str,
        payload: dict[str, Any] | None = None,
        occurred_at: datetime | None = None,
        correlation_id: str | None = None,
        trace_id: str | None = None,
        assurance_level: str | None = None,
        content_handling_mode: str | None = None,
        deployment_control: str | None = None,
        verification_status: str | None = None,
    ) -> tuple[EvidenceEvent, bool]:
        """
        Append an evidence event idempotently.

        Returns (event, created) where created is False on replay.
        """
        existing = self._repo.get_event_by_idempotency(
            trajectory_id=trajectory.id,
            source_type=source_type,
            source_reference=source_reference,
            event_type=event_type,
        )
        if existing:
            return existing, False

        mode = content_handling_mode or DEFAULT_CONTENT_HANDLING.value
        stored_payload, redaction_status, digest = apply_content_handling(payload, mode)
        level = assurance_level or assurance_for_deployment(
            source_type=source_type,
            deployment_control=deployment_control or trajectory.deployment_control,
            verification_status=verification_status,
        )
        if isinstance(level, AssuranceLevel):
            level = level.value

        seq = self._repo.next_sequence_number(trajectory.id)
        occurred = occurred_at or _utcnow()
        event = self._repo.create_event(
            trajectory_id=trajectory.id,
            event_type=event_type,
            occurred_at=occurred,
            recorded_at=_utcnow(),
            sequence_number=seq,
            source_type=source_type,
            source_reference=source_reference,
            assurance_level=level,
            correlation_id=correlation_id or trajectory.correlation_id,
            trace_id=trace_id,
            payload=stored_payload,
            payload_digest=digest,
            content_handling_mode=mode,
            redaction_status=redaction_status.value,
        )
        self._repo.update_trajectory(
            trajectory,
            event_count=(trajectory.event_count or 0) + 1,
            last_event_at=occurred
            if (
                trajectory.last_event_at is None or occurred >= trajectory.last_event_at
            )
            else trajectory.last_event_at,
        )
        if redaction_status.value == "FAILED":
            self.ensure_finding(
                trajectory,
                finding_type=EvidenceFindingType.CONTENT_REDACTION_FAILED.value,
                severity=FindingSeverity.HIGH.value,
                title="Content redaction failed",
                description=(
                    "Secret redaction failed before persistence; raw content was "
                    "not stored. Event retained as metadata/digest-only."
                ),
                source_event_ids=[str(event.id)],
            )
        return event, True

    def ensure_relation(
        self,
        trajectory: RuntimeTrajectory,
        *,
        source_entity_type: str,
        source_entity_id: str,
        relation_type: str,
        target_entity_type: str,
        target_entity_id: str,
    ) -> EvidenceRelation:
        existing = self._repo.get_relation(
            trajectory_id=trajectory.id,
            source_entity_type=source_entity_type,
            source_entity_id=source_entity_id,
            relation_type=relation_type,
            target_entity_type=target_entity_type,
            target_entity_id=target_entity_id,
        )
        if existing:
            return existing
        return self._repo.create_relation(
            trajectory_id=trajectory.id,
            source_entity_type=source_entity_type,
            source_entity_id=source_entity_id,
            relation_type=relation_type,
            target_entity_type=target_entity_type,
            target_entity_id=target_entity_id,
        )

    def ensure_finding(
        self,
        trajectory: RuntimeTrajectory,
        *,
        finding_type: str,
        severity: str,
        title: str,
        description: str | None = None,
        source_event_ids: list[str] | None = None,
    ) -> EvidenceFinding:
        existing = self._repo.find_open_finding(
            trajectory_id=trajectory.id,
            finding_type=finding_type,
        )
        if existing:
            return existing
        finding = self._repo.create_finding(
            trajectory_id=trajectory.id,
            finding_type=finding_type,
            severity=severity,
            title=title,
            description=description,
            source_event_ids=source_event_ids or [],
            status=FindingStatus.OPEN.value,
        )
        self._repo.update_trajectory(
            trajectory,
            finding_count=(trajectory.finding_count or 0) + 1,
        )
        self.append_event(
            trajectory,
            event_type=EvidenceEventType.FINDING_CREATED.value,
            source_type=EvidenceSourceType.DERIVED.value,
            source_reference=f"finding:{finding.id}",
            payload={
                "finding_id": str(finding.id),
                "finding_type": finding_type,
                "severity": severity,
                "title": title,
            },
            assurance_level=AssuranceLevel.MEDIUM.value,
        )
        return finding

    # ------------------------------------------------------------------
    # Client observation + model mismatch
    # ------------------------------------------------------------------

    def ingest_client_observation(
        self,
        *,
        ai_system_id: UUID,
        agent_id: UUID,
        agent_version_id: UUID,
        runtime_identity_id: UUID,
        event_type: str,
        client_type: str,
        hook_event: str,
        observation_payload: dict[str, Any],
        client_integration_id: UUID | None = None,
        delegation_id: UUID | None = None,
        conversation_id: str | None = None,
        client_session_id: str | None = None,
        correlation_id: str | None = None,
        generation_id: str | None = None,
        occurred_at: datetime | None = None,
        content_handling_mode: str | None = None,
        deployment_control: str | None = None,
        verification_status: str | None = None,
        ai_system_policy: dict[str, Any] | None = None,
        agent_policy: dict[str, Any] | None = None,
    ) -> RuntimeTrajectory:
        """Ingest a CLIENT_OBSERVED prompt/model/output event into a trajectory."""
        from rai_gateway.evidence.content_policy import resolve_content_handling

        trajectory = self.get_or_create_trajectory(
            ai_system_id=ai_system_id,
            agent_id=agent_id,
            agent_version_id=agent_version_id,
            runtime_identity_id=runtime_identity_id,
            client_integration_id=client_integration_id,
            delegation_id=delegation_id,
            conversation_id=conversation_id,
            client_session_id=client_session_id,
            correlation_id=correlation_id,
            generation_id=generation_id,
            deployment_control=deployment_control,
            occurred_at=occurred_at,
        )
        resolved_mode = resolve_content_handling(
            event_type,
            ai_system_policy=ai_system_policy
            or self._ai_system_content_policy(ai_system_id),
            agent_policy=agent_policy or self._agent_content_policy(agent_version_id),
            evidence_type_override=content_handling_mode,
        ).value
        source_ref = (
            f"observe:{client_type}:{hook_event}:"
            f"{generation_id or correlation_id or 'anon'}"
        )
        event, created = self.append_event(
            trajectory,
            event_type=event_type,
            source_type=EvidenceSourceType.CLIENT_OBSERVED.value,
            source_reference=source_ref,
            payload={
                **observation_payload,
                "client_type": client_type,
                "hook_event": hook_event,
            },
            occurred_at=occurred_at,
            correlation_id=correlation_id,
            content_handling_mode=resolved_mode,
            deployment_control=deployment_control,
            verification_status=verification_status,
        )
        if created:
            self._maybe_create_content_artifact(
                trajectory,
                event=event,
                event_type=event_type,
            )
            observed_model = observation_payload.get("observed_model")
            model_event_id = str(event.id)
            # When a prompt/output hook also carries model metadata, normalize a
            # dedicated MODEL_REQUEST_OBSERVED event for coverage/findings.
            if (
                observed_model
                and event_type != EvidenceEventType.MODEL_REQUEST_OBSERVED.value
            ):
                model_mode = resolve_content_handling(
                    EvidenceEventType.MODEL_REQUEST_OBSERVED.value,
                    ai_system_policy=ai_system_policy
                    or self._ai_system_content_policy(ai_system_id),
                    agent_policy=agent_policy
                    or self._agent_content_policy(agent_version_id),
                ).value
                model_event, model_created = self.append_event(
                    trajectory,
                    event_type=EvidenceEventType.MODEL_REQUEST_OBSERVED.value,
                    source_type=EvidenceSourceType.CLIENT_OBSERVED.value,
                    source_reference=f"{source_ref}:model",
                    payload={
                        "observed_model": observed_model,
                        "client_type": client_type,
                        "hook_event": hook_event,
                    },
                    occurred_at=occurred_at,
                    correlation_id=correlation_id,
                    content_handling_mode=model_mode,
                    deployment_control=deployment_control,
                    verification_status=verification_status,
                )
                if model_created:
                    model_event_id = str(model_event.id)
            if observed_model:
                self.evaluate_observed_model(
                    trajectory,
                    observed_model=str(observed_model),
                    source_event_id=model_event_id,
                    client_type=client_type,
                )
        self.refresh_coverage(trajectory)
        return trajectory

    def _tool_display_fields(self, tool_id: UUID | None) -> dict[str, Any]:
        """Resolve human-readable tool labels for evidence payloads."""
        if not tool_id:
            return {}
        from rai_gateway.models.registry import ToolResource

        tool = self._db.query(ToolResource).filter(ToolResource.id == tool_id).first()
        if not tool:
            return {}
        return {
            "tool_name": tool.name,
            "tool_key": tool.tool_key,
        }

    def _ai_system_content_policy(self, ai_system_id: UUID) -> dict[str, Any] | None:
        from rai_gateway.models.registry import AISystem

        system = self._db.query(AISystem).filter(AISystem.id == ai_system_id).first()
        if not system:
            return None
        # Optional future field; also accept configuration via related agent metadata.
        return getattr(system, "evidence_content_policy", None)

    def _agent_content_policy(self, agent_version_id: UUID) -> dict[str, Any] | None:
        from rai_gateway.models.registry import AgentVersion

        version = (
            self._db.query(AgentVersion)
            .filter(AgentVersion.id == agent_version_id)
            .first()
        )
        if not version:
            return None
        meta = version.configuration_snapshot or {}
        if isinstance(meta, dict):
            policy = meta.get("evidence_content_policy")
            if isinstance(policy, dict):
                return policy
        return None

    def _maybe_create_content_artifact(
        self,
        trajectory: RuntimeTrajectory,
        *,
        event: EvidenceEvent,
        event_type: str,
    ) -> Any | None:
        """Persist inspectable content as EvidenceArtifact when policy permits."""
        mode = event.content_handling_mode
        if mode not in {"FULL", "REDACTED"}:
            return None
        if event.redaction_status == "FAILED":
            return None
        artifact_type = artifact_type_for_event(event_type)
        if artifact_type is None:
            return None
        inline = extract_inline_content(
            event.payload if isinstance(event.payload, dict) else None
        )
        if not inline:
            return None
        # Digest the inspectable body only so identical model/agent output can share storage.
        digest = sha256_digest(inline)
        # Avoid duplicate storage when model response == agent output.
        existing = self._repo.find_artifact_by_digest(
            trajectory_id=trajectory.id, content_digest=digest
        )
        if existing:
            self.ensure_relation(
                trajectory,
                source_entity_type=EvidenceEntityType.EVENT.value,
                source_entity_id=str(event.id),
                relation_type=EvidenceRelationType.PRODUCED.value,
                target_entity_type=EvidenceEntityType.ARTIFACT.value,
                target_entity_id=str(existing.id),
            )
            return existing
        artifact = self._repo.create_artifact(
            trajectory_id=trajectory.id,
            event_id=event.id,
            artifact_type=artifact_type.value,
            source_type=event.source_type,
            inline_content=inline,
            content_digest=digest,
            mime_type="text/plain",
            size_bytes=len(inline.encode("utf-8")),
            content_handling_mode=mode,
            sensitivity_classification="INTERNAL",
            encrypted=False,
        )
        self.ensure_relation(
            trajectory,
            source_entity_type=EvidenceEntityType.EVENT.value,
            source_entity_id=str(event.id),
            relation_type=EvidenceRelationType.PRODUCED.value,
            target_entity_type=EvidenceEntityType.ARTIFACT.value,
            target_entity_id=str(artifact.id),
        )
        return artifact

    def evaluate_observed_model(
        self,
        trajectory: RuntimeTrajectory,
        *,
        observed_model: str,
        source_event_id: str | None = None,
        client_type: str | None = None,
    ) -> EvidenceFinding | None:
        """Compare CLIENT_OBSERVED model against WP1 Agent Version model deps."""
        from rai_gateway.registry.service import RegistryService

        registry = RegistryService(self._db)
        allowed = self._allowed_model_identifiers(registry, trajectory.agent_version_id)
        observed_norm = observed_model.strip().lower()
        if not observed_norm:
            return None

        if not allowed:
            return self.ensure_finding(
                trajectory,
                finding_type=EvidenceFindingType.OBSERVED_MODEL_MISMATCH.value,
                severity=FindingSeverity.LOW.value,
                title="Observed model with no registered Agent Version models",
                description=(
                    f"Client observed model '{observed_model}' but Agent Version "
                    f"{trajectory.agent_version_id} has no registered model "
                    "dependencies. Observation is CLIENT_OBSERVED only and does "
                    "not cryptographically prove which model executed."
                    + (f" Client={client_type}." if client_type else "")
                ),
                source_event_ids=[source_event_id] if source_event_id else [],
            )

        if any(
            observed_norm == item or observed_norm in item or item in observed_norm
            for item in allowed
        ):
            return None

        allowed_display = sorted(allowed)[:20]
        return self.ensure_finding(
            trajectory,
            finding_type=EvidenceFindingType.OBSERVED_MODEL_MISMATCH.value,
            severity=FindingSeverity.MEDIUM.value,
            title=f"Observed model mismatch: {observed_model}",
            description=(
                f"Observed model '{observed_model}' is outside the models "
                f"registered on Agent Version {trajectory.agent_version_id}. "
                f"Allowed identifiers include: {', '.join(allowed_display)}. "
                "This is a DERIVED evidence finding from CLIENT_OBSERVED metadata; "
                "it is not a WP4 enforcement denial."
                + (f" Client={client_type}." if client_type else "")
            ),
            source_event_ids=[source_event_id] if source_event_id else [],
        )

    def _allowed_model_identifiers(
        self, registry: Any, agent_version_id: UUID
    ) -> set[str]:
        allowed: set[str] = set()
        try:
            deps = registry.list_version_dependencies(agent_version_id)
        except Exception:  # noqa: BLE001
            return allowed
        for dep in deps:
            if getattr(dep, "resource_type", None) != "model":
                continue
            try:
                model = registry.get_model_resource(dep.resource_id)
            except Exception:  # noqa: BLE001
                continue
            for value in (
                getattr(model, "model_name", None),
                getattr(model, "model_version", None),
                getattr(model, "deployment_reference", None),
                getattr(model, "provider", None),
            ):
                if value:
                    allowed.add(str(value).strip().lower())
            provider = getattr(model, "provider", None)
            name = getattr(model, "model_name", None)
            if provider and name:
                allowed.add(f"{provider}/{name}".strip().lower())
            metadata = getattr(model, "metadata_", None) or {}
            if isinstance(metadata, dict):
                for key in ("aliases", "native_aliases"):
                    aliases = metadata.get(key)
                    if isinstance(aliases, list):
                        for alias in aliases:
                            if alias:
                                allowed.add(str(alias).strip().lower())
                    elif isinstance(aliases, str) and aliases.strip():
                        allowed.add(aliases.strip().lower())
        return {item for item in allowed if item}

    # ------------------------------------------------------------------
    # WP4 projection
    # ------------------------------------------------------------------

    def project_receipt(
        self,
        receipt_id: UUID,
    ) -> RuntimeTrajectory | None:
        """Project a WP4 enforcement receipt into trajectory evidence (idempotent)."""
        query = self._db.query(RuntimeEnforcementReceipt).filter(
            RuntimeEnforcementReceipt.id == receipt_id
        )
        receipt = query.first()
        if not receipt:
            return None

        client_fields = extract_client_session_fields(receipt.client_context)
        client_integration_id = self._resolve_client_integration_id(
            runtime_identity_id=receipt.runtime_identity_id,
            client_type=client_fields.get("client_type"),
        )
        trajectory = self.get_or_create_trajectory(
            ai_system_id=receipt.ai_system_id,
            agent_id=receipt.agent_id,
            agent_version_id=receipt.agent_version_id,
            runtime_identity_id=receipt.runtime_identity_id,
            client_integration_id=client_integration_id,
            delegation_id=receipt.delegation_id,
            conversation_id=client_fields["conversation_id"],
            client_session_id=client_fields["client_session_id"],
            correlation_id=receipt.correlation_id,
            generation_id=client_fields["generation_id"],
            enforcement_mode=receipt.enforcement_mode,
            deployment_control=receipt.deployment_control,
            occurred_at=receipt.started_at,
        )

        receipt_ref = str(receipt.id)
        tool_attempt_id = f"receipt:{receipt_ref}:attempt"
        occurred = receipt.started_at or _utcnow()

        # SESSION_STARTED once per trajectory (first projection).
        if (trajectory.event_count or 0) == 0:
            self.append_event(
                trajectory,
                event_type=EvidenceEventType.SESSION_STARTED.value,
                source_type=EvidenceSourceType.RAI_AUTHORITATIVE.value,
                source_reference=f"trajectory:{trajectory.id}:session",
                payload={
                    "runtime_identity_id": str(receipt.runtime_identity_id),
                    "client_type": client_fields["client_type"],
                    "conversation_id": client_fields["conversation_id"],
                    "session_id": client_fields["client_session_id"],
                },
                occurred_at=occurred,
                correlation_id=receipt.correlation_id,
                trace_id=receipt.trace_id,
                deployment_control=receipt.deployment_control,
                verification_status=receipt.verification_status,
            )

        # Observed model (client-observed, never elevated).
        if client_fields["observed_model"]:
            model_event, created_model = self.append_event(
                trajectory,
                event_type=EvidenceEventType.MODEL_REQUEST_OBSERVED.value,
                source_type=EvidenceSourceType.CLIENT_OBSERVED.value,
                source_reference=f"receipt:{receipt_ref}:observed_model",
                payload={"observed_model": client_fields["observed_model"]},
                occurred_at=occurred,
                correlation_id=receipt.correlation_id,
                trace_id=receipt.trace_id,
                deployment_control=receipt.deployment_control,
                verification_status=receipt.verification_status,
            )
            if created_model:
                self.evaluate_observed_model(
                    trajectory,
                    observed_model=str(client_fields["observed_model"]),
                    source_event_id=str(model_event.id),
                    client_type=client_fields.get("client_type"),
                )

        attempt_event, _ = self.append_event(
            trajectory,
            event_type=EvidenceEventType.TOOL_ATTEMPTED.value,
            source_type=EvidenceSourceType.RAI_AUTHORITATIVE.value,
            source_reference=tool_attempt_id,
            payload={
                "receipt_id": receipt_ref,
                "tool_id": str(receipt.tool_id) if receipt.tool_id else None,
                **self._tool_display_fields(receipt.tool_id),
                "action_digest": receipt.action_digest,
                "action_summary": receipt.action_summary,
                "integration_type": receipt.integration_type,
                "integration_id": str(receipt.integration_id)
                if receipt.integration_id
                else None,
            },
            occurred_at=occurred,
            correlation_id=receipt.correlation_id,
            trace_id=receipt.trace_id,
            deployment_control=receipt.deployment_control,
            verification_status=receipt.verification_status,
        )

        self.ensure_relation(
            trajectory,
            source_entity_type=EvidenceEntityType.RUNTIME_IDENTITY.value,
            source_entity_id=str(receipt.runtime_identity_id),
            relation_type=EvidenceRelationType.INITIATED.value,
            target_entity_type=EvidenceEntityType.EVENT.value,
            target_entity_id=str(attempt_event.id),
        )
        if receipt.tool_id:
            self.ensure_relation(
                trajectory,
                source_entity_type=EvidenceEntityType.EVENT.value,
                source_entity_id=str(attempt_event.id),
                relation_type=EvidenceRelationType.RELATED_TO.value,
                target_entity_type=EvidenceEntityType.TOOL.value,
                target_entity_id=str(receipt.tool_id),
            )

        # Authority resolved (from receipt identity binding).
        authority_event, _ = self.append_event(
            trajectory,
            event_type=EvidenceEventType.AUTHORITY_RESOLVED.value,
            source_type=EvidenceSourceType.RAI_AUTHORITATIVE.value,
            source_reference=f"receipt:{receipt_ref}:authority",
            payload={
                "runtime_identity_id": str(receipt.runtime_identity_id),
                "delegation_id": str(receipt.delegation_id)
                if receipt.delegation_id
                else None,
                "agent_version_id": str(receipt.agent_version_id),
            },
            occurred_at=occurred,
            correlation_id=receipt.correlation_id,
            trace_id=receipt.trace_id,
        )
        self.ensure_relation(
            trajectory,
            source_entity_type=EvidenceEntityType.EVENT.value,
            source_entity_id=str(attempt_event.id),
            relation_type=EvidenceRelationType.FOLLOWED_BY.value,
            target_entity_type=EvidenceEntityType.EVENT.value,
            target_entity_id=str(authority_event.id),
        )

        # Policy evaluation.
        if receipt.policy_decision is not None or receipt.policy_effect is not None:
            policy_event, _ = self.append_event(
                trajectory,
                event_type=EvidenceEventType.POLICY_EVALUATED.value,
                source_type=EvidenceSourceType.RAI_AUTHORITATIVE.value,
                source_reference=f"receipt:{receipt_ref}:policy",
                payload={
                    "policy_effect": receipt.policy_effect,
                    "matched_rule_ids": receipt.matched_rule_ids,
                    "policy_decision": receipt.policy_decision,
                    "reason_code": receipt.reason_code,
                    "human_explanation": receipt.human_explanation,
                    "tool_id": str(receipt.tool_id) if receipt.tool_id else None,
                    **self._tool_display_fields(receipt.tool_id),
                },
                occurred_at=occurred,
                correlation_id=receipt.correlation_id,
                trace_id=receipt.trace_id,
            )
            self.ensure_relation(
                trajectory,
                source_entity_type=EvidenceEntityType.EVENT.value,
                source_entity_id=str(attempt_event.id),
                relation_type=EvidenceRelationType.EVALUATED_BY.value,
                target_entity_type=EvidenceEntityType.EVENT.value,
                target_entity_id=str(policy_event.id),
            )
            for rule_id in receipt.matched_rule_ids or []:
                self.ensure_relation(
                    trajectory,
                    source_entity_type=EvidenceEntityType.EVENT.value,
                    source_entity_id=str(policy_event.id),
                    relation_type=EvidenceRelationType.MATCHED_POLICY.value,
                    target_entity_type=EvidenceEntityType.POLICY_RULE.value,
                    target_entity_id=str(rule_id),
                )

        # Approval lifecycle — shared source refs with WP3 projection for idempotency.
        if receipt.approval_request_id:
            apr_id = str(receipt.approval_request_id)
            approval_req_event, _ = self.append_event(
                trajectory,
                event_type=EvidenceEventType.APPROVAL_REQUESTED.value,
                source_type=EvidenceSourceType.RAI_AUTHORITATIVE.value,
                source_reference=f"approval:{apr_id}:requested",
                payload={
                    "approval_request_id": apr_id,
                    "approval_consumed": receipt.approval_consumed,
                    "projected_from": "receipt",
                },
                occurred_at=occurred,
                correlation_id=receipt.correlation_id,
                trace_id=receipt.trace_id,
            )
            self.ensure_relation(
                trajectory,
                source_entity_type=EvidenceEntityType.EVENT.value,
                source_entity_id=str(attempt_event.id),
                relation_type=EvidenceRelationType.REQUIRED_APPROVAL.value,
                target_entity_type=EvidenceEntityType.APPROVAL_REQUEST.value,
                target_entity_id=apr_id,
            )
            if receipt.approval_consumed:
                consumed_event, _ = self.append_event(
                    trajectory,
                    event_type=EvidenceEventType.APPROVAL_CONSUMED.value,
                    source_type=EvidenceSourceType.RAI_AUTHORITATIVE.value,
                    source_reference=f"approval:{apr_id}:consumed",
                    payload={
                        "approval_request_id": apr_id,
                        "projected_from": "receipt",
                    },
                    occurred_at=occurred,
                    correlation_id=receipt.correlation_id,
                    trace_id=receipt.trace_id,
                )
                self.ensure_relation(
                    trajectory,
                    source_entity_type=EvidenceEntityType.APPROVAL_REQUEST.value,
                    source_entity_id=apr_id,
                    relation_type=EvidenceRelationType.AUTHORIZED.value,
                    target_entity_type=EvidenceEntityType.RECEIPT.value,
                    target_entity_id=receipt_ref,
                )
                self.ensure_relation(
                    trajectory,
                    source_entity_type=EvidenceEntityType.EVENT.value,
                    source_entity_id=str(approval_req_event.id),
                    relation_type=EvidenceRelationType.FOLLOWED_BY.value,
                    target_entity_type=EvidenceEntityType.EVENT.value,
                    target_entity_id=str(consumed_event.id),
                )

        # Enforcement decision.
        decision = receipt.enforcement_decision
        if decision in {
            EnforcementDecisionType.ALLOW.value,
            EnforcementDecisionType.MONITOR.value,
        }:
            decision_type = EvidenceEventType.ACTION_ALLOWED.value
            decision_relation = EvidenceRelationType.AUTHORIZED.value
        else:
            decision_type = EvidenceEventType.ACTION_DENIED.value
            decision_relation = EvidenceRelationType.DENIED_BY.value

        decision_event, _ = self.append_event(
            trajectory,
            event_type=decision_type,
            source_type=EvidenceSourceType.RAI_AUTHORITATIVE.value,
            source_reference=f"receipt:{receipt_ref}:decision",
            payload={
                "enforcement_decision": decision,
                "reason_code": receipt.reason_code,
                "human_explanation": receipt.human_explanation,
                "enforcement_mode": receipt.enforcement_mode,
                "monitor": receipt.monitor,
                "tool_id": str(receipt.tool_id) if receipt.tool_id else None,
                **self._tool_display_fields(receipt.tool_id),
            },
            occurred_at=occurred,
            correlation_id=receipt.correlation_id,
            trace_id=receipt.trace_id,
        )
        self.ensure_relation(
            trajectory,
            source_entity_type=EvidenceEntityType.RECEIPT.value,
            source_entity_id=receipt_ref,
            relation_type=decision_relation,
            target_entity_type=EvidenceEntityType.EVENT.value,
            target_entity_id=str(decision_event.id),
        )

        # Execution lifecycle from receipt state.
        self._project_execution(trajectory, receipt, attempt_event)

        # Deterministic findings from receipt state.
        self._derive_receipt_findings(trajectory, receipt)

        # Coverage / completeness / status.
        self.refresh_coverage(trajectory)
        self._db.flush()
        return trajectory

    def project_receipt_safe(self, receipt_id: UUID) -> RuntimeTrajectory | None:
        """Best-effort projection that never raises into the WP4 path."""
        try:
            trajectory = self.project_receipt(receipt_id)
            self._db.commit()
            return trajectory
        except Exception:  # noqa: BLE001 — must not break enforcement
            logger.exception(
                "evidence.project_receipt_failed",
                extra={"receipt_id": str(receipt_id)},
            )
            self._db.rollback()
            return None

    def project_approval(
        self,
        approval_request_id: UUID,
    ) -> RuntimeTrajectory | None:
        """Project a WP3 approval request lifecycle into trajectory evidence."""
        from rai_gateway.approval.domain import ApprovalDecisionType, ApprovalStatus
        from rai_gateway.models.approval import ApprovalRequest
        from rai_gateway.models.runtime_enforcement import RuntimeEnforcementReceipt
        from rai_gateway.runtime_enforcement.repository import (
            RuntimeEnforcementRepository,
        )

        query = self._db.query(ApprovalRequest).filter(
            ApprovalRequest.id == approval_request_id
        )
        request = query.first()
        if not request:
            return None

        apr_id = str(request.id)
        conversation_id = None
        client_session_id = None
        client_integration_id = None
        related = RuntimeEnforcementRepository(self._db).list_receipts_for_approval(
            request.id, limit=5
        )
        if not related and request.correlation_id:
            related = (
                self._db.query(RuntimeEnforcementReceipt)
                .filter(
                    RuntimeEnforcementReceipt.runtime_identity_id
                    == request.runtime_identity_id,
                    RuntimeEnforcementReceipt.correlation_id == request.correlation_id,
                )
                .order_by(RuntimeEnforcementReceipt.started_at.desc())
                .limit(5)
                .all()
            )
        if related:
            fields = extract_client_session_fields(related[0].client_context)
            conversation_id = fields.get("conversation_id")
            client_session_id = fields.get("client_session_id")
            client_integration_id = self._resolve_client_integration_id(
                runtime_identity_id=request.runtime_identity_id,
                client_type=fields.get("client_type"),
            )

        trajectory = self.get_or_create_trajectory(
            ai_system_id=request.ai_system_id,
            agent_id=request.agent_id,
            agent_version_id=request.agent_version_id,
            runtime_identity_id=request.runtime_identity_id,
            client_integration_id=client_integration_id,
            delegation_id=request.delegation_id,
            conversation_id=conversation_id,
            client_session_id=client_session_id,
            correlation_id=request.correlation_id,
            occurred_at=request.created_at,
        )

        self.append_event(
            trajectory,
            event_type=EvidenceEventType.AUTHORITY_RESOLVED.value,
            source_type=EvidenceSourceType.RAI_AUTHORITATIVE.value,
            source_reference=f"approval:{apr_id}:authority",
            payload={
                "runtime_identity_id": str(request.runtime_identity_id),
                "delegation_id": str(request.delegation_id)
                if request.delegation_id
                else None,
                "agent_version_id": str(request.agent_version_id),
                "projected_from": "approval",
            },
            occurred_at=request.created_at or _utcnow(),
            correlation_id=request.correlation_id,
        )

        requested_event, _ = self.append_event(
            trajectory,
            event_type=EvidenceEventType.APPROVAL_REQUESTED.value,
            source_type=EvidenceSourceType.RAI_AUTHORITATIVE.value,
            source_reference=f"approval:{apr_id}:requested",
            payload={
                "approval_request_id": apr_id,
                "status": request.status,
                "action_digest": request.action_digest,
                "tool_id": str(request.tool_id) if request.tool_id else None,
                "risk_tier": request.risk_tier,
                "business_reason": request.business_reason,
                "requirement_reason": request.requirement_reason,
                "created_by": request.created_by,
                "expires_at": request.expires_at.isoformat()
                if request.expires_at
                else None,
                "projected_from": "approval",
            },
            occurred_at=request.created_at or _utcnow(),
            correlation_id=request.correlation_id,
        )
        self.ensure_relation(
            trajectory,
            source_entity_type=EvidenceEntityType.EVENT.value,
            source_entity_id=str(requested_event.id),
            relation_type=EvidenceRelationType.RELATED_TO.value,
            target_entity_type=EvidenceEntityType.APPROVAL_REQUEST.value,
            target_entity_id=apr_id,
        )

        for decision in request.decisions or []:
            decided_event, _ = self.append_event(
                trajectory,
                event_type=EvidenceEventType.APPROVAL_DECIDED.value,
                source_type=EvidenceSourceType.RAI_AUTHORITATIVE.value,
                source_reference=f"approval:{apr_id}:decided:{decision.id}",
                payload={
                    "approval_request_id": apr_id,
                    "decision_id": str(decision.id),
                    "decision": decision.decision,
                    "decided_by": decision.decided_by,
                    "decision_reason": decision.decision_reason,
                    "authentication_assurance": decision.authentication_assurance,
                    "projected_from": "approval",
                },
                occurred_at=decision.decided_at or request.decided_at or _utcnow(),
                correlation_id=decision.correlation_id or request.correlation_id,
            )
            relation = (
                EvidenceRelationType.APPROVED_BY.value
                if decision.decision == ApprovalDecisionType.APPROVED.value
                else EvidenceRelationType.REJECTED_BY.value
            )
            self.ensure_relation(
                trajectory,
                source_entity_type=EvidenceEntityType.APPROVAL_REQUEST.value,
                source_entity_id=apr_id,
                relation_type=relation,
                target_entity_type=EvidenceEntityType.APPROVAL_DECISION.value,
                target_entity_id=str(decision.id),
            )
            self.ensure_relation(
                trajectory,
                source_entity_type=EvidenceEntityType.EVENT.value,
                source_entity_id=str(requested_event.id),
                relation_type=EvidenceRelationType.FOLLOWED_BY.value,
                target_entity_type=EvidenceEntityType.EVENT.value,
                target_entity_id=str(decided_event.id),
            )

        if request.status == ApprovalStatus.CONSUMED.value:
            consumed_event, _ = self.append_event(
                trajectory,
                event_type=EvidenceEventType.APPROVAL_CONSUMED.value,
                source_type=EvidenceSourceType.RAI_AUTHORITATIVE.value,
                source_reference=f"approval:{apr_id}:consumed",
                payload={
                    "approval_request_id": apr_id,
                    "consumed_at": request.consumed_at.isoformat()
                    if request.consumed_at
                    else None,
                    "projected_from": "approval",
                },
                occurred_at=request.consumed_at or _utcnow(),
                correlation_id=request.correlation_id,
            )
            self.ensure_relation(
                trajectory,
                source_entity_type=EvidenceEntityType.EVENT.value,
                source_entity_id=str(requested_event.id),
                relation_type=EvidenceRelationType.FOLLOWED_BY.value,
                target_entity_type=EvidenceEntityType.EVENT.value,
                target_entity_id=str(consumed_event.id),
            )
            for receipt in related:
                self.ensure_relation(
                    trajectory,
                    source_entity_type=EvidenceEntityType.APPROVAL_REQUEST.value,
                    source_entity_id=apr_id,
                    relation_type=EvidenceRelationType.AUTHORIZED.value,
                    target_entity_type=EvidenceEntityType.RECEIPT.value,
                    target_entity_id=str(receipt.id),
                )

        self.refresh_coverage(trajectory)
        self._db.flush()
        return trajectory

    def project_approval_safe(self, approval_request_id: UUID) -> None:
        """Best-effort approval projection; never fails the WP3 path."""
        try:
            self.project_approval(approval_request_id)
            self._db.commit()
        except Exception:  # noqa: BLE001 — must not break approval lifecycle
            logger.exception(
                "evidence.project_approval_failed",
                extra={"approval_request_id": str(approval_request_id)},
            )
            self._db.rollback()

    def _project_execution(
        self,
        trajectory: RuntimeTrajectory,
        receipt: RuntimeEnforcementReceipt,
        attempt_event: EvidenceEvent,
    ) -> None:
        receipt_ref = str(receipt.id)
        status = receipt.execution_status
        source = receipt.execution_source

        if source == ExecutionSource.RAI_EXECUTED.value:
            event_source = EvidenceSourceType.RAI_EXECUTED.value
        elif source == ExecutionSource.CLIENT_REPORTED.value:
            event_source = EvidenceSourceType.CLIENT_REPORTED.value
        else:
            event_source = EvidenceSourceType.RAI_AUTHORITATIVE.value

        exec_occurred = (
            receipt.reported_at
            or receipt.completed_at
            or receipt.started_at
            or _utcnow()
        )

        if status in {
            ExecutionStatus.STARTED.value,
            ExecutionStatus.IN_PROGRESS.value,
            ExecutionStatus.PENDING_CLIENT_REPORT.value,
        }:
            started_event, _ = self.append_event(
                trajectory,
                event_type=EvidenceEventType.TOOL_EXECUTION_STARTED.value,
                source_type=event_source
                if status != ExecutionStatus.PENDING_CLIENT_REPORT.value
                else EvidenceSourceType.RAI_AUTHORITATIVE.value,
                source_reference=f"receipt:{receipt_ref}:exec_started",
                payload={
                    "execution_status": status,
                    "execution_source": source,
                    "enforcement_mode": receipt.enforcement_mode,
                    "tool_id": str(receipt.tool_id) if receipt.tool_id else None,
                    **self._tool_display_fields(receipt.tool_id),
                },
                occurred_at=receipt.started_at or exec_occurred,
                correlation_id=receipt.correlation_id,
                trace_id=receipt.trace_id,
                deployment_control=receipt.deployment_control,
                verification_status=receipt.verification_status,
            )
            self.ensure_relation(
                trajectory,
                source_entity_type=EvidenceEntityType.RECEIPT.value,
                source_entity_id=receipt_ref,
                relation_type=EvidenceRelationType.EXECUTED_AS.value,
                target_entity_type=EvidenceEntityType.EVENT.value,
                target_entity_id=str(started_event.id),
            )

        if status == ExecutionStatus.SUCCEEDED.value:
            success_event, _ = self.append_event(
                trajectory,
                event_type=EvidenceEventType.TOOL_EXECUTION_SUCCEEDED.value,
                source_type=event_source,
                source_reference=f"receipt:{receipt_ref}:exec_succeeded",
                payload={
                    "execution_status": status,
                    "execution_source": source,
                    "downstream_reference": receipt.downstream_reference,
                    "duration_ms": receipt.duration_ms,
                    "execution_report": receipt.execution_report,
                    "tool_id": str(receipt.tool_id) if receipt.tool_id else None,
                    **self._tool_display_fields(receipt.tool_id),
                },
                occurred_at=exec_occurred,
                correlation_id=receipt.correlation_id,
                trace_id=receipt.trace_id,
                deployment_control=receipt.deployment_control,
                verification_status=receipt.verification_status,
            )
            self.ensure_relation(
                trajectory,
                source_entity_type=EvidenceEntityType.RECEIPT.value,
                source_entity_id=receipt_ref,
                relation_type=EvidenceRelationType.EXECUTED_AS.value,
                target_entity_type=EvidenceEntityType.EVENT.value,
                target_entity_id=str(success_event.id),
            )
            if receipt.execution_report is not None:
                result_event, _ = self.append_event(
                    trajectory,
                    event_type=EvidenceEventType.TOOL_RESULT_OBSERVED.value,
                    source_type=event_source,
                    source_reference=f"receipt:{receipt_ref}:tool_result",
                    payload={
                        "execution_report": receipt.execution_report,
                        "tool_id": str(receipt.tool_id) if receipt.tool_id else None,
                        **self._tool_display_fields(receipt.tool_id),
                    },
                    occurred_at=exec_occurred,
                    correlation_id=receipt.correlation_id,
                    trace_id=receipt.trace_id,
                    deployment_control=receipt.deployment_control,
                    verification_status=receipt.verification_status,
                )
                self.ensure_relation(
                    trajectory,
                    source_entity_type=EvidenceEntityType.EVENT.value,
                    source_entity_id=str(success_event.id),
                    relation_type=EvidenceRelationType.PRODUCED.value,
                    target_entity_type=EvidenceEntityType.EVENT.value,
                    target_entity_id=str(result_event.id),
                )

        if status == ExecutionStatus.FAILED.value:
            failed_event, _ = self.append_event(
                trajectory,
                event_type=EvidenceEventType.TOOL_EXECUTION_FAILED.value,
                source_type=event_source,
                source_reference=f"receipt:{receipt_ref}:exec_failed",
                payload={
                    "execution_status": status,
                    "execution_source": source,
                    "downstream_reference": receipt.downstream_reference,
                    "duration_ms": receipt.duration_ms,
                    "execution_report": receipt.execution_report,
                    "tool_id": str(receipt.tool_id) if receipt.tool_id else None,
                    **self._tool_display_fields(receipt.tool_id),
                },
                occurred_at=exec_occurred,
                correlation_id=receipt.correlation_id,
                trace_id=receipt.trace_id,
                deployment_control=receipt.deployment_control,
                verification_status=receipt.verification_status,
            )
            self.ensure_relation(
                trajectory,
                source_entity_type=EvidenceEntityType.RECEIPT.value,
                source_entity_id=receipt_ref,
                relation_type=EvidenceRelationType.EXECUTED_AS.value,
                target_entity_type=EvidenceEntityType.EVENT.value,
                target_entity_id=str(failed_event.id),
            )

        if status == ExecutionStatus.UNKNOWN.value:
            missing_event, _ = self.append_event(
                trajectory,
                event_type=EvidenceEventType.EVIDENCE_MISSING.value,
                source_type=EvidenceSourceType.DERIVED.value,
                source_reference=f"receipt:{receipt_ref}:exec_missing",
                payload={
                    "expected": "post_execution_report",
                    "execution_status": status,
                    "receipt_id": receipt_ref,
                },
                occurred_at=exec_occurred,
                correlation_id=receipt.correlation_id,
                trace_id=receipt.trace_id,
            )
            self.ensure_relation(
                trajectory,
                source_entity_type=EvidenceEntityType.EVENT.value,
                source_entity_id=str(attempt_event.id),
                relation_type=EvidenceRelationType.DERIVED_FROM.value,
                target_entity_type=EvidenceEntityType.EVENT.value,
                target_entity_id=str(missing_event.id),
            )

    def _derive_receipt_findings(
        self,
        trajectory: RuntimeTrajectory,
        receipt: RuntimeEnforcementReceipt,
    ) -> None:
        if receipt.execution_status == ExecutionStatus.UNKNOWN.value and (
            receipt.enforcement_decision
            in {
                EnforcementDecisionType.ALLOW.value,
                EnforcementDecisionType.MONITOR.value,
            }
        ):
            self.ensure_finding(
                trajectory,
                finding_type=EvidenceFindingType.MISSING_EXECUTION_RESULT.value,
                severity=FindingSeverity.HIGH.value,
                title="Missing post-execution report",
                description=(
                    f"Receipt {receipt.id} was allowed but execution outcome "
                    "was never reported (status=UNKNOWN)."
                ),
                source_event_ids=[],
            )
            self._repo.update_trajectory(
                trajectory,
                status=TrajectoryStatus.INCOMPLETE.value,
            )

        if (
            receipt.enforcement_mode == "HOOK_ENFORCED"
            and receipt.verification_status in {None, "DECLARED", "UNKNOWN"}
            and receipt.deployment_control == "LOCAL_HOOK"
        ):
            self.ensure_finding(
                trajectory,
                finding_type=EvidenceFindingType.UNVERIFIED_ENFORCEMENT.value,
                severity=FindingSeverity.MEDIUM.value,
                title="Unverified local hook enforcement",
                description=(
                    "Execution evidence relies on an unverified local client hook "
                    "and must not be treated as authoritative."
                ),
            )

        if receipt.enforcement_decision == EnforcementDecisionType.DENY.value:
            reason = receipt.reason_code or ""
            if reason.startswith("AUTHORITY") or "AUTHORITY" in reason:
                finding_type = EvidenceFindingType.AUTHORITY_DENIAL.value
            else:
                finding_type = EvidenceFindingType.POLICY_DENIAL.value
            self.ensure_finding(
                trajectory,
                finding_type=finding_type,
                severity=FindingSeverity.MEDIUM.value,
                title=f"Action denied: {reason or 'policy/authority'}",
                description=receipt.human_explanation,
            )

        if receipt.reason_code in {
            "APPROVAL_ACTION_MISMATCH",
            "APPROVAL_ALREADY_CONSUMED",
            "APPROVAL_EXPIRED",
        }:
            self.ensure_finding(
                trajectory,
                finding_type=EvidenceFindingType.APPROVAL_MISMATCH.value,
                severity=FindingSeverity.HIGH.value,
                title=f"Approval mismatch: {receipt.reason_code}",
                description=receipt.human_explanation,
            )

    # ------------------------------------------------------------------
    # Coverage
    # ------------------------------------------------------------------

    def refresh_coverage(self, trajectory: RuntimeTrajectory) -> dict[str, Any]:
        events = self._repo.list_events(trajectory.id, limit=2000)
        types = {event.event_type for event in events}

        def has(*candidates: str) -> bool:
            return any(item in types for item in candidates)

        coverage = {
            "identity": CoverageState.COMPLETE.value
            if trajectory.runtime_identity_id
            or has(EvidenceEventType.AUTHORITY_RESOLVED.value)
            else CoverageState.MISSING.value,
            "authority": CoverageState.COMPLETE.value
            if has(EvidenceEventType.AUTHORITY_RESOLVED.value)
            else CoverageState.MISSING.value,
            "policy": (
                CoverageState.COMPLETE.value
                if has(EvidenceEventType.POLICY_EVALUATED.value)
                else (
                    CoverageState.NOT_REQUIRED.value
                    if not has(EvidenceEventType.TOOL_ATTEMPTED.value)
                    else CoverageState.MISSING.value
                )
            ),
            "approval": (
                CoverageState.COMPLETE.value
                if has(
                    EvidenceEventType.APPROVAL_CONSUMED.value,
                    EvidenceEventType.APPROVAL_DECIDED.value,
                )
                else (
                    CoverageState.NOT_REQUIRED.value
                    if not has(EvidenceEventType.APPROVAL_REQUESTED.value)
                    else CoverageState.MISSING.value
                )
            ),
            "execution": self._execution_coverage(types),
            "prompt": self._observation_coverage(
                events, (EvidenceEventType.PROMPT_OBSERVED.value,)
            ),
            "output": self._observation_coverage(
                events,
                (
                    EvidenceEventType.AGENT_OUTPUT_OBSERVED.value,
                    EvidenceEventType.MODEL_RESPONSE_OBSERVED.value,
                ),
            ),
            "model": self._observation_coverage(
                events, (EvidenceEventType.MODEL_REQUEST_OBSERVED.value,)
            ),
        }

        required_keys = ("identity", "authority", "policy", "execution")
        present = 0
        expected = 0
        for key in required_keys:
            state = coverage[key]
            if state == CoverageState.NOT_REQUIRED.value:
                continue
            expected += 1
            if state in {
                CoverageState.COMPLETE.value,
                CoverageState.OBSERVED.value,
                CoverageState.CAPTURED.value,
                CoverageState.REDACTED.value,
                CoverageState.HASH_ONLY.value,
                CoverageState.METADATA_ONLY.value,
                CoverageState.DO_NOT_STORE.value,
            }:
                present += 1
        # Approval counted when required.
        if coverage["approval"] != CoverageState.NOT_REQUIRED.value:
            expected += 1
            if coverage["approval"] == CoverageState.COMPLETE.value:
                present += 1

        completeness = int(round((present / expected) * 100)) if expected else 100

        assurance = {
            "highest": self._highest_assurance(events),
            "has_client_reported": any(
                e.source_type == EvidenceSourceType.CLIENT_REPORTED.value
                for e in events
            ),
            "has_authoritative": any(
                e.source_type
                in {
                    EvidenceSourceType.RAI_AUTHORITATIVE.value,
                    EvidenceSourceType.RAI_EXECUTED.value,
                }
                for e in events
            ),
        }

        status = trajectory.status
        if status == TrajectoryStatus.ACTIVE.value:
            if coverage["execution"] == CoverageState.MISSING.value and has(
                EvidenceEventType.ACTION_ALLOWED.value
            ):
                # Keep ACTIVE until gap threshold marks UNKNOWN / incomplete.
                pass
            elif coverage["execution"] in {
                CoverageState.COMPLETE.value,
                CoverageState.NOT_REQUIRED.value,
            } and has(
                EvidenceEventType.ACTION_DENIED.value,
                EvidenceEventType.TOOL_EXECUTION_SUCCEEDED.value,
                EvidenceEventType.TOOL_EXECUTION_FAILED.value,
            ):
                # Do not auto-complete multi-tool sessions; leave ACTIVE.
                pass

        if has(EvidenceEventType.EVIDENCE_MISSING.value):
            status = TrajectoryStatus.INCOMPLETE.value

        self._repo.update_trajectory(
            trajectory,
            coverage_summary=coverage,
            assurance_summary=assurance,
            completeness_pct=completeness,
            status=status,
            finding_count=len(self._repo.list_findings(trajectory.id)),
            event_count=len(events),
        )
        self._project_conversation(trajectory)
        return coverage

    def _execution_coverage(self, types: set[str]) -> str:
        if EvidenceEventType.TOOL_EXECUTION_SUCCEEDED.value in types:
            return CoverageState.COMPLETE.value
        if EvidenceEventType.TOOL_EXECUTION_FAILED.value in types:
            return CoverageState.COMPLETE.value
        if EvidenceEventType.EVIDENCE_MISSING.value in types:
            return CoverageState.MISSING.value
        if EvidenceEventType.ACTION_DENIED.value in types and not (
            EvidenceEventType.TOOL_EXECUTION_STARTED.value in types
            or EvidenceEventType.TOOL_EXECUTION_SUCCEEDED.value in types
        ):
            return CoverageState.NOT_REQUIRED.value
        if EvidenceEventType.TOOL_EXECUTION_STARTED.value in types:
            return CoverageState.UNKNOWN.value
        if EvidenceEventType.ACTION_ALLOWED.value in types:
            return CoverageState.MISSING.value
        # Approval-only / pre-tool trajectories are not missing execution yet.
        if EvidenceEventType.TOOL_ATTEMPTED.value not in types:
            return CoverageState.NOT_REQUIRED.value
        return CoverageState.UNKNOWN.value

    def _observation_coverage(
        self,
        events: list[EvidenceEvent],
        event_types: tuple[str, ...],
    ) -> str:
        """Map observation events to explicit availability reasons (not NOT_AVAILABLE)."""
        wanted = set(event_types)
        matching = [event for event in events if event.event_type in wanted]
        if not matching:
            return CoverageState.NOT_OBSERVED.value

        mode = (matching[0].content_handling_mode or "").upper()
        if mode == ContentHandlingMode.FULL.value:
            return CoverageState.CAPTURED.value
        if mode == ContentHandlingMode.REDACTED.value:
            return CoverageState.REDACTED.value
        if mode == ContentHandlingMode.HASH_ONLY.value:
            return CoverageState.HASH_ONLY.value
        if mode == ContentHandlingMode.METADATA_ONLY.value:
            return CoverageState.METADATA_ONLY.value
        if mode == ContentHandlingMode.DO_NOT_STORE.value:
            return CoverageState.DO_NOT_STORE.value
        # Observed without a recognized mode — still mark as observed/captured.
        return CoverageState.OBSERVED.value

    def _resolve_client_integration_id(
        self,
        *,
        runtime_identity_id: UUID,
        client_type: str | None,
    ) -> UUID | None:
        """Resolve RuntimeClientIntegration id; never use MCP integration_id."""
        if not client_type:
            return None
        try:
            from rai_gateway.models.client_hooks import RuntimeClientIntegration
        except ImportError:  # pragma: no cover
            return None
        row = (
            self._db.query(RuntimeClientIntegration)
            .filter(
                RuntimeClientIntegration.runtime_identity_id == runtime_identity_id,
                RuntimeClientIntegration.client_type == client_type,
            )
            .first()
        )
        return row.id if row else None

    def _highest_assurance(self, events: list[EvidenceEvent]) -> str:
        order = {
            AssuranceLevel.HIGH.value: 4,
            AssuranceLevel.MEDIUM.value: 3,
            AssuranceLevel.LOW.value: 2,
            AssuranceLevel.UNKNOWN.value: 1,
        }
        best = AssuranceLevel.UNKNOWN.value
        best_score = 0
        for event in events:
            score = order.get(event.assurance_level, 0)
            if score > best_score:
                best = event.assurance_level
                best_score = score
        return best

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def serialize_trajectory_summary(
        self, trajectory: RuntimeTrajectory, *, enrich_names: bool = True
    ) -> dict[str, Any]:
        summary: dict[str, Any] = {
            "id": str(trajectory.id),
            "ai_system_id": str(trajectory.ai_system_id),
            "agent_id": str(trajectory.agent_id),
            "agent_version_id": str(trajectory.agent_version_id),
            "runtime_identity_id": str(trajectory.runtime_identity_id),
            "client_integration_id": str(trajectory.client_integration_id)
            if trajectory.client_integration_id
            else None,
            "delegation_id": str(trajectory.delegation_id)
            if trajectory.delegation_id
            else None,
            "session_key": trajectory.session_key,
            "conversation_id": trajectory.conversation_id,
            "runtime_conversation_id": (
                str(trajectory.runtime_conversation_id)
                if trajectory.runtime_conversation_id
                else None
            ),
            "client_session_id": trajectory.client_session_id,
            "correlation_id": trajectory.correlation_id,
            "trajectory_semantics": getattr(trajectory, "trajectory_semantics", None),
            "started_at": trajectory.started_at.isoformat()
            if trajectory.started_at
            else None,
            "last_event_at": trajectory.last_event_at.isoformat()
            if trajectory.last_event_at
            else None,
            # Prefer closed end; fall back to last event so list Duration is not blank.
            "ended_at": (trajectory.ended_at or trajectory.last_event_at).isoformat()
            if (trajectory.ended_at or trajectory.last_event_at)
            else None,
            "status": trajectory.status,
            "enforcement_mode": trajectory.enforcement_mode,
            "deployment_control": trajectory.deployment_control,
            "assurance_summary": trajectory.assurance_summary or {},
            "coverage_summary": trajectory.coverage_summary or {},
            "event_count": trajectory.event_count,
            "finding_count": trajectory.finding_count,
            "completeness_pct": trajectory.completeness_pct,
            "legal_hold": trajectory.legal_hold,
            "retention_days": trajectory.retention_days,
            "eligible_for_purge_at": trajectory.eligible_for_purge_at.isoformat()
            if getattr(trajectory, "eligible_for_purge_at", None)
            else None,
        }
        if enrich_names:
            summary.update(self._resolve_display_names(trajectory))
            delegation = summary.get("delegation")
            if (
                not summary.get("delegation_id")
                and isinstance(delegation, dict)
                and delegation.get("id")
            ):
                summary["delegation_id"] = delegation["id"]
        return summary

    def _resolve_display_names(self, trajectory: RuntimeTrajectory) -> dict[str, Any]:
        from rai_gateway.models.client_hooks import RuntimeClientIntegration
        from rai_gateway.models.identity import AgentRuntimeIdentity, DelegationGrant
        from rai_gateway.models.productization import SdkSession
        from rai_gateway.models.registry import Agent, AgentVersion, AISystem

        system = (
            self._db.query(AISystem)
            .filter(AISystem.id == trajectory.ai_system_id)
            .first()
        )
        agent = self._db.query(Agent).filter(Agent.id == trajectory.agent_id).first()
        version = (
            self._db.query(AgentVersion)
            .filter(AgentVersion.id == trajectory.agent_version_id)
            .first()
        )
        identity = (
            self._db.query(AgentRuntimeIdentity)
            .filter(AgentRuntimeIdentity.id == trajectory.runtime_identity_id)
            .first()
        )
        client_type = None
        if trajectory.client_integration_id:
            integration = (
                self._db.query(RuntimeClientIntegration)
                .filter(RuntimeClientIntegration.id == trajectory.client_integration_id)
                .first()
            )
            client_type = integration.client_type if integration else None

        sdk_session = (
            self._db.query(SdkSession)
            .filter(SdkSession.trajectory_id == trajectory.id)
            .order_by(SdkSession.created_at.desc())
            .first()
        )
        if not client_type and sdk_session is not None:
            client_type = "sdk"
        if not client_type:
            for event in self._repo.list_events(trajectory.id, limit=50):
                payload = event.payload if isinstance(event.payload, dict) else {}
                raw = payload.get("client_type")
                if isinstance(raw, str) and raw.strip():
                    client_type = raw.strip()
                    break

        delegation = None
        delegation_id = trajectory.delegation_id
        if not delegation_id and sdk_session is not None and sdk_session.delegation_id:
            delegation_id = sdk_session.delegation_id
        if not delegation_id:
            # Backfill display from AUTHORITY_RESOLVED when the row was created
            # before observation/enforcement stamped trajectory.delegation_id.
            for event in self._repo.list_events(trajectory.id, limit=100):
                if event.event_type != EvidenceEventType.AUTHORITY_RESOLVED.value:
                    continue
                payload = event.payload if isinstance(event.payload, dict) else {}
                raw = payload.get("delegation_id")
                if not raw:
                    continue
                try:
                    delegation_id = UUID(str(raw))
                except (TypeError, ValueError):
                    continue
                break
        if not delegation_id and trajectory.runtime_identity_id:
            # Last resort: most recent ACTIVE grant for this runtime identity.
            grant_row = (
                self._db.query(DelegationGrant)
                .filter(
                    DelegationGrant.delegate_runtime_identity_id
                    == trajectory.runtime_identity_id,
                    DelegationGrant.status == "ACTIVE",
                )
                .order_by(DelegationGrant.created_at.desc())
                .first()
            )
            if grant_row:
                delegation_id = grant_row.id
        if delegation_id:
            grant = (
                self._db.query(DelegationGrant)
                .filter(DelegationGrant.id == delegation_id)
                .first()
            )
            if grant:
                delegation = {
                    "id": str(grant.id),
                    "delegator_type": grant.delegator_type,
                    "delegator_id": grant.delegator_id,
                    "delegate_runtime_identity_id": str(
                        grant.delegate_runtime_identity_id
                    ),
                    "parent_delegation_id": (
                        str(grant.parent_delegation_id)
                        if grant.parent_delegation_id
                        else None
                    ),
                    "status": grant.status,
                    "scope": grant.scope or {},
                    "valid_from": (
                        grant.valid_from.isoformat() if grant.valid_from else None
                    ),
                    "expires_at": (
                        grant.expires_at.isoformat() if grant.expires_at else None
                    ),
                    "created_by": grant.created_by,
                    "created_at": (
                        grant.created_at.isoformat() if grant.created_at else None
                    ),
                    "revoked_at": (
                        grant.revoked_at.isoformat() if grant.revoked_at else None
                    ),
                    "revocation_reason": grant.revocation_reason,
                }

        return {
            "ai_system_name": system.name if system else None,
            "agent_name": agent.name if agent else None,
            "agent_avatar": agent.avatar if agent else None,
            "agent_version_number": version.version_number if version else None,
            "runtime_identity_name": identity.name if identity else None,
            "client_type": client_type,
            "delegation": delegation,
        }

    def serialize_trajectory_detail(
        self, trajectory: RuntimeTrajectory
    ) -> dict[str, Any]:
        detail = self.serialize_trajectory_summary(trajectory)
        detail["events"] = [
            self.serialize_event(event)
            for event in self._repo.list_events(trajectory.id)
        ]
        detail["relations"] = [
            self.serialize_relation(rel)
            for rel in self._repo.list_relations(trajectory.id)
        ]
        detail["findings"] = [
            self.serialize_finding(finding)
            for finding in self._repo.list_findings(trajectory.id)
        ]
        detail["artifacts"] = [
            self.serialize_artifact(artifact)
            for artifact in self._repo.list_artifacts(trajectory.id)
        ]
        return detail

    def serialize_event(self, event: EvidenceEvent) -> dict[str, Any]:
        payload = event.payload if isinstance(event.payload, dict) else event.payload
        if (
            isinstance(payload, dict)
            and payload.get("tool_id")
            and not payload.get("tool_name")
        ):
            try:
                tool_uuid = UUID(str(payload["tool_id"]))
            except (TypeError, ValueError):
                tool_uuid = None
            if tool_uuid is not None:
                enriched = dict(payload)
                enriched.update(self._tool_display_fields(tool_uuid))
                payload = enriched
        preview = None
        content_status = None
        if isinstance(payload, dict):
            preview = content_preview(payload)
        if preview:
            content_status = "AVAILABLE"
        else:
            content_status = content_status_for_mode(event.content_handling_mode)
        return {
            "id": str(event.id),
            "trajectory_id": str(event.trajectory_id),
            "event_type": event.event_type,
            "occurred_at": event.occurred_at.isoformat() if event.occurred_at else None,
            "recorded_at": event.recorded_at.isoformat() if event.recorded_at else None,
            "sequence_number": event.sequence_number,
            "source_type": event.source_type,
            "source_reference": event.source_reference,
            "assurance_level": event.assurance_level,
            "correlation_id": event.correlation_id,
            "trace_id": event.trace_id,
            "payload": payload,
            "payload_digest": event.payload_digest,
            "content_handling_mode": event.content_handling_mode,
            "redaction_status": event.redaction_status,
            "content_preview": preview,
            "content_status": content_status,
        }

    def serialize_event_detail(
        self, trajectory: RuntimeTrajectory, event: EvidenceEvent
    ) -> dict[str, Any]:
        """Full event detail including related events and linked artifacts."""
        detail = self.serialize_event(event)
        artifacts = self._repo.list_artifacts_for_event(
            trajectory_id=trajectory.id, event_id=event.id
        )
        detail["artifacts"] = [self.serialize_artifact(a) for a in artifacts]
        related: list[dict[str, Any]] = []
        for other in self._repo.list_events(trajectory.id):
            if other.id == event.id:
                continue
            # Same generation / observation family or nearby sequence.
            same_gen = (
                event.correlation_id
                and other.correlation_id
                and event.correlation_id == other.correlation_id
            )
            nearby = (
                abs((other.sequence_number or 0) - (event.sequence_number or 0)) <= 5
            )
            if same_gen or nearby:
                related.append(
                    {
                        "id": str(other.id),
                        "event_type": other.event_type,
                        "occurred_at": other.occurred_at.isoformat()
                        if other.occurred_at
                        else None,
                        "sequence_number": other.sequence_number,
                        "source_type": other.source_type,
                        "assurance_level": other.assurance_level,
                    }
                )
            if len(related) >= 12:
                break
        detail["related_events"] = related
        detail["trajectory"] = {
            "id": str(trajectory.id),
            "conversation_id": trajectory.conversation_id,
            "client_session_id": trajectory.client_session_id,
            "correlation_id": trajectory.correlation_id,
            "deployment_control": trajectory.deployment_control,
            **self._resolve_display_names(trajectory),
        }
        return detail

    def serialize_relation(self, relation: EvidenceRelation) -> dict[str, Any]:
        return {
            "id": str(relation.id),
            "trajectory_id": str(relation.trajectory_id),
            "source_entity_type": relation.source_entity_type,
            "source_entity_id": relation.source_entity_id,
            "relation_type": relation.relation_type,
            "target_entity_type": relation.target_entity_type,
            "target_entity_id": relation.target_entity_id,
            "created_at": relation.created_at.isoformat()
            if relation.created_at
            else None,
        }

    def serialize_finding(self, finding: EvidenceFinding) -> dict[str, Any]:
        return {
            "id": str(finding.id),
            "trajectory_id": str(finding.trajectory_id),
            "finding_type": finding.finding_type,
            "severity": finding.severity,
            "title": finding.title,
            "description": finding.description,
            "source_event_ids": finding.source_event_ids or [],
            "status": finding.status,
            "created_at": finding.created_at.isoformat()
            if finding.created_at
            else None,
        }

    def serialize_artifact(self, artifact: Any) -> dict[str, Any]:
        return {
            "id": str(artifact.id),
            "trajectory_id": str(artifact.trajectory_id),
            "event_id": str(artifact.event_id) if artifact.event_id else None,
            "artifact_type": artifact.artifact_type,
            "source_type": artifact.source_type,
            "content_location": artifact.content_location,
            "inline_content": artifact.inline_content,
            "content_digest": artifact.content_digest,
            "mime_type": artifact.mime_type,
            "size_bytes": artifact.size_bytes,
            "content_handling_mode": artifact.content_handling_mode,
            "sensitivity_classification": artifact.sensitivity_classification,
            "encrypted": artifact.encrypted,
            "created_at": artifact.created_at.isoformat()
            if artifact.created_at
            else None,
        }

    def export_trajectory(self, trajectory: RuntimeTrajectory) -> dict[str, Any]:
        from rai_gateway.evidence.redaction import sha256_digest

        detail = self.serialize_trajectory_detail(trajectory)
        export = {
            "schema_version": "wp5.evidence.v1",
            "generated_at": _utcnow().isoformat(),
            "trajectory_id": str(trajectory.id),
            "trajectory": detail,
        }
        export["export_digest"] = sha256_digest(
            {
                "trajectory_id": export["trajectory_id"],
                "schema_version": export["schema_version"],
                "events": [
                    {"id": e["id"], "payload_digest": e["payload_digest"]}
                    for e in detail["events"]
                ],
                "findings": [f["id"] for f in detail["findings"]],
                "relations": [r["id"] for r in detail["relations"]],
            }
        )
        return export

    # ------------------------------------------------------------------
    # Observed user prompts (operator list / detail)
    # ------------------------------------------------------------------

    def list_observed_prompts(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        query = self._db.query(EvidenceEvent).filter(
            EvidenceEvent.event_type == EvidenceEventType.PROMPT_OBSERVED.value
        )
        events = (
            query.order_by(EvidenceEvent.occurred_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [self.serialize_observed_prompt_summary(event) for event in events]

    def get_observed_prompt(
        self,
        event_id: UUID,
    ) -> dict[str, Any] | None:
        query = self._db.query(EvidenceEvent).filter(
            EvidenceEvent.id == event_id,
            EvidenceEvent.event_type == EvidenceEventType.PROMPT_OBSERVED.value,
        )
        event = query.first()
        if not event:
            return None
        return self.serialize_observed_prompt_detail(event)

    def serialize_observed_prompt_summary(self, event: EvidenceEvent) -> dict[str, Any]:
        from rai_gateway.evidence.redaction import extract_inline_content

        trajectory = self.get_trajectory(event.trajectory_id)
        names = self._resolve_display_names(trajectory) if trajectory else {}
        payload = event.payload if isinstance(event.payload, dict) else {}
        content = extract_inline_content(payload) if isinstance(payload, dict) else None

        artifacts = self._repo.list_artifacts_for_event(
            trajectory_id=event.trajectory_id, event_id=event.id
        )
        size_bytes = None
        for artifact in artifacts:
            if artifact.size_bytes is not None:
                size_bytes = artifact.size_bytes
                if not content and artifact.inline_content:
                    content = artifact.inline_content
                break
        if size_bytes is None and content:
            size_bytes = len(content.encode("utf-8"))

        enforcement_status, execution_status = (
            self._prompt_status_from_trajectory(trajectory)
            if trajectory
            else (None, None)
        )

        preview = content
        if preview and len(preview) > 160:
            preview = preview[:159].rstrip() + "…"

        return {
            "id": str(event.id),
            "trajectory_id": str(event.trajectory_id),
            "occurred_at": event.occurred_at.isoformat() if event.occurred_at else None,
            "content_preview": preview,
            "content_bytes": size_bytes,
            "content_handling_mode": event.content_handling_mode,
            "content_status": (
                "AVAILABLE"
                if content
                else content_status_for_mode(event.content_handling_mode)
            ),
            "trajectory_score": trajectory.completeness_pct if trajectory else None,
            "trajectory_status": trajectory.status if trajectory else None,
            "enforcement_status": enforcement_status,
            "execution_status": execution_status,
            "event_count": trajectory.event_count if trajectory else 0,
            "ai_system_id": str(trajectory.ai_system_id) if trajectory else None,
            "ai_system_name": names.get("ai_system_name"),
            "agent_id": str(trajectory.agent_id) if trajectory else None,
            "agent_name": names.get("agent_name"),
            "agent_avatar": names.get("agent_avatar"),
            "runtime_identity_id": (
                str(trajectory.runtime_identity_id) if trajectory else None
            ),
            "runtime_identity_name": names.get("runtime_identity_name"),
            "client_type": names.get("client_type"),
            "correlation_id": event.correlation_id
            or (trajectory.correlation_id if trajectory else None),
        }

    def serialize_observed_prompt_detail(self, event: EvidenceEvent) -> dict[str, Any]:
        summary = self.serialize_observed_prompt_summary(event)
        trajectory = self.get_trajectory(event.trajectory_id)
        if not trajectory:
            return summary

        events = self._repo.list_events(trajectory.id)
        payload = event.payload if isinstance(event.payload, dict) else {}
        user_prompt = None
        if isinstance(payload, dict):
            for key in ("prompt", "content", "text"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    user_prompt = value
                    break
        artifacts = self._repo.list_artifacts_for_event(
            trajectory_id=trajectory.id, event_id=event.id
        )
        if not user_prompt:
            for artifact in artifacts:
                if artifact.inline_content:
                    user_prompt = artifact.inline_content
                    break

        client_user_email = None
        observed_model = None
        if isinstance(payload, dict):
            for key in (
                "user_email",
                "observed_client_user",
                "client_user",
                "observed_user",
            ):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    client_user_email = value
                    break
            model_val = payload.get("observed_model") or payload.get("model")
            if isinstance(model_val, str) and model_val.strip():
                observed_model = model_val

        model_responses: list[dict[str, Any]] = []
        agent_outputs: list[dict[str, Any]] = []
        policy_evaluations: list[dict[str, Any]] = []
        rejections: list[dict[str, Any]] = []

        for other in events:
            other_payload = other.payload if isinstance(other.payload, dict) else {}
            if not client_user_email and isinstance(other_payload, dict):
                for key in (
                    "user_email",
                    "observed_client_user",
                    "client_user",
                    "observed_user",
                ):
                    value = other_payload.get(key)
                    if isinstance(value, str) and value.strip():
                        client_user_email = value
                        break
            if (
                not observed_model
                and isinstance(other_payload, dict)
                and other_payload.get("observed_model")
            ):
                observed_model = str(other_payload["observed_model"])

            if other.event_type == EvidenceEventType.MODEL_RESPONSE_OBSERVED.value:
                model_responses.append(self.serialize_event(other))
            elif other.event_type == EvidenceEventType.AGENT_OUTPUT_OBSERVED.value:
                agent_outputs.append(self.serialize_event(other))
            elif other.event_type == EvidenceEventType.POLICY_EVALUATED.value:
                policy_evaluations.append(self.serialize_event(other))
            elif other.event_type in (
                EvidenceEventType.ACTION_DENIED.value,
                EvidenceEventType.APPROVAL_DECIDED.value,
            ):
                effect = None
                if isinstance(other_payload, dict):
                    effect = other_payload.get("decision") or other_payload.get(
                        "enforcement_decision"
                    )
                    if other.event_type == EvidenceEventType.APPROVAL_DECIDED.value:
                        decision = other_payload.get("decision") or other_payload.get(
                            "status"
                        )
                        if str(decision).upper() not in {"REJECTED", "DENIED", "DENY"}:
                            continue
                        effect = decision
                if other.event_type == EvidenceEventType.ACTION_DENIED.value or effect:
                    rejections.append(self.serialize_event(other))

        if (
            summary.get("enforcement_status") is None
            or summary.get("execution_status") is None
        ):
            corr = summary.get("correlation_id")
            if corr:
                receipt = (
                    self._db.query(RuntimeEnforcementReceipt)
                    .filter(RuntimeEnforcementReceipt.correlation_id == corr)
                    .order_by(RuntimeEnforcementReceipt.started_at.desc())
                    .first()
                )
                if receipt:
                    if summary.get("enforcement_status") is None:
                        summary["enforcement_status"] = receipt.enforcement_decision
                    if summary.get("execution_status") is None:
                        summary["execution_status"] = receipt.execution_status
                    if not client_user_email and isinstance(
                        receipt.client_context, dict
                    ):
                        client_user_email = receipt.client_context.get(
                            "user_email"
                        ) or receipt.client_context.get("observed_client_user")
                    if not observed_model and isinstance(receipt.client_context, dict):
                        observed_model = receipt.client_context.get("observed_model")

        summary.update(
            {
                "user_prompt": user_prompt,
                "client_user_email": client_user_email,
                "observed_model": observed_model,
                "ai_identity": {
                    "runtime_identity_id": str(trajectory.runtime_identity_id),
                    "runtime_identity_name": summary.get("runtime_identity_name"),
                    "ai_system_id": str(trajectory.ai_system_id),
                    "ai_system_name": summary.get("ai_system_name"),
                    "agent_id": str(trajectory.agent_id),
                    "agent_name": summary.get("agent_name"),
                    "agent_avatar": summary.get("agent_avatar"),
                    "agent_version_id": str(trajectory.agent_version_id),
                },
                "model_responses": model_responses,
                "agent_outputs": agent_outputs,
                "policy_evaluations": policy_evaluations,
                "rejections": rejections,
                "events": [self.serialize_event(e) for e in events],
                "findings": [
                    self.serialize_finding(f)
                    for f in self._repo.list_findings(trajectory.id)
                ],
            }
        )
        return summary

    def _prompt_status_from_trajectory(
        self, trajectory: RuntimeTrajectory
    ) -> tuple[str | None, str | None]:
        events = self._repo.list_events(trajectory.id)
        enforcement_status: str | None = None
        execution_status: str | None = None
        for event in events:
            payload = event.payload if isinstance(event.payload, dict) else {}
            if event.event_type == EvidenceEventType.ACTION_DENIED.value:
                enforcement_status = "DENY"
            elif event.event_type == EvidenceEventType.ACTION_ALLOWED.value:
                if enforcement_status is None:
                    decision = None
                    if isinstance(payload, dict):
                        decision = payload.get("enforcement_decision") or payload.get(
                            "decision"
                        )
                    enforcement_status = str(decision) if decision else "ALLOW"
            elif event.event_type == EvidenceEventType.POLICY_EVALUATED.value:
                if enforcement_status is None and isinstance(payload, dict):
                    effect = payload.get("policy_effect") or payload.get("effect")
                    if effect:
                        enforcement_status = str(effect)
            elif event.event_type == EvidenceEventType.TOOL_EXECUTION_SUCCEEDED.value:
                execution_status = "SUCCEEDED"
            elif event.event_type == EvidenceEventType.TOOL_EXECUTION_FAILED.value:
                execution_status = "FAILED"
            elif event.event_type == EvidenceEventType.TOOL_EXECUTION_STARTED.value:
                if execution_status is None:
                    execution_status = "STARTED"
        if enforcement_status is None or execution_status is None:
            corr = trajectory.correlation_id
            if corr:
                receipt = (
                    self._db.query(RuntimeEnforcementReceipt)
                    .filter(RuntimeEnforcementReceipt.correlation_id == corr)
                    .order_by(RuntimeEnforcementReceipt.started_at.desc())
                    .first()
                )
                if receipt:
                    enforcement_status = (
                        enforcement_status or receipt.enforcement_decision
                    )
                    execution_status = execution_status or receipt.execution_status
        return enforcement_status, execution_status
