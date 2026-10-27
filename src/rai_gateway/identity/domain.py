"""Domain types and invariants for WP2 runtime identity and delegation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Final
from uuid import UUID

MAX_DELEGATION_DEPTH: Final[int] = 10


class RuntimeIdentityStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class IdentityType(StrEnum):
    RAI_API_CREDENTIAL = "RAI_API_CREDENTIAL"
    EXTERNAL_SUBJECT = "EXTERNAL_SUBJECT"


class CredentialType(StrEnum):
    API_KEY = "API_KEY"


class CredentialStatus(StrEnum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class AuthenticationMethod(StrEnum):
    API_KEY = "API_KEY"
    OIDC = "OIDC"
    MTLS = "MTLS"


@dataclass(frozen=True)
class RuntimeAuthenticationProof:
    """Verified authentication evidence — never includes secrets or raw tokens."""

    method: str
    credential_id: UUID | None = None
    binding_id: UUID | None = None
    issuer: str | None = None
    subject_hash: str | None = None
    acr: str | None = None
    amr: tuple[str, ...] = ()
    auth_time: datetime | None = None
    verified: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "credential_id": str(self.credential_id) if self.credential_id else None,
            "binding_id": str(self.binding_id) if self.binding_id else None,
            "issuer": self.issuer,
            "subject_hash": self.subject_hash,
            "acr": self.acr,
            "amr": list(self.amr),
            "auth_time": self.auth_time.isoformat() if self.auth_time else None,
            "verified": self.verified,
        }


class DelegatorType(StrEnum):
    HUMAN = "HUMAN"
    SERVICE = "SERVICE"
    RUNTIME_IDENTITY = "RUNTIME_IDENTITY"


class DelegationStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class DelegationChangeType(StrEnum):
    CREATED = "CREATED"
    SCOPE_UPDATE = "SCOPE_UPDATE"
    EXPIRY_UPDATE = "EXPIRY_UPDATE"
    SUSPEND = "SUSPEND"
    REACTIVATE = "REACTIVATE"
    REVOKE = "REVOKE"


class EffectiveDelegationStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    BLOCKED_BY_PARENT = "BLOCKED_BY_PARENT"
    BLOCKED_BY_IDENTITY = "BLOCKED_BY_IDENTITY"
    NOT_YET_VALID = "NOT_YET_VALID"


class ResourceScopeMode(StrEnum):
    ALL_DECLARED = "ALL_DECLARED"
    EXPLICIT = "EXPLICIT"


DELEGATION_TRANSITIONS: dict[DelegationStatus, set[DelegationStatus]] = {
    DelegationStatus.ACTIVE: {
        DelegationStatus.SUSPENDED,
        DelegationStatus.REVOKED,
        DelegationStatus.EXPIRED,
    },
    DelegationStatus.SUSPENDED: {
        DelegationStatus.ACTIVE,
        DelegationStatus.REVOKED,
        DelegationStatus.EXPIRED,
    },
    DelegationStatus.REVOKED: set(),
    DelegationStatus.EXPIRED: set(),
}


RUNTIME_IDENTITY_TRANSITIONS: dict[
    RuntimeIdentityStatus, set[RuntimeIdentityStatus]
] = {
    RuntimeIdentityStatus.ACTIVE: {
        RuntimeIdentityStatus.SUSPENDED,
        RuntimeIdentityStatus.REVOKED,
        RuntimeIdentityStatus.EXPIRED,
    },
    RuntimeIdentityStatus.SUSPENDED: {
        RuntimeIdentityStatus.ACTIVE,
        RuntimeIdentityStatus.REVOKED,
    },
    RuntimeIdentityStatus.REVOKED: set(),
    RuntimeIdentityStatus.EXPIRED: set(),
}


def _sorted_ids(values: list[str] | None) -> list[str]:
    return sorted({str(v) for v in (values or []) if v})


@dataclass(frozen=True)
class ResourceScope:
    """Single resource dimension with explicit ALL_DECLARED vs EXPLICIT mode."""

    mode: ResourceScopeMode = ResourceScopeMode.ALL_DECLARED
    ids: tuple[str, ...] = ()

    def to_dict(self, *, values_key: str = "ids") -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            values_key: list(self.ids),
        }

    @classmethod
    def all_declared(cls) -> ResourceScope:
        return cls(mode=ResourceScopeMode.ALL_DECLARED, ids=())

    @classmethod
    def explicit(cls, ids: list[str] | None) -> ResourceScope:
        return cls(mode=ResourceScopeMode.EXPLICIT, ids=tuple(_sorted_ids(ids)))

    @classmethod
    def from_v1_list(cls, values: list[str] | None) -> ResourceScope:
        cleaned = _sorted_ids(values)
        if cleaned:
            return cls.explicit(cleaned)
        return cls.all_declared()

    @classmethod
    def from_dict(
        cls, data: dict[str, Any] | None, *, values_key: str = "ids"
    ) -> ResourceScope:
        if not data:
            return cls.all_declared()
        mode_raw = data.get("mode") or ResourceScopeMode.ALL_DECLARED.value
        mode = ResourceScopeMode(mode_raw)
        ids = _sorted_ids(data.get(values_key) or data.get("ids") or data.get("values"))
        if mode == ResourceScopeMode.EXPLICIT:
            return cls.explicit(ids)
        return cls.all_declared()

    def is_subset_of(self, parent: ResourceScope) -> bool:
        if parent.mode == ResourceScopeMode.ALL_DECLARED:
            return True
        # Parent EXPLICIT
        if self.mode == ResourceScopeMode.ALL_DECLARED:
            return False
        return set(self.ids).issubset(set(parent.ids))

    def intersect(self, other: ResourceScope) -> ResourceScope:
        if self.mode == ResourceScopeMode.ALL_DECLARED:
            return other
        if other.mode == ResourceScopeMode.ALL_DECLARED:
            return self
        return ResourceScope.explicit(sorted(set(self.ids) & set(other.ids)))

    def resolve_against(self, declared: set[str]) -> set[str]:
        if self.mode == ResourceScopeMode.ALL_DECLARED:
            return set(declared)
        return set(self.ids) & set(declared)


@dataclass
class DelegationScope:
    """Bounded delegation authority envelope (Scope V2 with V1 compat)."""

    models: ResourceScope = field(default_factory=ResourceScope.all_declared)
    data_sources: ResourceScope = field(default_factory=ResourceScope.all_declared)
    mcp_servers: ResourceScope = field(default_factory=ResourceScope.all_declared)
    tools: ResourceScope = field(default_factory=ResourceScope.all_declared)
    environments: ResourceScope = field(default_factory=ResourceScope.all_declared)
    # Legacy field — accepted on read only; prefer tools
    tool_keys: list[str] = field(default_factory=list)
    scope_version: int = 2

    # --- Legacy accessors (EXPLICIT ids only; empty means ALL_DECLARED) ---

    @property
    def model_ids(self) -> list[str]:
        return (
            list(self.models.ids)
            if self.models.mode == ResourceScopeMode.EXPLICIT
            else []
        )

    @property
    def data_source_ids(self) -> list[str]:
        return (
            list(self.data_sources.ids)
            if self.data_sources.mode == ResourceScopeMode.EXPLICIT
            else []
        )

    @property
    def mcp_server_ids(self) -> list[str]:
        return (
            list(self.mcp_servers.ids)
            if self.mcp_servers.mode == ResourceScopeMode.EXPLICIT
            else []
        )

    @property
    def tool_ids(self) -> list[str]:
        return (
            list(self.tools.ids)
            if self.tools.mode == ResourceScopeMode.EXPLICIT
            else []
        )

    @property
    def environment(self) -> str | None:
        if (
            self.environments.mode == ResourceScopeMode.EXPLICIT
            and self.environments.ids
        ):
            return self.environments.ids[0]
        return None

    def to_dict(self) -> dict[str, Any]:
        """Persist as Scope V2 JSON."""
        return {
            "scope_version": 2,
            "models": self.models.to_dict(),
            "data_sources": self.data_sources.to_dict(),
            "mcp_servers": self.mcp_servers.to_dict(),
            "tools": self.tools.to_dict(),
            "environments": self.environments.to_dict(values_key="values"),
        }

    def to_legacy_dict(self) -> dict[str, Any]:
        """Compatibility shape for existing API consumers."""
        return {
            "model_ids": self.model_ids,
            "data_source_ids": self.data_source_ids,
            "mcp_server_ids": self.mcp_server_ids,
            "tool_ids": self.tool_ids,
            "environment": self.environment,
        }

    def to_effective_flat(self) -> dict[str, Any]:
        return {
            "models": list(self.models.ids)
            if self.models.mode == ResourceScopeMode.EXPLICIT
            else [],
            "data_sources": (
                list(self.data_sources.ids)
                if self.data_sources.mode == ResourceScopeMode.EXPLICIT
                else []
            ),
            "mcp_servers": (
                list(self.mcp_servers.ids)
                if self.mcp_servers.mode == ResourceScopeMode.EXPLICIT
                else []
            ),
            "tools": list(self.tools.ids)
            if self.tools.mode == ResourceScopeMode.EXPLICIT
            else [],
            "environments": list(self.environments.ids)
            if self.environments.mode == ResourceScopeMode.EXPLICIT
            else [],
            "models_mode": self.models.mode.value,
            "data_sources_mode": self.data_sources.mode.value,
            "mcp_servers_mode": self.mcp_servers.mode.value,
            "tools_mode": self.tools.mode.value,
            "environments_mode": self.environments.mode.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> DelegationScope:
        if not data:
            return cls()
        version = int(data.get("scope_version") or 1)
        if version >= 2 and ("models" in data or "tools" in data):
            return cls(
                models=ResourceScope.from_dict(data.get("models")),
                data_sources=ResourceScope.from_dict(data.get("data_sources")),
                mcp_servers=ResourceScope.from_dict(data.get("mcp_servers")),
                tools=ResourceScope.from_dict(data.get("tools")),
                environments=ResourceScope.from_dict(
                    data.get("environments"), values_key="values"
                ),
                tool_keys=_sorted_ids(data.get("tool_keys")),
                scope_version=2,
            )
        # V1 compatibility
        env = data.get("environment")
        environments = (
            ResourceScope.explicit([env]) if env else ResourceScope.all_declared()
        )
        return cls(
            models=ResourceScope.from_v1_list(data.get("model_ids")),
            data_sources=ResourceScope.from_v1_list(data.get("data_source_ids")),
            mcp_servers=ResourceScope.from_v1_list(data.get("mcp_server_ids")),
            tools=ResourceScope.from_v1_list(data.get("tool_ids")),
            environments=environments,
            tool_keys=_sorted_ids(data.get("tool_keys")),
            scope_version=1,
        )

    def is_subset_of(self, parent: DelegationScope) -> bool:
        return (
            self.models.is_subset_of(parent.models)
            and self.data_sources.is_subset_of(parent.data_sources)
            and self.mcp_servers.is_subset_of(parent.mcp_servers)
            and self.tools.is_subset_of(parent.tools)
            and self.environments.is_subset_of(parent.environments)
        )

    def intersect(self, other: DelegationScope) -> DelegationScope:
        return DelegationScope(
            models=self.models.intersect(other.models),
            data_sources=self.data_sources.intersect(other.data_sources),
            mcp_servers=self.mcp_servers.intersect(other.mcp_servers),
            tools=self.tools.intersect(other.tools),
            environments=self.environments.intersect(other.environments),
            scope_version=2,
        )

    def resolve_against_catalog(
        self,
        *,
        model_ids: set[str],
        data_source_ids: set[str],
        mcp_server_ids: set[str],
        tool_ids: set[str],
    ) -> DelegationScope:
        """Intersect modes with version-declared resources into EXPLICIT effective sets."""
        return DelegationScope(
            models=ResourceScope.explicit(
                sorted(self.models.resolve_against(model_ids))
            ),
            data_sources=ResourceScope.explicit(
                sorted(self.data_sources.resolve_against(data_source_ids))
            ),
            mcp_servers=ResourceScope.explicit(
                sorted(self.mcp_servers.resolve_against(mcp_server_ids))
            ),
            tools=ResourceScope.explicit(sorted(self.tools.resolve_against(tool_ids))),
            environments=self.environments,
            scope_version=2,
        )


class AuthorityDenialReason(StrEnum):
    UNKNOWN_CREDENTIAL = "UNKNOWN_CREDENTIAL"
    INVALID_CREDENTIAL = "INVALID_CREDENTIAL"
    CREDENTIAL_REVOKED = "CREDENTIAL_REVOKED"
    CREDENTIAL_EXPIRED = "CREDENTIAL_EXPIRED"
    UNKNOWN_IDENTITY = "UNKNOWN_IDENTITY"
    IDENTITY_SUSPENDED = "IDENTITY_SUSPENDED"
    IDENTITY_REVOKED = "IDENTITY_REVOKED"
    IDENTITY_EXPIRED = "IDENTITY_EXPIRED"
    AGENT_SUSPENDED = "AGENT_SUSPENDED"
    AGENT_VERSION_INELIGIBLE = "AGENT_VERSION_INELIGIBLE"
    IDENTITY_VERSION_MISMATCH = "IDENTITY_VERSION_MISMATCH"
    DELEGATION_EXPIRED = "DELEGATION_EXPIRED"
    DELEGATION_REVOKED = "DELEGATION_REVOKED"
    DELEGATION_SUSPENDED = "DELEGATION_SUSPENDED"
    AUTHORITY_SCOPE_EXCEEDED = "AUTHORITY_SCOPE_EXCEEDED"
    DELEGATION_CYCLE = "DELEGATION_CYCLE"
    DELEGATION_DEPTH_EXCEEDED = "DELEGATION_DEPTH_EXCEEDED"
    BROKEN_DELEGATION_CHAIN = "BROKEN_DELEGATION_CHAIN"
    DELEGATION_NOT_YET_VALID = "DELEGATION_NOT_YET_VALID"
    DELEGATION_BLOCKED_BY_PARENT = "DELEGATION_BLOCKED_BY_PARENT"
    DELEGATION_BLOCKED_BY_IDENTITY = "DELEGATION_BLOCKED_BY_IDENTITY"
