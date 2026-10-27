"""WP5 approval lifecycle projection into trajectories."""

from __future__ import annotations

from rai_gateway.approval.authorization import ApproverContext
from rai_gateway.approval.canonicalizer import canonicalize_action
from rai_gateway.approval.consumption import ApprovalConsumptionService
from rai_gateway.approval.domain import (
    ActionTarget,
    ProposedAction,
)
from rai_gateway.approval.service import ApprovalService
from rai_gateway.evidence.domain import (
    AssuranceLevel,
    EvidenceEventType,
    EvidenceRelationType,
    EvidenceSourceType,
)
from rai_gateway.evidence.service import TrajectoryService


def _authority(db_session, stack):
    return ApprovalConsumptionService(db_session).resolve_authority_for_identity(
        stack["identity"].id,
        stack["delegation"].id,
    )


def _create_request(db_session, stack, **kwargs):
    authority = _authority(db_session, stack)
    return ApprovalService(db_session).create_request(
        authority,
        integration_type="mcp",
        integration_id=stack["mcp"].id,
        tool_id=stack["tool"].id,
        target_type="Customer",
        target_identifier="CUST-100",
        parameters={"status": "Active"},
        business_reason="Update customer status",
        created_by="ahmed",
        force=True,
        **kwargs,
    )


def _proposed_action(stack) -> ProposedAction:
    return ProposedAction(
        ai_system_id=stack["system"].id,
        agent_id=stack["agent"].id,
        agent_version_id=stack["version"].id,
        runtime_identity_id=stack["identity"].id,
        delegation_id=stack["delegation"].id,
        integration_type="mcp",
        integration_id=stack["mcp"].id,
        tool_id=stack["tool"].id,
        target=ActionTarget(type="Customer", id="CUST-100"),
        parameters={"status": "Active"},
    )


class TestApprovalProjection:
    def test_create_approve_consume_events(self, db_session, approval_stack):
        evidence = TrajectoryService(db_session)
        request = _create_request(
            db_session, approval_stack, correlation_id="apr-corr-1"
        )

        # Auto-projected on create.
        rows = evidence.list_trajectories(
            runtime_identity_id=approval_stack["identity"].id
        )
        assert rows
        trajectory = rows[0]
        types = {e.event_type for e in evidence.list_events(trajectory.id)}
        assert EvidenceEventType.APPROVAL_REQUESTED.value in types

        ApprovalService(db_session).approve(
            request.id,
            approver=ApproverContext(actor="manager", role="admin"),
            decision_reason="Looks good",
        )
        events = evidence.list_events(trajectory.id)
        decided = [
            e
            for e in events
            if e.event_type == EvidenceEventType.APPROVAL_DECIDED.value
        ]
        assert len(decided) == 1
        assert decided[0].source_type == EvidenceSourceType.RAI_AUTHORITATIVE.value
        assert decided[0].assurance_level == AssuranceLevel.HIGH.value
        assert decided[0].payload["decided_by"] == "manager"
        assert decided[0].payload["decision"] == "APPROVED"

        authority = _authority(db_session, approval_stack)
        action = _proposed_action(approval_stack)
        result = ApprovalConsumptionService(db_session).consume(
            authority,
            action,
            approval_request_id=request.id,
            correlation_id="apr-corr-1",
        )
        assert result.allowed is True

        events = evidence.list_events(trajectory.id)
        types = {e.event_type for e in events}
        assert EvidenceEventType.APPROVAL_CONSUMED.value in types

        relations = evidence.list_relations(trajectory.id)
        assert any(
            r.relation_type == EvidenceRelationType.APPROVED_BY.value for r in relations
        )

    def test_reject_emits_rejected_by(self, db_session, approval_stack):
        evidence = TrajectoryService(db_session)
        request = _create_request(db_session, approval_stack)
        ApprovalService(db_session).reject(
            request.id,
            approver=ApproverContext(actor="manager", role="admin"),
            decision_reason="Too risky",
        )
        rows = evidence.list_trajectories(
            runtime_identity_id=approval_stack["identity"].id
        )
        events = evidence.list_events(rows[0].id)
        decided = [
            e
            for e in events
            if e.event_type == EvidenceEventType.APPROVAL_DECIDED.value
        ]
        assert decided[0].payload["decision"] == "REJECTED"
        relations = evidence.list_relations(rows[0].id)
        assert any(
            r.relation_type == EvidenceRelationType.REJECTED_BY.value for r in relations
        )

    def test_idempotent_with_receipt_shared_source_refs(
        self, db_session, approval_stack
    ):
        evidence = TrajectoryService(db_session)
        request = _create_request(
            db_session, approval_stack, correlation_id="shared-corr"
        )
        ApprovalService(db_session).approve(
            request.id,
            approver=ApproverContext(actor="manager", role="admin"),
        )

        # Re-project explicitly — should not duplicate REQUESTED.
        t1 = evidence.project_approval(request.id)
        count1 = len(
            [
                e
                for e in evidence.list_events(t1.id)
                if e.event_type == EvidenceEventType.APPROVAL_REQUESTED.value
            ]
        )
        t2 = evidence.project_approval(request.id)
        count2 = len(
            [
                e
                for e in evidence.list_events(t2.id)
                if e.event_type == EvidenceEventType.APPROVAL_REQUESTED.value
            ]
        )
        db_session.commit()
        assert t1.id == t2.id
        assert count1 == count2 == 1

    def test_digest_stable_for_action(self, approval_stack):
        action = _proposed_action(approval_stack)
        _, digest = canonicalize_action(action)
        assert digest
