"""Lifecycle projection — business-readable stages over immutable evidence events."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from rai_gateway.evidence.domain import (
    ContentHandlingMode,
    CoverageState,
    EvidenceEventType,
)
from rai_gateway.evidence.redaction import content_preview, extract_inline_content
from rai_gateway.models.evidence import EvidenceEvent, RuntimeTrajectory
from rai_gateway.models.identity import AgentRuntimeIdentity, DelegationGrant
from rai_gateway.models.registry import Agent, AgentVersion, AISystem, ToolResource

_ACTION_TYPES = frozenset(
    {
        EvidenceEventType.TOOL_ATTEMPTED.value,
        EvidenceEventType.AUTHORITY_RESOLVED.value,
        EvidenceEventType.POLICY_EVALUATED.value,
        EvidenceEventType.APPROVAL_REQUESTED.value,
        EvidenceEventType.APPROVAL_DECIDED.value,
        EvidenceEventType.APPROVAL_CONSUMED.value,
        EvidenceEventType.ACTION_ALLOWED.value,
        EvidenceEventType.ACTION_DENIED.value,
        EvidenceEventType.TOOL_EXECUTION_STARTED.value,
        EvidenceEventType.TOOL_EXECUTION_SUCCEEDED.value,
        EvidenceEventType.TOOL_EXECUTION_FAILED.value,
        EvidenceEventType.TOOL_RESULT_OBSERVED.value,
    }
)

# Application-reported configuration provenance keys (not RAI-owned prompts).
_PROVENANCE_KEYS = (
    "configuration_id",
    "configuration_version",
    "configuration_digest",
    "configuration_source",
    "configuration_environment",
    "deployment_id",
    "release_id",
)


class LifecycleProjectionService:
    """Project immutable evidence events into a stable lifecycle DTO."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def project(
        self,
        trajectory: RuntimeTrajectory,
        *,
        events: list[EvidenceEvent] | None = None,
    ) -> dict[str, Any]:
        rows = events
        if rows is None:
            from rai_gateway.evidence.repository import EvidenceRepository

            rows = EvidenceRepository(self._db).list_events(trajectory.id, limit=2000)
        ordered = sorted(
            rows, key=lambda e: (e.sequence_number, e.occurred_at or datetime.min)
        )

        stages: list[dict[str, Any]] = []
        action_buckets: dict[str, list[EvidenceEvent]] = {}
        action_order: list[str] = []

        for event in ordered:
            if event.event_type in {
                EvidenceEventType.PROMPT_OBSERVED.value,
            }:
                stages.append(self._input_stage(event))
            elif event.event_type == EvidenceEventType.MODEL_REQUEST_OBSERVED.value:
                stages.append(self._model_stage(event))
            elif event.event_type in {
                EvidenceEventType.AGENT_OUTPUT_OBSERVED.value,
                EvidenceEventType.MODEL_RESPONSE_OBSERVED.value,
            }:
                stages.append(self._output_stage(event))
            elif event.event_type == EvidenceEventType.SESSION_COMPLETED.value:
                stages.append(self._completed_stage(event, trajectory))
            elif event.event_type in _ACTION_TYPES:
                key = self._action_group_key(event)
                if key not in action_buckets:
                    action_buckets[key] = []
                    action_order.append(key)
                action_buckets[key].append(event)

        # Insert action stages in first-seen order among lifecycle stages by
        # earliest sequence of their attempt event.
        action_stages = [
            self._action_stage(key, action_buckets[key], trajectory)
            for key in action_order
        ]
        stages = self._merge_by_sequence(stages, action_stages)

        # Explicit gaps when prompt/model/output never observed.
        types = {e.event_type for e in ordered}
        if EvidenceEventType.PROMPT_OBSERVED.value not in types:
            stages.insert(
                0,
                {
                    "id": "stage-input-missing",
                    "type": "INPUT",
                    "label": "User Request",
                    "status": CoverageState.NOT_OBSERVED.value,
                    "occurred_at": None,
                    "event_ids": [],
                    "content": {
                        "availability": CoverageState.NOT_OBSERVED.value,
                        "preview": None,
                        "reason": "No observeInput / prompt hook recorded for this turn",
                    },
                },
            )
        if EvidenceEventType.MODEL_REQUEST_OBSERVED.value not in types:
            # Place after input if present.
            insert_at = 1 if stages and stages[0].get("type") == "INPUT" else 0
            stages.insert(
                insert_at,
                {
                    "id": "stage-model-missing",
                    "type": "MODEL",
                    "label": "Model",
                    "status": CoverageState.NOT_OBSERVED.value,
                    "occurred_at": None,
                    "event_ids": [],
                    "content": {
                        "availability": CoverageState.NOT_OBSERVED.value,
                        "preview": None,
                        "reason": "observed_model was not supplied by the integration",
                    },
                },
            )

        if trajectory.status in {"COMPLETED", "CLOSED"} and not any(
            s.get("type") == "COMPLETED" for s in stages
        ):
            stages.append(self._completed_stage(None, trajectory))

        summary = self._summary(trajectory, ordered)
        stages = self._attach_metering(trajectory, stages, summary)
        provenance = self._extract_configuration_provenance(ordered)
        return {
            "trajectory_id": str(trajectory.id),
            "conversation_id": trajectory.conversation_id,
            "runtime_conversation_id": (
                str(trajectory.runtime_conversation_id)
                if trajectory.runtime_conversation_id
                else None
            ),
            "status": trajectory.status,
            "summary": summary,
            "configuration_provenance": provenance,
            "stages": stages,
        }

    def _merge_by_sequence(
        self,
        non_action: list[dict[str, Any]],
        actions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        combined = non_action + actions

        def sort_key(stage: dict[str, Any]) -> tuple[int, str]:
            seq = stage.get("_sort_seq")
            if seq is None:
                # Missing stages sort early within their type.
                if stage.get("type") == "INPUT":
                    return (-2, stage.get("id", ""))
                if stage.get("type") == "MODEL":
                    return (-1, stage.get("id", ""))
                return (10_000, stage.get("id", ""))
            return (int(seq), stage.get("id", ""))

        ordered = sorted(combined, key=sort_key)
        for stage in ordered:
            stage.pop("_sort_seq", None)
        return ordered

    def _action_group_key(self, event: EvidenceEvent) -> str:
        payload = event.payload if isinstance(event.payload, dict) else {}
        receipt = payload.get("receipt_id")
        if receipt:
            return f"receipt:{receipt}"
        digest = payload.get("action_digest")
        if digest:
            return f"digest:{digest}"
        # Fall back to source_reference prefix before last colon segment.
        ref = event.source_reference or str(event.id)
        if ":attempt" in ref:
            return ref.split(":attempt")[0]
        return f"event:{event.id}"

    def _content_block(self, event: EvidenceEvent) -> dict[str, Any]:
        mode = (event.content_handling_mode or "").upper()
        availability = mode
        if mode == ContentHandlingMode.FULL.value:
            availability = CoverageState.CAPTURED.value
        payload = event.payload if isinstance(event.payload, dict) else None
        preview = content_preview(payload)
        inline = extract_inline_content(payload)
        reason = None
        if availability in {
            ContentHandlingMode.METADATA_ONLY.value,
            ContentHandlingMode.HASH_ONLY.value,
            ContentHandlingMode.DO_NOT_STORE.value,
            ContentHandlingMode.REDACTED.value,
        }:
            reason = f"Evidence content policy = {mode}"
        return {
            "availability": availability,
            "preview": preview or (inline[:120] if inline else None),
            "reason": reason,
        }

    def _evidence_block(self, event: EvidenceEvent) -> dict[str, Any]:
        return {
            "source": event.source_type,
            "assurance": event.assurance_level,
        }

    def _input_stage(self, event: EvidenceEvent) -> dict[str, Any]:
        return {
            "id": f"stage-input-{event.id}",
            "type": "INPUT",
            "label": "User Request",
            "status": self._content_block(event)["availability"],
            "occurred_at": event.occurred_at.isoformat() if event.occurred_at else None,
            "event_ids": [str(event.id)],
            "content": self._content_block(event),
            "evidence": self._evidence_block(event),
            "_sort_seq": event.sequence_number,
        }

    def _model_stage(self, event: EvidenceEvent) -> dict[str, Any]:
        payload = event.payload if isinstance(event.payload, dict) else {}
        model = payload.get("observed_model") or payload.get("model")
        stage: dict[str, Any] = {
            "id": f"stage-model-{event.id}",
            "type": "MODEL",
            "label": "Model",
            "status": CoverageState.OBSERVED.value,
            "occurred_at": event.occurred_at.isoformat() if event.occurred_at else None,
            "event_ids": [str(event.id)],
            "model": {
                "observed_model": model,
                "observational": True,
            },
            "evidence": self._evidence_block(event),
            "_sort_seq": event.sequence_number,
        }
        digest = payload.get("configuration_digest")
        if isinstance(digest, str) and digest.strip():
            stage["configuration_digest"] = digest
        return stage

    def _extract_configuration_provenance(
        self, events: list[EvidenceEvent]
    ) -> dict[str, Any] | None:
        """Collect application-reported configuration identifiers from evidence."""
        preferred = {
            EvidenceEventType.PROMPT_OBSERVED.value,
            EvidenceEventType.MODEL_REQUEST_OBSERVED.value,
            EvidenceEventType.MODEL_RESPONSE_OBSERVED.value,
            EvidenceEventType.AGENT_OUTPUT_OBSERVED.value,
            EvidenceEventType.SESSION_STARTED.value,
        }
        candidates = [e for e in events if e.event_type in preferred] or events
        merged: dict[str, Any] = {}
        for event in candidates:
            payload = event.payload if isinstance(event.payload, dict) else {}
            for key in _PROVENANCE_KEYS:
                value = payload.get(key)
                if isinstance(value, str) and value.strip() and key not in merged:
                    merged[key] = value.strip()
        if not merged:
            return None
        return {
            **merged,
            "source": merged.get("configuration_source") or "APPLICATION_REPORTED",
            "assurance": "APPLICATION_REPORTED",
        }

    def last_observed_for_system(
        self,
        *,
        ai_system_id: UUID,
        lookback_limit: int = 200,
    ) -> dict[str, Any] | None:
        """Return the most recent application-reported config for an AI system.

        Labels remain APPLICATION_REPORTED — RAI does not verify persona bodies.
        """
        system = (
            self._db.query(AISystem)
            .filter(
                AISystem.id == ai_system_id,
            )
            .first()
        )
        if system is None:
            return None

        preferred = {
            EvidenceEventType.PROMPT_OBSERVED.value,
            EvidenceEventType.MODEL_REQUEST_OBSERVED.value,
            EvidenceEventType.MODEL_RESPONSE_OBSERVED.value,
            EvidenceEventType.AGENT_OUTPUT_OBSERVED.value,
            EvidenceEventType.SESSION_STARTED.value,
        }
        pairs = (
            self._db.query(EvidenceEvent, RuntimeTrajectory)
            .join(
                RuntimeTrajectory,
                EvidenceEvent.trajectory_id == RuntimeTrajectory.id,
            )
            .filter(RuntimeTrajectory.ai_system_id == ai_system_id)
            .filter(EvidenceEvent.event_type.in_(preferred))
            .order_by(EvidenceEvent.occurred_at.desc(), EvidenceEvent.id.desc())
            .limit(max(1, min(lookback_limit, 500)))
            .all()
        )
        if not pairs:
            return {
                "ai_system_id": str(ai_system_id),
                "found": False,
                "source": "APPLICATION_REPORTED",
                "assurance": "UNKNOWN",
                "message": "No application-reported configuration observed yet.",
            }

        # Prefer the newest event that carries configuration provenance keys.
        # MODEL_REQUEST_OBSERVED synthesized from observe_input may only have
        # observed_model and must not shadow the prompt/session provenance.
        fallback_model: dict[str, Any] | None = None
        for event, trajectory in pairs:
            payload = event.payload if isinstance(event.payload, dict) else {}
            merged: dict[str, Any] = {}
            for key in _PROVENANCE_KEYS:
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    merged[key] = value.strip()
            model = payload.get("observed_model") or payload.get("model")
            model_str = (
                model.strip() if isinstance(model, str) and model.strip() else None
            )
            if model_str and fallback_model is None:
                fallback_model = {
                    "ai_system_id": str(ai_system_id),
                    "found": True,
                    "observed_model": model_str,
                    "source": "APPLICATION_REPORTED",
                    "assurance": "APPLICATION_REPORTED",
                    "last_seen_at": (
                        event.occurred_at.isoformat() if event.occurred_at else None
                    ),
                    "trajectory_id": str(trajectory.id),
                    "conversation_id": trajectory.conversation_id,
                    "message": (
                        "Application-reported runtime metadata. RAI does not own or "
                        "verify the application persona / system prompt body."
                    ),
                }
            if not merged:
                continue
            if model_str:
                merged["observed_model"] = model_str
            return {
                "ai_system_id": str(ai_system_id),
                "found": True,
                **merged,
                "source": merged.get("configuration_source") or "APPLICATION_REPORTED",
                "assurance": "APPLICATION_REPORTED",
                "last_seen_at": (
                    event.occurred_at.isoformat() if event.occurred_at else None
                ),
                "trajectory_id": str(trajectory.id),
                "conversation_id": trajectory.conversation_id,
                "message": (
                    "Application-reported runtime metadata. RAI does not own or "
                    "verify the application persona / system prompt body."
                ),
            }
        if fallback_model is not None:
            return fallback_model
        return {
            "ai_system_id": str(ai_system_id),
            "found": False,
            "source": "APPLICATION_REPORTED",
            "assurance": "UNKNOWN",
            "message": "Recent events lack configuration provenance metadata.",
        }

    def _output_stage(self, event: EvidenceEvent) -> dict[str, Any]:
        return {
            "id": f"stage-output-{event.id}",
            "type": "OUTPUT",
            "label": "AI Response",
            "status": self._content_block(event)["availability"],
            "occurred_at": event.occurred_at.isoformat() if event.occurred_at else None,
            "event_ids": [str(event.id)],
            "content": self._content_block(event),
            "evidence": self._evidence_block(event),
            "_sort_seq": event.sequence_number,
        }

    def _completed_stage(
        self, event: EvidenceEvent | None, trajectory: RuntimeTrajectory
    ) -> dict[str, Any]:
        occurred = None
        event_ids: list[str] = []
        sort_seq = 20_000
        if event is not None:
            occurred = event.occurred_at.isoformat() if event.occurred_at else None
            event_ids = [str(event.id)]
            sort_seq = event.sequence_number
        elif trajectory.ended_at:
            occurred = trajectory.ended_at.isoformat()
        return {
            "id": "stage-completed",
            "type": "COMPLETED",
            "label": "Completed",
            "status": trajectory.status,
            "occurred_at": occurred,
            "event_ids": event_ids,
            "_sort_seq": sort_seq,
        }

    def _action_stage(
        self,
        key: str,
        events: list[EvidenceEvent],
        trajectory: RuntimeTrajectory,
    ) -> dict[str, Any]:
        by_type = {e.event_type: e for e in events}
        attempt = by_type.get(EvidenceEventType.TOOL_ATTEMPTED.value) or events[0]
        payload = attempt.payload if isinstance(attempt.payload, dict) else {}

        tool_label = self._tool_label_from_payload(payload)
        tool_id = payload.get("tool_id")
        if not tool_id:
            summary = payload.get("action_summary")
            if isinstance(summary, dict):
                tool_id = summary.get("tool_id")
        if not tool_label and tool_id:
            try:
                tool = (
                    self._db.query(ToolResource)
                    .filter(ToolResource.id == UUID(str(tool_id)))
                    .first()
                )
                tool_label = tool.name if tool else str(tool_id)
            except (TypeError, ValueError):
                tool_label = str(tool_id)
        tool_label = tool_label or "Action"

        status = self._derive_action_status(by_type)
        authority_event = by_type.get(EvidenceEventType.AUTHORITY_RESOLVED.value)
        policy_event = by_type.get(EvidenceEventType.POLICY_EVALUATED.value)
        approval_requested = by_type.get(EvidenceEventType.APPROVAL_REQUESTED.value)
        approval_decided = by_type.get(EvidenceEventType.APPROVAL_DECIDED.value)
        approval_consumed = by_type.get(EvidenceEventType.APPROVAL_CONSUMED.value)
        allowed = by_type.get(EvidenceEventType.ACTION_ALLOWED.value)
        denied = by_type.get(EvidenceEventType.ACTION_DENIED.value)
        exec_started = by_type.get(EvidenceEventType.TOOL_EXECUTION_STARTED.value)
        exec_ok = by_type.get(EvidenceEventType.TOOL_EXECUTION_SUCCEEDED.value)
        exec_fail = by_type.get(EvidenceEventType.TOOL_EXECUTION_FAILED.value)
        result_event = by_type.get(EvidenceEventType.TOOL_RESULT_OBSERVED.value)

        authority = self._authority_block(authority_event, trajectory)
        policy = self._policy_block(policy_event)
        approval = self._approval_block(
            approval_requested, approval_decided, approval_consumed
        )
        enforcement = self._enforcement_block(allowed, denied, trajectory)
        execution = self._execution_block(exec_started, exec_ok, exec_fail)
        result = None
        if result_event:
            result = self._content_block(result_event)
        elif exec_ok or exec_fail:
            result = {
                "availability": CoverageState.METADATA_ONLY.value,
                "preview": None,
                "reason": None,
            }
        else:
            result = {
                "availability": CoverageState.NOT_OBSERVED.value,
                "preview": None,
                "reason": "No tool result evidence recorded",
            }

        return {
            "id": f"action-{key}",
            "type": "ACTION",
            "label": tool_label,
            "status": status,
            "occurred_at": attempt.occurred_at.isoformat()
            if attempt.occurred_at
            else None,
            "event_ids": [str(e.id) for e in events],
            "authority": authority,
            "policy": policy,
            "approval": approval,
            "enforcement": enforcement,
            "execution": execution,
            "result": result,
            "_sort_seq": attempt.sequence_number,
        }

    @staticmethod
    def _tool_label_from_payload(payload: dict[str, Any]) -> str | None:
        """Return a human-readable string label; never an action_summary object."""
        for key in ("tool_key", "tool_name", "action_name", "name"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        summary = payload.get("action_summary")
        if isinstance(summary, str) and summary.strip():
            return summary.strip()
        if isinstance(summary, dict):
            for key in ("tool_key", "tool_name", "action", "name"):
                value = summary.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            target = summary.get("target")
            if isinstance(target, dict):
                for key in ("tool_key", "name", "resource"):
                    value = target.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
            tool_id = summary.get("tool_id")
            if isinstance(tool_id, str) and tool_id.strip():
                return None  # resolve via DB below using payload tool_id
        return None

    def _derive_action_status(self, by_type: dict[str, EvidenceEvent]) -> str:
        if EvidenceEventType.ACTION_DENIED.value in by_type:
            return "DENIED"
        if EvidenceEventType.APPROVAL_REQUESTED.value in by_type and not (
            EvidenceEventType.APPROVAL_CONSUMED.value in by_type
            or EvidenceEventType.ACTION_ALLOWED.value in by_type
        ):
            return "AWAITING_APPROVAL"
        if EvidenceEventType.TOOL_EXECUTION_SUCCEEDED.value in by_type:
            return "SUCCEEDED"
        if EvidenceEventType.TOOL_EXECUTION_FAILED.value in by_type:
            return "FAILED"
        if EvidenceEventType.TOOL_EXECUTION_STARTED.value in by_type:
            return "EXECUTING"
        if EvidenceEventType.ACTION_ALLOWED.value in by_type:
            return "INCOMPLETE"
        if EvidenceEventType.TOOL_ATTEMPTED.value in by_type:
            return "PENDING"
        return "UNKNOWN"

    def _authority_block(
        self, event: EvidenceEvent | None, trajectory: RuntimeTrajectory
    ) -> dict[str, Any]:
        identity = (
            self._db.query(AgentRuntimeIdentity)
            .filter(AgentRuntimeIdentity.id == trajectory.runtime_identity_id)
            .first()
        )
        delegation = None
        delegation_id = trajectory.delegation_id
        if (
            event
            and isinstance(event.payload, dict)
            and event.payload.get("delegation_id")
        ):
            try:
                delegation_id = UUID(str(event.payload["delegation_id"]))
            except (TypeError, ValueError):
                pass
        if delegation_id:
            grant = (
                self._db.query(DelegationGrant)
                .filter(DelegationGrant.id == delegation_id)
                .first()
            )
            if grant:
                delegation = {
                    "id": str(grant.id),
                    "status": grant.status,
                    "delegator_type": grant.delegator_type,
                    "delegator_id": grant.delegator_id,
                }
        return {
            "status": "VERIFIED" if event else "UNKNOWN",
            "runtime_identity": {
                "id": str(trajectory.runtime_identity_id),
                "name": identity.name if identity else None,
            },
            "delegation": delegation,
        }

    def _policy_block(self, event: EvidenceEvent | None) -> dict[str, Any]:
        if event is None:
            return {"status": "NOT_EVALUATED", "decision": None, "matched_rules": []}
        payload = event.payload if isinstance(event.payload, dict) else {}
        decision = payload.get("decision") or payload.get("effect")
        rules = payload.get("matched_rules") or []
        if not rules and payload.get("rule_id"):
            rules = [
                {
                    "id": payload.get("rule_id"),
                    "name": payload.get("rule_title") or payload.get("rule_name"),
                }
            ]
        return {
            "status": "EVALUATED",
            "decision": decision,
            "matched_rules": rules if isinstance(rules, list) else [],
        }

    def _approval_block(
        self,
        requested: EvidenceEvent | None,
        decided: EvidenceEvent | None,
        consumed: EvidenceEvent | None,
    ) -> dict[str, Any]:
        if not requested and not decided and not consumed:
            return {"required": False, "status": "NOT_REQUIRED"}
        status = "REQUESTED"
        if consumed:
            status = "CONSUMED"
        elif decided:
            payload = decided.payload if isinstance(decided.payload, dict) else {}
            status = str(payload.get("decision") or "DECIDED")
        return {"required": True, "status": status}

    def _enforcement_block(
        self,
        allowed: EvidenceEvent | None,
        denied: EvidenceEvent | None,
        trajectory: RuntimeTrajectory,
    ) -> dict[str, Any]:
        event = denied or allowed
        decision = None
        assurance = None
        if denied:
            decision = "DENY"
            assurance = denied.assurance_level
        elif allowed:
            decision = "ALLOW"
            assurance = allowed.assurance_level
        return {
            "decision": decision,
            "mode": trajectory.enforcement_mode,
            "assurance": assurance,
            "status": "DECIDED" if event else "UNKNOWN",
        }

    def _execution_block(
        self,
        started: EvidenceEvent | None,
        succeeded: EvidenceEvent | None,
        failed: EvidenceEvent | None,
    ) -> dict[str, Any]:
        if succeeded:
            duration = None
            payload = succeeded.payload if isinstance(succeeded.payload, dict) else {}
            if payload.get("duration_ms") is not None:
                duration = payload.get("duration_ms")
            return {"status": "SUCCEEDED", "duration_ms": duration}
        if failed:
            payload = failed.payload if isinstance(failed.payload, dict) else {}
            return {
                "status": "FAILED",
                "duration_ms": payload.get("duration_ms"),
                "error": payload.get("error") or payload.get("error_message"),
            }
        if started:
            return {"status": "EXECUTING", "duration_ms": None}
        return {"status": "NOT_OBSERVED", "duration_ms": None}

    def _summary(
        self, trajectory: RuntimeTrajectory, events: list[EvidenceEvent]
    ) -> dict[str, Any]:
        started = trajectory.started_at
        ended = trajectory.ended_at or trajectory.last_event_at
        duration_ms = None
        if started and ended:
            duration_ms = int((ended - started).total_seconds() * 1000)
        assurance = (trajectory.assurance_summary or {}).get("highest")
        risk = None
        if trajectory.finding_count:
            # Highest finding severity is computed lazily by callers; keep null here
            # unless coverage already projected something.
            risk = None
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
        return {
            "started_at": started.isoformat() if started else None,
            "completed_at": ended.isoformat() if ended else None,
            "duration_ms": duration_ms,
            "risk_level": risk,
            "assurance": assurance,
            "event_count": len(events),
            "ai_system_name": system.name if system else None,
            "agent_name": agent.name if agent else None,
            "agent_version_number": version.version_number if version else None,
            "coverage_summary": trajectory.coverage_summary or {},
            "completeness_pct": trajectory.completeness_pct,
        }

    def _attach_metering(
        self,
        trajectory: RuntimeTrajectory,
        stages: list[dict[str, Any]],
        summary: dict[str, Any],
    ) -> list[dict[str, Any]]:
        from rai_gateway.finops.metering import RuntimeMeteringService, aggregate_spans
        from rai_gateway.models.metering import RuntimeMeteringSpan

        system = (
            self._db.query(AISystem)
            .filter(AISystem.id == trajectory.ai_system_id)
            .first()
        )
        if system is None:
            return stages
        spans = (
            self._db.query(RuntimeMeteringSpan)
            .filter(
                RuntimeMeteringSpan.trajectory_id == trajectory.id,
            )
            .order_by(RuntimeMeteringSpan.started_at.asc())
            .all()
        )
        economics = aggregate_spans(spans)
        summary.update(
            {
                "total_input_tokens": economics["input_tokens"],
                "total_output_tokens": economics["output_tokens"],
                "total_tokens": economics["total_tokens"],
                "total_cost": economics["total_cost"],
                "currency": economics["currency"],
                "cost_state": economics["cost_state"],
                "model_calls": economics["model_calls"],
                "tool_calls": economics["tool_calls"],
                "metering_source": economics["metering_source"],
            }
        )
        svc = RuntimeMeteringService(self._db)
        model_spans = [span for span in spans if span.span_type == "MODEL_CALL"]
        tool_spans = [span for span in spans if span.span_type == "TOOL_CALL"]
        model_index = 0
        for stage in stages:
            if stage.get("type") == "MODEL" and model_index < len(model_spans):
                stage["metering"] = svc.serialize_span(model_spans[model_index])
                label = model_spans[model_index].model
                if label:
                    stage["label"] = label
                model_index += 1
            if stage.get("type") == "ACTION":
                label = str(stage.get("label") or "")
                match = next(
                    (
                        span
                        for span in tool_spans
                        if span.operation and span.operation == label
                    ),
                    None,
                )
                if match:
                    stage["metering"] = svc.serialize_span(match)
        return stages
