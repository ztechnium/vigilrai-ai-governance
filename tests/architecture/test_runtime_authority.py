"""Fail-closed architecture tests for WP2 runtime authority."""

from __future__ import annotations

import uuid

import pytest

from rai_gateway.identity.errors import AuthorityDeniedError
from rai_gateway.identity.resolver import RuntimeAuthorityResolver
from rai_gateway.identity.service import CredentialService, RuntimeIdentityService
from rai_gateway.registry.domain import AgentStatus, AgentVersionStatus, AISystemStatus
from rai_gateway.registry.service import RegistryService


@pytest.fixture()
def registry(db_session) -> RegistryService:
    return RegistryService(db_session)


@pytest.fixture()
def wp2_stack(registry: RegistryService, db_session, test_organization) -> dict:
    suffix = uuid.uuid4().hex[:8]
    system = registry.create_ai_system(
        system_key=f"arch-sys-{suffix}",
        name="Arch System",
        created_by="tester",
    )
    for status in (AISystemStatus.UNDER_REVIEW, AISystemStatus.APPROVED):
        registry.transition_ai_system(system.id, status.value, updated_by="tester")

    agent_a = registry.create_agent(
        system.id,
        agent_key=f"agent-a-{suffix}",
        name="Agent A",
        created_by="tester",
    )
    agent_b = registry.create_agent(
        system.id,
        agent_key=f"agent-b-{suffix}",
        name="Agent B",
        created_by="tester",
    )
    for agent in (agent_a, agent_b):
        for status in (AgentStatus.UNDER_REVIEW, AgentStatus.APPROVED):
            registry.transition_agent(agent.id, status.value, updated_by="tester")

    version_a = registry.create_agent_version(agent_a.id, created_by="tester")
    version_b = registry.create_agent_version(agent_b.id, created_by="tester")
    for version in (version_a, version_b):
        for status in (AgentVersionStatus.UNDER_REVIEW, AgentVersionStatus.APPROVED):
            registry.transition_agent_version(
                version.id, status.value, updated_by="tester"
            )

    identity_svc = RuntimeIdentityService(db_session)
    identity = identity_svc.create_runtime_identity(
        agent_id=agent_a.id,
        agent_version_id=version_a.id,
        name="Agent A Runtime",
        created_by="tester",
    )
    cred_svc = CredentialService(db_session)
    issued = cred_svc.issue_credential(identity.id, created_by="tester")

    return {
        "system": system,
        "agent_a": agent_a,
        "agent_b": agent_b,
        "version_a": version_a,
        "version_b": version_b,
        "identity": identity,
        "secret": issued.plaintext_secret,
    }


def test_caller_cannot_impersonate_another_agent(db_session, wp2_stack) -> None:
    resolver = RuntimeAuthorityResolver(db_session)
    with pytest.raises(AuthorityDeniedError) as exc:
        resolver.resolve_from_credential(
            wp2_stack["secret"],
            claimed_agent_id=wp2_stack["agent_b"].id,
        )
    assert exc.value.reason == "IDENTITY_VERSION_MISMATCH"


def test_caller_cannot_select_newer_version(db_session, wp2_stack, registry) -> None:
    v2 = registry.create_agent_version(
        wp2_stack["agent_a"].id, created_by="tester", change_summary="newer"
    )
    for status in (AgentVersionStatus.UNDER_REVIEW, AgentVersionStatus.APPROVED):
        registry.transition_agent_version(v2.id, status.value, updated_by="tester")

    resolver = RuntimeAuthorityResolver(db_session)
    with pytest.raises(AuthorityDeniedError) as exc:
        resolver.resolve_from_credential(
            wp2_stack["secret"],
            claimed_version_id=v2.id,
        )
    assert exc.value.reason == "IDENTITY_VERSION_MISMATCH"


def test_revoked_credential_denied(db_session, wp2_stack) -> None:
    cred_svc = CredentialService(db_session)
    creds = cred_svc.list_credentials(wp2_stack["identity"].id)
    cred_svc.revoke_credential(
        wp2_stack["identity"].id, creds[0].id, revoked_by="tester"
    )

    resolver = RuntimeAuthorityResolver(db_session)
    with pytest.raises(AuthorityDeniedError):
        resolver.resolve_from_credential(wp2_stack["secret"])


def test_suspended_system_denied(db_session, wp2_stack, registry) -> None:
    registry.transition_ai_system(
        wp2_stack["system"].id,
        AISystemStatus.SUSPENDED.value,
        updated_by="tester",
    )
    resolver = RuntimeAuthorityResolver(db_session)
    with pytest.raises(AuthorityDeniedError):
        resolver.resolve_from_credential(wp2_stack["secret"])
