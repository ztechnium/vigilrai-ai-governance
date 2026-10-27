"""WP4 runtime enforcement integration tests."""

from __future__ import annotations

import threading
import uuid

from rai_gateway.approval.authorization import ApproverContext
from rai_gateway.approval.domain import ApprovalStatus
from rai_gateway.approval.service import ApprovalService
from rai_gateway.policy.domain import PolicyEffect
from rai_gateway.policy.service import PolicyCollectionService
from rai_gateway.runtime_enforcement.domain import (
    EnforcementDecisionType,
    ExecutionStatus,
    RuntimeActionRequest,
    RuntimeActionTarget,
    RuntimeEnforcementReasonCode,
)
from rai_gateway.runtime_enforcement.service import RuntimeEnforcementService
from runtime_enforcement.fakes import FakeAdapter


def _request(stack, **kwargs) -> RuntimeActionRequest:
    defaults = {
        "integration_type": "mcp",
        "integration_id": stack["mcp"].id,
        "tool_id": stack["submit_tool"].id,
        "target": RuntimeActionTarget(type="PurchaseOrder"),
        "parameters": {"supplier": "SUP-104", "amount": 50000, "currency": "EGP"},
        "delegation_id": stack["delegation"].id,
    }
    defaults.update(kwargs)
    return RuntimeActionRequest(**defaults)


def _svc(db_session, fake_adapter: FakeAdapter) -> RuntimeEnforcementService:
    from rai_gateway.runtime_enforcement.adapters.base import RuntimeAdapterRegistry

    registry = RuntimeAdapterRegistry([fake_adapter])
    return RuntimeEnforcementService(db_session, adapter_registry=registry)


def test_allow_executes_downstream(db_session, runtime_stack, fake_adapter) -> None:
    svc = _svc(db_session, fake_adapter)
    result = svc.enforce_and_execute(
        _request(runtime_stack),
        credential_secret=runtime_stack["credential_secret"],
    )
    assert result.allowed is True
    assert result.execution_attempted is True
    assert result.execution_status == ExecutionStatus.SUCCEEDED.value
    assert fake_adapter.invocation_count == 1
    assert result.receipt_id is not None


def test_policy_deny_never_invokes(db_session, runtime_stack, fake_adapter) -> None:
    PolicyCollectionService(db_session).create_tool_rule(
        runtime_stack["system"].id,
        title="Deny delete",
        tool_id=runtime_stack["delete_tool"].id,
        mcp_server_id=runtime_stack["mcp"].id,
        effect=PolicyEffect.DENY.value,
        actor="tester",
    )

    svc = _svc(db_session, fake_adapter)
    result = svc.enforce_and_execute(
        _request(runtime_stack, tool_id=runtime_stack["delete_tool"].id),
        credential_secret=runtime_stack["credential_secret"],
    )
    assert result.allowed is False
    assert result.reason_code == RuntimeEnforcementReasonCode.POLICY_DENIED.value
    assert result.execution_attempted is False
    assert fake_adapter.invocation_count == 0


def test_require_approval_without_approval_never_invokes(
    db_session, runtime_stack, fake_adapter
) -> None:
    PolicyCollectionService(db_session).create_tool_rule(
        runtime_stack["system"].id,
        title="High Value PO",
        tool_id=runtime_stack["submit_tool"].id,
        mcp_server_id=runtime_stack["mcp"].id,
        effect=PolicyEffect.REQUIRE_APPROVAL.value,
        required_approver_role="business_approver",
        conditions=[
            {
                "parameter_path": "amount",
                "operator": "gte",
                "value_type": "number",
                "value": 100000,
            }
        ],
        actor="tester",
    )

    svc = _svc(db_session, fake_adapter)
    result = svc.enforce_and_execute(
        _request(
            runtime_stack,
            parameters={"supplier": "SUP-104", "amount": 150000, "currency": "EGP"},
        ),
        credential_secret=runtime_stack["credential_secret"],
    )
    assert result.allowed is False
    assert result.effect == EnforcementDecisionType.REQUIRE_APPROVAL.value
    assert result.reason_code == RuntimeEnforcementReasonCode.APPROVAL_REQUIRED.value
    assert fake_adapter.invocation_count == 0


def test_approved_action_consumes_and_executes(
    db_session, runtime_stack, fake_adapter
) -> None:
    PolicyCollectionService(db_session).create_tool_rule(
        runtime_stack["system"].id,
        title="High Value PO",
        tool_id=runtime_stack["submit_tool"].id,
        mcp_server_id=runtime_stack["mcp"].id,
        effect=PolicyEffect.REQUIRE_APPROVAL.value,
        required_approver_role="business_approver",
        conditions=[
            {
                "parameter_path": "amount",
                "operator": "gte",
                "value_type": "number",
                "value": 100000,
            }
        ],
        actor="tester",
    )

    from rai_gateway.approval.consumption import ApprovalConsumptionService

    authority = ApprovalConsumptionService(db_session).resolve_authority_for_identity(
        runtime_stack["identity"].id,
        runtime_stack["delegation"].id,
    )
    approval = ApprovalService(db_session).create_request(
        authority,
        integration_type="mcp",
        integration_id=runtime_stack["mcp"].id,
        tool_id=runtime_stack["submit_tool"].id,
        target_type="PurchaseOrder",
        parameters={"supplier": "SUP-104", "amount": 150000, "currency": "EGP"},
        created_by="ahmed",
        force=True,
    )
    ApprovalService(db_session).approve(
        approval.id,
        approver=ApproverContext(actor="manager", role="admin"),
    )

    svc = _svc(db_session, fake_adapter)
    result = svc.enforce_and_execute(
        _request(
            runtime_stack,
            parameters={"supplier": "SUP-104", "amount": 150000, "currency": "EGP"},
            approval_request_id=approval.id,
        ),
        credential_secret=runtime_stack["credential_secret"],
    )
    assert result.allowed is True
    assert result.approval_consumed is True
    assert fake_adapter.invocation_count == 1

    db_session.refresh(approval)
    assert approval.status == ApprovalStatus.CONSUMED.value


def test_tampered_parameters_denied(db_session, runtime_stack, fake_adapter) -> None:
    from rai_gateway.approval.consumption import ApprovalConsumptionService

    authority = ApprovalConsumptionService(db_session).resolve_authority_for_identity(
        runtime_stack["identity"].id,
        runtime_stack["delegation"].id,
    )
    approval = ApprovalService(db_session).create_request(
        authority,
        integration_type="mcp",
        integration_id=runtime_stack["mcp"].id,
        tool_id=runtime_stack["submit_tool"].id,
        target_type="PurchaseOrder",
        parameters={"supplier": "SUP-104", "amount": 150000, "currency": "EGP"},
        created_by="ahmed",
        force=True,
    )
    ApprovalService(db_session).approve(
        approval.id,
        approver=ApproverContext(actor="manager", role="admin"),
    )

    PolicyCollectionService(db_session).create_tool_rule(
        runtime_stack["system"].id,
        title="High Value PO",
        tool_id=runtime_stack["submit_tool"].id,
        mcp_server_id=runtime_stack["mcp"].id,
        effect=PolicyEffect.REQUIRE_APPROVAL.value,
        required_approver_role="business_approver",
        conditions=[
            {
                "parameter_path": "amount",
                "operator": "gte",
                "value_type": "number",
                "value": 100000,
            }
        ],
        actor="tester",
    )

    svc = _svc(db_session, fake_adapter)
    result = svc.enforce_and_execute(
        _request(
            runtime_stack,
            parameters={"supplier": "SUP-104", "amount": 250000, "currency": "EGP"},
            approval_request_id=approval.id,
        ),
        credential_secret=runtime_stack["credential_secret"],
    )
    assert result.allowed is False
    assert result.reason_code in {
        RuntimeEnforcementReasonCode.APPROVAL_NOT_FOUND.value,
        RuntimeEnforcementReasonCode.APPROVAL_ACTION_MISMATCH.value,
    }
    assert fake_adapter.invocation_count == 0


def test_execution_failure_still_allowed(
    db_session, runtime_stack, fake_adapter
) -> None:
    fake_adapter.should_fail = True
    svc = _svc(db_session, fake_adapter)
    result = svc.enforce_and_execute(
        _request(runtime_stack),
        credential_secret=runtime_stack["credential_secret"],
    )
    assert result.allowed is True
    assert result.effect == EnforcementDecisionType.ALLOW.value
    assert result.execution_attempted is True
    assert result.execution_status == ExecutionStatus.FAILED.value
    assert fake_adapter.invocation_count == 1


def test_invalid_credential_denied(db_session, runtime_stack, fake_adapter) -> None:
    svc = _svc(db_session, fake_adapter)
    result = svc.enforce_and_execute(
        _request(runtime_stack),
        credential_secret="invalid-secret",
    )
    assert result.allowed is False
    assert fake_adapter.invocation_count == 0


def test_unknown_tool_denied(db_session, runtime_stack, fake_adapter) -> None:
    svc = _svc(db_session, fake_adapter)
    result = svc.enforce_and_execute(
        _request(runtime_stack, tool_id=uuid.uuid4()),
        credential_secret=runtime_stack["credential_secret"],
    )
    assert result.allowed is False
    assert (
        result.reason_code == RuntimeEnforcementReasonCode.RESOURCE_NOT_REGISTERED.value
    )
    assert fake_adapter.invocation_count == 0


def test_monitor_executes_with_flag(db_session, runtime_stack, fake_adapter) -> None:
    PolicyCollectionService(db_session).create_tool_rule(
        runtime_stack["system"].id,
        title="Monitor PO",
        tool_id=runtime_stack["submit_tool"].id,
        mcp_server_id=runtime_stack["mcp"].id,
        effect=PolicyEffect.MONITOR.value,
        actor="tester",
    )

    svc = _svc(db_session, fake_adapter)
    result = svc.enforce_and_execute(
        _request(runtime_stack),
        credential_secret=runtime_stack["credential_secret"],
    )
    assert result.allowed is True
    assert result.monitor is True
    assert fake_adapter.invocation_count == 1


def test_authorize_consumes_prior_approval_on_later_turn(
    db_session, runtime_stack, fake_adapter
) -> None:
    """A later authorize of the same action consumes an existing approval.

    Hook clients such as QAA do not resend approval_request_id. Each customer
    message uses a new idempotency key, so the match is the action digest.
    """
    PolicyCollectionService(db_session).create_tool_rule(
        runtime_stack["system"].id,
        title="High Value PO",
        tool_id=runtime_stack["submit_tool"].id,
        mcp_server_id=runtime_stack["mcp"].id,
        effect=PolicyEffect.REQUIRE_APPROVAL.value,
        required_approver_role="business_approver",
        conditions=[
            {
                "parameter_path": "amount",
                "operator": "gte",
                "value_type": "number",
                "value": 100000,
            }
        ],
        actor="tester",
    )
    svc = _svc(db_session, fake_adapter)
    parameters = {"supplier": "SUP-104", "amount": 150000, "currency": "EGP"}
    first = svc.authorize(
        _request(
            runtime_stack,
            parameters=parameters,
            idempotency_key="escalate:message-1",
        ),
        credential_secret=runtime_stack["credential_secret"],
    )
    assert first.allowed is False
    assert first.reason_code == RuntimeEnforcementReasonCode.APPROVAL_REQUIRED.value
    assert first.approval_request_id is not None

    ApprovalService(db_session).approve(
        first.approval_request_id,
        approver=ApproverContext(actor="manager", role="admin"),
    )

    second = svc.authorize(
        _request(
            runtime_stack,
            parameters=parameters,
            idempotency_key="escalate:message-2",
        ),
        credential_secret=runtime_stack["credential_secret"],
    )
    assert second.allowed is True
    assert second.approval_consumed is True
    assert second.approval_request_id == first.approval_request_id
    assert second.execution_attempted is False
    assert fake_adapter.invocation_count == 0

    approval = ApprovalService(db_session).get_request(first.approval_request_id)
    assert approval.status == ApprovalStatus.CONSUMED.value


def test_authorize_does_not_execute(db_session, runtime_stack, fake_adapter) -> None:
    svc = _svc(db_session, fake_adapter)
    result = svc.authorize(
        _request(runtime_stack),
        credential_secret=runtime_stack["credential_secret"],
    )
    assert result.allowed is True
    assert result.execution_attempted is False
    assert fake_adapter.invocation_count == 0


def test_idempotency_replay_no_duplicate_execution(
    db_session, runtime_stack, fake_adapter
) -> None:
    svc = _svc(db_session, fake_adapter)
    req = _request(runtime_stack, idempotency_key="idem-1")
    first = svc.enforce_and_execute(
        req, credential_secret=runtime_stack["credential_secret"]
    )
    second = svc.enforce_and_execute(
        req, credential_secret=runtime_stack["credential_secret"]
    )
    assert first.allowed is True
    assert second.allowed is True
    assert second.receipt_id == first.receipt_id
    assert fake_adapter.invocation_count == 1


def test_concurrent_approval_consumption(
    db_session, db_engine, runtime_stack, fake_adapter
) -> None:
    PolicyCollectionService(db_session).create_tool_rule(
        runtime_stack["system"].id,
        title="High Value PO",
        tool_id=runtime_stack["submit_tool"].id,
        mcp_server_id=runtime_stack["mcp"].id,
        effect=PolicyEffect.REQUIRE_APPROVAL.value,
        required_approver_role="business_approver",
        conditions=[
            {
                "parameter_path": "amount",
                "operator": "gte",
                "value_type": "number",
                "value": 100000,
            }
        ],
        actor="tester",
    )

    from rai_gateway.approval.consumption import ApprovalConsumptionService

    authority = ApprovalConsumptionService(db_session).resolve_authority_for_identity(
        runtime_stack["identity"].id,
        runtime_stack["delegation"].id,
    )
    approval = ApprovalService(db_session).create_request(
        authority,
        integration_type="mcp",
        integration_id=runtime_stack["mcp"].id,
        tool_id=runtime_stack["submit_tool"].id,
        target_type="PurchaseOrder",
        parameters={"supplier": "SUP-104", "amount": 150000, "currency": "EGP"},
        created_by="ahmed",
        force=True,
    )
    ApprovalService(db_session).approve(
        approval.id,
        approver=ApproverContext(actor="manager", role="admin"),
    )

    results: list = []
    barrier = threading.Barrier(2)

    def attempt() -> None:
        from sqlalchemy.orm import sessionmaker

        session_local = sessionmaker(
            autocommit=False, autoflush=False, bind=db_engine["engine"]
        )
        session = session_local()
        try:
            adapter = FakeAdapter()
            from rai_gateway.runtime_enforcement.adapters.base import (
                RuntimeAdapterRegistry,
            )

            svc = RuntimeEnforcementService(
                session, adapter_registry=RuntimeAdapterRegistry([adapter])
            )
            barrier.wait(timeout=5)
            result = svc.enforce_and_execute(
                _request(
                    runtime_stack,
                    parameters={
                        "supplier": "SUP-104",
                        "amount": 150000,
                        "currency": "EGP",
                    },
                    approval_request_id=approval.id,
                ),
                credential_secret=runtime_stack["credential_secret"],
            )
            results.append((result.allowed, adapter.invocation_count))
        finally:
            session.close()

    t1 = threading.Thread(target=attempt)
    t2 = threading.Thread(target=attempt)
    t1.start()
    t2.start()
    t1.join(timeout=30)
    t2.join(timeout=30)

    allowed_count = sum(1 for allowed, _ in results if allowed)
    total_invocations = sum(count for _, count in results)
    assert allowed_count == 1
    assert total_invocations == 1
