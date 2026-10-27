"""SDK data-access authorize — masking before model receives data."""

from __future__ import annotations

import uuid
from uuid import UUID

import pytest

from rai_gateway.data_access.domain import DataAccessDecisionType
from rai_gateway.governance.domain import GovernanceRole, MembershipStatus
from rai_gateway.governance.service import GovernanceService
from rai_gateway.identity.domain import DelegatorType
from rai_gateway.identity.service import (
    CredentialService,
    DelegationService,
    RuntimeIdentityService,
)
from rai_gateway.registry.domain import AgentStatus, AgentVersionStatus, AISystemStatus
from rai_gateway.registry.service import RegistryService
from rai_gateway.runtime_enforcement.domain import EnforcementMode
from rai_gateway.sdk.service import SdkService


@pytest.fixture()
def data_access_sdk_stack(db_session) -> dict:
    gov = GovernanceService(db_session)
    registry = RegistryService(db_session)
    suffix = uuid.uuid4().hex[:8]
    gov.create_membership(
        user_id=f"admin-{suffix}",
        role=GovernanceRole.ORGANIZATION_ADMIN.value,
        created_by="tester",
        status=MembershipStatus.ACTIVE.value,
    )

    system = registry.create_ai_system(
        system_key=f"da-sys-{suffix}",
        name="Data Access AI",
        created_by="tester",
    )
    for status in (AISystemStatus.UNDER_REVIEW, AISystemStatus.APPROVED):
        registry.transition_ai_system(system.id, status.value, updated_by="tester")
    gov.link_ai_system(system.id, "tester")

    agent = registry.create_agent(
        system.id,
        agent_key=f"da-agent-{suffix}",
        name="DA Agent",
        created_by="tester",
    )
    for status in (AgentStatus.UNDER_REVIEW, AgentStatus.APPROVED):
        registry.transition_agent(agent.id, status.value, updated_by="tester")

    version = registry.create_agent_version(agent.id, created_by="tester")
    for status in (AgentVersionStatus.UNDER_REVIEW, AgentVersionStatus.APPROVED):
        registry.transition_agent_version(version.id, status.value, updated_by="tester")

    identity = RuntimeIdentityService(db_session).create_runtime_identity(
        agent_id=agent.id,
        agent_version_id=version.id,
        name="DA Runtime",
        created_by="tester",
    )
    issued = CredentialService(db_session).issue_credential(
        identity.id, created_by="tester"
    )
    DelegationService(db_session).create_delegation(
        delegator_type=DelegatorType.HUMAN.value,
        delegator_id="owner",
        delegate_runtime_identity_id=identity.id,
        scope={},
        created_by="tester",
    )

    svc = SdkService(db_session)
    integration = svc.create_integration(
        integration_key=f"da-sdk-{suffix}",
        name="DA SDK",
        runtime_identity_id=identity.id,
        created_by="tester",
        enforcement_mode=EnforcementMode.HOOK_ENFORCED.value,
        fail_closed=True,
    )
    return {
        "svc": svc,
        "credential_secret": issued.plaintext_secret,
        "integration": integration,
    }


def test_sdk_authorize_data_access_masks_before_model(data_access_sdk_stack):
    svc: SdkService = data_access_sdk_stack["svc"]
    auth = svc.authenticate(
        secret=data_access_sdk_stack["credential_secret"], token=None
    )
    session = svc.start_session(
        auth,
        integration_id=UUID(data_access_sdk_stack["integration"]["id"]),
        principal="agent-bot",
    )
    session_id = UUID(session["rai_session_id"])

    denied = svc.authorize_data_access(
        auth,
        session_id=session_id,
        resource="customers",
        fields=["national_id", "email", "city"],
        purpose="sales_outreach",
        payload={
            "national_id": "29801011234567",
            "email": "a@example.com",
            "city": "Cairo",
        },
    )
    assert denied["decision"] == DataAccessDecisionType.DENY.value
    assert denied["transformed_payload"] is None
    assert "national_id" in denied["denied_fields"]
    assert denied["receipt_id"] is not None

    # Denied data-access should still project onto the trajectory Investigation feed.
    from rai_gateway.evidence.domain import EvidenceEventType
    from rai_gateway.models.evidence import EvidenceEvent
    from rai_gateway.models.productization import SdkSession

    session_row = (
        data_access_sdk_stack["svc"]
        ._db.query(SdkSession)
        .filter(SdkSession.id == session_id)
        .first()
    )
    assert session_row is not None and session_row.trajectory_id is not None
    events = (
        data_access_sdk_stack["svc"]
        ._db.query(EvidenceEvent)
        .filter(EvidenceEvent.trajectory_id == session_row.trajectory_id)
        .all()
    )
    assert any(
        event.event_type == EvidenceEventType.DATA_ACCESS_DENIED.value
        for event in events
    )

    masked = svc.authorize_data_access(
        auth,
        session_id=session_id,
        resource="customers",
        fields=["national_id", "full_name"],
        purpose="kyc",
        payload={
            "national_id": "29801011234567",
            "full_name": "Ada Lovelace",
        },
    )
    assert masked["decision"] == DataAccessDecisionType.MASK.value
    assert masked["allowed"] is True
    transformed = masked["transformed_payload"]
    assert isinstance(transformed, dict)
    assert transformed["national_id"] != "29801011234567"
    assert "29801011234567" not in str(transformed)


def test_sdk_data_access_observe_only_passthrough(db_session):
    gov = GovernanceService(db_session)
    registry = RegistryService(db_session)
    suffix = uuid.uuid4().hex[:8]
    system = registry.create_ai_system(
        system_key=f"obs-sys-{suffix}",
        name="Obs AI",
        created_by="tester",
    )
    for status in (AISystemStatus.UNDER_REVIEW, AISystemStatus.APPROVED):
        registry.transition_ai_system(system.id, status.value, updated_by="tester")
    gov.link_ai_system(system.id, "tester")
    agent = registry.create_agent(
        system.id,
        agent_key=f"obs-agent-{suffix}",
        name="Obs Agent",
        created_by="tester",
    )
    for status in (AgentStatus.UNDER_REVIEW, AgentStatus.APPROVED):
        registry.transition_agent(agent.id, status.value, updated_by="tester")
    version = registry.create_agent_version(agent.id, created_by="tester")
    for status in (AgentVersionStatus.UNDER_REVIEW, AgentVersionStatus.APPROVED):
        registry.transition_agent_version(version.id, status.value, updated_by="tester")
    identity = RuntimeIdentityService(db_session).create_runtime_identity(
        agent_id=agent.id,
        agent_version_id=version.id,
        name="Obs Runtime",
        created_by="tester",
    )
    issued = CredentialService(db_session).issue_credential(
        identity.id, created_by="tester"
    )
    svc = SdkService(db_session)
    integration = svc.create_integration(
        integration_key=f"obs-sdk-{suffix}",
        name="Obs SDK",
        runtime_identity_id=identity.id,
        created_by="tester",
        enforcement_mode=EnforcementMode.OBSERVE_ONLY.value,
        fail_closed=False,
    )
    auth = svc.authenticate(secret=issued.plaintext_secret, token=None)
    session = svc.start_session(auth, integration_id=UUID(integration["id"]))
    payload = {"national_id": "29801011234567"}
    result = svc.authorize_data_access(
        auth,
        session_id=UUID(session["rai_session_id"]),
        resource="customers",
        fields=["national_id"],
        payload=payload,
    )
    assert result["decision"] == "MONITOR"
    assert result["transformed_payload"] == payload
