"""PostgreSQL integration tests for WP3 durable approval."""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from rai_gateway.approval.authorization import ApproverContext
from rai_gateway.approval.consumption import ApprovalConsumptionService
from rai_gateway.approval.domain import (
    ActionTarget,
    ApprovalDenialCode,
    ApprovalStatus,
    ProposedAction,
)
from rai_gateway.approval.errors import ApprovalDeniedError
from rai_gateway.approval.service import ApprovalService
from rai_gateway.auth.passwords import hash_password
from rai_gateway.core.database import get_db
from rai_gateway.governance.domain import GovernanceRole, MembershipStatus
from rai_gateway.main import app
from rai_gateway.models.approval import ApprovalRequest
from rai_gateway.models.database import AdminCredential, UserAccount
from rai_gateway.models.governance import OrganizationMembership
from rai_gateway.registry.service import RegistryService
from rai_gateway.services.admin_console import _ensure_default_rbac_seed


@pytest.fixture()
def tenant_api_client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


def _seed_approver(db_session, org) -> dict:
    _ensure_default_rbac_seed(db_session)
    suffix = uuid.uuid4().hex[:8]
    email = f"approver-{suffix}@example.com"
    user_id = f"approver-{suffix}"
    db_session.add(
        UserAccount(
            user_id=user_id,
            email=email,
            name="Approver",
            status="active",
            email_verified_at=datetime.now(timezone.utc),
        )
    )
    db_session.flush()
    db_session.add(
        AdminCredential(
            email=email,
            user_id=user_id,
            password_hash=hash_password("SecurePass123!"),
            is_active=True,
        )
    )
    memberships = []
    for role in (
        GovernanceRole.ORGANIZATION_ADMIN.value,
        GovernanceRole.BUSINESS_APPROVER.value,
    ):
        m = OrganizationMembership(
            user_id=user_id,
            role=role,
            status=MembershipStatus.ACTIVE.value,
            created_by=user_id,
        )
        db_session.add(m)
        memberships.append(m)
    db_session.commit()
    for m in memberships:
        db_session.refresh(m)
    return {
        "email": email,
        "password": "SecurePass123!",
        "user_id": user_id,
        "memberships": memberships,
        "approve_membership_id": next(
            m.id
            for m in memberships
            if m.role == GovernanceRole.BUSINESS_APPROVER.value
        ),
    }


def _tenant_headers(client: TestClient, member: dict, org_id) -> dict[str, str]:
    login = client.post(
        "/v1/auth/login",
        json={"email": member["email"], "password": member["password"]},
    )
    assert login.status_code == 200, login.text
    return {
        "Authorization": f"Bearer {login.json()['access_token']}",
    }


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


def test_create_and_approve_request(db_session, approval_stack) -> None:
    request = _create_request(db_session, approval_stack)
    assert request.status == ApprovalStatus.PENDING.value
    assert request.action_digest

    approved = ApprovalService(db_session).approve(
        request.id,
        approver=ApproverContext(actor="manager", role="admin"),
    )
    assert approved.status == ApprovalStatus.APPROVED.value
    assert approved.decisions[-1].decided_by == "manager"


def test_self_approval_denied(db_session, approval_stack) -> None:
    request = _create_request(db_session, approval_stack)
    with pytest.raises(ApprovalDeniedError) as exc:
        ApprovalService(db_session).approve(
            request.id,
            approver=ApproverContext(actor="ahmed", role="admin"),
        )
    assert exc.value.reason == ApprovalDenialCode.SELF_APPROVAL_DENIED.value


def test_tool_outside_delegation_denied(db_session, approval_stack) -> None:
    authority = _authority(db_session, approval_stack)
    with pytest.raises(ApprovalDeniedError) as exc:
        ApprovalService(db_session).create_request(
            authority,
            integration_type="mcp",
            integration_id=approval_stack["mcp"].id,
            tool_id=approval_stack["extra_tool"].id,
            target_type="Customer",
            target_identifier="CUST-100",
            parameters={},
            created_by="tester",
            force=True,
        )
    assert exc.value.reason == ApprovalDenialCode.AUTHORITY_SCOPE_EXCEEDED.value


def test_tampering_denied_on_consume(db_session, approval_stack) -> None:
    request = _create_request(db_session, approval_stack)
    ApprovalService(db_session).approve(
        request.id,
        approver=ApproverContext(actor="manager", role="admin"),
    )
    consumption = ApprovalConsumptionService(db_session)
    authority = _authority(db_session, approval_stack)

    base_action = ProposedAction(
        ai_system_id=approval_stack["system"].id,
        agent_id=approval_stack["agent"].id,
        agent_version_id=approval_stack["version"].id,
        runtime_identity_id=approval_stack["identity"].id,
        delegation_id=approval_stack["delegation"].id,
        integration_type="mcp",
        integration_id=approval_stack["mcp"].id,
        tool_id=approval_stack["tool"].id,
        target=ActionTarget(type="Customer", id="CUST-100"),
        parameters={"status": "Active"},
    )

    ok = consumption.consume(authority, base_action)
    assert ok.allowed is True

    tampered = ProposedAction(
        ai_system_id=approval_stack["system"].id,
        agent_id=approval_stack["agent"].id,
        agent_version_id=approval_stack["version"].id,
        runtime_identity_id=approval_stack["identity"].id,
        delegation_id=approval_stack["delegation"].id,
        integration_type="mcp",
        integration_id=approval_stack["mcp"].id,
        tool_id=approval_stack["tool"].id,
        target=ActionTarget(type="Customer", id="CUST-100"),
        parameters={"status": "Inactive"},
    )
    denied = consumption.consume(authority, tampered)
    assert denied.allowed is False
    assert denied.reason in {
        ApprovalDenialCode.APPROVAL_NOT_FOUND,
        ApprovalDenialCode.APPROVAL_ALREADY_CONSUMED,
        ApprovalDenialCode.APPROVAL_ACTION_MISMATCH,
    }


def test_expired_approval_denied(db_session, approval_stack) -> None:
    request = _create_request(db_session, approval_stack)
    ApprovalService(db_session).approve(
        request.id,
        approver=ApproverContext(actor="manager", role="admin"),
    )
    request = db_session.get(ApprovalRequest, request.id)
    request.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.commit()
    consumption = ApprovalConsumptionService(db_session)
    authority = _authority(db_session, approval_stack)
    action = ProposedAction(
        ai_system_id=approval_stack["system"].id,
        agent_id=approval_stack["agent"].id,
        agent_version_id=approval_stack["version"].id,
        runtime_identity_id=approval_stack["identity"].id,
        delegation_id=approval_stack["delegation"].id,
        integration_type="mcp",
        integration_id=approval_stack["mcp"].id,
        tool_id=approval_stack["tool"].id,
        target=ActionTarget(type="Customer", id="CUST-100"),
        parameters={"status": "Active"},
    )
    result = consumption.consume(authority, action)
    assert result.allowed is False
    assert result.reason == ApprovalDenialCode.APPROVAL_EXPIRED


def test_concurrent_consumption_only_one_wins(
    db_session, approval_stack, db_engine
) -> None:
    from sqlalchemy.orm import sessionmaker

    request = _create_request(db_session, approval_stack)
    ApprovalService(db_session).approve(
        request.id,
        approver=ApproverContext(actor="manager", role="admin"),
    )

    results: list[bool] = []
    barrier = threading.Barrier(2)
    session_local = sessionmaker(bind=db_engine["engine"])

    def worker() -> None:
        local_db = session_local()
        try:
            barrier.wait(timeout=5)
            consumption = ApprovalConsumptionService(local_db)
            authority = consumption.resolve_authority_for_identity(
                approval_stack["identity"].id,
                approval_stack["delegation"].id,
            )
            action = ProposedAction(
                ai_system_id=approval_stack["system"].id,
                agent_id=approval_stack["agent"].id,
                agent_version_id=approval_stack["version"].id,
                runtime_identity_id=approval_stack["identity"].id,
                delegation_id=approval_stack["delegation"].id,
                integration_type="mcp",
                integration_id=approval_stack["mcp"].id,
                tool_id=approval_stack["tool"].id,
                target=ActionTarget(type="Customer", id="CUST-100"),
                parameters={"status": "Active"},
            )
            result = consumption.consume(authority, action)
            results.append(result.allowed)
        finally:
            local_db.close()

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert results.count(True) == 1
    assert results.count(False) == 1


def test_suspended_agent_denies_consumption(
    db_session, approval_stack, registry
) -> None:
    consumption = ApprovalConsumptionService(db_session)
    authority = consumption.resolve_authority_for_identity(
        approval_stack["identity"].id,
        approval_stack["delegation"].id,
    )
    request = _create_request(db_session, approval_stack)
    ApprovalService(db_session).approve(
        request.id,
        approver=ApproverContext(actor="manager", role="admin"),
    )
    registry.transition_agent(
        approval_stack["agent"].id,
        "SUSPENDED",
        updated_by="tester",
    )
    db_session.expire_all()
    action = ProposedAction(
        ai_system_id=approval_stack["system"].id,
        agent_id=approval_stack["agent"].id,
        agent_version_id=approval_stack["version"].id,
        runtime_identity_id=approval_stack["identity"].id,
        delegation_id=approval_stack["delegation"].id,
        integration_type="mcp",
        integration_id=approval_stack["mcp"].id,
        tool_id=approval_stack["tool"].id,
        target=ActionTarget(type="Customer", id="CUST-100"),
        parameters={"status": "Active"},
    )
    result = consumption.consume(authority, action)
    assert result.allowed is False


def test_approval_api_flow(
    tenant_api_client: TestClient,
    db_session,
    approval_stack,
    test_organization,
) -> None:
    member = _seed_approver(db_session, test_organization)
    headers = _tenant_headers(tenant_api_client, member, test_organization.id)

    create = tenant_api_client.post(
        "/v1/approval-requests",
        headers=headers,
        json={
            "runtime_identity_id": str(approval_stack["identity"].id),
            "delegation_id": str(approval_stack["delegation"].id),
            "integration_type": "mcp",
            "integration_id": str(approval_stack["mcp"].id),
            "tool_id": str(approval_stack["tool"].id),
            "target_type": "Customer",
            "target_identifier": "CUST-100",
            "parameters": {"status": "Active"},
            "business_reason": "Customer update",
            "force": True,
        },
    )
    assert create.status_code == 201, create.text
    request_id = create.json()["id"]

    approve = tenant_api_client.post(
        f"/v1/approval-requests/{request_id}/approve",
        headers=headers,
        json={
            "acting_membership_id": str(member["approve_membership_id"]),
            "decision_reason": "Looks good",
        },
    )
    assert approve.status_code == 200, approve.text
    assert approve.json()["status"] == "APPROVED"

    consume = tenant_api_client.post(
        "/v1/approval-requests/consume",
        headers=headers,
        json={
            "runtime_identity_id": str(approval_stack["identity"].id),
            "delegation_id": str(approval_stack["delegation"].id),
            "integration_type": "mcp",
            "integration_id": str(approval_stack["mcp"].id),
            "tool_id": str(approval_stack["tool"].id),
            "target_type": "Customer",
            "target_identifier": "CUST-100",
            "parameters": {"status": "Active"},
        },
    )
    assert consume.status_code == 200
    assert consume.json()["allowed"] is True


def test_create_approval_retired_system_returns_403(
    tenant_api_client: TestClient,
    db_session,
    approval_stack,
    registry: RegistryService,
    test_organization,
) -> None:
    from rai_gateway.registry.domain import AISystemStatus

    member = _seed_approver(db_session, test_organization)
    headers = _tenant_headers(tenant_api_client, member, test_organization.id)

    registry.transition_ai_system(
        approval_stack["system"].id,
        AISystemStatus.RETIRED.value,
        updated_by="tester",
    )
    response = tenant_api_client.post(
        "/v1/approval-requests",
        headers=headers,
        json={
            "runtime_identity_id": str(approval_stack["identity"].id),
            "delegation_id": str(approval_stack["delegation"].id),
            "integration_type": "mcp",
            "integration_id": str(approval_stack["mcp"].id),
            "tool_id": str(approval_stack["tool"].id),
            "target_type": "Customer",
            "target_identifier": "CUST-100",
            "parameters": {"status": "Active"},
            "force": True,
        },
    )
    assert response.status_code == 403, response.text
    body = response.json()
    assert "RETIRED" in body["detail"]["message"]
