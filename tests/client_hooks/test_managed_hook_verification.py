"""Managed hook attestation — LOCAL stays DECLARED; TEAM/MDM need hash match."""

from __future__ import annotations

import pytest

from rai_gateway.client_hooks.service import ClientIntegrationRepository
from rai_gateway.runtime_enforcement.domain import (
    DeploymentControl,
    VerificationStatus,
)


def test_local_hook_cannot_self_promote_to_verified(db_session, runtime_stack):
    repo = ClientIntegrationRepository(db_session)
    identity_id = runtime_stack["identity"].id
    row = repo.record_heartbeat(
        identity_id,
        "cursor",
        client_version="1.0",
        bridge_version="0.1.0",
        protocol_version="1",
        deployment_control=DeploymentControl.LOCAL_HOOK.value,
        verification_status=VerificationStatus.VERIFIED.value,
        observed_bridge_hash="abc123hash",
    )
    assert row.deployment_control == DeploymentControl.LOCAL_HOOK.value
    assert row.verification_status == VerificationStatus.DECLARED.value


def test_unregistered_managed_claim_demoted_to_local(db_session, runtime_stack):
    repo = ClientIntegrationRepository(db_session)
    identity_id = runtime_stack["identity"].id
    row = repo.record_heartbeat(
        identity_id,
        "cursor",
        client_version="1.0",
        bridge_version="0.1.0",
        protocol_version="1",
        deployment_control=DeploymentControl.TEAM_MANAGED_HOOK.value,
        verification_status=VerificationStatus.DECLARED.value,
        observed_bridge_hash="deadbeef01",
    )
    assert row.deployment_control == DeploymentControl.LOCAL_HOOK.value
    assert row.verification_status != VerificationStatus.VERIFIED.value
    assert row.expected_bridge_hash is None


def test_managed_profile_attestation_verified_on_hash_match(db_session, runtime_stack):
    repo = ClientIntegrationRepository(db_session)
    identity_id = runtime_stack["identity"].id
    expected = "sha256:managed-bridge-aaaaaaaa"
    repo.register_managed_profile(
        identity_id,
        "cursor",
        deployment_control=DeploymentControl.TEAM_MANAGED_HOOK.value,
        expected_bridge_hash=expected,
        expected_bridge_version="0.1.0",
        managed_profile_key="team-cursor-v1",
    )
    row = repo.record_heartbeat(
        identity_id,
        "cursor",
        client_version="1.0",
        bridge_version="0.1.0",
        protocol_version="1",
        deployment_control=DeploymentControl.TEAM_MANAGED_HOOK.value,
        verification_status=VerificationStatus.DECLARED.value,
        observed_bridge_hash=expected,
    )
    assert row.deployment_control == DeploymentControl.TEAM_MANAGED_HOOK.value
    assert row.verification_status == VerificationStatus.VERIFIED.value
    assert row.last_attested_at is not None
    assert row.observed_bridge_hash == expected


def test_managed_profile_hash_mismatch_stays_declared(db_session, runtime_stack):
    repo = ClientIntegrationRepository(db_session)
    identity_id = runtime_stack["identity"].id
    repo.register_managed_profile(
        identity_id,
        "claude_code",
        deployment_control=DeploymentControl.MDM_MANAGED.value,
        expected_bridge_hash="sha256:expected-bbbbbbbb",
        expected_bridge_version="0.2.0",
    )
    row = repo.record_heartbeat(
        identity_id,
        "claude_code",
        client_version="2.0",
        bridge_version="0.2.0",
        protocol_version="1",
        deployment_control=DeploymentControl.MDM_MANAGED.value,
        verification_status=VerificationStatus.VERIFIED.value,
        observed_bridge_hash="sha256:wrong-cccccccc",
    )
    assert row.deployment_control == DeploymentControl.MDM_MANAGED.value
    assert row.verification_status == VerificationStatus.DECLARED.value


def test_managed_profile_rejects_local_control(db_session, runtime_stack):
    repo = ClientIntegrationRepository(db_session)
    with pytest.raises(ValueError, match="managed"):
        repo.register_managed_profile(
            runtime_stack["identity"].id,
            "cursor",
            deployment_control=DeploymentControl.LOCAL_HOOK.value,
            expected_bridge_hash="sha256:not-enough",
        )
