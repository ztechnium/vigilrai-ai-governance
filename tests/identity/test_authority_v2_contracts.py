"""Authority V2 contracts: authentication proof, snapshot digest, org ownership."""

from __future__ import annotations

import uuid

import pytest

from rai_gateway.identity.authority_snapshot import (
    assert_snapshot_is_safe,
    build_authority_digest,
    snapshot_and_digest,
)
from rai_gateway.identity.domain import AuthenticationMethod, RuntimeIdentityStatus
from rai_gateway.identity.errors import AuthorityDeniedError
from rai_gateway.identity.resolver import RuntimeAuthorityResolver
from rai_gateway.identity.service import CredentialService, RuntimeIdentityService
from rai_gateway.registry.domain import AgentStatus, AgentVersionStatus, AISystemStatus
from rai_gateway.registry.service import RegistryService


@pytest.fixture()
def registry(db_session) -> RegistryService:
    return RegistryService(db_session)


@pytest.fixture()
def authority_stack(registry: RegistryService, db_session, test_organization) -> dict:
    suffix = uuid.uuid4().hex[:8]
    system = registry.create_ai_system(
        system_key=f"auth-sys-{suffix}",
        name="Authority System",
        created_by="tester",
    )
    for status in (AISystemStatus.UNDER_REVIEW, AISystemStatus.APPROVED):
        registry.transition_ai_system(system.id, status.value, updated_by="tester")

    agent = registry.create_agent(
        system.id,
        agent_key=f"auth-agent-{suffix}",
        name="Authority Agent",
        created_by="tester",
    )
    for status in (AgentStatus.UNDER_REVIEW, AgentStatus.APPROVED):
        registry.transition_agent(agent.id, status.value, updated_by="tester")

    version = registry.create_agent_version(agent.id, created_by="tester")
    registry.transition_agent_version(
        version.id, AgentVersionStatus.UNDER_REVIEW.value, updated_by="tester"
    )
    registry.transition_agent_version(
        version.id, AgentVersionStatus.APPROVED.value, updated_by="tester"
    )

    identity_service = RuntimeIdentityService(db_session)
    identity = identity_service.create_runtime_identity(
        agent_id=agent.id,
        agent_version_id=version.id,
        name="Production Runtime",
        created_by="tester",
        environment="production",
    )
    issued = CredentialService(db_session).issue_credential(
        identity.id, created_by="tester"
    )
    return {
        "organization": test_organization,
        "system": system,
        "agent": agent,
        "version": version,
        "identity": identity,
        "plaintext": issued.plaintext_secret,
        "credential": issued.credential,
    }


def test_api_key_resolution_sets_org_proof_and_digest(authority_stack, db_session):
    resolver = RuntimeAuthorityResolver(db_session)
    ctx = resolver.resolve_from_credential(authority_stack["plaintext"])

    assert ctx.authentication_proof is not None
    assert ctx.authentication_proof.method == AuthenticationMethod.API_KEY.value
    assert ctx.authentication_proof.credential_id == authority_stack["credential"].id
    assert ctx.authority_digest
    assert ctx.authority_snapshot is not None
    assert_snapshot_is_safe(ctx.authority_snapshot)
    assert "key_hash" not in str(ctx.authority_snapshot)
    assert ctx.authority_digest == build_authority_digest(ctx.authority_snapshot)


def test_authority_digest_is_deterministic(authority_stack, db_session):
    resolver = RuntimeAuthorityResolver(db_session)
    ctx1 = resolver.resolve_from_credential(authority_stack["plaintext"])
    snap_a, dig_a = snapshot_and_digest(ctx1)
    snap_b, dig_b = snapshot_and_digest(ctx1)
    assert snap_a == snap_b
    assert dig_a == dig_b
    assert dig_a == ctx1.authority_digest


def test_oidc_and_mtls_share_lifecycle_checks(authority_stack, db_session):
    identity = authority_stack["identity"]
    resolver = RuntimeAuthorityResolver(db_session)

    oidc_ctx = resolver.resolve_from_oidc(
        identity,
        issuer="https://issuer.example",
        subject_hash="sha256:abc",
    )
    assert oidc_ctx.authentication_proof.method == AuthenticationMethod.OIDC.value

    mtls_ctx = resolver.resolve_from_mtls(identity, subject_hash="sha256:cert")
    assert mtls_ctx.authentication_proof.method == AuthenticationMethod.MTLS.value

    RuntimeIdentityService(db_session).suspend_runtime_identity(
        identity.id,
        updated_by="tester",
    )
    db_session.refresh(identity)
    assert identity.status == RuntimeIdentityStatus.SUSPENDED.value

    with pytest.raises(AuthorityDeniedError) as oidc_exc:
        resolver.resolve_from_oidc(identity)
    assert oidc_exc.value.reason == "IDENTITY_SUSPENDED"

    with pytest.raises(AuthorityDeniedError) as mtls_exc:
        resolver.resolve_from_mtls(identity)
    assert mtls_exc.value.reason == "IDENTITY_SUSPENDED"

    with pytest.raises(AuthorityDeniedError) as api_exc:
        resolver.resolve_from_credential(authority_stack["plaintext"])
    assert api_exc.value.reason == "IDENTITY_SUSPENDED"


def test_snapshot_rejects_secret_keys():
    with pytest.raises(ValueError):
        assert_snapshot_is_safe({"authentication": {"key_hash": "abc"}})
