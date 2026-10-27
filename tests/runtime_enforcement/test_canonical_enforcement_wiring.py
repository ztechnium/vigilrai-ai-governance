"""Backend acceptance for canonical enforcement wiring (PR5)."""

from __future__ import annotations

from rai_gateway.models.runtime_enforcement import (
    RuntimeControlDecision,
    RuntimeEnforcementReceipt,
)
from rai_gateway.runtime_enforcement.adapters.base import RuntimeAdapterRegistry
from rai_gateway.runtime_enforcement.domain import (
    EnforcementDecisionType,
    ExecutionStatus,
    RuntimeActionRequest,
    RuntimeEnforcementReasonCode,
)
from rai_gateway.runtime_enforcement.service import RuntimeEnforcementService
from runtime_enforcement.fakes import FakeAdapter


def _request(stack, **overrides) -> RuntimeActionRequest:
    base = {
        "integration_type": "mcp",
        "integration_id": stack["mcp"].id,
        "tool_id": stack["submit_tool"].id,
        "parameters": {"po": "1"},
        "delegation_id": stack["delegation"].id,
        "environment": "production",
    }
    base.update(overrides)
    return RuntimeActionRequest(**base)


def _svc(db_session, fake_adapter: FakeAdapter) -> RuntimeEnforcementService:
    return RuntimeEnforcementService(
        db_session, adapter_registry=RuntimeAdapterRegistry([fake_adapter])
    )


def test_allow_succeeded_persists_control_children(
    db_session, runtime_stack, fake_adapter
):
    svc = _svc(db_session, fake_adapter)
    result = svc.enforce_and_execute(
        _request(runtime_stack),
        credential_secret=runtime_stack["credential_secret"],
    )
    assert result.allowed is True
    assert result.receipt_id is not None
    controls = (
        db_session.query(RuntimeControlDecision)
        .filter(RuntimeControlDecision.receipt_id == result.receipt_id)
        .order_by(RuntimeControlDecision.sequence)
        .all()
    )
    assert len(controls) >= 2
    assert controls[0].control_type == "AUTHORITY"
    assert controls[0].effect == "ALLOW"
    receipt = db_session.get(RuntimeEnforcementReceipt, result.receipt_id)
    assert receipt.receipt_schema_version == 2
    assert receipt.decision_finalized_at is not None
    assert receipt.decision_digest
    assert receipt.authority_snapshot is not None
    assert receipt.enforcement_decision == EnforcementDecisionType.ALLOW.value


def test_execution_failure_does_not_rewrite_decision(
    db_session, runtime_stack, fake_adapter
):
    fake_adapter.should_fail = True
    svc = _svc(db_session, fake_adapter)
    result = svc.enforce_and_execute(
        _request(runtime_stack),
        credential_secret=runtime_stack["credential_secret"],
    )
    assert result.allowed is True
    assert result.execution_status == ExecutionStatus.FAILED.value
    receipt = db_session.get(RuntimeEnforcementReceipt, result.receipt_id)
    assert receipt.enforcement_decision == EnforcementDecisionType.ALLOW.value
    assert receipt.execution_status == ExecutionStatus.FAILED.value


def test_scope_violation_records_authority_deny_and_skipped(
    db_session, runtime_stack, fake_adapter
):
    from rai_gateway.identity.service import DelegationService

    # Narrow delegation so delete_tool is outside effective authority.
    DelegationService(db_session).update_delegation(
        runtime_stack["delegation"].id,
        updated_by="tester",
        scope={
            "mcp_server_ids": [str(runtime_stack["mcp"].id)],
            "tool_ids": [str(runtime_stack["submit_tool"].id)],
        },
        change_reason="narrow for authority test",
    )
    svc = _svc(db_session, fake_adapter)
    result = svc.enforce_and_execute(
        _request(runtime_stack, tool_id=runtime_stack["delete_tool"].id),
        credential_secret=runtime_stack["credential_secret"],
    )
    assert result.allowed is False
    assert (
        result.reason_code
        == RuntimeEnforcementReasonCode.AUTHORITY_SCOPE_EXCEEDED.value
    )
    controls = (
        db_session.query(RuntimeControlDecision)
        .filter(RuntimeControlDecision.receipt_id == result.receipt_id)
        .order_by(RuntimeControlDecision.sequence)
        .all()
    )
    assert controls[0].control_type == "AUTHORITY"
    assert controls[0].effect == "DENY"
    assert any(c.status == "SKIPPED" for c in controls[1:])
    assert fake_adapter.invocation_count == 0
