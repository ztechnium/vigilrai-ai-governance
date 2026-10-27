"""WP5 content capture: handling modes, artifacts, export, tenant isolation."""

from __future__ import annotations

import uuid
from unittest.mock import patch

from rai_gateway.client_hooks.observation import extract_observation_payload
from rai_gateway.evidence.content_policy import resolve_content_handling
from rai_gateway.evidence.domain import (
    ContentHandlingMode,
    EvidenceEventType,
    EvidenceFindingType,
    EvidenceSourceType,
)
from rai_gateway.evidence.redaction import apply_content_handling
from rai_gateway.evidence.service import TrajectoryService


def _base_ids(runtime_stack):
    return {
        "ai_system_id": runtime_stack["system"].id,
        "agent_id": runtime_stack["agent"].id,
        "agent_version_id": runtime_stack["version"].id,
        "runtime_identity_id": runtime_stack["identity"].id,
    }


class TestContentPolicyResolver:
    def test_demo_defaults_are_redacted(self):
        mode = resolve_content_handling(EvidenceEventType.PROMPT_OBSERVED.value)
        assert mode == ContentHandlingMode.REDACTED
        assert (
            resolve_content_handling(EvidenceEventType.AGENT_OUTPUT_OBSERVED.value)
            == ContentHandlingMode.REDACTED
        )

    def test_production_keeps_prompt_and_output(self, monkeypatch):
        from rai_gateway.core.config import settings

        monkeypatch.setattr(settings, "evidence_use_demo_content_defaults", False)
        for attr in (
            "evidence_prompt_handling_mode",
            "evidence_model_request_handling_mode",
            "evidence_model_response_handling_mode",
            "evidence_agent_output_handling_mode",
            "evidence_tool_parameters_handling_mode",
            "evidence_tool_result_handling_mode",
        ):
            monkeypatch.setattr(settings, attr, None)

        assert (
            resolve_content_handling(EvidenceEventType.PROMPT_OBSERVED.value)
            == ContentHandlingMode.REDACTED
        )
        assert (
            resolve_content_handling(EvidenceEventType.MODEL_RESPONSE_OBSERVED.value)
            == ContentHandlingMode.REDACTED
        )
        assert (
            resolve_content_handling(EvidenceEventType.AGENT_OUTPUT_OBSERVED.value)
            == ContentHandlingMode.REDACTED
        )
        assert (
            resolve_content_handling(EvidenceEventType.TOOL_ATTEMPTED.value)
            == ContentHandlingMode.METADATA_ONLY
        )

    def test_agent_override_wins(self):
        mode = resolve_content_handling(
            EvidenceEventType.PROMPT_OBSERVED.value,
            agent_policy={"prompt": "HASH_ONLY"},
        )
        assert mode == ContentHandlingMode.HASH_ONLY

    def test_explicit_override_wins(self):
        mode = resolve_content_handling(
            EvidenceEventType.PROMPT_OBSERVED.value,
            agent_policy={"prompt": "FULL"},
            evidence_type_override="DO_NOT_STORE",
        )
        assert mode == ContentHandlingMode.DO_NOT_STORE


class TestRedactedStoresReadableContent:
    def test_redacted_keeps_scrubbed_prompt(self):
        payload = {
            "prompt": "Search Jira with key sk-abcdefghijklmnopqrstuvwxyz",
            "hook_event": "beforeSubmitPrompt",
        }
        stored, status, digest = apply_content_handling(
            payload, ContentHandlingMode.REDACTED
        )
        assert stored is not None
        assert "prompt" in stored
        assert "Search Jira" in stored["prompt"]
        assert "sk-" not in stored["prompt"]
        assert "[REDACTED]" in stored["prompt"]
        assert status.value == "APPLIED"
        assert digest

    def test_full_stores_scrubbed_content(self):
        stored, status, _ = apply_content_handling(
            {"prompt": "hello", "api_key": "secret"},
            ContentHandlingMode.FULL,
        )
        assert stored["prompt"] == "hello"
        assert stored["api_key"] == "[REDACTED]"
        assert status.value == "APPLIED"

    def test_redaction_failure_does_not_leak_raw(self):
        with patch(
            "rai_gateway.evidence.redaction.redact_secrets",
            side_effect=RuntimeError("boom"),
        ):
            stored, status, digest = apply_content_handling(
                {"prompt": "TOP SECRET RAW", "client_type": "cursor"},
                ContentHandlingMode.REDACTED,
            )
        assert status.value == "FAILED"
        assert digest
        assert stored is not None
        assert "TOP SECRET RAW" not in str(stored)
        assert "prompt" not in stored or stored.get("prompt") != "TOP SECRET RAW"


class TestContentCaptureIngest:
    def test_default_policy_stores_redacted_prompt_and_artifact(
        self, db_session, runtime_stack
    ):
        svc = TrajectoryService(db_session)
        conv = f"conv-cap-{uuid.uuid4().hex[:6]}"
        payload = extract_observation_payload(
            "cursor",
            "beforeSubmitPrompt",
            {
                "prompt": "Search Jira for all Mahally issues updated this week",
                "model": "claude-sonnet",
            },
        )
        trajectory = svc.ingest_client_observation(
            **_base_ids(runtime_stack),
            event_type=EvidenceEventType.PROMPT_OBSERVED.value,
            client_type="cursor",
            hook_event="beforeSubmitPrompt",
            observation_payload=payload,
            conversation_id=conv,
            correlation_id="corr-cap-1",
            generation_id="gen-cap-1",
        )
        db_session.commit()
        events = [
            e
            for e in svc.list_events(trajectory.id)
            if e.event_type == EvidenceEventType.PROMPT_OBSERVED.value
        ]
        assert len(events) == 1
        assert events[0].content_handling_mode == ContentHandlingMode.REDACTED.value
        assert events[0].payload is not None
        assert (
            events[0].payload.get("prompt")
            == "Search Jira for all Mahally issues updated this week"
        )
        artifacts = svc.list_artifacts(trajectory.id)
        assert len(artifacts) >= 1
        assert artifacts[0].artifact_type == "USER_PROMPT"
        assert "Mahally" in (artifacts[0].inline_content or "")

        detail = svc.serialize_event_detail(trajectory, events[0])
        assert detail["content_status"] == "AVAILABLE"
        assert "Mahally" in (detail["content_preview"] or "")

    def test_metadata_only_stores_no_content(self, db_session, runtime_stack):
        svc = TrajectoryService(db_session)
        trajectory = svc.ingest_client_observation(
            **_base_ids(runtime_stack),
            event_type=EvidenceEventType.PROMPT_OBSERVED.value,
            client_type="cursor",
            hook_event="beforeSubmitPrompt",
            observation_payload={"prompt": "hidden"},
            conversation_id=f"conv-meta-{uuid.uuid4().hex[:6]}",
            correlation_id="corr-meta",
            generation_id="gen-meta",
            content_handling_mode=ContentHandlingMode.METADATA_ONLY.value,
        )
        db_session.commit()
        event = next(
            e
            for e in svc.list_events(trajectory.id)
            if e.event_type == EvidenceEventType.PROMPT_OBSERVED.value
        )
        assert "prompt" not in (event.payload or {})
        assert svc.list_artifacts(trajectory.id) == []
        serialized = svc.serialize_event(event)
        assert serialized["content_status"] == "NOT_STORED"

    def test_hash_only_and_do_not_store(self, db_session, runtime_stack):
        svc = TrajectoryService(db_session)
        hashed = svc.ingest_client_observation(
            **_base_ids(runtime_stack),
            event_type=EvidenceEventType.AGENT_OUTPUT_OBSERVED.value,
            client_type="cursor",
            hook_event="afterAgentResponse",
            observation_payload={"output": "agent answer"},
            conversation_id=f"conv-hash-{uuid.uuid4().hex[:6]}",
            correlation_id="corr-hash",
            generation_id="gen-hash",
            content_handling_mode=ContentHandlingMode.HASH_ONLY.value,
        )
        omitted = svc.ingest_client_observation(
            **_base_ids(runtime_stack),
            event_type=EvidenceEventType.AGENT_OUTPUT_OBSERVED.value,
            client_type="cursor",
            hook_event="afterAgentResponse",
            observation_payload={"output": "should not store"},
            conversation_id=f"conv-omit-{uuid.uuid4().hex[:6]}",
            correlation_id="corr-omit",
            generation_id="gen-omit",
            content_handling_mode=ContentHandlingMode.DO_NOT_STORE.value,
        )
        db_session.commit()
        hash_event = next(
            e
            for e in svc.list_events(hashed.id)
            if e.event_type == EvidenceEventType.AGENT_OUTPUT_OBSERVED.value
        )
        assert "content_digest" in (hash_event.payload or {})
        assert "output" not in (hash_event.payload or {})
        omit_event = next(
            e
            for e in svc.list_events(omitted.id)
            if e.event_type == EvidenceEventType.AGENT_OUTPUT_OBSERVED.value
        )
        assert omit_event.payload is None
        assert omit_event.payload_digest

    def test_export_respects_handling_mode(self, db_session, runtime_stack):
        svc = TrajectoryService(db_session)
        trajectory = svc.ingest_client_observation(
            **_base_ids(runtime_stack),
            event_type=EvidenceEventType.PROMPT_OBSERVED.value,
            client_type="cursor",
            hook_event="beforeSubmitPrompt",
            observation_payload={"prompt": "export me"},
            conversation_id=f"conv-exp-{uuid.uuid4().hex[:6]}",
            correlation_id="corr-exp",
            generation_id="gen-exp",
            content_handling_mode=ContentHandlingMode.REDACTED.value,
        )
        db_session.commit()
        export = svc.export_trajectory(trajectory)
        prompt_events = [
            e
            for e in export["trajectory"]["events"]
            if e["event_type"] == EvidenceEventType.PROMPT_OBSERVED.value
        ]
        assert prompt_events[0]["payload"]["prompt"] == "export me"
        assert any(
            a["inline_content"] == "export me"
            for a in export["trajectory"]["artifacts"]
        )

    def test_tenant_isolation_event_lookup(self, db_session, runtime_stack):
        svc = TrajectoryService(db_session)
        t1 = svc.ingest_client_observation(
            **_base_ids(runtime_stack),
            event_type=EvidenceEventType.PROMPT_OBSERVED.value,
            client_type="cursor",
            hook_event="beforeSubmitPrompt",
            observation_payload={"prompt": "tenant a"},
            conversation_id=f"conv-t1-{uuid.uuid4().hex[:6]}",
            correlation_id="corr-t1",
            generation_id="gen-t1",
        )
        t2 = svc.ingest_client_observation(
            **_base_ids(runtime_stack),
            event_type=EvidenceEventType.PROMPT_OBSERVED.value,
            client_type="cursor",
            hook_event="beforeSubmitPrompt",
            observation_payload={"prompt": "tenant b"},
            conversation_id=f"conv-t2-{uuid.uuid4().hex[:6]}",
            correlation_id="corr-t2",
            generation_id="gen-t2",
        )
        db_session.commit()
        event = next(
            e
            for e in svc.list_events(t1.id)
            if e.event_type == EvidenceEventType.PROMPT_OBSERVED.value
        )
        assert svc.get_event(t1.id, event.id) is not None
        assert svc.get_event(t2.id, event.id) is None

    def test_duplicate_identical_output_reuses_artifact(
        self, db_session, runtime_stack
    ):
        svc = TrajectoryService(db_session)
        conv = f"conv-dup-{uuid.uuid4().hex[:6]}"
        ids = _base_ids(runtime_stack)
        common = {
            **ids,
            "client_type": "cursor",
            "conversation_id": conv,
            "correlation_id": "corr-dup",
            "generation_id": "gen-dup",
            "content_handling_mode": ContentHandlingMode.FULL.value,
        }
        svc.ingest_client_observation(
            **common,
            event_type=EvidenceEventType.MODEL_RESPONSE_OBSERVED.value,
            hook_event="afterAgentThought",
            observation_payload={"output": "same answer"},
        )
        svc.ingest_client_observation(
            **common,
            event_type=EvidenceEventType.AGENT_OUTPUT_OBSERVED.value,
            hook_event="afterAgentResponse",
            observation_payload={"output": "same answer"},
        )
        db_session.commit()
        matching = [
            t
            for t in svc.list_trajectories(
                runtime_identity_id=ids["runtime_identity_id"]
            )
            if t.conversation_id == conv
        ]
        traj = matching[0]
        artifacts = svc.list_artifacts(traj.id)
        # One artifact body reused via digest dedupe.
        assert len(artifacts) == 1


class TestRedactionFailureFinding:
    def test_append_event_records_finding_on_redaction_failure(
        self, db_session, runtime_stack
    ):
        svc = TrajectoryService(db_session)
        trajectory = svc.get_or_create_trajectory(**_base_ids(runtime_stack))
        with patch(
            "rai_gateway.evidence.redaction.redact_secrets",
            side_effect=RuntimeError("fail"),
        ):
            event, created = svc.append_event(
                trajectory,
                event_type=EvidenceEventType.PROMPT_OBSERVED.value,
                source_type=EvidenceSourceType.CLIENT_OBSERVED.value,
                source_reference=f"fail:{uuid.uuid4().hex}",
                payload={"prompt": "raw should not leak"},
                content_handling_mode=ContentHandlingMode.FULL.value,
            )
        db_session.commit()
        assert created
        assert event.redaction_status == "FAILED"
        findings = svc.list_findings(trajectory.id)
        assert any(
            f.finding_type == EvidenceFindingType.CONTENT_REDACTION_FAILED.value
            for f in findings
        )
