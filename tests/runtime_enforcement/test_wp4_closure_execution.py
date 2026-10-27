"""WP4 closure: post-execution reporting and receipt detail sections."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from rai_gateway.client_hooks.domain import NativeHookEvent
from rai_gateway.client_hooks.service import ClientHookService
from rai_gateway.identity.domain import DelegatorType
from rai_gateway.identity.service import (
    CredentialService,
    DelegationService,
    RuntimeIdentityService,
)
from rai_gateway.models.registry import MCPServer, ToolResource
from rai_gateway.models.runtime_enforcement import RuntimeEnforcementReceipt
from rai_gateway.policy.content_evaluator import (
    CONTENT_EVALUATOR_REASON,
    CONTENT_EVALUATOR_STATUS,
    get_content_policy_evaluator,
)
from rai_gateway.registry.domain import (
    AgentStatus,
    AgentVersionStatus,
    AISystemStatus,
    CatalogScope,
)
from rai_gateway.registry.seed_mcp_catalog import (
    DEFAULT_SEED_PATH,
    MCPSeedCatalogService,
)
from rai_gateway.registry.service import RegistryService
from rai_gateway.runtime_enforcement.domain import (
    ClientExecutionReport,
    ExecutionSource,
    ExecutionStatus,
    VerificationStatus,
)
from rai_gateway.runtime_enforcement.receipt_serializer import serialize_receipt_detail
from rai_gateway.runtime_enforcement.service import RuntimeEnforcementService


def _hook_runtime_stack(db_session, *, system_key: str = "closure-sys") -> dict:
    MCPSeedCatalogService(db_session).seed(DEFAULT_SEED_PATH)
    registry = RegistryService(db_session)
    mcp = (
        db_session.query(MCPServer)
        .filter(MCPServer.server_key == "atlassian")
        .order_by(MCPServer.created_at.desc())
        .first()
    )
    assert mcp is not None
    tool = (
        db_session.query(ToolResource)
        .filter(ToolResource.tool_key == "atlassian.getAccessibleAtlassianResources")
        .order_by(ToolResource.created_at.desc())
        .first()
    )
    assert tool is not None
    # Make seeded catalog rows visible to the tenant for version binding.
    mcp.status = "ACTIVE"
    mcp.scope = CatalogScope.ORGANIZATION.value
    tool.status = "ACTIVE"
    tool.scope = CatalogScope.ORGANIZATION.value
    db_session.commit()

    system = registry.create_ai_system(
        system_key=system_key,
        name="Closure Sys",
        created_by="tester",
    )
    for status in (AISystemStatus.UNDER_REVIEW, AISystemStatus.APPROVED):
        registry.transition_ai_system(system.id, status.value, updated_by="tester")
    agent = registry.create_agent(
        system.id,
        agent_key=f"{system_key}-agent",
        name="Closure Agent",
        created_by="tester",
    )
    for status in (AgentStatus.UNDER_REVIEW, AgentStatus.APPROVED):
        registry.transition_agent(agent.id, status.value, updated_by="tester")
    version = registry.create_agent_version(agent.id, created_by="tester")
    registry.add_version_dependency(
        version.id, resource_type="mcp_server", resource_id=mcp.id
    )
    registry.add_version_dependency(
        version.id, resource_type="tool", resource_id=tool.id
    )
    for status in (AgentVersionStatus.UNDER_REVIEW, AgentVersionStatus.APPROVED):
        registry.transition_agent_version(version.id, status.value, updated_by="tester")
    identity = RuntimeIdentityService(db_session).create_runtime_identity(
        agent_id=agent.id,
        agent_version_id=version.id,
        name="Closure Runtime",
        created_by="tester",
    )
    issued = CredentialService(db_session).issue_credential(
        identity.id, created_by="tester"
    )
    delegation = DelegationService(db_session).create_delegation(
        delegator_type=DelegatorType.HUMAN.value,
        delegator_id="tester@example.com",
        delegate_runtime_identity_id=identity.id,
        scope={
            "mcp_server_ids": [str(mcp.id)],
            "tool_ids": [str(tool.id)],
        },
        created_by="tester",
    )
    return {
        "credential": issued.plaintext_secret,
        "identity": identity,
        "mcp": mcp,
        "tool": tool,
        "delegation": delegation,
    }


def test_hook_allow_pending_then_execution_result(db_session, test_organization):
    stack = _hook_runtime_stack(db_session)
    svc = ClientHookService(db_session)

    pre = svc.authorize_hook(
        NativeHookEvent(
            client_type="cursor",
            hook_event="beforeMCPExecution",
            payload={
                "command": "atlassian",
                "tool_name": "getAccessibleAtlassianResources",
                "tool_input": "{}",
                "conversation_id": "conv-1",
                "generation_id": "gen-1",
                "session_id": "sess-1",
                "cursor_version": "1.0.0",
                "model": "default",
                "user_email": "ops@example.com",
            },
        ),
        credential_secret=stack["credential"],
    )
    assert pre.allowed is True
    assert pre.receipt_id is not None

    receipt = (
        db_session.query(RuntimeEnforcementReceipt)
        .filter(RuntimeEnforcementReceipt.id == pre.receipt_id)
        .one()
    )
    assert receipt.execution_status == ExecutionStatus.PENDING_CLIENT_REPORT.value
    assert receipt.execution_source == ExecutionSource.CLIENT_REPORTED.value
    assert receipt.client_context["client_type"] == "cursor"
    assert "transcript_path" not in (receipt.client_context or {})

    detail = serialize_receipt_detail(receipt, db_session)
    assert detail["execution"]["status"] == ExecutionStatus.PENDING_CLIENT_REPORT.value
    assert (
        detail["assurance"]["verification_status"] == VerificationStatus.DECLARED.value
    )
    assert (
        detail["policy_evaluation"]["content_rule_enforcement"]["status"]
        == CONTENT_EVALUATOR_STATUS
    )
    assert (
        detail["policy_evaluation"]["content_rule_enforcement"]["reason"]
        == CONTENT_EVALUATOR_REASON
    )

    reported = RuntimeEnforcementService(db_session).report_execution_result(
        ClientExecutionReport(
            enforcement_receipt_id=pre.receipt_id,
            client_type="cursor",
            hook_event="afterMCPExecution",
            status=ExecutionStatus.SUCCEEDED.value,
            duration_ms=412,
            safe_result_metadata={"ok": True},
        ),
        runtime_identity_id=stack["identity"].id,
    )
    assert reported.execution_status == ExecutionStatus.SUCCEEDED.value
    assert reported.execution_source == ExecutionSource.CLIENT_REPORTED.value

    db_session.refresh(receipt)
    assert receipt.execution_status == ExecutionStatus.SUCCEEDED.value
    assert receipt.duration_ms == 412

    # Idempotent duplicate report
    again = RuntimeEnforcementService(db_session).report_execution_result(
        ClientExecutionReport(
            enforcement_receipt_id=pre.receipt_id,
            status=ExecutionStatus.SUCCEEDED.value,
        ),
        runtime_identity_id=stack["identity"].id,
    )
    assert again.human_explanation == "Idempotent execution report replay"


def test_execution_report_rejects_unknown_and_denied(db_session, test_organization):
    stack = _hook_runtime_stack(db_session, system_key="closure-deny")
    enforcement = RuntimeEnforcementService(db_session)

    unknown = enforcement.report_execution_result(
        ClientExecutionReport(
            enforcement_receipt_id=uuid4(),
            status=ExecutionStatus.SUCCEEDED.value,
        ),
        runtime_identity_id=stack["identity"].id,
    )
    assert unknown.reason_code == "EXECUTION_REPORT_UNKNOWN_RECEIPT"

    mismatch = enforcement.report_execution_result(
        ClientExecutionReport(
            enforcement_receipt_id=uuid4(),
            status=ExecutionStatus.SUCCEEDED.value,
        ),
        runtime_identity_id=uuid4(),
    )
    assert mismatch.reason_code == "EXECUTION_REPORT_UNKNOWN_RECEIPT"

    # Unknown tool → DENY path (no receipt overwrite possible without a receipt).
    blocked = ClientHookService(db_session).authorize_hook(
        NativeHookEvent(
            client_type="cursor",
            hook_event="beforeMCPExecution",
            payload={
                "command": "unknown-mcp",
                "tool_name": "unknown-tool",
                "tool_input": "{}",
            },
        ),
        credential_secret=stack["credential"],
    )
    assert blocked.allowed is False


def test_stale_pending_becomes_unknown(db_session, test_organization):
    stack = _hook_runtime_stack(db_session, system_key="closure-stale")
    svc = ClientHookService(db_session)
    pre = svc.authorize_hook(
        NativeHookEvent(
            client_type="cursor",
            hook_event="beforeMCPExecution",
            payload={
                "command": "atlassian",
                "tool_name": "getAccessibleAtlassianResources",
                "tool_input": "{}",
            },
        ),
        credential_secret=stack["credential"],
    )
    receipt = (
        db_session.query(RuntimeEnforcementReceipt)
        .filter(RuntimeEnforcementReceipt.id == pre.receipt_id)
        .one()
    )
    receipt.started_at = datetime.now(timezone.utc) - timedelta(hours=2)
    db_session.commit()

    count = RuntimeEnforcementService(db_session).mark_stale_pending_reports(
        older_than_seconds=3600
    )
    assert count == 1
    db_session.refresh(receipt)
    assert receipt.execution_status == ExecutionStatus.UNKNOWN.value


def test_content_evaluator_seam_not_active():
    result = get_content_policy_evaluator().evaluate(
        input_text="hello",
        output_text=None,
        applicable_rules=[],
    )
    assert result.status == CONTENT_EVALUATOR_STATUS
    assert result.reason == CONTENT_EVALUATOR_REASON
