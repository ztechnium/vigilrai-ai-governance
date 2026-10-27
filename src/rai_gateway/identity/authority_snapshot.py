"""Immutable authority snapshot + deterministic digest for runtime decisions."""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID

from rai_gateway.identity.domain import (
    AuthenticationMethod,
    DelegationScope,
    RuntimeAuthenticationProof,
)
from rai_gateway.registry.eligibility import EligibilityResult


# TYPE_CHECKING-friendly imports avoided: snapshot builders accept duck-typed ctx.
def _normalize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(k): _normalize_value(v)
            for k, v in sorted(value.items(), key=lambda item: item[0])
        }
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    if isinstance(value, float):
        return format(value, ".15g")
    if isinstance(value, UUID):
        return str(value)
    if value is None:
        return None
    return value


def canonical_json(payload: dict[str, Any]) -> str:
    """Stable JSON serialization for digests."""
    return json.dumps(
        _normalize_value(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def digest_payload(payload: dict[str, Any]) -> str:
    """Return SHA-256 hex digest of canonical JSON."""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _eligibility_dict(eligibility: EligibilityResult | None) -> dict[str, Any]:
    if eligibility is None:
        return {"eligible": True, "reason": None}
    return {
        "eligible": bool(eligibility.eligible),
        "reason": eligibility.reason,
    }


def _effective_scope_dict(scope: DelegationScope) -> dict[str, Any]:
    """Flatten scope for snapshot."""
    if hasattr(scope, "to_effective_flat"):
        return scope.to_effective_flat()
    data = scope.to_dict()
    return {
        "models": data.get("model_ids") or [],
        "data_sources": data.get("data_source_ids") or [],
        "mcp_servers": data.get("mcp_server_ids") or [],
        "tools": data.get("tool_ids") or [],
        "environments": ([data["environment"]] if data.get("environment") else []),
    }


def _chain_entries(chain: list[Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for entry in chain:
        entries.append(
            {
                "id": str(entry.delegation_id),
                "revision": getattr(entry, "revision", None),
                "stored_status": getattr(entry, "stored_status", None),
                "scope_digest": getattr(entry, "scope_digest", None),
                "delegator_type": entry.delegator_type,
                "delegator_id": entry.delegator_id,
                "scope": entry.scope,
            }
        )
    return entries


def build_authority_snapshot(
    ctx: Any,
    *,
    schema_version: int = 2,
) -> dict[str, Any]:
    """Build a secret-free authority snapshot from a resolved context."""
    identity = ctx.runtime_identity
    system = ctx.ai_system
    agent = ctx.agent
    version = ctx.agent_version
    proof = getattr(ctx, "authentication_proof", None)
    if proof is not None:
        authentication = proof.to_dict()
    else:
        credential = getattr(ctx, "credential", None)
        authentication = {
            "method": None,
            "credential_id": str(credential.id) if credential else None,
            "binding_id": None,
            "issuer": None,
            "subject_hash": None,
            "acr": None,
            "amr": [],
            "auth_time": None,
            "verified": True,
        }
    chain = getattr(ctx, "delegation_chain", []) or []
    selected_id = str(chain[-1].delegation_id) if chain else None
    return {
        "schema_version": schema_version,
        "ai_system": {
            "id": str(system.id),
            "status": getattr(system, "status", None),
        },
        "agent": {
            "id": str(agent.id),
            "status": getattr(agent, "status", None),
        },
        "agent_version": {
            "id": str(version.id),
            "version_number": getattr(version, "version_number", None),
            "lifecycle_status": getattr(version, "lifecycle_status", None),
            "configuration_digest": getattr(version, "configuration_digest", None),
        },
        "runtime_identity": {
            "id": str(identity.id),
            "identity_key": identity.identity_key,
            "status": identity.status,
            "environment": identity.environment,
        },
        "authentication": authentication,
        "delegation": {
            "selected_id": selected_id,
            "chain": _chain_entries(chain),
            "effective_scope": _effective_scope_dict(ctx.effective_scope),
            "initiating_principal": getattr(ctx, "initiating_principal", None),
        },
        "eligibility": _eligibility_dict(getattr(ctx, "eligibility", None)),
    }


def build_authority_digest(snapshot: dict[str, Any]) -> str:
    return digest_payload(snapshot)


def snapshot_and_digest(
    ctx: Any,
    *,
    schema_version: int = 2,
) -> tuple[dict[str, Any], str]:
    snapshot = build_authority_snapshot(ctx, schema_version=schema_version)
    return snapshot, build_authority_digest(snapshot)


def assert_snapshot_is_safe(snapshot: dict[str, Any]) -> None:
    """Raise ValueError if snapshot appears to contain secrets."""
    forbidden_keys = {
        "key_hash",
        "plaintext",
        "plaintext_secret",
        "access_token",
        "refresh_token",
        "bearer",
        "private_key",
        "raw_certificate",
        "password",
        "api_key",
        "secret",
    }

    def _walk(node: Any, path: str = "") -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                lowered = str(k).lower()
                if lowered in forbidden_keys:
                    raise ValueError(
                        f"Forbidden key in authority snapshot: {path}.{k}"
                        if path
                        else f"Forbidden key in authority snapshot: {k}"
                    )
                _walk(v, f"{path}.{k}" if path else str(k))
        elif isinstance(node, list):
            for i, item in enumerate(node):
                _walk(item, f"{path}[{i}]")

    _walk(snapshot)


def proof_from_api_key_credential(
    credential_id: UUID | None,
) -> RuntimeAuthenticationProof:
    return RuntimeAuthenticationProof(
        method=AuthenticationMethod.API_KEY.value,
        credential_id=credential_id,
        verified=True,
    )


def proof_from_oidc(
    *,
    binding_id: UUID | None = None,
    issuer: str | None = None,
    subject_hash: str | None = None,
    acr: str | None = None,
    amr: list[str] | None = None,
    auth_time: Any = None,
) -> RuntimeAuthenticationProof:
    return RuntimeAuthenticationProof(
        method=AuthenticationMethod.OIDC.value,
        binding_id=binding_id,
        issuer=issuer,
        subject_hash=subject_hash,
        acr=acr,
        amr=tuple(amr or ()),
        auth_time=auth_time,
        verified=True,
    )


def proof_from_mtls(
    *,
    binding_id: UUID | None = None,
    subject_hash: str | None = None,
) -> RuntimeAuthenticationProof:
    return RuntimeAuthenticationProof(
        method=AuthenticationMethod.MTLS.value,
        binding_id=binding_id,
        subject_hash=subject_hash,
        verified=True,
    )
