"""Runtime authority resolution for WP2 / Authority V2."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from rai_gateway.identity.authority_snapshot import (
    proof_from_api_key_credential,
    proof_from_mtls,
    proof_from_oidc,
    snapshot_and_digest,
)
from rai_gateway.identity.domain import (
    AuthorityDenialReason,
    DelegationScope,
    RuntimeAuthenticationProof,
    RuntimeIdentityStatus,
)
from rai_gateway.identity.errors import AuthorityDeniedError
from rai_gateway.identity.service import CredentialService, DelegationService
from rai_gateway.models.identity import (
    AgentRuntimeIdentity,
    RuntimeCredential,
)
from rai_gateway.models.registry import Agent, AgentVersion, AISystem
from rai_gateway.registry.eligibility import EligibilityResult, EligibilityService


@dataclass
class DelegationChainEntry:
    delegation_id: UUID
    delegator_type: str
    delegator_id: str
    scope: dict[str, Any]
    revision: int | None = None
    stored_status: str | None = None
    scope_digest: str | None = None


@dataclass
class RuntimeAuthorityContext:
    runtime_identity: AgentRuntimeIdentity
    ai_system: AISystem
    agent: Agent
    agent_version: AgentVersion
    credential: RuntimeCredential | None
    initiating_principal: str | None
    authentication_proof: RuntimeAuthenticationProof | None = None
    authority_digest: str | None = None
    authority_snapshot: dict[str, Any] | None = None
    delegation_chain: list[DelegationChainEntry] = field(default_factory=list)
    effective_scope: DelegationScope = field(default_factory=DelegationScope)
    eligibility: EligibilityResult | None = None


@dataclass
class AuthenticatedRuntimeContext:
    runtime_identity: AgentRuntimeIdentity
    credential: RuntimeCredential | None = None
    authentication_proof: RuntimeAuthenticationProof | None = None
    claimed_agent_id: UUID | None = None
    claimed_version_id: UUID | None = None
    delegation_id: UUID | None = None


class RuntimeAuthorityResolver:
    """Central fail-closed runtime authority resolution."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._credential_service = CredentialService(db)
        self._delegation_service = DelegationService(db)
        self._eligibility = EligibilityService(db)

    def authenticate_credential(
        self, plaintext_secret: str
    ) -> RuntimeCredential | None:
        return self._credential_service.authenticate(plaintext_secret)

    def resolve(
        self, auth_context: AuthenticatedRuntimeContext
    ) -> RuntimeAuthorityContext:
        identity = auth_context.runtime_identity
        credential = auth_context.credential
        self._check_identity_lifecycle(identity)
        if (
            auth_context.claimed_agent_id
            and auth_context.claimed_agent_id != identity.agent_id
        ):
            raise AuthorityDeniedError(
                AuthorityDenialReason.IDENTITY_VERSION_MISMATCH.value,
                "Authenticated identity does not match claimed agent",
            )
        if (
            auth_context.claimed_version_id
            and auth_context.claimed_version_id != identity.agent_version_id
        ):
            raise AuthorityDeniedError(
                AuthorityDenialReason.IDENTITY_VERSION_MISMATCH.value,
                "Authenticated identity does not match claimed agent version",
            )
        agent = self._db.query(Agent).filter(Agent.id == identity.agent_id).first()
        version = (
            self._db.query(AgentVersion)
            .filter(AgentVersion.id == identity.agent_version_id)
            .first()
        )
        if not agent or not version:
            raise AuthorityDeniedError(
                AuthorityDenialReason.AGENT_VERSION_INELIGIBLE.value,
                "Bound agent version records are missing",
            )
        system = (
            self._db.query(AISystem).filter(AISystem.id == agent.ai_system_id).first()
        )
        if not system:
            raise AuthorityDeniedError(
                AuthorityDenialReason.AGENT_VERSION_INELIGIBLE.value,
                "AI system record is missing",
            )
        eligibility = self._eligibility.evaluate(
            system_id=system.id,
            agent_id=agent.id,
            version_id=version.id,
        )
        if not eligibility.eligible:
            reason = self._map_eligibility_reason(eligibility.reason)
            raise AuthorityDeniedError(reason, eligibility.reason)
        chain_entries: list[DelegationChainEntry] = []
        effective_scope = DelegationScope()
        initiating_principal: str | None = None
        if auth_context.delegation_id:
            chain = self._delegation_service.resolve_active_chain(
                auth_context.delegation_id
            )
            leaf = chain[-1]
            if leaf.delegate_runtime_identity_id != identity.id:
                raise AuthorityDeniedError(
                    AuthorityDenialReason.BROKEN_DELEGATION_CHAIN.value,
                    "Delegation does not apply to authenticated runtime identity",
                )
            effective_scope = DelegationScope()
            for grant in chain:
                chain_entries.append(
                    DelegationChainEntry(
                        delegation_id=grant.id,
                        delegator_type=grant.delegator_type,
                        delegator_id=grant.delegator_id,
                        scope=grant.scope or {},
                        revision=getattr(grant, "revision_number", None),
                        stored_status=grant.status,
                        scope_digest=getattr(grant, "scope_digest", None),
                    )
                )
                effective_scope = effective_scope.intersect(
                    DelegationScope.from_dict(grant.scope)
                )
            initiating_principal = chain[0].delegator_id
            # Intersect with version-declared resources for canonical effective scope.
            from rai_gateway.identity.version_resources import (
                load_version_resource_catalog,
            )

            catalog = load_version_resource_catalog(
                self._db,
                version.id,
            )
            effective_scope = effective_scope.resolve_against_catalog(
                model_ids=catalog.model_ids,
                data_source_ids=catalog.data_source_ids,
                mcp_server_ids=catalog.mcp_server_ids,
                tool_ids=catalog.tool_ids,
            )
        proof = auth_context.authentication_proof
        if proof is None and credential is not None:
            proof = proof_from_api_key_credential(credential.id)
        ctx = RuntimeAuthorityContext(
            runtime_identity=identity,
            ai_system=system,
            agent=agent,
            agent_version=version,
            credential=credential,
            initiating_principal=initiating_principal,
            authentication_proof=proof,
            delegation_chain=chain_entries,
            effective_scope=effective_scope,
            eligibility=eligibility,
        )
        snapshot, digest = snapshot_and_digest(ctx)
        ctx.authority_snapshot = snapshot
        ctx.authority_digest = digest
        return ctx

    def resolve_from_credential(
        self,
        plaintext_secret: str,
        *,
        claimed_agent_id: UUID | None = None,
        claimed_version_id: UUID | None = None,
        delegation_id: UUID | None = None,
    ) -> RuntimeAuthorityContext:
        credential = self._credential_service.authenticate(plaintext_secret)
        if not credential:
            raise AuthorityDeniedError(
                AuthorityDenialReason.INVALID_CREDENTIAL.value,
                "Invalid or revoked runtime credential",
            )
        identity = credential.runtime_identity
        if not identity:
            raise AuthorityDeniedError(
                AuthorityDenialReason.UNKNOWN_IDENTITY.value,
                "Runtime identity not found for credential",
            )
        return self.resolve(
            AuthenticatedRuntimeContext(
                credential=credential,
                runtime_identity=identity,
                authentication_proof=proof_from_api_key_credential(credential.id),
                claimed_agent_id=claimed_agent_id,
                claimed_version_id=claimed_version_id,
                delegation_id=delegation_id,
            )
        )

    def resolve_from_oidc(
        self,
        identity: AgentRuntimeIdentity,
        *,
        binding_id: UUID | None = None,
        issuer: str | None = None,
        subject_hash: str | None = None,
        acr: str | None = None,
        amr: list[str] | None = None,
        auth_time: Any = None,
        claimed_agent_id: UUID | None = None,
        claimed_version_id: UUID | None = None,
        delegation_id: UUID | None = None,
    ) -> RuntimeAuthorityContext:
        """OIDC path shares the same lifecycle + eligibility resolution as API keys."""
        return self.resolve(
            AuthenticatedRuntimeContext(
                runtime_identity=identity,
                credential=None,
                authentication_proof=proof_from_oidc(
                    binding_id=binding_id,
                    issuer=issuer,
                    subject_hash=subject_hash,
                    acr=acr,
                    amr=amr,
                    auth_time=auth_time,
                ),
                claimed_agent_id=claimed_agent_id,
                claimed_version_id=claimed_version_id,
                delegation_id=delegation_id,
            )
        )

    def resolve_from_mtls(
        self,
        identity: AgentRuntimeIdentity,
        *,
        binding_id: UUID | None = None,
        subject_hash: str | None = None,
        claimed_agent_id: UUID | None = None,
        claimed_version_id: UUID | None = None,
        delegation_id: UUID | None = None,
    ) -> RuntimeAuthorityContext:
        """mTLS path shares the same lifecycle + eligibility resolution as API keys."""
        return self.resolve(
            AuthenticatedRuntimeContext(
                runtime_identity=identity,
                credential=None,
                authentication_proof=proof_from_mtls(
                    binding_id=binding_id,
                    subject_hash=subject_hash,
                ),
                claimed_agent_id=claimed_agent_id,
                claimed_version_id=claimed_version_id,
                delegation_id=delegation_id,
            )
        )

    def _check_identity_lifecycle(self, identity: AgentRuntimeIdentity) -> None:
        from datetime import datetime, timezone

        if identity.status == RuntimeIdentityStatus.SUSPENDED.value:
            raise AuthorityDeniedError(
                AuthorityDenialReason.IDENTITY_SUSPENDED.value,
                "Runtime identity is suspended",
            )
        if identity.status == RuntimeIdentityStatus.REVOKED.value:
            raise AuthorityDeniedError(
                AuthorityDenialReason.IDENTITY_REVOKED.value,
                "Runtime identity is revoked",
            )
        if identity.status == RuntimeIdentityStatus.EXPIRED.value:
            raise AuthorityDeniedError(
                AuthorityDenialReason.IDENTITY_EXPIRED.value,
                "Runtime identity is expired",
            )
        if identity.expires_at and identity.expires_at <= datetime.now(timezone.utc):
            identity.status = RuntimeIdentityStatus.EXPIRED.value
            self._db.commit()
            raise AuthorityDeniedError(
                AuthorityDenialReason.IDENTITY_EXPIRED.value,
                "Runtime identity has expired",
            )

    def _map_eligibility_reason(self, reason: str) -> str:
        lowered = reason.lower()
        if "agent status" in lowered:
            return AuthorityDenialReason.AGENT_SUSPENDED.value
        if "system status" in lowered:
            return AuthorityDenialReason.AGENT_VERSION_INELIGIBLE.value
        if "version status" in lowered:
            return AuthorityDenialReason.AGENT_VERSION_INELIGIBLE.value
        return AuthorityDenialReason.AGENT_VERSION_INELIGIBLE.value
