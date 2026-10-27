"""Integration tests for client hook authorization."""

from __future__ import annotations

from rai_gateway.approval.authorization import ApproverContext
from rai_gateway.approval.service import ApprovalService
from rai_gateway.client_hooks.domain import NativeHookEvent
from rai_gateway.client_hooks.service import ClientHookService
from rai_gateway.policy.domain import PolicyEffect
from rai_gateway.policy.service import PolicyCollectionService


def _hook_svc(db_session) -> ClientHookService:
    return ClientHookService(db_session)


def test_cursor_hook_deny_unknown_tool(db_session, runtime_stack) -> None:
    svc = _hook_svc(db_session)
    result = svc.authorize_hook(
        NativeHookEvent(
            client_type="cursor",
            hook_event="beforeMCPExecution",
            payload={
                "mcp_server_name": runtime_stack["mcp"].server_key,
                "tool_name": "unknown_tool_xyz",
                "tool_input": {},
            },
        ),
        credential_secret=runtime_stack["credential_secret"],
    )
    assert result.allowed is False
    assert result.client_response["permission"] == "deny"


def test_cursor_hook_allow(db_session, runtime_stack) -> None:
    svc = _hook_svc(db_session)
    result = svc.authorize_hook(
        NativeHookEvent(
            client_type="cursor",
            hook_event="beforeMCPExecution",
            payload={
                "mcp_server_name": runtime_stack["mcp"].server_key,
                "tool_name": runtime_stack["submit_tool"].tool_key,
                "tool_input": {"amount": 50000},
            },
            delegation_id=runtime_stack["delegation"].id,
        ),
        credential_secret=runtime_stack["credential_secret"],
    )
    assert result.allowed is True
    assert result.client_response["permission"] == "allow"
    assert result.debug is None


def test_cursor_hook_debug_includes_mapping_details(
    db_session, runtime_stack, monkeypatch
) -> None:
    monkeypatch.setenv("RAI_HOOK_DEBUG", "1")
    svc = _hook_svc(db_session)
    result = svc.authorize_hook(
        NativeHookEvent(
            client_type="cursor",
            hook_event="beforeMCPExecution",
            payload={
                "mcp_server_name": runtime_stack["mcp"].server_key,
                "tool_name": runtime_stack["submit_tool"].tool_key,
                "tool_input": {"amount": 50000},
            },
            delegation_id=runtime_stack["delegation"].id,
        ),
        credential_secret=runtime_stack["credential_secret"],
    )
    assert result.allowed is True
    assert result.debug is not None
    assert result.debug["native_mcp"] == runtime_stack["mcp"].server_key
    assert result.debug["native_tool"] == runtime_stack["submit_tool"].tool_key
    assert result.debug["mapped_mcp_id"] == str(runtime_stack["mcp"].id)
    assert result.debug["mapped_tool_id"] == str(runtime_stack["submit_tool"].id)
    assert result.debug["mapping_failure_reason"] is None


def test_cursor_hook_debug_exposes_mapping_failure(
    db_session, runtime_stack, monkeypatch
) -> None:
    monkeypatch.setenv("RAI_HOOK_DEBUG", "1")
    svc = _hook_svc(db_session)
    result = svc.authorize_hook(
        NativeHookEvent(
            client_type="cursor",
            hook_event="beforeMCPExecution",
            payload={
                "mcp_server_name": runtime_stack["mcp"].server_key,
                "tool_name": "unknown_tool_xyz",
                "tool_input": {},
            },
        ),
        credential_secret=runtime_stack["credential_secret"],
    )
    assert result.allowed is False
    assert result.reason_code == "RESOURCE_NOT_REGISTERED"
    assert result.debug is not None
    assert result.debug["mapped_mcp_id"] is None
    assert result.debug["mapped_tool_id"] is None
    assert "Unknown tool" in result.debug["mapping_failure_reason"]


def test_claude_hook_policy_deny(db_session, runtime_stack) -> None:
    PolicyCollectionService(db_session).create_tool_rule(
        runtime_stack["system"].id,
        title="Deny delete",
        tool_id=runtime_stack["delete_tool"].id,
        mcp_server_id=runtime_stack["mcp"].id,
        effect=PolicyEffect.DENY.value,
        actor="tester",
    )
    svc = _hook_svc(db_session)
    result = svc.authorize_hook(
        NativeHookEvent(
            client_type="claude_code",
            hook_event="PreToolUse",
            payload={
                "tool_name": runtime_stack["delete_tool"].tool_key,
                "tool_input": {},
            },
        ),
        credential_secret=runtime_stack["credential_secret"],
    )
    assert result.allowed is False
    assert result.client_response["decision"] == "deny"


def test_gemini_hook_require_approval(db_session, runtime_stack) -> None:
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
    svc = _hook_svc(db_session)
    result = svc.authorize_hook(
        NativeHookEvent(
            client_type="gemini_cli",
            hook_event="BeforeTool",
            payload={
                "name": runtime_stack["submit_tool"].tool_key,
                "args": {"amount": 150000},
            },
            delegation_id=runtime_stack["delegation"].id,
        ),
        credential_secret=runtime_stack["credential_secret"],
    )
    assert result.allowed is False
    assert result.effect == "REQUIRE_APPROVAL"
    assert result.approval_request_id is not None
    assert str(result.approval_request_id) in result.client_response.get("reason", "")
    assert result.client_response["decision"] == "deny"
    from rai_gateway.models.approval import ApprovalRequest

    apr = db_session.get(ApprovalRequest, result.approval_request_id)
    assert apr is not None
    assert apr.status == "PENDING"


def test_cursor_after_mcp_reports_execution(db_session, runtime_stack) -> None:
    svc = _hook_svc(db_session)
    allow = svc.authorize_hook(
        NativeHookEvent(
            client_type="cursor",
            hook_event="beforeMCPExecution",
            payload={
                "command": runtime_stack["mcp"].server_key,
                "tool_name": runtime_stack["submit_tool"].tool_key,
                "tool_input": {"amount": 50000},
            },
            delegation_id=runtime_stack["delegation"].id,
        ),
        credential_secret=runtime_stack["credential_secret"],
    )
    assert allow.allowed is True
    assert allow.receipt_id is not None

    reported = svc.authorize_hook(
        NativeHookEvent(
            client_type="cursor",
            hook_event="afterMCPExecution",
            payload={
                "command": runtime_stack["mcp"].server_key,
                "tool_name": runtime_stack["submit_tool"].tool_key,
                "tool_input": {"amount": 50000},
                "duration_ms": 42,
                "result": {"ok": True},
            },
            delegation_id=runtime_stack["delegation"].id,
        ),
        credential_secret=runtime_stack["credential_secret"],
    )
    assert reported.allowed is True
    assert reported.enforcement_result["execution_status"] == "SUCCEEDED"
    from rai_gateway.models.runtime_enforcement import RuntimeEnforcementReceipt

    receipt = db_session.get(RuntimeEnforcementReceipt, allow.receipt_id)
    assert receipt is not None
    assert receipt.execution_attempted is True
    assert receipt.execution_status == "SUCCEEDED"
    assert receipt.duration_ms == 42


def test_gemini_hook_approved_retry(db_session, runtime_stack) -> None:
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
        parameters={"amount": 150000},
        created_by="ahmed",
        force=True,
    )
    ApprovalService(db_session).approve(
        approval.id,
        approver=ApproverContext(actor="manager", role="admin"),
    )

    # Hook authorize returns allow (does not execute downstream)
    svc = _hook_svc(db_session)
    result = svc.authorize_hook(
        NativeHookEvent(
            client_type="gemini_cli",
            hook_event="BeforeTool",
            payload={
                "name": runtime_stack["submit_tool"].tool_key,
                "args": {"amount": 150000},
            },
            delegation_id=runtime_stack["delegation"].id,
        ),
        credential_secret=runtime_stack["credential_secret"],
    )
    assert result.allowed is True
    assert result.client_response["decision"] == "allow"


def test_bridge_failure_gemini_exit_code(db_session, runtime_stack) -> None:
    from rai_gateway.client_hooks.adapters import GeminiCLIHookAdapter

    svc = _hook_svc(db_session)
    result = svc._failure_block(
        GeminiCLIHookAdapter(),
        reason="RAI unavailable",
        reason_code="DOWNSTREAM_UNAVAILABLE",
        trace_id="test",
    )
    assert result.exit_code == 2
