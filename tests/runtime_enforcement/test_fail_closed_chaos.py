"""§3.7 chaos tests — mandatory control errors fail closed with zero downstream calls."""

from __future__ import annotations

from unittest.mock import patch

from rai_gateway.approval.authorization import ApproverContext
from rai_gateway.approval.service import ApprovalService
from rai_gateway.core.config import settings
from rai_gateway.policy.domain import PolicyEffect
from rai_gateway.policy.service import PolicyCollectionService
from rai_gateway.runtime_enforcement.domain import (
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

    return RuntimeEnforcementService(
        db_session, adapter_registry=RuntimeAdapterRegistry([fake_adapter])
    )


def test_risk_service_error_fail_closed_zero_downstream(
    db_session, runtime_stack, fake_adapter, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "fail_closed_on_rai_unavailable", True)
    svc = _svc(db_session, fake_adapter)

    with patch(
        "rai_gateway.risk_intelligence.service.RiskIntelligenceService.authorization_overlay",
        side_effect=RuntimeError("simulated risk DB error"),
    ):
        result = svc.enforce_and_execute(
            _request(runtime_stack),
            credential_secret=runtime_stack["credential_secret"],
        )

    assert result.allowed is False
    assert result.execution_attempted is False
    assert (
        result.reason_code
        == RuntimeEnforcementReasonCode.RISK_CONTROL_UNAVAILABLE.value
    )
    assert fake_adapter.invocation_count == 0


def test_budget_service_error_fail_closed_zero_downstream(
    db_session, runtime_stack, fake_adapter, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "fail_closed_on_rai_unavailable", True)
    svc = _svc(db_session, fake_adapter)

    with patch(
        "rai_gateway.risk_intelligence.service.RiskIntelligenceService.budget_authorization_check",
        side_effect=RuntimeError("simulated budget DB error"),
    ):
        result = svc.enforce_and_execute(
            _request(runtime_stack),
            credential_secret=runtime_stack["credential_secret"],
        )

    assert result.allowed is False
    assert result.execution_attempted is False
    assert (
        result.reason_code
        == RuntimeEnforcementReasonCode.RISK_CONTROL_UNAVAILABLE.value
    )
    assert fake_adapter.invocation_count == 0


def test_policy_evaluator_error_fail_closed_zero_downstream(
    db_session, runtime_stack, fake_adapter
) -> None:
    svc = _svc(db_session, fake_adapter)

    with patch.object(
        svc._policy,
        "evaluate",
        side_effect=RuntimeError("simulated policy evaluator crash"),
    ):
        result = svc.enforce_and_execute(
            _request(runtime_stack),
            credential_secret=runtime_stack["credential_secret"],
        )

    assert result.allowed is False
    assert result.execution_attempted is False
    assert (
        result.reason_code
        == RuntimeEnforcementReasonCode.POLICY_EVALUATION_FAILED.value
    )
    assert fake_adapter.invocation_count == 0


def test_approval_requirement_error_fail_closed_zero_downstream(
    db_session, runtime_stack, fake_adapter, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "fail_closed_on_rai_unavailable", True)
    svc = _svc(db_session, fake_adapter)

    with patch.object(
        svc._requirement,
        "evaluate",
        side_effect=RuntimeError("simulated approval requirement error"),
    ):
        result = svc.enforce_and_execute(
            _request(runtime_stack),
            credential_secret=runtime_stack["credential_secret"],
        )

    assert result.allowed is False
    assert result.execution_attempted is False
    assert (
        result.reason_code
        == RuntimeEnforcementReasonCode.APPROVAL_CONTROL_UNAVAILABLE.value
    )
    assert fake_adapter.invocation_count == 0


def test_approval_consume_error_fail_closed_zero_downstream(
    db_session, runtime_stack, fake_adapter, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "fail_closed_on_rai_unavailable", True)
    PolicyCollectionService(db_session).create_tool_rule(
        runtime_stack["system"].id,
        title="High Value PO chaos",
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
    with patch.object(
        svc._consumption,
        "consume",
        side_effect=RuntimeError("simulated approval consume DB error"),
    ):
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

    assert result.allowed is False
    assert result.execution_attempted is False
    assert (
        result.reason_code
        == RuntimeEnforcementReasonCode.APPROVAL_CONTROL_UNAVAILABLE.value
    )
    assert fake_adapter.invocation_count == 0


def test_risk_error_advisory_when_fail_closed_disabled(
    db_session, runtime_stack, fake_adapter, monkeypatch
) -> None:
    """When fail-closed is off, risk control errors degrade (do not hard-deny)."""
    monkeypatch.setattr(settings, "fail_closed_on_rai_unavailable", False)
    svc = _svc(db_session, fake_adapter)

    with patch(
        "rai_gateway.risk_intelligence.service.RiskIntelligenceService.authorization_overlay",
        side_effect=RuntimeError("simulated risk DB error"),
    ):
        result = svc.enforce_and_execute(
            _request(runtime_stack),
            credential_secret=runtime_stack["credential_secret"],
        )

    assert result.allowed is True
    assert result.execution_attempted is True
    assert fake_adapter.invocation_count == 1
