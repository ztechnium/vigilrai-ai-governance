"""Phase 2 conversation projection + lifecycle API tests."""

from __future__ import annotations

import uuid

from rai_gateway.evidence.conversation_projection import (
    ConversationProjectionService,
    build_conversation_key,
)
from rai_gateway.evidence.domain import EvidenceEventType
from rai_gateway.evidence.lifecycle_projection import LifecycleProjectionService
from rai_gateway.evidence.service import TrajectoryService
from rai_gateway.runtime_enforcement.adapters.base import RuntimeAdapterRegistry
from rai_gateway.runtime_enforcement.domain import RuntimeActionRequest
from rai_gateway.runtime_enforcement.service import RuntimeEnforcementService
from runtime_enforcement.fakes import FakeAdapter


def _svc(db_session, fake_adapter: FakeAdapter) -> RuntimeEnforcementService:
    return RuntimeEnforcementService(
        db_session, adapter_registry=RuntimeAdapterRegistry([fake_adapter])
    )


def _authorize_turn(
    db_session,
    runtime_stack,
    fake_adapter: FakeAdapter,
    *,
    conversation_id: str,
    session_id: str,
    tool_id,
):
    request = RuntimeActionRequest(
        integration_type="mcp",
        integration_id=runtime_stack["mcp"].id,
        tool_id=tool_id,
        parameters={"q": "appointments"},
        delegation_id=runtime_stack["delegation"].id,
        correlation_id=f"corr-{uuid.uuid4().hex[:8]}",
        client_context={
            "client_type": "sdk",
            "hook_event": "authorize",
            "conversation_id": conversation_id,
            "session_id": session_id,
        },
    )
    return _svc(db_session, fake_adapter).enforce_and_execute(
        request, credential_secret=runtime_stack["credential_secret"]
    )


class TestConversationProjection:
    def test_conversation_key_scopes_by_integration(self):
        ci = uuid.uuid4()
        a = build_conversation_key(
            client_integration_id=ci,
            external_conversation_id="wa-1",
        )
        b = build_conversation_key(
            client_integration_id=None,
            external_conversation_id="wa-1",
        )
        assert a != b
        assert "wa-1" in a

    def test_same_conversation_multiple_turns_one_projection(
        self, db_session, runtime_stack, fake_adapter
    ):
        evidence = TrajectoryService(db_session)
        conv = f"wa-{uuid.uuid4().hex[:8]}"
        r1 = _authorize_turn(
            db_session,
            runtime_stack,
            fake_adapter,
            conversation_id=conv,
            session_id=f"{conv}-t1",
            tool_id=runtime_stack["submit_tool"].id,
        )
        r2 = _authorize_turn(
            db_session,
            runtime_stack,
            fake_adapter,
            conversation_id=conv,
            session_id=f"{conv}-t2",
            tool_id=runtime_stack["delete_tool"].id,
        )
        t1 = evidence.project_receipt(r1.receipt_id)
        t2 = evidence.project_receipt(r2.receipt_id)
        db_session.commit()

        assert t1 is not None and t2 is not None
        assert t1.id != t2.id
        assert t1.runtime_conversation_id is not None
        assert t1.runtime_conversation_id == t2.runtime_conversation_id

        listed = ConversationProjectionService(db_session).list_conversations(
            conversation_id=conv,
            limit=20,
        )
        assert listed["has_more"] is False
        assert len(listed["items"]) == 1
        item = listed["items"][0]
        assert item["external_conversation_id"] == conv
        assert item["trajectory_count"] >= 2
        assert item["id"] == str(t1.runtime_conversation_id)

        detail = ConversationProjectionService(db_session).get_conversation(
            t1.runtime_conversation_id
        )
        assert detail is not None
        under = ConversationProjectionService(
            db_session
        ).list_conversation_trajectories(t1.runtime_conversation_id, limit=10)
        assert under is not None
        assert len(under["items"]) >= 2


class TestLifecycleProjection:
    def test_lifecycle_groups_action_by_receipt(
        self, db_session, runtime_stack, fake_adapter
    ):
        evidence = TrajectoryService(db_session)
        conv = f"life-{uuid.uuid4().hex[:8]}"
        result = _authorize_turn(
            db_session,
            runtime_stack,
            fake_adapter,
            conversation_id=conv,
            session_id=f"{conv}-t1",
            tool_id=runtime_stack["submit_tool"].id,
        )
        trajectory = evidence.project_receipt(result.receipt_id)
        db_session.commit()
        assert trajectory is not None

        evidence.ingest_client_observation(
            ai_system_id=trajectory.ai_system_id,
            agent_id=trajectory.agent_id,
            agent_version_id=trajectory.agent_version_id,
            runtime_identity_id=trajectory.runtime_identity_id,
            event_type=EvidenceEventType.PROMPT_OBSERVED.value,
            client_type="sdk",
            hook_event="observe_input",
            observation_payload={
                "prompt": "Show me my appointments",
                "observed_model": "gemini-2.5-flash",
            },
            conversation_id=conv,
            client_session_id=f"{conv}-t1",
            correlation_id=trajectory.correlation_id,
            content_handling_mode="REDACTED",
        )
        db_session.commit()

        events = evidence.list_events(trajectory.id, limit=2000)
        lifecycle = LifecycleProjectionService(db_session).project(
            trajectory, events=events
        )
        assert lifecycle["trajectory_id"] == str(trajectory.id)
        types = [s["type"] for s in lifecycle["stages"]]
        assert "INPUT" in types
        assert "ACTION" in types
        actions = [s for s in lifecycle["stages"] if s["type"] == "ACTION"]
        assert len(actions) >= 1
        action = actions[0]
        assert isinstance(action["label"], str)
        assert action["label"]
        assert action["status"] in {
            "SUCCEEDED",
            "INCOMPLETE",
            "FAILED",
            "DENIED",
            "EXECUTING",
            "PENDING",
        }
        assert action["event_ids"]
        assert "authority" in action
        assert "policy" in action
        assert "enforcement" in action
        assert "execution" in action

    def test_lifecycle_extracts_configuration_provenance(
        self, db_session, runtime_stack, fake_adapter
    ):
        evidence = TrajectoryService(db_session)
        conv = f"prov-{uuid.uuid4().hex[:8]}"
        result = _authorize_turn(
            db_session,
            runtime_stack,
            fake_adapter,
            conversation_id=conv,
            session_id=f"{conv}-t1",
            tool_id=runtime_stack["submit_tool"].id,
        )
        trajectory = evidence.project_receipt(result.receipt_id)
        db_session.commit()
        assert trajectory is not None

        evidence.ingest_client_observation(
            ai_system_id=trajectory.ai_system_id,
            agent_id=trajectory.agent_id,
            agent_version_id=trajectory.agent_version_id,
            runtime_identity_id=trajectory.runtime_identity_id,
            event_type=EvidenceEventType.PROMPT_OBSERVED.value,
            client_type="sdk",
            hook_event="observe_input",
            observation_payload={
                "prompt": "Book with Osama",
                "configuration_id": "lapeep-agent",
                "configuration_version": "42",
                "configuration_digest": "sha256:abc",
                "release_id": "9f219e",
            },
            conversation_id=conv,
            client_session_id=f"{conv}-t1",
            correlation_id=trajectory.correlation_id,
            content_handling_mode="FULL",
        )
        db_session.commit()

        events = evidence.list_events(trajectory.id, limit=2000)
        lifecycle = LifecycleProjectionService(db_session).project(
            trajectory, events=events
        )
        provenance = lifecycle["configuration_provenance"]
        assert provenance is not None
        assert provenance["configuration_id"] == "lapeep-agent"
        assert provenance["configuration_version"] == "42"
        assert provenance["configuration_digest"] == "sha256:abc"
        assert provenance["release_id"] == "9f219e"
        assert provenance["assurance"] == "APPLICATION_REPORTED"
        assert provenance["source"] == "APPLICATION_REPORTED"
