"""Audit Explorer search tests."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from rai_gateway.evidence.audit_search import (
    AuditSearchFilters,
    AuditSearchService,
    default_audit_window,
)
from rai_gateway.evidence.service import TrajectoryService
from rai_gateway.runtime_enforcement.adapters.base import RuntimeAdapterRegistry
from rai_gateway.runtime_enforcement.domain import RuntimeActionRequest
from rai_gateway.runtime_enforcement.service import RuntimeEnforcementService
from runtime_enforcement.fakes import FakeAdapter


def _svc(db_session, fake_adapter: FakeAdapter) -> RuntimeEnforcementService:
    return RuntimeEnforcementService(
        db_session, adapter_registry=RuntimeAdapterRegistry([fake_adapter])
    )


def test_default_audit_window_is_24h():
    end = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)
    start, finish = default_audit_window(now=end)
    assert finish == end
    assert finish - start == timedelta(hours=24)


def test_audit_search_requires_bounded_range(db_session, runtime_stack):
    svc = AuditSearchService(db_session)
    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError, match="31 days"):
        svc.search(
            filters=AuditSearchFilters(
                date_from=now - timedelta(days=40),
                date_to=now,
            ),
            limit=10,
        )


def test_audit_search_returns_enforcement_rows(db_session, runtime_stack, fake_adapter):
    request = RuntimeActionRequest(
        integration_type="mcp",
        integration_id=runtime_stack["mcp"].id,
        tool_id=runtime_stack["submit_tool"].id,
        parameters={"q": "audit"},
        delegation_id=runtime_stack["delegation"].id,
        correlation_id=f"corr-audit-{uuid.uuid4().hex[:8]}",
        client_context={
            "client_type": "sdk",
            "conversation_id": f"conv-audit-{uuid.uuid4().hex[:6]}",
            "session_id": f"turn-{uuid.uuid4().hex[:6]}",
        },
    )
    result = _svc(db_session, fake_adapter).enforce_and_execute(
        request, credential_secret=runtime_stack["credential_secret"]
    )
    assert result.receipt_id
    TrajectoryService(db_session).project_receipt(result.receipt_id)
    db_session.commit()

    now = datetime.now(timezone.utc)
    payload = AuditSearchService(db_session).search(
        filters=AuditSearchFilters(
            date_from=now - timedelta(hours=24),
            date_to=now + timedelta(minutes=1),
            entity_types=("ENFORCEMENT",),
            correlation_id=request.correlation_id,
        ),
        limit=25,
    )
    assert payload["has_more"] is False
    assert len(payload["items"]) >= 1
    row = payload["items"][0]
    assert row["record_type"] == "ENFORCEMENT"
    assert row["detail_reference"].startswith("/runtime/enforcement/")
    assert row["correlation_id"] == request.correlation_id


def test_audit_search_content_and_record_kind(db_session, runtime_stack, fake_adapter):
    from rai_gateway.evidence.domain import EvidenceEventType
    from rai_gateway.evidence.service import TrajectoryService as TS

    evidence = TS(db_session)
    conv = f"audit-content-{uuid.uuid4().hex[:8]}"
    request = RuntimeActionRequest(
        integration_type="mcp",
        integration_id=runtime_stack["mcp"].id,
        tool_id=runtime_stack["submit_tool"].id,
        parameters={"q": "audit-content"},
        delegation_id=runtime_stack["delegation"].id,
        correlation_id=f"corr-content-{uuid.uuid4().hex[:8]}",
        client_context={
            "client_type": "sdk",
            "conversation_id": conv,
            "session_id": f"{conv}-t1",
        },
    )
    result = _svc(db_session, fake_adapter).enforce_and_execute(
        request, credential_secret=runtime_stack["credential_secret"]
    )
    trajectory = evidence.project_receipt(result.receipt_id)
    db_session.commit()
    assert trajectory is not None

    unique_prompt = f"unique-audit-phrase-{uuid.uuid4().hex[:10]}"
    evidence.ingest_client_observation(
        ai_system_id=trajectory.ai_system_id,
        agent_id=trajectory.agent_id,
        agent_version_id=trajectory.agent_version_id,
        runtime_identity_id=trajectory.runtime_identity_id,
        event_type=EvidenceEventType.PROMPT_OBSERVED.value,
        client_type="sdk",
        hook_event="observe_input",
        observation_payload={"prompt": unique_prompt},
        conversation_id=conv,
        client_session_id=f"{conv}-t1",
        correlation_id=trajectory.correlation_id,
        content_handling_mode="FULL",
    )
    db_session.commit()

    now = datetime.now(timezone.utc)
    payload = AuditSearchService(db_session).search(
        filters=AuditSearchFilters(
            date_from=now - timedelta(hours=24),
            date_to=now + timedelta(minutes=1),
            entity_types=("EVIDENCE_EVENT",),
            record_kind="INPUT",
            content_search=unique_prompt,
        ),
        limit=25,
    )
    assert len(payload["items"]) >= 1
    row = payload["items"][0]
    assert row["record_type"] == "EVIDENCE_EVENT"
    assert row["action"] == EvidenceEventType.PROMPT_OBSERVED.value
    assert "?event=" in row["detail_reference"]
    assert f"/runtime/trajectories/{trajectory.id}" in row["detail_reference"]
    # Result must not embed raw prompt text
    assert unique_prompt not in str(row)


def test_last_observed_configuration_for_system(
    db_session, runtime_stack, fake_adapter
):
    from rai_gateway.evidence.domain import EvidenceEventType
    from rai_gateway.evidence.lifecycle_projection import LifecycleProjectionService
    from rai_gateway.evidence.service import TrajectoryService as TS

    evidence = TS(db_session)
    conv = f"prov-sys-{uuid.uuid4().hex[:8]}"
    request = RuntimeActionRequest(
        integration_type="mcp",
        integration_id=runtime_stack["mcp"].id,
        tool_id=runtime_stack["submit_tool"].id,
        parameters={"q": "prov"},
        delegation_id=runtime_stack["delegation"].id,
        correlation_id=f"corr-prov-{uuid.uuid4().hex[:8]}",
        client_context={
            "client_type": "sdk",
            "conversation_id": conv,
            "session_id": f"{conv}-t1",
        },
    )
    result = _svc(db_session, fake_adapter).enforce_and_execute(
        request, credential_secret=runtime_stack["credential_secret"]
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
            "prompt": "hi",
            "configuration_id": "lapeep-agent",
            "configuration_version": "42",
            "configuration_digest": "sha256:abc",
            "release_id": "9f219e",
            "observed_model": "gemini-test",
        },
        conversation_id=conv,
        client_session_id=f"{conv}-t1",
        correlation_id=trajectory.correlation_id,
        content_handling_mode="FULL",
    )
    db_session.commit()

    result = LifecycleProjectionService(db_session).last_observed_for_system(
        ai_system_id=trajectory.ai_system_id,
    )
    assert result is not None
    assert result["found"] is True
    assert result["configuration_id"] == "lapeep-agent"
    assert result["configuration_digest"] == "sha256:abc"
    assert result["assurance"] == "APPLICATION_REPORTED"
    assert result["observed_model"] == "gemini-test"
