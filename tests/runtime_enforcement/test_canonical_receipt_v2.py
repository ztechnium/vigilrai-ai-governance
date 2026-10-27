"""Tests for canonical enforcement receipt V2 persistence."""

from __future__ import annotations

import pytest

from rai_gateway.models.runtime_enforcement import RuntimeEnforcementReceipt
from rai_gateway.runtime_enforcement.control_decision import (
    ControlDecisionInput,
    ControlDecisionStatus,
    ControlType,
    DecisionPhase,
)
from rai_gateway.runtime_enforcement.repository import (
    FinalizedDecisionMutationError,
    RuntimeEnforcementRepository,
)


@pytest.fixture()
def repo(db_session) -> RuntimeEnforcementRepository:
    return RuntimeEnforcementRepository(db_session)


def _minimal_receipt_fields(test_organization, runtime_stack) -> dict:
    return {
        "runtime_identity_id": runtime_stack["identity"].id,
        "ai_system_id": runtime_stack["system"].id,
        "agent_id": runtime_stack["agent"].id,
        "agent_version_id": runtime_stack["version"].id,
        "integration_type": "mcp",
        "action_digest": "digest-abc",
        "enforcement_decision": "ALLOW",
        "execution_status": "NOT_ATTEMPTED",
        "decision_phase": DecisionPhase.EXECUTE.value,
        "authority_digest": "auth-digest",
        "authority_snapshot": {"schema_version": 2},
        "effective_scope_digest": "scope-digest",
    }


def test_append_controls_finalize_and_immutability(
    repo, db_session, test_organization, runtime_stack
):
    receipt = repo.create_decision_receipt(
        **_minimal_receipt_fields(test_organization, runtime_stack)
    )
    assert receipt.receipt_schema_version == 2
    assert receipt.decision_chain_id is not None

    repo.append_control_decision(
        receipt,
        ControlDecisionInput(
            control_type=ControlType.AUTHORITY.value,
            status=ControlDecisionStatus.EVALUATED.value,
            effect="ALLOW",
        ),
    )
    repo.append_control_decision(
        receipt,
        ControlDecisionInput(
            control_type=ControlType.POLICY.value,
            policy_domain="ACTION",
            status=ControlDecisionStatus.EVALUATED.value,
            effect="ALLOW",
            matched_rule_ids=["r1"],
        ),
    )
    repo.append_control_decision(
        receipt,
        ControlDecisionInput(
            control_type=ControlType.BUDGET.value,
            status=ControlDecisionStatus.SKIPPED.value,
            reason_code="SHORT_CIRCUITED",
        ),
    )

    controls = repo.list_control_decisions(receipt.id)
    assert [c.sequence for c in controls] == [1, 2, 3]
    assert controls[2].status == ControlDecisionStatus.SKIPPED.value

    repo.finalize_decision(
        receipt,
        enforcement_decision="ALLOW",
        reason_code=None,
        policy_effect="ALLOW",
        control_summary={"control_count": 3},
    )
    assert receipt.decision_finalized_at is not None
    digest1 = receipt.decision_digest
    assert digest1
    digest2 = repo.compute_decision_digest(receipt)
    assert digest1 == digest2

    with pytest.raises(FinalizedDecisionMutationError):
        repo.append_control_decision(
            receipt,
            ControlDecisionInput(control_type=ControlType.RISK.value),
        )
    with pytest.raises(FinalizedDecisionMutationError):
        repo.update_receipt(receipt, enforcement_decision="DENY")
    with pytest.raises(FinalizedDecisionMutationError):
        repo.finalize_decision(receipt, enforcement_decision="DENY")

    repo.update_execution_outcome(
        receipt,
        execution_attempted=True,
        execution_status="FAILED",
        execution_report={"error": "downstream"},
    )
    assert receipt.enforcement_decision == "ALLOW"
    assert receipt.execution_status == "FAILED"
    db_session.commit()


def test_historical_schema_v1_has_no_authority_snapshot(
    db_session, test_organization, runtime_stack
):
    receipt = RuntimeEnforcementReceipt(
        receipt_schema_version=1,
        runtime_identity_id=runtime_stack["identity"].id,
        ai_system_id=runtime_stack["system"].id,
        agent_id=runtime_stack["agent"].id,
        agent_version_id=runtime_stack["version"].id,
        integration_type="mcp",
        action_digest="legacy",
        enforcement_decision="ALLOW",
        execution_status="SUCCEEDED",
        authority_snapshot=None,
    )
    db_session.add(receipt)
    db_session.commit()
    assert receipt.receipt_schema_version == 1
    assert receipt.authority_snapshot is None
