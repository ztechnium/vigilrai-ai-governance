"""WP5 client observation ingestion and model mismatch findings."""

from __future__ import annotations

import uuid

from rai_gateway.client_hooks.observation import extract_observation_payload
from rai_gateway.evidence.domain import (
    ContentHandlingMode,
    EvidenceEventType,
    EvidenceFindingType,
    EvidenceSourceType,
)
from rai_gateway.evidence.redaction import apply_content_handling
from rai_gateway.evidence.service import TrajectoryService
from rai_gateway.models.registry import AgentVersionDependency


def _base_ids(runtime_stack):
    return {
        "ai_system_id": runtime_stack["system"].id,
        "agent_id": runtime_stack["agent"].id,
        "agent_version_id": runtime_stack["version"].id,
        "runtime_identity_id": runtime_stack["identity"].id,
    }


def _attach_model(db_session, registry, version_id, *, model_name: str, aliases=None):
    model = registry.create_model_resource(
        provider="anthropic",
        model_name=model_name,
        metadata_={"aliases": aliases or []},
    )
    # Runtime stack versions are already APPROVED; attach dep directly for tests.
    db_session.add(
        AgentVersionDependency(
            agent_version_id=version_id,
            resource_type="model",
            resource_id=model.id,
            required=True,
        )
    )
    db_session.commit()
    return model


class TestObservationIngest:
    def test_prompt_observed_correlated_and_redacted(self, db_session, runtime_stack):
        svc = TrajectoryService(db_session)
        conv = f"conv-obs-{uuid.uuid4().hex[:6]}"
        payload = extract_observation_payload(
            "cursor",
            "beforeSubmitPrompt",
            {
                "prompt": "Search Jira for secrets api_key=sk-secret",
                "model": "gpt-5.4-mini",
                "conversation_id": conv,
            },
        )
        trajectory = svc.ingest_client_observation(
            **_base_ids(runtime_stack),
            event_type=EvidenceEventType.PROMPT_OBSERVED.value,
            client_type="cursor",
            hook_event="beforeSubmitPrompt",
            observation_payload=payload,
            conversation_id=conv,
            correlation_id="corr-obs-1",
            generation_id="gen-1",
            content_handling_mode=ContentHandlingMode.METADATA_ONLY.value,
        )
        db_session.commit()
        events = svc.list_events(trajectory.id)
        prompt_events = [
            e for e in events if e.event_type == EvidenceEventType.PROMPT_OBSERVED.value
        ]
        assert len(prompt_events) == 1
        assert prompt_events[0].source_type == EvidenceSourceType.CLIENT_OBSERVED.value
        assert prompt_events[0].payload is not None
        assert "prompt" not in (prompt_events[0].payload or {})
        prompt_cov = trajectory.coverage_summary.get("prompt")
        model_cov = trajectory.coverage_summary.get("model")
        assert prompt_cov not in {None, "NOT_OBSERVED", "NOT_AVAILABLE"}
        assert model_cov not in {None, "NOT_OBSERVED", "NOT_AVAILABLE"}
        model_events = [
            e
            for e in events
            if e.event_type == EvidenceEventType.MODEL_REQUEST_OBSERVED.value
        ]
        assert len(model_events) == 1
        # Policy mode is projected into coverage (not collapsed to NOT_AVAILABLE).
        assert prompt_cov in {
            prompt_events[0].content_handling_mode,
            "CAPTURED",
            "OBSERVED",
        }
        assert model_cov in {
            model_events[0].content_handling_mode,
            "CAPTURED",
            "OBSERVED",
        }

        svc.ingest_client_observation(
            **_base_ids(runtime_stack),
            event_type=EvidenceEventType.PROMPT_OBSERVED.value,
            client_type="cursor",
            hook_event="beforeSubmitPrompt",
            observation_payload=payload,
            conversation_id=conv,
            correlation_id="corr-obs-1",
            generation_id="gen-1",
        )
        db_session.commit()
        assert (
            len(
                [
                    e
                    for e in svc.list_events(trajectory.id)
                    if e.event_type == EvidenceEventType.PROMPT_OBSERVED.value
                ]
            )
            == 1
        )

    def test_unavailable_prompt_stays_not_observed(self, db_session, runtime_stack):
        svc = TrajectoryService(db_session)
        trajectory = svc.get_or_create_trajectory(**_base_ids(runtime_stack))
        svc.refresh_coverage(trajectory)
        db_session.commit()
        assert trajectory.coverage_summary.get("prompt") == "NOT_OBSERVED"
        assert trajectory.coverage_summary.get("output") == "NOT_OBSERVED"

    def test_do_not_store_omits_content(self):
        stored, status, digest = apply_content_handling(
            {"prompt": "secret text", "hook_event": "beforeSubmitPrompt"},
            ContentHandlingMode.DO_NOT_STORE,
        )
        assert stored is None
        assert status.value == "OMITTED"
        assert digest


class TestObservedModelMismatch:
    def test_no_registered_models_creates_finding(self, db_session, runtime_stack):
        svc = TrajectoryService(db_session)
        trajectory = svc.ingest_client_observation(
            **_base_ids(runtime_stack),
            event_type=EvidenceEventType.MODEL_REQUEST_OBSERVED.value,
            client_type="cursor",
            hook_event="beforeSubmitPrompt",
            observation_payload={"observed_model": "gpt-5.4-mini"},
            conversation_id="conv-mm-1",
            correlation_id="corr-mm-1",
            generation_id="gen-mm-1",
        )
        db_session.commit()
        findings = svc.list_findings(trajectory.id)
        assert any(
            f.finding_type == EvidenceFindingType.OBSERVED_MODEL_MISMATCH.value
            for f in findings
        )
        svc.evaluate_observed_model(
            trajectory, observed_model="gpt-5.4-mini", client_type="cursor"
        )
        db_session.commit()
        assert (
            len(
                [
                    f
                    for f in svc.list_findings(trajectory.id)
                    if f.finding_type
                    == EvidenceFindingType.OBSERVED_MODEL_MISMATCH.value
                ]
            )
            == 1
        )

    def test_allowed_model_no_finding(self, db_session, runtime_stack, registry):
        _attach_model(
            db_session,
            registry,
            runtime_stack["version"].id,
            model_name="claude-sonnet",
            aliases=["claude-sonnet-4", "Claude Sonnet"],
        )
        svc = TrajectoryService(db_session)
        trajectory = svc.ingest_client_observation(
            **_base_ids(runtime_stack),
            event_type=EvidenceEventType.MODEL_REQUEST_OBSERVED.value,
            client_type="cursor",
            hook_event="beforeSubmitPrompt",
            observation_payload={"observed_model": "claude-sonnet"},
            conversation_id="conv-mm-ok",
            correlation_id="corr-mm-ok",
            generation_id="gen-mm-ok",
        )
        db_session.commit()
        findings = [
            f
            for f in svc.list_findings(trajectory.id)
            if f.finding_type == EvidenceFindingType.OBSERVED_MODEL_MISMATCH.value
        ]
        assert findings == []

    def test_disallowed_model_mismatch(self, db_session, runtime_stack, registry):
        _attach_model(
            db_session,
            registry,
            runtime_stack["version"].id,
            model_name="claude-sonnet",
        )
        svc = TrajectoryService(db_session)
        trajectory = svc.ingest_client_observation(
            **_base_ids(runtime_stack),
            event_type=EvidenceEventType.MODEL_REQUEST_OBSERVED.value,
            client_type="cursor",
            hook_event="beforeSubmitPrompt",
            observation_payload={"observed_model": "gpt-5.4-mini"},
            conversation_id="conv-mm-bad",
            correlation_id="corr-mm-bad",
            generation_id="gen-mm-bad",
        )
        db_session.commit()
        findings = [
            f
            for f in svc.list_findings(trajectory.id)
            if f.finding_type == EvidenceFindingType.OBSERVED_MODEL_MISMATCH.value
        ]
        assert len(findings) == 1
        assert "gpt-5.4-mini" in findings[0].description
        assert "claude-sonnet" in findings[0].description.lower()
