"""PostgreSQL integration tests for WP2 runtime identity."""

from __future__ import annotations

import uuid

import pytest

from rai_gateway.identity.domain import (
    CredentialStatus,
    DelegatorType,
    RuntimeIdentityStatus,
)
from rai_gateway.identity.errors import AuthorityDeniedError, ScopeExceededError
from rai_gateway.identity.resolver import RuntimeAuthorityResolver
from rai_gateway.identity.service import (
    CredentialService,
    DelegationService,
    RuntimeIdentityService,
)
from rai_gateway.registry.domain import AgentStatus, AgentVersionStatus, AISystemStatus
from rai_gateway.registry.service import RegistryService


@pytest.fixture()
def registry(db_session) -> RegistryService:
    return RegistryService(db_session)


@pytest.fixture()
def approved_stack(registry: RegistryService, test_organization) -> dict:
    suffix = uuid.uuid4().hex[:8]
    system = registry.create_ai_system(
        system_key=f"wp2-sys-{suffix}",
        name="WP2 System",
        created_by="tester",
    )
    for status in (AISystemStatus.UNDER_REVIEW, AISystemStatus.APPROVED):
        registry.transition_ai_system(system.id, status.value, updated_by="tester")

    agent = registry.create_agent(
        system.id,
        agent_key=f"wp2-agent-{suffix}",
        name="WP2 Agent",
        created_by="tester",
    )
    for status in (AgentStatus.UNDER_REVIEW, AgentStatus.APPROVED):
        registry.transition_agent(agent.id, status.value, updated_by="tester")

    version = registry.create_agent_version(agent.id, created_by="tester")

    tool = registry.create_tool_resource(
        tool_key=f"get_supplier_{suffix}",
        name="Get Supplier",
    )
    registry.add_version_dependency(
        version.id,
        resource_type="tool",
        resource_id=tool.id,
    )

    for status in (AgentVersionStatus.UNDER_REVIEW, AgentVersionStatus.APPROVED):
        registry.transition_agent_version(version.id, status.value, updated_by="tester")

    return {"system": system, "agent": agent, "version": version, "tool": tool}


@pytest.fixture()
def identity_service(db_session) -> RuntimeIdentityService:
    return RuntimeIdentityService(db_session)


@pytest.fixture()
def runtime_identity(
    identity_service: RuntimeIdentityService, approved_stack
) -> object:
    return identity_service.create_runtime_identity(
        agent_id=approved_stack["agent"].id,
        agent_version_id=approved_stack["version"].id,
        name="Test Runtime",
        created_by="tester",
    )


def test_create_runtime_identity_binds_exact_version(
    identity_service: RuntimeIdentityService, approved_stack
) -> None:
    identity = identity_service.create_runtime_identity(
        agent_id=approved_stack["agent"].id,
        agent_version_id=approved_stack["version"].id,
        name="Procurement Runtime",
        created_by="tester",
        environment="production",
    )
    assert identity.agent_version_id == approved_stack["version"].id
    assert identity.status == RuntimeIdentityStatus.ACTIVE.value


def test_credential_issue_and_authenticate(
    db_session, identity_service: RuntimeIdentityService, runtime_identity
) -> None:
    cred_service = CredentialService(db_session)
    issued = cred_service.issue_credential(runtime_identity.id, created_by="tester")
    assert issued.plaintext_secret
    assert "rai_rt_" in issued.plaintext_secret

    # Plaintext must not be persisted
    assert issued.credential.key_hash != issued.plaintext_secret

    authenticated = cred_service.authenticate(issued.plaintext_secret)
    assert authenticated is not None
    assert authenticated.id == issued.credential.id


def test_revoked_credential_fails_authentication(
    db_session, identity_service: RuntimeIdentityService, runtime_identity
) -> None:
    cred_service = CredentialService(db_session)
    issued = cred_service.issue_credential(runtime_identity.id, created_by="tester")
    cred_service.revoke_credential(
        runtime_identity.id, issued.credential.id, revoked_by="tester"
    )
    assert cred_service.authenticate(issued.plaintext_secret) is None


def test_rotate_credential_revokes_old(
    db_session, identity_service: RuntimeIdentityService, runtime_identity
) -> None:
    cred_service = CredentialService(db_session)
    issued = cred_service.issue_credential(runtime_identity.id, created_by="tester")
    rotated = cred_service.rotate_credential(
        runtime_identity.id, issued.credential.id, rotated_by="tester"
    )

    assert cred_service.authenticate(issued.plaintext_secret) is None
    assert cred_service.authenticate(rotated.plaintext_secret) is not None
    old = cred_service.get_credential(runtime_identity.id, issued.credential.id)
    assert old.status == CredentialStatus.REVOKED.value


def test_suspend_identity_lifecycle(
    identity_service: RuntimeIdentityService, runtime_identity
) -> None:
    suspended = identity_service.suspend_runtime_identity(
        runtime_identity.id, updated_by="tester"
    )
    assert suspended.status == RuntimeIdentityStatus.SUSPENDED.value

    activated = identity_service.activate_runtime_identity(
        runtime_identity.id, updated_by="tester"
    )
    assert activated.status == RuntimeIdentityStatus.ACTIVE.value


def test_revoke_identity_revokes_credentials(
    db_session, identity_service: RuntimeIdentityService, runtime_identity
) -> None:
    cred_service = CredentialService(db_session)
    issued = cred_service.issue_credential(runtime_identity.id, created_by="tester")
    identity_service.revoke_runtime_identity(runtime_identity.id, updated_by="tester")

    cred = cred_service.get_credential(runtime_identity.id, issued.credential.id)
    assert cred.status == CredentialStatus.REVOKED.value


def test_delegation_creation_and_revocation(
    db_session,
    identity_service: RuntimeIdentityService,
    approved_stack,
    runtime_identity,
) -> None:
    delegation_service = DelegationService(db_session)
    grant = delegation_service.create_delegation(
        delegator_type=DelegatorType.HUMAN.value,
        delegator_id="mohamed@example.com",
        delegate_runtime_identity_id=runtime_identity.id,
        scope={"tool_ids": [str(approved_stack["tool"].id)]},
        created_by="tester",
    )
    assert grant.status == "ACTIVE"

    revoked = delegation_service.revoke_delegation(
        grant.id, revoked_by="tester", reason="test"
    )
    assert revoked.status == "REVOKED"


def test_update_delegation(
    db_session,
    identity_service: RuntimeIdentityService,
    approved_stack,
    runtime_identity,
) -> None:
    delegation_service = DelegationService(db_session)
    grant = delegation_service.create_delegation(
        delegator_type=DelegatorType.HUMAN.value,
        delegator_id="mohamed@example.com",
        delegate_runtime_identity_id=runtime_identity.id,
        scope={"tool_ids": [str(approved_stack["tool"].id)]},
        created_by="tester",
    )

    updated = delegation_service.update_delegation(
        grant.id,
        updated_by="tester",
        scope={"tool_ids": [str(approved_stack["tool"].id)]},
        change_reason="narrow tools",
    )
    assert updated.revision_number == 2
    assert updated.scope_digest is not None


def test_child_scope_cannot_exceed_parent(
    db_session,
    identity_service: RuntimeIdentityService,
    approved_stack,
    runtime_identity,
    registry: RegistryService,
) -> None:
    delegation_service = DelegationService(db_session)
    parent = delegation_service.create_delegation(
        delegator_type=DelegatorType.HUMAN.value,
        delegator_id="parent@example.com",
        delegate_runtime_identity_id=runtime_identity.id,
        scope={"tool_ids": [str(approved_stack["tool"].id)]},
        created_by="tester",
    )

    child_identity = identity_service.create_runtime_identity(
        agent_id=approved_stack["agent"].id,
        agent_version_id=approved_stack["version"].id,
        name="Child Runtime",
        created_by="tester",
    )

    extra_tool = registry.create_tool_resource(
        tool_key=f"delete_everything_{uuid.uuid4().hex[:8]}",
        name="Delete Everything",
    )

    with pytest.raises(ScopeExceededError):
        delegation_service.create_delegation(
            delegator_type=DelegatorType.RUNTIME_IDENTITY.value,
            delegator_id=str(runtime_identity.id),
            delegate_runtime_identity_id=child_identity.id,
            parent_delegation_id=parent.id,
            scope={
                "tool_ids": [
                    str(approved_stack["tool"].id),
                    str(extra_tool.id),
                ]
            },
            created_by="tester",
        )


def test_resolve_runtime_authority(
    db_session,
    identity_service: RuntimeIdentityService,
    runtime_identity,
    approved_stack,
) -> None:
    cred_service = CredentialService(db_session)
    issued = cred_service.issue_credential(runtime_identity.id, created_by="tester")

    resolver = RuntimeAuthorityResolver(db_session)
    ctx = resolver.resolve_from_credential(issued.plaintext_secret)
    assert ctx.runtime_identity.id == runtime_identity.id
    assert ctx.agent_version.id == approved_stack["version"].id
    assert ctx.eligibility is not None
    assert ctx.eligibility.eligible is True


def test_version_mismatch_denied(
    db_session,
    identity_service: RuntimeIdentityService,
    runtime_identity,
    approved_stack,
    registry,
) -> None:
    v2 = registry.create_agent_version(
        approved_stack["agent"].id, created_by="tester", change_summary="v2"
    )
    cred_service = CredentialService(db_session)
    issued = cred_service.issue_credential(runtime_identity.id, created_by="tester")

    resolver = RuntimeAuthorityResolver(db_session)
    with pytest.raises(AuthorityDeniedError) as exc_info:
        resolver.resolve_from_credential(
            issued.plaintext_secret,
            claimed_version_id=v2.id,
        )
    assert exc_info.value.reason == "IDENTITY_VERSION_MISMATCH"


def test_suspended_agent_denied(
    db_session,
    identity_service: RuntimeIdentityService,
    runtime_identity,
    approved_stack,
    registry,
) -> None:
    cred_service = CredentialService(db_session)
    issued = cred_service.issue_credential(runtime_identity.id, created_by="tester")

    registry.transition_agent(
        approved_stack["agent"].id,
        AgentStatus.SUSPENDED.value,
        updated_by="tester",
    )

    resolver = RuntimeAuthorityResolver(db_session)
    with pytest.raises(AuthorityDeniedError):
        resolver.resolve_from_credential(issued.plaintext_secret)
