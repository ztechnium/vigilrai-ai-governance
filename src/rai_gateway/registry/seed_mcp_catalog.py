"""Idempotent enterprise MCP seed catalog loader."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from rai_gateway.models.registry import MCPServer, ModelResource, ToolResource
from rai_gateway.registry.domain import CatalogScope

FORBIDDEN_SEED_KEYS = frozenset(
    {
        "credentials",
        "credential",
        "secret",
        "secrets",
        "password",
        "token",
        "api_key",
        "apikey",
        "endpoint",
        "endpoints",
        "tenant_url",
        "customer_endpoint",
        "connection_string",
    }
)
VALID_CAPABILITY_TYPES = frozenset(
    {"READ", "SEARCH", "CREATE", "UPDATE", "DELETE", "EXECUTE", "ADMIN"}
)
VALID_SIDE_EFFECTS = frozenset({"NONE", "REVERSIBLE", "CONSEQUENTIAL"})
VALID_RISKS = frozenset({"LOW", "MEDIUM", "HIGH", "CRITICAL"})
NON_ACTIVE_SEED_STATUSES = frozenset({"", "SEEDED", "DISCOVERED", "UNCLASSIFIED"})
DEFAULT_SEED_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "mcp_seed_catalog.json"
)


@dataclass
class SeedResult:
    mcps_created: int = 0
    mcps_updated: int = 0
    tools_created: int = 0
    tools_updated: int = 0
    models_created: int = 0
    models_updated: int = 0
    mcp_ids: dict[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "mcps_created": self.mcps_created,
            "mcps_updated": self.mcps_updated,
            "tools_created": self.tools_created,
            "tools_updated": self.tools_updated,
            "models_created": self.models_created,
            "models_updated": self.models_updated,
            "mcp_ids": self.mcp_ids or {},
        }


def _assert_no_secrets(obj: Any, path: str = "$") -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            lowered = str(key).lower()
            if lowered in FORBIDDEN_SEED_KEYS or any(
                token in lowered
                for token in ("secret", "password", "credential", "api_key")
            ):
                raise ValueError(
                    f"Seed catalog must not include secrets/endpoints at {path}.{key}"
                )
            _assert_no_secrets(value, f"{path}.{key}")
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            _assert_no_secrets(item, f"{path}[{idx}]")


def _tool_key(canonical_key: str, native_name: str) -> str:
    return f"{canonical_key}.{native_name}"


def _consequential(side_effect: str, risk: str) -> bool:
    return side_effect in {"REVERSIBLE", "CONSEQUENTIAL"} or risk in {
        "HIGH",
        "CRITICAL",
    }


def load_seed_catalog(path: Path | None = None) -> dict[str, Any]:
    seed_path = path or DEFAULT_SEED_PATH
    data = json.loads(seed_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "mcps" not in data:
        raise ValueError("Seed catalog must be an object with an 'mcps' array")
    _assert_no_secrets(data)
    return data


class MCPSeedCatalogService:
    """Upsert seeded MCP templates and known tools without granting authority."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def seed(self, path: Path | None = None, *, scope: str | None = None) -> SeedResult:
        catalog = load_seed_catalog(path)
        source_type = catalog.get("source_type") or "SEEDED_TEMPLATE"
        scope = (scope or CatalogScope.PLATFORM.value).upper()
        if scope not in {CatalogScope.PLATFORM.value, CatalogScope.ORGANIZATION.value}:
            raise ValueError(f"Unknown catalog scope: {scope}")
        result = SeedResult(mcp_ids={})
        for mcp_def in catalog.get("mcps") or []:
            canonical_key = str(mcp_def["canonical_key"]).strip()
            if not canonical_key:
                raise ValueError("MCP canonical_key is required")
            aliases = [
                str(a).strip()
                for a in (mcp_def.get("native_aliases") or [canonical_key])
                if str(a).strip()
            ]
            if canonical_key not in aliases:
                aliases.insert(0, canonical_key)
            mcp_meta = {
                "source_type": source_type,
                "canonical_key": canonical_key,
                "vendor": mcp_def.get("vendor"),
                "category": mcp_def.get("category"),
                "native_aliases": aliases,
                "seed_version": catalog.get("version"),
            }
            existing_query = self._db.query(MCPServer).filter(
                MCPServer.server_key == canonical_key,
                MCPServer.scope == scope,
            )
            existing = existing_query.first()
            if existing:
                existing.name = mcp_def.get("display_name") or existing.name
                existing.description = (
                    mcp_def.get("description") or existing.description
                )
                existing.provider = mcp_def.get("vendor") or existing.provider
                existing.scope = scope
                merged = dict(existing.metadata_ or {})
                merged.update(mcp_meta)
                existing.metadata_ = merged
                result.mcps_updated += 1
                mcp = existing
            else:
                mcp = MCPServer(
                    server_key=canonical_key,
                    name=mcp_def.get("display_name") or canonical_key,
                    description=mcp_def.get("description"),
                    provider=mcp_def.get("vendor"),
                    status="SEEDED",
                    scope=scope,
                    metadata_=mcp_meta,
                )
                self._db.add(mcp)
                result.mcps_created += 1
            self._db.flush()
            result.mcp_ids[canonical_key] = str(mcp.id)
            for tool_def in mcp_def.get("tools") or []:
                self._upsert_tool(
                    mcp,
                    canonical_key,
                    tool_def,
                    result,
                    scope=scope,
                )
        for model_def in catalog.get("models") or []:
            self._upsert_model(
                model_def,
                result,
                scope=scope,
            )
        self._db.commit()
        return result

    def _upsert_tool(
        self,
        mcp: MCPServer,
        canonical_key: str,
        tool_def: dict[str, Any],
        result: SeedResult,
        *,
        scope: str = CatalogScope.PLATFORM.value,
    ) -> None:
        native_name = str(tool_def["native_name"]).strip()
        if not native_name:
            raise ValueError(f"Tool native_name required for MCP {canonical_key}")
        capability = str(tool_def.get("capability_type") or "READ").upper()
        side_effect = str(tool_def.get("side_effect") or "NONE").upper()
        risk = str(tool_def.get("default_risk") or "LOW").upper()
        if capability not in VALID_CAPABILITY_TYPES:
            raise ValueError(f"Invalid capability_type for {native_name}: {capability}")
        if side_effect not in VALID_SIDE_EFFECTS:
            raise ValueError(f"Invalid side_effect for {native_name}: {side_effect}")
        if risk not in VALID_RISKS:
            raise ValueError(f"Invalid default_risk for {native_name}: {risk}")
        tool_key = _tool_key(canonical_key, native_name)
        meta = {
            "native_name": native_name,
            "native_aliases": [native_name],
            "capability_type": capability,
            "side_effect": side_effect,
            "default_risk": risk,
            "default_requires_approval": bool(
                tool_def.get("default_requires_approval", False)
            ),
            "group": tool_def.get("group"),
            "source_type": "SEEDED_TEMPLATE",
        }
        existing_query = self._db.query(ToolResource).filter(
            ToolResource.tool_key == tool_key,
            ToolResource.scope == scope,
        )
        existing = existing_query.first()
        if existing:
            existing.name = tool_def.get("display_name") or native_name
            existing.description = tool_def.get("description") or existing.description
            existing.category = tool_def.get("group") or existing.category
            existing.provider = mcp.provider
            existing.mcp_server_id = mcp.id
            existing.sensitivity = risk
            existing.consequential_action = _consequential(side_effect, risk)
            existing.scope = scope
            merged = dict(existing.metadata_ or {})
            merged.update(meta)
            existing.metadata_ = merged
            if (existing.status or "").upper() in NON_ACTIVE_SEED_STATUSES:
                existing.status = "SEEDED"
            result.tools_updated += 1
        else:
            tool = ToolResource(
                tool_key=tool_key,
                name=tool_def.get("display_name") or native_name,
                description=tool_def.get("description"),
                category=tool_def.get("group"),
                provider=mcp.provider,
                mcp_server_id=mcp.id,
                sensitivity=risk,
                consequential_action=_consequential(side_effect, risk),
                status="SEEDED",
                scope=scope,
                metadata_=meta,
            )
            self._db.add(tool)
            result.tools_created += 1

    def _upsert_model(
        self,
        model_def: dict[str, Any],
        result: SeedResult,
        *,
        scope: str,
    ) -> None:
        provider = str(model_def.get("provider") or "").strip()
        model_name = str(model_def.get("model_name") or "").strip()
        if not provider or not model_name:
            raise ValueError("Seed model requires provider and model_name")
        meta = {
            "source_type": "SEEDED_TEMPLATE",
            "display_name": model_def.get("display_name") or model_name,
            "description": model_def.get("description"),
            "family": model_def.get("family"),
        }
        existing_query = self._db.query(ModelResource).filter(
            ModelResource.provider == provider,
            ModelResource.model_name == model_name,
            ModelResource.scope == scope,
        )
        existing = existing_query.first()
        if existing:
            existing.model_version = (
                model_def.get("model_version") or existing.model_version
            )
            existing.hosting_type = (
                model_def.get("hosting_type") or existing.hosting_type
            )
            existing.scope = scope
            merged = dict(existing.metadata_ or {})
            merged.update(meta)
            existing.metadata_ = merged
            result.models_updated += 1
            return
        self._db.add(
            ModelResource(
                provider=provider,
                model_name=model_name,
                model_version=model_def.get("model_version"),
                hosting_type=model_def.get("hosting_type") or "EXTERNAL_API",
                status="ACTIVE",
                scope=scope,
                metadata_=meta,
            )
        )
        result.models_created += 1
