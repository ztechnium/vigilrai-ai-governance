"""WP2 runtime identity, credential, and delegation services."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from rai_gateway.identity.authority_snapshot import digest_payload
from rai_gateway.identity.domain import (
    MAX_DELEGATION_DEPTH,
    RUNTIME_IDENTITY_TRANSITIONS,
    CredentialStatus,
    CredentialType,
    DelegationChangeType,
    DelegationScope,
    DelegationStatus,
    EffectiveDelegationStatus,
    IdentityType,
    RuntimeIdentityStatus,
)
from rai_gateway.identity.errors import (
    InvalidTransitionError,
    NotFoundError,
    RelationshipError,
    ScopeExceededError,
)
from rai_gateway.identity.version_resources import (
    VersionResourceCatalog,
    load_version_resource_catalog,
)
from rai_gateway.models.identity import (
    AgentRuntimeIdentity,
    DelegationGrant,
    DelegationRevision,
    RuntimeCredential,
)
from rai_gateway.models.registry import Agent, AgentVersion, AISystem
from rai_gateway.registry.domain import validate_lifecycle_transition


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _owned_identity_query(db: Session):
    """Runtime identities joined to their agent and AI system."""
    query = (
        db.query(AgentRuntimeIdentity)
        .join(Agent, AgentRuntimeIdentity.agent_id == Agent.id)
        .join(AISystem, Agent.ai_system_id == AISystem.id)
    )
    return query


def _owned_delegation_query(db: Session):
    """Delegation grants joined through the delegate identity to an AI system."""
    query = (
        db.query(DelegationGrant)
        .join(
            AgentRuntimeIdentity,
            DelegationGrant.delegate_runtime_identity_id == AgentRuntimeIdentity.id,
        )
        .join(Agent, AgentRuntimeIdentity.agent_id == Agent.id)
        .join(AISystem, Agent.ai_system_id == AISystem.id)
    )
    return query


@dataclass
class IssuedCredential:
    credential: RuntimeCredential
    plaintext_secret: str


class RuntimeIdentityService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def _get_agent_in_tenant(self, agent_id: UUID) -> Agent:
        query = self._db.query(Agent).filter(Agent.id == agent_id)
        agent = query.first()
        if not agent:
            raise NotFoundError("Agent", str(agent_id))
        return agent

    def create_runtime_identity(
        self,
        *,
        agent_id: UUID,
        agent_version_id: UUID,
        name: str,
        created_by: str,
        identity_type: str = IdentityType.RAI_API_CREDENTIAL.value,
        auth_provider: str | None = None,
        external_subject: str | None = None,
        environment: str | None = None,
        expires_at: datetime | None = None,
    ) -> AgentRuntimeIdentity:
        agent = self._get_agent_in_tenant(agent_id)
        version = (
            self._db.query(AgentVersion)
            .filter(
                AgentVersion.id == agent_version_id,
                AgentVersion.agent_id == agent_id,
            )
            .first()
        )
        if not version:
            raise RelationshipError(
                "Agent version does not belong to the specified agent"
            )
        system = (
            self._db.query(AISystem).filter(AISystem.id == agent.ai_system_id).first()
        )
        if not system:
            raise RelationshipError("AI system record is missing for agent")
        identity_key = f"rti_{uuid.uuid4().hex[:16]}"
        identity = AgentRuntimeIdentity(
            identity_key=identity_key,
            agent_id=agent_id,
            agent_version_id=agent_version_id,
            name=name,
            identity_type=identity_type,
            auth_provider=auth_provider,
            external_subject=external_subject,
            environment=environment,
            status=RuntimeIdentityStatus.ACTIVE.value,
            created_by=created_by,
            expires_at=expires_at,
        )
        self._db.add(identity)
        self._db.commit()
        self._db.refresh(identity)
        return identity

    def get_runtime_identity(self, identity_id: UUID) -> AgentRuntimeIdentity:
        identity = (
            _owned_identity_query(self._db)
            .filter(AgentRuntimeIdentity.id == identity_id)
            .first()
        )
        if not identity:
            raise NotFoundError("Runtime identity", str(identity_id))
        return identity

    def list_runtime_identities(
        self,
        *,
        agent_id: UUID | None = None,
        agent_version_id: UUID | None = None,
        status: str | None = None,
        environment: str | None = None,
        search: str | None = None,
    ) -> list[AgentRuntimeIdentity]:
        query = _owned_identity_query(self._db)
        if agent_id:
            query = query.filter(AgentRuntimeIdentity.agent_id == agent_id)
        if agent_version_id:
            query = query.filter(
                AgentRuntimeIdentity.agent_version_id == agent_version_id
            )
        if status:
            query = query.filter(AgentRuntimeIdentity.status == status)
        if environment:
            query = query.filter(AgentRuntimeIdentity.environment == environment)
        if search:
            pattern = f"%{search}%"
            query = query.filter(
                (AgentRuntimeIdentity.name.ilike(pattern))
                | (AgentRuntimeIdentity.identity_key.ilike(pattern))
            )
        return query.order_by(AgentRuntimeIdentity.created_at.desc()).all()

    def update_runtime_identity(
        self,
        identity_id: UUID,
        *,
        updated_by: str,
        name: str | None = None,
        environment: str | None = None,
        auth_provider: str | None = None,
        external_subject: str | None = None,
        expires_at: datetime | None = None,
    ) -> AgentRuntimeIdentity:
        identity = self.get_runtime_identity(identity_id)
        if name is not None:
            identity.name = name
        if environment is not None:
            identity.environment = environment
        if auth_provider is not None:
            identity.auth_provider = auth_provider
        if external_subject is not None:
            identity.external_subject = external_subject
        if expires_at is not None:
            identity.expires_at = expires_at
        identity.updated_by = updated_by
        self._db.commit()
        self._db.refresh(identity)
        return identity

    def _transition(
        self,
        identity: AgentRuntimeIdentity,
        target: str,
        *,
        updated_by: str,
        reason: str | None = None,
    ) -> AgentRuntimeIdentity:
        try:
            validate_lifecycle_transition(
                identity.status,
                target,
                RUNTIME_IDENTITY_TRANSITIONS,
                RuntimeIdentityStatus,
            )
        except ValueError as exc:
            raise InvalidTransitionError(str(exc)) from exc
        identity.status = target
        identity.updated_by = updated_by
        now = _utcnow()
        if target == RuntimeIdentityStatus.REVOKED.value:
            identity.revoked_at = now
            identity.revocation_reason = reason
        if target == RuntimeIdentityStatus.EXPIRED.value:
            identity.revoked_at = identity.revoked_at or now
        self._db.commit()
        self._db.refresh(identity)
        return identity

    def suspend_runtime_identity(
        self,
        identity_id: UUID,
        *,
        updated_by: str,
        reason: str | None = None,
    ) -> AgentRuntimeIdentity:
        return self._transition(
            self.get_runtime_identity(identity_id),
            RuntimeIdentityStatus.SUSPENDED.value,
            updated_by=updated_by,
            reason=reason,
        )

    def activate_runtime_identity(
        self,
        identity_id: UUID,
        *,
        updated_by: str,
        reason: str | None = None,
    ) -> AgentRuntimeIdentity:
        return self._transition(
            self.get_runtime_identity(identity_id),
            RuntimeIdentityStatus.ACTIVE.value,
            updated_by=updated_by,
            reason=reason,
        )

    def revoke_runtime_identity(
        self,
        identity_id: UUID,
        *,
        updated_by: str,
        reason: str | None = None,
    ) -> AgentRuntimeIdentity:
        identity = self._transition(
            self.get_runtime_identity(identity_id),
            RuntimeIdentityStatus.REVOKED.value,
            updated_by=updated_by,
            reason=reason,
        )
        cred_service = CredentialService(self._db)
        for cred in cred_service.list_credentials(identity_id):
            if cred.status == CredentialStatus.ACTIVE.value:
                cred_service.revoke_credential(
                    identity_id,
                    cred.id,
                    revoked_by=updated_by,
                )
        return identity

    def mark_expired_if_needed(self, identity: AgentRuntimeIdentity) -> None:
        if (
            identity.expires_at
            and identity.expires_at <= _utcnow()
            and identity.status == RuntimeIdentityStatus.ACTIVE.value
        ):
            identity.status = RuntimeIdentityStatus.EXPIRED.value
            identity.revoked_at = _utcnow()
            self._db.commit()


class CredentialService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def _require_identity(self, identity_id: UUID) -> AgentRuntimeIdentity:
        return RuntimeIdentityService(self._db).get_runtime_identity(identity_id)

    def issue_credential(
        self,
        identity_id: UUID,
        *,
        created_by: str,
        expires_at: datetime | None = None,
    ) -> IssuedCredential:
        identity = self._require_identity(identity_id)
        if identity.status != RuntimeIdentityStatus.ACTIVE.value:
            raise RelationshipError(
                "Cannot issue credential for non-active runtime identity"
            )
        credential_key = f"rai_rt_{secrets.token_hex(12)}"
        plaintext = f"{credential_key}.{secrets.token_urlsafe(32)}"
        credential = RuntimeCredential(
            runtime_identity_id=identity_id,
            credential_key=credential_key,
            credential_type=CredentialType.API_KEY.value,
            key_hash=_sha256_hex(plaintext),
            status=CredentialStatus.ACTIVE.value,
            expires_at=expires_at,
            created_by=created_by,
        )
        self._db.add(credential)
        self._db.commit()
        self._db.refresh(credential)
        return IssuedCredential(credential=credential, plaintext_secret=plaintext)

    def list_credentials(self, identity_id: UUID) -> list[RuntimeCredential]:
        self._require_identity(identity_id)
        return (
            self._db.query(RuntimeCredential)
            .filter(RuntimeCredential.runtime_identity_id == identity_id)
            .order_by(RuntimeCredential.issued_at.desc())
            .all()
        )

    def get_credential(
        self, identity_id: UUID, credential_id: UUID
    ) -> RuntimeCredential:
        self._require_identity(identity_id)
        credential = (
            self._db.query(RuntimeCredential)
            .filter(
                RuntimeCredential.id == credential_id,
                RuntimeCredential.runtime_identity_id == identity_id,
            )
            .first()
        )
        if not credential:
            raise NotFoundError("Credential", str(credential_id))
        return credential

    def authenticate(self, plaintext_secret: str) -> RuntimeCredential | None:
        key_hash = _sha256_hex(plaintext_secret)
        credential = (
            self._db.query(RuntimeCredential)
            .filter(RuntimeCredential.key_hash == key_hash)
            .first()
        )
        if not credential:
            return None
        if credential.status != CredentialStatus.ACTIVE.value:
            return None
        if credential.expires_at and credential.expires_at <= _utcnow():
            credential.status = CredentialStatus.EXPIRED.value
            self._db.commit()
            return None
        credential.last_used_at = _utcnow()
        identity = credential.runtime_identity
        if identity:
            identity.last_authenticated_at = _utcnow()
        self._db.commit()
        return credential

    def revoke_credential(
        self,
        identity_id: UUID,
        credential_id: UUID,
        *,
        revoked_by: str,
    ) -> RuntimeCredential:
        credential = self.get_credential(identity_id, credential_id)
        if credential.status == CredentialStatus.REVOKED.value:
            return credential
        credential.status = CredentialStatus.REVOKED.value
        credential.revoked_at = _utcnow()
        self._db.commit()
        self._db.refresh(credential)
        return credential

    def rotate_credential(
        self,
        identity_id: UUID,
        credential_id: UUID,
        *,
        rotated_by: str,
        expires_at: datetime | None = None,
    ) -> IssuedCredential:
        old = self.get_credential(identity_id, credential_id)
        issued = self.issue_credential(
            identity_id,
            created_by=rotated_by,
            expires_at=expires_at,
        )
        old.status = CredentialStatus.REVOKED.value
        old.revoked_at = _utcnow()
        old.replaced_by_id = issued.credential.id
        self._db.commit()
        self._db.refresh(issued.credential)
        return issued


class DelegationService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def _scope_digest(self, scope: DelegationScope) -> str:
        return digest_payload(scope.to_dict())

    def _append_revision(
        self,
        grant: DelegationGrant,
        *,
        change_type: str,
        changed_by: str,
        change_reason: str | None = None,
        bump_revision: bool = True,
    ) -> DelegationRevision:
        if bump_revision:
            grant.revision_number = int(grant.revision_number or 0) + 1
        revision = DelegationRevision(
            delegation_id=grant.id,
            revision_number=grant.revision_number,
            scope_version=int(grant.scope_version or 2),
            scope_snapshot=grant.scope or {},
            scope_digest=grant.scope_digest,
            valid_from=grant.valid_from,
            expires_at=grant.expires_at,
            change_type=change_type,
            change_reason=change_reason,
            changed_by=changed_by,
        )
        self._db.add(revision)
        return revision

    def create_delegation(
        self,
        *,
        delegator_type: str,
        delegator_id: str,
        delegate_runtime_identity_id: UUID,
        scope: dict[str, Any],
        created_by: str,
        parent_delegation_id: UUID | None = None,
        expires_at: datetime | None = None,
        valid_from: datetime | None = None,
    ) -> DelegationGrant:
        delegate = RuntimeIdentityService(self._db).get_runtime_identity(
            delegate_runtime_identity_id
        )
        child_scope = DelegationScope.from_dict(scope)
        self._validate_scope_against_version(
            delegate.agent_version_id,
            child_scope,
        )
        if parent_delegation_id:
            parent_grant = self.get_delegation(parent_delegation_id)
            if parent_grant.status != DelegationStatus.ACTIVE.value:
                raise RelationshipError("Parent delegation is not active")
            parent_scope = DelegationScope.from_dict(parent_grant.scope)
            if not child_scope.is_subset_of(parent_scope):
                raise ScopeExceededError(
                    "Child delegation scope exceeds parent authority"
                )
            depth = self._chain_depth(parent_grant)
            if depth >= MAX_DELEGATION_DEPTH:
                raise RelationshipError(
                    f"Delegation depth exceeds maximum of {MAX_DELEGATION_DEPTH}"
                )
            if self._would_create_cycle(
                parent_delegation_id,
                delegate_runtime_identity_id,
            ):
                raise RelationshipError("Delegation would create a cycle")
        scope_dict = child_scope.to_dict()
        digest = self._scope_digest(child_scope)
        grant = DelegationGrant(
            delegator_type=delegator_type,
            delegator_id=delegator_id,
            delegate_runtime_identity_id=delegate_runtime_identity_id,
            parent_delegation_id=parent_delegation_id,
            status=DelegationStatus.ACTIVE.value,
            scope=scope_dict,
            scope_version=2,
            revision_number=1,
            scope_digest=digest,
            valid_from=valid_from or _utcnow(),
            expires_at=expires_at,
            created_by=created_by,
        )
        self._db.add(grant)
        self._db.flush()
        self._append_revision(
            grant,
            change_type=DelegationChangeType.CREATED.value,
            changed_by=created_by,
            bump_revision=False,
        )
        self._db.commit()
        self._db.refresh(grant)
        return grant

    def get_delegation(self, delegation_id: UUID) -> DelegationGrant:
        grant = (
            _owned_delegation_query(self._db)
            .filter(DelegationGrant.id == delegation_id)
            .first()
        )
        if not grant:
            raise NotFoundError("Delegation", str(delegation_id))
        return grant

    def list_delegations(
        self,
        *,
        delegate_runtime_identity_id: UUID | None = None,
        delegator_id: str | None = None,
        status: str | None = None,
    ) -> list[DelegationGrant]:
        query = _owned_delegation_query(self._db)
        if delegate_runtime_identity_id:
            query = query.filter(
                DelegationGrant.delegate_runtime_identity_id
                == delegate_runtime_identity_id
            )
        if delegator_id:
            query = query.filter(DelegationGrant.delegator_id == delegator_id)
        if status:
            query = query.filter(DelegationGrant.status == status)
        return query.order_by(DelegationGrant.created_at.desc()).all()

    def list_revisions(self, delegation_id: UUID) -> list[DelegationRevision]:
        self.get_delegation(delegation_id)
        return (
            self._db.query(DelegationRevision)
            .filter(DelegationRevision.delegation_id == delegation_id)
            .order_by(DelegationRevision.revision_number.asc())
            .all()
        )

    def update_delegation(
        self,
        delegation_id: UUID,
        *,
        updated_by: str,
        scope: dict[str, Any] | None = None,
        expires_at: datetime | None = None,
        clear_expires_at: bool = False,
        valid_from: datetime | None = None,
        change_reason: str | None = None,
    ) -> DelegationGrant:
        grant = self.get_delegation(delegation_id)
        if grant.status != DelegationStatus.ACTIVE.value:
            raise InvalidTransitionError(
                f"Cannot update delegation in status {grant.status}"
            )
        delegate = RuntimeIdentityService(self._db).get_runtime_identity(
            grant.delegate_runtime_identity_id
        )
        change_type = DelegationChangeType.SCOPE_UPDATE.value
        if scope is not None:
            new_scope = DelegationScope.from_dict(scope)
            self._validate_scope_against_version(
                delegate.agent_version_id,
                new_scope,
            )
            if grant.parent_delegation_id:
                parent = self.get_delegation(grant.parent_delegation_id)
                parent_scope = DelegationScope.from_dict(parent.scope)
                if not new_scope.is_subset_of(parent_scope):
                    raise ScopeExceededError(
                        "Updated delegation scope exceeds parent authority"
                    )
            self._validate_children_scope_subset(grant.id, new_scope)
            grant.scope = new_scope.to_dict()
            grant.scope_version = 2
            grant.scope_digest = self._scope_digest(new_scope)
            change_type = DelegationChangeType.SCOPE_UPDATE.value
        if clear_expires_at or expires_at is not None or valid_from is not None:
            if clear_expires_at:
                grant.expires_at = None
            elif expires_at is not None:
                grant.expires_at = expires_at
            if valid_from is not None:
                grant.valid_from = valid_from
            if scope is None:
                change_type = DelegationChangeType.EXPIRY_UPDATE.value
        self._append_revision(
            grant,
            change_type=change_type,
            changed_by=updated_by,
            change_reason=change_reason,
        )
        self._db.commit()
        self._db.refresh(grant)
        return grant

    def suspend_delegation(
        self,
        delegation_id: UUID,
        *,
        updated_by: str,
        reason: str | None = None,
    ) -> DelegationGrant:
        if not reason:
            raise InvalidTransitionError("Suspend requires a reason")
        grant = self.get_delegation(delegation_id)
        if grant.status == DelegationStatus.SUSPENDED.value:
            return grant
        if grant.status != DelegationStatus.ACTIVE.value:
            raise InvalidTransitionError(
                f"Cannot suspend delegation in status {grant.status}"
            )
        grant.status = DelegationStatus.SUSPENDED.value
        self._append_revision(
            grant,
            change_type=DelegationChangeType.SUSPEND.value,
            changed_by=updated_by,
            change_reason=reason,
        )
        self._db.commit()
        self._db.refresh(grant)
        return grant

    def activate_delegation(
        self,
        delegation_id: UUID,
        *,
        updated_by: str,
        reason: str | None = None,
    ) -> DelegationGrant:
        if not reason:
            raise InvalidTransitionError("Reactivate requires a reason")
        grant = self.get_delegation(delegation_id)
        if grant.status in (
            DelegationStatus.REVOKED.value,
            DelegationStatus.EXPIRED.value,
        ):
            raise InvalidTransitionError(
                f"Cannot reactivate delegation in status {grant.status}"
            )
        if grant.status == DelegationStatus.ACTIVE.value:
            return grant
        if grant.status != DelegationStatus.SUSPENDED.value:
            raise InvalidTransitionError(
                f"Cannot reactivate delegation in status {grant.status}"
            )
        grant.status = DelegationStatus.ACTIVE.value
        self._append_revision(
            grant,
            change_type=DelegationChangeType.REACTIVATE.value,
            changed_by=updated_by,
            change_reason=reason,
        )
        self._db.commit()
        self._db.refresh(grant)
        return grant

    def _validate_children_scope_subset(
        self, delegation_id: UUID, parent_scope: DelegationScope
    ) -> None:
        children = (
            self._db.query(DelegationGrant)
            .filter(
                DelegationGrant.parent_delegation_id == delegation_id,
                DelegationGrant.status.in_(
                    [
                        DelegationStatus.ACTIVE.value,
                        DelegationStatus.SUSPENDED.value,
                    ]
                ),
            )
            .all()
        )
        for child in children:
            child_scope = DelegationScope.from_dict(child.scope)
            if not child_scope.is_subset_of(parent_scope):
                raise ScopeExceededError(
                    "Updated scope would exceed authority granted to child delegations"
                )

    def revoke_delegation(
        self,
        delegation_id: UUID,
        *,
        revoked_by: str,
        reason: str | None = None,
    ) -> DelegationGrant:
        if not reason:
            raise InvalidTransitionError("Revoke requires a reason")
        grant = self.get_delegation(delegation_id)
        if grant.status == DelegationStatus.REVOKED.value:
            return grant
        grant.status = DelegationStatus.REVOKED.value
        grant.revoked_at = _utcnow()
        grant.revocation_reason = reason
        self._append_revision(
            grant,
            change_type=DelegationChangeType.REVOKE.value,
            changed_by=revoked_by,
            change_reason=reason,
        )
        self._db.commit()
        self._db.refresh(grant)
        return grant

    def compute_effective_status(self, grant: DelegationGrant) -> str:
        now = _utcnow()
        if grant.status == DelegationStatus.REVOKED.value:
            return EffectiveDelegationStatus.REVOKED.value
        if grant.status == DelegationStatus.EXPIRED.value:
            return EffectiveDelegationStatus.EXPIRED.value
        if grant.expires_at and grant.expires_at <= now:
            return EffectiveDelegationStatus.EXPIRED.value
        if grant.valid_from and grant.valid_from > now:
            return EffectiveDelegationStatus.NOT_YET_VALID.value
        if grant.status == DelegationStatus.SUSPENDED.value:
            return EffectiveDelegationStatus.SUSPENDED.value
        identity = RuntimeIdentityService(self._db).get_runtime_identity(
            grant.delegate_runtime_identity_id
        )
        if identity.status != RuntimeIdentityStatus.ACTIVE.value:
            return EffectiveDelegationStatus.BLOCKED_BY_IDENTITY.value
        current = grant
        visited: set[UUID] = set()
        while current.parent_delegation_id:
            if current.parent_delegation_id in visited:
                return EffectiveDelegationStatus.BLOCKED_BY_PARENT.value
            visited.add(current.parent_delegation_id)
            parent = self.get_delegation(current.parent_delegation_id)
            if parent.status != DelegationStatus.ACTIVE.value:
                return EffectiveDelegationStatus.BLOCKED_BY_PARENT.value
            if parent.expires_at and parent.expires_at <= now:
                return EffectiveDelegationStatus.BLOCKED_BY_PARENT.value
            if parent.valid_from and parent.valid_from > now:
                return EffectiveDelegationStatus.BLOCKED_BY_PARENT.value
            current = parent
        return EffectiveDelegationStatus.ACTIVE.value

    def compute_effective_scope(self, grant: DelegationGrant) -> DelegationScope:
        """Intersect version catalog with full root→leaf chain scopes."""
        chain = self._walk_chain(grant)
        delegate = RuntimeIdentityService(self._db).get_runtime_identity(
            grant.delegate_runtime_identity_id
        )
        catalog = load_version_resource_catalog(
            self._db,
            delegate.agent_version_id,
        )
        effective = DelegationScope()
        for node in chain:
            effective = effective.intersect(DelegationScope.from_dict(node.scope))
        return effective.resolve_against_catalog(
            model_ids=catalog.model_ids,
            data_source_ids=catalog.data_source_ids,
            mcp_server_ids=catalog.mcp_server_ids,
            tool_ids=catalog.tool_ids,
        )

    def _walk_chain(self, grant: DelegationGrant) -> list[DelegationGrant]:
        chain: list[DelegationGrant] = []
        current: DelegationGrant | None = grant
        visited: set[UUID] = set()
        while current is not None:
            if current.id in visited:
                raise RelationshipError("Delegation cycle detected")
            visited.add(current.id)
            chain.insert(0, current)
            if current.parent_delegation_id is None:
                break
            current = self.get_delegation(current.parent_delegation_id)
        if len(chain) > MAX_DELEGATION_DEPTH:
            raise RelationshipError(
                f"Delegation depth exceeds maximum of {MAX_DELEGATION_DEPTH}"
            )
        return chain

    def resolve_active_chain(self, delegation_id: UUID) -> list[DelegationGrant]:
        """Return delegation chain from root to leaf, validating active state."""
        leaf = self.get_delegation(delegation_id)
        chain = self._walk_chain(leaf)
        now = _utcnow()
        for grant in chain:
            if grant.status == DelegationStatus.REVOKED.value:
                raise RelationshipError("Delegation chain contains revoked grant")
            if grant.status == DelegationStatus.SUSPENDED.value:
                raise RelationshipError("Delegation chain contains suspended grant")
            if grant.status == DelegationStatus.EXPIRED.value:
                raise RelationshipError("Delegation chain contains expired grant")
            if grant.valid_from and grant.valid_from > now:
                raise RelationshipError("Delegation chain is not yet valid")
            if grant.expires_at and grant.expires_at <= now:
                grant.status = DelegationStatus.EXPIRED.value
                self._db.commit()
                raise RelationshipError("Delegation chain contains expired grant")
        return chain

    def _chain_depth(self, grant: DelegationGrant) -> int:
        return len(self._walk_chain(grant))

    def _would_create_cycle(self, parent_id: UUID, delegate_identity_id: UUID) -> bool:
        parent = self.get_delegation(parent_id)
        if parent.delegate_runtime_identity_id == delegate_identity_id:
            return True
        chain = self._walk_chain(parent)
        for grant in chain:
            if grant.delegate_runtime_identity_id == delegate_identity_id:
                return True
        return False

    def _validate_scope_against_version(
        self, version_id: UUID, scope: DelegationScope
    ) -> None:
        catalog = load_version_resource_catalog(self._db, version_id)
        self._validate_scope_against_catalog(scope, catalog)

    def _validate_scope_against_catalog(
        self, scope: DelegationScope, catalog: VersionResourceCatalog
    ) -> None:
        # Only EXPLICIT ids must be declared; ALL_DECLARED needs no id checks.
        for model_id in scope.model_ids:
            if model_id not in catalog.model_ids:
                raise ScopeExceededError(
                    f"Model {model_id} is not declared on agent version"
                )
        for ds_id in scope.data_source_ids:
            if ds_id not in catalog.data_source_ids:
                raise ScopeExceededError(
                    f"Data source {ds_id} is not declared on agent version"
                )
        for mcp_id in scope.mcp_server_ids:
            if mcp_id not in catalog.mcp_server_ids:
                raise ScopeExceededError(
                    f"MCP server {mcp_id} is not declared on agent version"
                )
        for tool_id in scope.tool_ids:
            tool = catalog.tool_by_id(tool_id)
            if tool is None:
                raise ScopeExceededError(
                    f"Tool {tool_id} is not declared on agent version"
                )
            if tool.mcp_server_id and tool.mcp_server_id not in catalog.mcp_server_ids:
                raise ScopeExceededError(
                    f"Tool {tool_id} belongs to MCP not declared on agent version"
                )
        if scope.tool_keys:
            declared_keys = {t.tool_key for t in catalog.declared_tools}
            for tool_key in scope.tool_keys:
                if tool_key not in declared_keys:
                    raise ScopeExceededError(
                        f"Tool {tool_key} is not declared on agent version"
                    )
