#!/usr/bin/env python3
"""Seed MCP catalog tools, activate them, and attach to an agent version.

Unknown-tool hook denials happen when the runtime identity's agent version does
not expose the native MCP/tool names Cursor sends. This script:

1. Idempotently seeds ``data/mcp_seed_catalog.json``
2. Sets the target MCP + its tools to ACTIVE (enforcement requires ACTIVE)
3. Attaches the MCP to a DRAFT/REASSESSMENT agent version (MCP-only dep so all
   tools on that MCP are exposed)
4. Optionally expands active delegation scopes for runtime identities on that
   version

Usage:
  python scripts/attach_seeded_mcp_to_version.py \\
    --version-id ada35d01-22d0-4a11-8e13-2323d9e328f5 \\
    --mcp-key atlassian \\
    --mcp-key cursor_local \\
    --expand-delegations
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rai_gateway.core.database import SessionLocal  # noqa: E402
from rai_gateway.identity.version_resources import (  # noqa: E402
    load_version_resource_catalog,
)
from rai_gateway.models.identity import (  # noqa: E402
    AgentRuntimeIdentity,
    DelegationGrant,
)
from rai_gateway.models.registry import (  # noqa: E402
    AgentVersion,
    AgentVersionDependency,
    MCPServer,
    ToolResource,
)
from rai_gateway.registry.domain import AgentVersionStatus  # noqa: E402
from rai_gateway.registry.seed_mcp_catalog import (  # noqa: E402
    DEFAULT_SEED_PATH,
    MCPSeedCatalogService,
)
from rai_gateway.registry.service import RegistryService  # noqa: E402

MUTABLE = {
    AgentVersionStatus.DRAFT.value,
    AgentVersionStatus.REASSESSMENT_REQUIRED.value,
}


def _activate_mcp(db, server_key: str) -> tuple[MCPServer, list[ToolResource]]:
    mcp = db.query(MCPServer).filter(MCPServer.server_key == server_key).one_or_none()
    if not mcp:
        raise SystemExit(f"MCP '{server_key}' not found after seed")
    mcp.status = "ACTIVE"
    tools = (
        db.query(ToolResource)
        .filter(ToolResource.mcp_server_id == mcp.id)
        .order_by(ToolResource.tool_key)
        .all()
    )
    for tool in tools:
        if (tool.status or "").upper() in {
            "",
            "SEEDED",
            "DISCOVERED",
            "UNCLASSIFIED",
            "ACTIVE",
        }:
            tool.status = "ACTIVE"
    db.commit()
    return mcp, tools


def _ensure_mcp_dependency(
    registry: RegistryService, version: AgentVersion, mcp: MCPServer
) -> str:
    existing = (
        registry._db.query(AgentVersionDependency)
        .filter(
            AgentVersionDependency.agent_version_id == version.id,
            AgentVersionDependency.resource_type == "mcp_server",
            AgentVersionDependency.resource_id == mcp.id,
        )
        .first()
    )
    if existing:
        return "already_present"

    if version.lifecycle_status not in MUTABLE:
        raise SystemExit(
            f"Agent version {version.id} is {version.lifecycle_status}. "
            "Transition it to REASSESSMENT_REQUIRED (Version Lifecycle → Require reassessment), "
            "or create a new DRAFT version, then re-run."
        )

    registry.add_version_dependency(
        version.id, resource_type="mcp_server", resource_id=mcp.id
    )
    return "attached"


def _strip_explicit_tool_deps(
    db, version: AgentVersion, mcp: MCPServer, tools: list[ToolResource]
) -> int:
    """Remove per-tool deps so the version exposes all tools on the MCP."""
    if version.lifecycle_status not in MUTABLE:
        raise SystemExit(
            f"Agent version {version.id} is {version.lifecycle_status}; "
            "cannot strip tool deps until REASSESSMENT_REQUIRED or DRAFT."
        )
    tool_ids = {t.id for t in tools}
    if not tool_ids:
        return 0
    rows = (
        db.query(AgentVersionDependency)
        .filter(
            AgentVersionDependency.agent_version_id == version.id,
            AgentVersionDependency.resource_type == "tool",
            AgentVersionDependency.resource_id.in_(tool_ids),
        )
        .all()
    )
    removed = 0
    for row in rows:
        db.delete(row)
        removed += 1
    if removed:
        db.commit()
    return removed


def _expand_delegations(
    db, version_id: UUID, mcp: MCPServer, tools: list[ToolResource]
) -> int:
    identities = (
        db.query(AgentRuntimeIdentity)
        .filter(AgentRuntimeIdentity.agent_version_id == version_id)
        .all()
    )
    identity_ids = {i.id for i in identities}
    if not identity_ids:
        return 0

    grants = (
        db.query(DelegationGrant)
        .filter(DelegationGrant.delegate_runtime_identity_id.in_(identity_ids))
        .all()
    )
    updated = 0
    tool_ids = {str(t.id) for t in tools}
    mcp_id = str(mcp.id)
    for grant in grants:
        if (grant.status or "").upper() not in {"ACTIVE", ""}:
            continue
        scope = dict(grant.scope or {})
        mcp_ids = set(str(x) for x in (scope.get("mcp_server_ids") or []))
        scoped_tools = set(str(x) for x in (scope.get("tool_ids") or []))
        before = (frozenset(mcp_ids), frozenset(scoped_tools))
        mcp_ids.add(mcp_id)
        # Always include the full ACTIVE tool set for this MCP.
        scoped_tools |= tool_ids
        scope["mcp_server_ids"] = sorted(mcp_ids)
        scope["tool_ids"] = sorted(scoped_tools)
        after = (
            frozenset(scope.get("mcp_server_ids") or []),
            frozenset(scope.get("tool_ids") or []),
        )
        if after != before:
            grant.scope = scope
            updated += 1
    if updated:
        db.commit()
    return updated


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version-id", type=UUID, required=True)
    parser.add_argument(
        "--mcp-key",
        action="append",
        dest="mcp_keys",
        required=True,
        help="MCP server_key to seed/activate/attach (repeatable)",
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=DEFAULT_SEED_PATH,
        help="Seed catalog JSON path",
    )
    parser.add_argument(
        "--expand-delegations",
        action="store_true",
        help="Add MCP/tools into active delegation scopes for identities on this version",
    )
    parser.add_argument(
        "--mcp-only",
        action="store_true",
        default=True,
        help="Strip per-tool version deps so all MCP tools are exposed (default: true)",
    )
    parser.add_argument(
        "--keep-tool-subset",
        action="store_true",
        help="Do not strip existing per-tool version dependencies",
    )
    parser.add_argument(
        "--diagnose-only",
        action="store_true",
        help="Print version catalog exposure without mutating attachments",
    )
    args = parser.parse_args(argv)
    mcp_only = args.mcp_only and not args.keep_tool_subset

    db = SessionLocal()
    try:
        seed_result = MCPSeedCatalogService(db).seed(args.path)
        version = (
            db.query(AgentVersion).filter(AgentVersion.id == args.version_id).first()
        )
        if not version:
            raise SystemExit(f"Agent version {args.version_id} not found")

        registry = RegistryService(db)
        report: dict = {
            "seed": seed_result.to_dict(),
            "version_id": str(version.id),
            "version_status": version.lifecycle_status,
            "mcps": {},
        }

        for key in args.mcp_keys:
            mcp, tools = _activate_mcp(db, key)
            entry = {
                "mcp_id": str(mcp.id),
                "tool_count": len(tools),
                "native_tools": [
                    (t.metadata_ or {}).get("native_name") or t.tool_key for t in tools
                ],
                "status": mcp.status,
            }
            if not args.diagnose_only:
                entry["dependency"] = _ensure_mcp_dependency(registry, version, mcp)
                if mcp_only:
                    entry["tool_deps_removed"] = _strip_explicit_tool_deps(
                        db, version, mcp, tools
                    )
                if args.expand_delegations:
                    entry["delegations_updated"] = _expand_delegations(
                        db, version.id, mcp, tools
                    )
            report["mcps"][key] = entry

        # Reload version status/deps after mutations
        db.refresh(version)
        catalog = load_version_resource_catalog(db, version.id)
        report["exposed"] = {
            m.server_key: [t.native_name or t.tool_key for t in m.tools]
            for m in catalog.mcp_servers
        }
        print(json.dumps(report, indent=2))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
