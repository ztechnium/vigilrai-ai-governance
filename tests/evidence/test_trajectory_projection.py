"""WP5 trajectory correlation, idempotency, and source/assurance tests."""

from __future__ import annotations

import uuid

from rai_gateway.evidence.correlation import build_session_key
from rai_gateway.evidence.domain import (
    AssuranceLevel,
    ContentHandlingMode,
    EvidenceEventType,
    EvidenceFindingType,
    EvidenceSourceType,
    TrajectoryStatus,
)
from rai_gateway.evidence.redaction import apply_content_handling, redact_secrets
from rai_gateway.evidence.service import TrajectoryService
from rai_gateway.runtime_enforcement.adapters.base import RuntimeAdapterRegistry
from rai_gateway.runtime_enforcement.domain import (
    EnforcementDecisionType,
    EnforcementMode,
    ExecutionSource,
    ExecutionStatus,
    RuntimeActionRequest,
)
from rai_gateway.runtime_enforcement.service import RuntimeEnforcementService
from runtime_enforcement.fakes import FakeAdapter


def _svc(db_session, fake_adapter: FakeAdapter) -> RuntimeEnforcementService:
    return RuntimeEnforcementService(
        db_session, adapter_registry=RuntimeAdapterRegistry([fake_adapter])
    )


def _authorize_tool(
    db_session,
    runtime_stack,
    fake_adapter: FakeAdapter,
    *,
    tool_id,
    conversation_id: str | None = None,
    session_id: str | None = None,
    observed_model: str | None = None,
    correlation_id: str | None = None,
    execute: bool = False,
):
    client_context = {
        "client_type": "cursor",
        "hook_event": "beforeMCPExecution",
    }
    if conversation_id:
        client_context["conversation_id"] = conversation_id
    if session_id:
        client_context["session_id"] = session_id
    if observed_model:
        client_context["observed_model"] = observed_model

    request = RuntimeActionRequest(
        integration_type="mcp",
        integration_id=runtime_stack["mcp"].id,
        tool_id=tool_id,
        parameters={"q": "Mahally sprint"},
        delegation_id=runtime_stack["delegation"].id,
        correlation_id=correlation_id or f"corr-{uuid.uuid4().hex[:8]}",
        client_context=client_context,
    )
    svc = _svc(db_session, fake_adapter)
    if execute:
        return svc.enforce_and_execute(
            request, credential_secret=runtime_stack["credential_secret"]
        )
    return svc.authorize(request, credential_secret=runtime_stack["credential_secret"])


class TestSessionKeyCorrelation:
    def test_session_preferred_over_conversation(self):
        rid = uuid.uuid4()
        ci = uuid.uuid4()
        key = build_session_key(
            runtime_identity_id=rid,
            client_integration_id=ci,
            conversation_id="conv-1",
            client_session_id="turn-1",
            correlation_id="corr-1",
        )
        assert key.startswith("sess:turn-1|")
        assert str(rid) in key
        assert str(ci) in key
        assert "conv:" not in key

    def test_generation_used_when_session_aliases_conversation(self):
        rid = uuid.uuid4()
        key = build_session_key(
            runtime_identity_id=rid,
            conversation_id="conv-same",
            client_session_id="conv-same",
            generation_id="gen-42",
        )
        assert key.startswith("gen:gen-42|")

    def test_conversation_alone_is_not_a_trajectory_key(self):
        rid = uuid.uuid4()
        key = build_session_key(
            runtime_identity_id=rid,
            conversation_id="conv-only",
            correlation_id="corr-9",
        )
        assert key.startswith("corr:corr-9|")
        assert "conv:" not in key

    def test_different_runtime_identity_separate_keys(self):
        a = build_session_key(
            runtime_identity_id=uuid.uuid4(),
            client_session_id="same-turn",
        )
        b = build_session_key(
            runtime_identity_id=uuid.uuid4(),
            client_session_id="same-turn",
        )
        assert a != b


class TestReceiptProjection:
    def test_same_conversation_different_turns_separate_trajectories(
        self, db_session, runtime_stack, fake_adapter
    ):
        """Conversation groups turns; each turn/session id is its own trajectory."""
        evidence_svc = TrajectoryService(db_session)
        conv = f"conv-{uuid.uuid4().hex[:8]}"
        r1 = _authorize_tool(
            db_session,
            runtime_stack,
            fake_adapter,
            tool_id=runtime_stack["submit_tool"].id,
            conversation_id=conv,
            session_id=f"{conv}-turn-1",
            execute=True,
        )
        r2 = _authorize_tool(
            db_session,
            runtime_stack,
            fake_adapter,
            tool_id=runtime_stack["delete_tool"].id,
            conversation_id=conv,
            session_id=f"{conv}-turn-2",
            execute=True,
        )
        assert r1.receipt_id and r2.receipt_id

        t1 = evidence_svc.project_receipt(r1.receipt_id)
        t2 = evidence_svc.project_receipt(r2.receipt_id)
        db_session.commit()

        assert t1 is not None and t2 is not None
        assert t1.id != t2.id
        assert t1.conversation_id == conv
        assert t2.conversation_id == conv

    def test_same_turn_session_one_trajectory(
        self, db_session, runtime_stack, fake_adapter
    ):
        evidence_svc = TrajectoryService(db_session)
        conv = f"conv-{uuid.uuid4().hex[:8]}"
        turn = f"{conv}-turn-1"
        r1 = _authorize_tool(
            db_session,
            runtime_stack,
            fake_adapter,
            tool_id=runtime_stack["submit_tool"].id,
            conversation_id=conv,
            session_id=turn,
            execute=True,
        )
        r2 = _authorize_tool(
            db_session,
            runtime_stack,
            fake_adapter,
            tool_id=runtime_stack["delete_tool"].id,
            conversation_id=conv,
            session_id=turn,
            execute=True,
        )
        assert r1.receipt_id and r2.receipt_id

        t1 = evidence_svc.project_receipt(r1.receipt_id)
        t2 = evidence_svc.project_receipt(r2.receipt_id)
        db_session.commit()

        assert t1 is not None and t2 is not None
        assert t1.id == t2.id

        events = evidence_svc.list_events(t1.id)
        attempt_types = [
            e for e in events if e.event_type == EvidenceEventType.TOOL_ATTEMPTED.value
        ]
        assert len(attempt_types) == 2
        seq = [e.sequence_number for e in events]
        assert seq == sorted(seq)

    def test_different_conversation_separate_trajectories(
        self, db_session, runtime_stack, fake_adapter
    ):
        evidence_svc = TrajectoryService(db_session)
        r1 = _authorize_tool(
            db_session,
            runtime_stack,
            fake_adapter,
            tool_id=runtime_stack["submit_tool"].id,
            conversation_id="conv-a",
            session_id="conv-a-turn-1",
            execute=True,
        )
        r2 = _authorize_tool(
            db_session,
            runtime_stack,
            fake_adapter,
            tool_id=runtime_stack["submit_tool"].id,
            conversation_id="conv-b",
            session_id="conv-b-turn-1",
            execute=True,
        )
        t1 = evidence_svc.project_receipt(r1.receipt_id)
        t2 = evidence_svc.project_receipt(r2.receipt_id)
        db_session.commit()
        assert t1.id != t2.id

    def test_idempotent_projection(self, db_session, runtime_stack, fake_adapter):
        evidence_svc = TrajectoryService(db_session)
        result = _authorize_tool(
            db_session,
            runtime_stack,
            fake_adapter,
            tool_id=runtime_stack["submit_tool"].id,
            conversation_id="conv-idem",
            execute=True,
        )
        t1 = evidence_svc.project_receipt(result.receipt_id)
        count1 = len(evidence_svc.list_events(t1.id))
        t2 = evidence_svc.project_receipt(result.receipt_id)
        count2 = len(evidence_svc.list_events(t2.id))
        db_session.commit()
        assert t1.id == t2.id
        assert count1 == count2

    def test_correlation_merges_corr_stub_into_conversation(
        self, db_session, runtime_stack, fake_adapter
    ):
        """Approval/corr stubs should merge when a receipt arrives with same correlation."""
        evidence_svc = TrajectoryService(db_session)
        corr = f"corr-merge-{uuid.uuid4().hex[:8]}"
        stub = evidence_svc.get_or_create_trajectory(
            ai_system_id=runtime_stack["system"].id,
            agent_id=runtime_stack["agent"].id,
            agent_version_id=runtime_stack["version"].id,
            runtime_identity_id=runtime_stack["identity"].id,
            correlation_id=corr,
        )
        assert stub.session_key.startswith("corr:")
        db_session.commit()

        result = _authorize_tool(
            db_session,
            runtime_stack,
            fake_adapter,
            tool_id=runtime_stack["submit_tool"].id,
            conversation_id="conv-merge-1",
            session_id="turn-merge-1",
            correlation_id=corr,
            execute=True,
        )
        merged = evidence_svc.project_receipt(result.receipt_id)
        db_session.commit()
        assert merged.id == stub.id
        assert merged.conversation_id == "conv-merge-1"
        assert merged.session_key.startswith("sess:")
        assert merged.client_session_id == "turn-merge-1"

    def test_source_and_assurance_levels(self, db_session, runtime_stack, fake_adapter):
        evidence_svc = TrajectoryService(db_session)
        result = _authorize_tool(
            db_session,
            runtime_stack,
            fake_adapter,
            tool_id=runtime_stack["submit_tool"].id,
            conversation_id="conv-assurance",
            observed_model="gpt-5.4-mini",
            execute=True,
        )
        trajectory = evidence_svc.project_receipt(result.receipt_id)
        db_session.commit()
        events = evidence_svc.list_events(trajectory.id)

        by_type = {e.event_type: e for e in events}
        policy = by_type[EvidenceEventType.POLICY_EVALUATED.value]
        assert policy.source_type == EvidenceSourceType.RAI_AUTHORITATIVE.value
        assert policy.assurance_level == AssuranceLevel.HIGH.value

        allowed = by_type[EvidenceEventType.ACTION_ALLOWED.value]
        assert allowed.source_type == EvidenceSourceType.RAI_AUTHORITATIVE.value

        succeeded = by_type[EvidenceEventType.TOOL_EXECUTION_SUCCEEDED.value]
        assert succeeded.source_type == EvidenceSourceType.RAI_EXECUTED.value
        assert succeeded.assurance_level == AssuranceLevel.HIGH.value

        observed = by_type[EvidenceEventType.MODEL_REQUEST_OBSERVED.value]
        assert observed.source_type == EvidenceSourceType.CLIENT_OBSERVED.value
        assert observed.assurance_level == AssuranceLevel.LOW.value

    def test_deny_has_no_execution_success(
        self, db_session, runtime_stack, fake_adapter
    ):
        from rai_gateway.policy.domain import PolicyEffect
        from rai_gateway.policy.service import PolicyCollectionService

        evidence_svc = TrajectoryService(db_session)
        PolicyCollectionService(db_session).create_tool_rule(
            runtime_stack["system"].id,
            title="Deny delete for WP5",
            tool_id=runtime_stack["delete_tool"].id,
            mcp_server_id=runtime_stack["mcp"].id,
            effect=PolicyEffect.DENY.value,
            actor="tester",
        )
        result = _authorize_tool(
            db_session,
            runtime_stack,
            fake_adapter,
            tool_id=runtime_stack["delete_tool"].id,
            conversation_id="conv-deny",
        )
        assert result.allowed is False
        assert result.receipt_id
        trajectory = evidence_svc.project_receipt(result.receipt_id)
        db_session.commit()
        types = {e.event_type for e in evidence_svc.list_events(trajectory.id)}
        assert EvidenceEventType.ACTION_DENIED.value in types
        assert EvidenceEventType.TOOL_EXECUTION_SUCCEEDED.value not in types
        findings = evidence_svc.list_findings(trajectory.id)
        assert any(
            f.finding_type
            in {
                EvidenceFindingType.POLICY_DENIAL.value,
                EvidenceFindingType.AUTHORITY_DENIAL.value,
            }
            for f in findings
        )
        from rai_gateway.risk_intelligence.service import RiskIntelligenceService

        risk = RiskIntelligenceService(db_session)
        listed = risk.list_findings(
            trajectory_id=trajectory.id,
            include_evidence=True,
        )
        assert any(
            item["finding_type"] in {"POLICY_DENIAL", "AUTHORITY_DENIAL"}
            for item in listed
        )

    def test_missing_execution_finding(self, db_session, runtime_stack, fake_adapter):
        evidence_svc = TrajectoryService(db_session)
        result = _authorize_tool(
            db_session,
            runtime_stack,
            fake_adapter,
            tool_id=runtime_stack["submit_tool"].id,
            conversation_id="conv-gap",
            execute=False,
        )
        assert result.receipt_id
        from rai_gateway.models.runtime_enforcement import RuntimeEnforcementReceipt

        receipt = (
            db_session.query(RuntimeEnforcementReceipt)
            .filter(RuntimeEnforcementReceipt.id == result.receipt_id)
            .one()
        )
        receipt.enforcement_decision = EnforcementDecisionType.ALLOW.value
        receipt.enforcement_mode = EnforcementMode.HOOK_ENFORCED.value
        receipt.execution_status = ExecutionStatus.UNKNOWN.value
        receipt.execution_source = ExecutionSource.CLIENT_REPORTED.value
        db_session.commit()

        trajectory = evidence_svc.project_receipt(receipt.id)
        db_session.commit()
        findings = evidence_svc.list_findings(trajectory.id)
        assert any(
            f.finding_type == EvidenceFindingType.MISSING_EXECUTION_RESULT.value
            for f in findings
        )
        assert trajectory.status == TrajectoryStatus.INCOMPLETE.value

    def test_auto_project_on_enforce(self, db_session, runtime_stack, fake_adapter):
        evidence_svc = TrajectoryService(db_session)
        result = _authorize_tool(
            db_session,
            runtime_stack,
            fake_adapter,
            tool_id=runtime_stack["submit_tool"].id,
            conversation_id="conv-auto",
            execute=True,
        )
        assert result.receipt_id
        rows = evidence_svc.list_trajectories(
            runtime_identity_id=runtime_stack["identity"].id,
            limit=20,
        )
        matching = [t for t in rows if t.conversation_id == "conv-auto"]
        assert matching
        events = evidence_svc.list_events(matching[0].id)
        assert any(
            e.event_type == EvidenceEventType.TOOL_ATTEMPTED.value for e in events
        )


class TestContentHandling:
    def test_secrets_never_persist(self):
        payload = {
            "api_key": "sk-secret",
            "Authorization": "Bearer abc",
            "q": "safe query",
            "nested": {"password": "hunter2", "ok": True},
        }
        scrubbed = redact_secrets(payload)
        assert scrubbed["api_key"] == "[REDACTED]"
        assert scrubbed["Authorization"] == "[REDACTED]"
        assert scrubbed["nested"]["password"] == "[REDACTED]"
        assert scrubbed["q"] == "safe query"

    def test_handling_modes(self):
        payload = {"prompt": "hello", "tool": "search", "api_key": "x"}
        full, _status, digest = apply_content_handling(
            payload, ContentHandlingMode.FULL
        )
        assert full is not None
        assert full["api_key"] == "[REDACTED]"
        assert digest

        hashed, status, hashed_digest = apply_content_handling(
            payload, ContentHandlingMode.HASH_ONLY
        )
        assert hashed is not None
        assert "content_digest" in hashed
        assert status.value == "HASHED"
        assert hashed_digest

        meta, _, _ = apply_content_handling(payload, ContentHandlingMode.METADATA_ONLY)
        assert meta is not None
        assert "prompt" not in meta
        assert meta.get("tool") == "search"

        redacted, redacted_status, _ = apply_content_handling(
            payload, ContentHandlingMode.REDACTED
        )
        assert redacted is not None
        assert redacted["prompt"] == "hello"
        assert redacted["api_key"] == "[REDACTED]"
        assert redacted_status.value == "APPLIED"

        omitted, status, dig2 = apply_content_handling(
            payload, ContentHandlingMode.DO_NOT_STORE
        )
        assert omitted is None
        assert status.value == "OMITTED"
        assert dig2
