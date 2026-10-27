"""Register the developer catalog in a running RAI control plane.

The script is idempotent. A new runtime credential is issued only when
`.rai-lab.json` does not already hold one for that AI system.

Usage:
  set RAI_BASE_URL=http://localhost:8001
  set RAI_ADMIN_EMAIL=admin@raigateway.local
  set RAI_ADMIN_PASSWORD=ChangeMe123!
  set RAI_TOOL_URL=http://127.0.0.1:8765/invoke
  python examples/developer_lab/provision.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from catalog import (
    DEFAULT_TOOL_URL,
    MCP_NAME,
    MCP_SERVER_KEY,
    SYSTEMS,
    system_by_key,
)
from http_api import ApiError, items_of, request_json

LAB_ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = LAB_ROOT / ".rai-lab.json"


def main() -> int:
    keys = sys.argv[1:] or None
    return provision_systems(keys)


def provision_systems(system_keys: list[str] | None = None) -> int:
    specs = SYSTEMS if not system_keys else [system_by_key(key) for key in system_keys]
    base = os.environ.get("RAI_BASE_URL", "http://localhost:8001").rstrip("/")
    email = os.environ.get("RAI_ADMIN_EMAIL", "admin@raigateway.local")
    password = os.environ.get("RAI_ADMIN_PASSWORD", "ChangeMe123!")
    tool_url = os.environ.get("RAI_TOOL_URL", DEFAULT_TOOL_URL)
    token = _login(base, email, password)
    previous = _load_manifest()
    mcp = _ensure_mcp(base, token, tool_url)
    manifest: dict[str, Any] = {
        "base_url": base,
        "tool_url": tool_url,
        "mcp_server_id": mcp["id"],
        "mcp_server_key": MCP_SERVER_KEY,
        "systems": dict((previous.get("systems") or {})),
    }
    for system in specs:
        saved = manifest["systems"].get(system["system_key"]) or {}
        manifest["systems"][system["system_key"]] = _provision_system(
            base, token, system, mcp_id=mcp["id"], saved=saved
        )
        print(f"provisioned {system['system_key']}")
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"wrote {MANIFEST_PATH}")
    return 0


def _login(base: str, email: str, password: str) -> str:
    body = request_json(
        "POST",
        f"{base}/v1/auth/login",
        payload={"email": email, "password": password},
    )
    token = (body or {}).get("access_token")
    if not token:
        raise SystemExit("Login did not return an access_token")
    return token


def _load_manifest() -> dict[str, Any]:
    if not MANIFEST_PATH.exists():
        return {}
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _provision_system(
    base: str,
    token: str,
    spec: dict[str, Any],
    *,
    mcp_id: str,
    saved: dict[str, Any],
) -> dict[str, Any]:
    system = _ensure_ai_system(base, token, spec)
    model = _ensure_model(base, token, spec["model"])
    tools = {
        tool["tool_key"]: _ensure_tool(base, token, tool, mcp_id=mcp_id)
        for tool in spec["tools"]
    }
    source = _ensure_policy_source(base, token, spec["policy"])
    obligation_id = _first_obligation_id(base, token, source["id"])
    _ensure_rules(
        base,
        token,
        spec,
        system_id=system["id"],
        tools=tools,
        mcp_id=mcp_id,
        source_id=source["id"],
        obligation_id=obligation_id,
    )
    if spec["content_rules"]:
        _ensure_mock_evaluator(base, token, system["id"])
    agent = _ensure_agent(base, token, system["id"], spec)
    version = _ensure_version(base, token, agent["id"])
    _ensure_dependencies(
        base,
        token,
        version_id=version["id"],
        model_id=model["id"],
        mcp_id=mcp_id,
        tool_ids=[tool["id"] for tool in tools.values()],
    )
    _approve_for_execution(
        base,
        token,
        system_id=system["id"],
        system_status=system.get("status"),
        agent_id=agent["id"],
        agent_status=agent.get("status"),
        version_id=version["id"],
        version_status=version.get("lifecycle_status"),
    )
    identity = _ensure_identity(
        base, token, agent["id"], version["id"], spec["system_key"]
    )
    api_key = saved.get("api_key")
    if not api_key or saved.get("runtime_identity_id") != identity["id"]:
        issued = request_json(
            "POST",
            f"{base}/v1/runtime-identities/{identity['id']}/credentials",
            token=token,
            payload={},
        )
        api_key = issued["plaintext_secret"]
    integration = _ensure_integration(base, token, spec["system_key"], identity["id"])
    return {
        "ai_system_id": system["id"],
        "model_id": model["id"],
        "agent_id": agent["id"],
        "agent_version_id": version["id"],
        "runtime_identity_id": identity["id"],
        "integration_id": integration["id"],
        "api_key": api_key,
        "policy_source_id": source["id"],
        "tools": {key: value["id"] for key, value in tools.items()},
    }


def _ensure_ai_system(base: str, token: str, spec: dict[str, Any]) -> dict:
    listed = request_json("GET", f"{base}/v1/ai-systems", token=token)
    for row in items_of(listed):
        if row.get("system_key") == spec["system_key"]:
            return row
    return request_json(
        "POST",
        f"{base}/v1/ai-systems",
        token=token,
        payload={
            "system_key": spec["system_key"],
            "name": spec["name"],
            "description": spec["description"],
            "business_purpose": spec["business_purpose"],
            "risk_tier": spec["risk_tier"],
            "data_classification": spec["data_classification"],
        },
    )


def _ensure_model(base: str, token: str, model: dict[str, Any]) -> dict:
    listed = request_json("GET", f"{base}/v1/registry/models", token=token)
    for row in items_of(listed):
        if (
            row.get("provider") == model["provider"]
            and row.get("model_name") == model["model_name"]
            and row.get("model_version") == model.get("model_version")
        ):
            return row
    return request_json(
        "POST",
        f"{base}/v1/registry/models",
        token=token,
        payload=model,
    )


def _ensure_mcp(base: str, token: str, tool_url: str) -> dict:
    listed = request_json("GET", f"{base}/v1/registry/mcp-servers", token=token)
    existing = next(
        (row for row in items_of(listed) if row.get("server_key") == MCP_SERVER_KEY),
        None,
    )
    if existing:
        return request_json(
            "PATCH",
            f"{base}/v1/registry/mcp-servers/{existing['id']}",
            token=token,
            payload={
                "endpoint_reference": tool_url,
                "name": MCP_NAME,
                "environment": "DEVELOPMENT",
            },
        )
    return request_json(
        "POST",
        f"{base}/v1/registry/mcp-servers",
        token=token,
        payload={
            "server_key": MCP_SERVER_KEY,
            "name": MCP_NAME,
            "description": "Local MCP endpoint used by the developer lab examples.",
            "provider": "developer-lab",
            "environment": "DEVELOPMENT",
            "endpoint_reference": tool_url,
            "trust_classification": "INTERNAL",
        },
    )


def _ensure_tool(base: str, token: str, tool: dict[str, Any], *, mcp_id: str) -> dict:
    listed = request_json("GET", f"{base}/v1/registry/tools", token=token)
    for row in items_of(listed):
        if row.get("tool_key") == tool["tool_key"]:
            row.setdefault("mcp_server_id", mcp_id)
            if row.get("consequential_action") != tool["consequential_action"]:
                request_json(
                    "PATCH",
                    f"{base}/v1/registry/tools/{row['id']}",
                    token=token,
                    payload={"consequential_action": tool["consequential_action"]},
                )
                row["consequential_action"] = tool["consequential_action"]
            return row
    created = request_json(
        "POST",
        f"{base}/v1/registry/tools",
        token=token,
        payload={
            "tool_key": tool["tool_key"],
            "name": tool["name"],
            "description": tool["description"],
            "category": tool["category"],
            "provider": "developer-lab",
            "mcp_server_id": mcp_id,
            "consequential_action": tool["consequential_action"],
        },
    )
    created["mcp_server_id"] = created.get("mcp_server_id") or mcp_id
    return created


def _ensure_policy_source(base: str, token: str, policy: dict[str, Any]) -> dict:
    listed = request_json(
        "GET",
        f"{base}/v1/policy-library?search={_query(policy['title'])}&limit=50",
        token=token,
    )
    for row in items_of(listed):
        if row.get("title") == policy["title"]:
            return row
    return request_json(
        "POST",
        f"{base}/v1/policy-library",
        token=token,
        payload={
            "title": policy["title"],
            "source_type": "MANUAL_TEXT",
            "authority": policy["authority"],
            "jurisdiction": policy["jurisdiction"],
            "policy_type": policy["policy_type"],
            "version": policy["version"],
            "content_text": policy["content_text"],
        },
    )


def _first_obligation_id(base: str, token: str, source_id: str) -> str | None:
    detail = request_json("GET", f"{base}/v1/policy-library/{source_id}", token=token)
    obligations = (detail or {}).get("obligations") or []
    if not obligations:
        return None
    return obligations[0]["id"]


def _ensure_rules(
    base: str,
    token: str,
    spec: dict[str, Any],
    *,
    system_id: str,
    tools: dict[str, dict],
    mcp_id: str,
    source_id: str,
    obligation_id: str | None,
) -> None:
    existing = request_json(
        "GET",
        f"{base}/v1/rai-rules?ai_system_id={system_id}&limit=200",
        token=token,
    )
    titles = {row.get("title") for row in items_of(existing)}
    for rule in spec["content_rules"]:
        if rule["title"] in titles:
            continue
        request_json(
            "POST",
            f"{base}/v1/ai-systems/{system_id}/policies/content-rules",
            token=token,
            payload={
                **rule,
                "source_policy_id": source_id,
                "source_obligation_id": obligation_id,
            },
        )
    for rule in spec["tool_rules"]:
        if rule["title"] in titles:
            continue
        request_json(
            "POST",
            f"{base}/v1/ai-systems/{system_id}/policies/tool-rules",
            token=token,
            payload={
                "title": rule["title"],
                "description": rule.get("description"),
                "mcp_server_id": mcp_id,
                "tool_id": tools[rule["tool_key"]]["id"],
                "effect": rule["effect"],
                "required_approver_role": rule.get("required_approver_role"),
                "severity": rule.get("severity"),
                "category": rule.get("category"),
                "conditions": rule.get("conditions") or [],
                "source_policy_id": source_id,
                "source_obligation_id": obligation_id,
            },
        )


def _ensure_mock_evaluator(base: str, token: str, system_id: str) -> None:
    request_json(
        "PUT",
        f"{base}/v1/content-evaluator/config",
        token=token,
        payload={
            "ai_system_id": system_id,
            "provider": "mock",
            "model": "mock-keyword",
            "enabled": True,
            "minimum_confidence_to_intervene": 0.9,
        },
    )


def _ensure_agent(base: str, token: str, system_id: str, spec: dict[str, Any]) -> dict:
    listed = request_json(
        "GET", f"{base}/v1/ai-systems/{system_id}/agents", token=token
    )
    for row in items_of(listed):
        if row.get("agent_key") == spec["agent_key"]:
            return row
    return request_json(
        "POST",
        f"{base}/v1/ai-systems/{system_id}/agents",
        token=token,
        payload={
            "agent_key": spec["agent_key"],
            "name": spec["agent_name"],
            "description": spec["description"],
            "business_purpose": spec["business_purpose"],
        },
    )


def _ensure_version(base: str, token: str, agent_id: str) -> dict:
    listed = request_json("GET", f"{base}/v1/agents/{agent_id}/versions", token=token)
    rows = items_of(listed)
    if rows:
        return rows[0]
    return request_json(
        "POST",
        f"{base}/v1/agents/{agent_id}/versions",
        token=token,
        payload={
            "change_summary": "Developer lab version bound to the local MCP tools.",
            "risk_tier": "MEDIUM",
            "configuration_snapshot": {
                "source": "examples/developer_lab",
                "execution": "rai_runtime_execute",
            },
        },
    )


def _ensure_dependencies(
    base: str,
    token: str,
    *,
    version_id: str,
    model_id: str,
    mcp_id: str,
    tool_ids: list[str],
) -> None:
    listed = request_json(
        "GET",
        f"{base}/v1/agent-versions/{version_id}/dependencies",
        token=token,
    )
    present = {
        (row.get("resource_type"), row.get("resource_id")) for row in items_of(listed)
    }
    pairs = [("model", model_id), ("mcp_server", mcp_id)]
    pairs.extend(("tool", tool_id) for tool_id in tool_ids)
    for resource_type, resource_id in pairs:
        if (resource_type, resource_id) in present:
            continue
        try:
            request_json(
                "POST",
                f"{base}/v1/agent-versions/{version_id}/dependencies",
                token=token,
                payload={
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "usage_purpose": "developer-lab",
                    "required": True,
                },
            )
        except ApiError as exc:
            if exc.status != 409:
                raise


def _approve_for_execution(
    base: str,
    token: str,
    *,
    system_id: str,
    system_status: str | None,
    agent_id: str,
    agent_status: str | None,
    version_id: str,
    version_status: str | None,
) -> None:
    """Runtime execution rechecks that the system, agent, and version are approved."""
    _advance_lifecycle(
        base,
        token,
        f"{base}/v1/ai-systems/{system_id}/lifecycle",
        system_status,
        status_field="status",
    )
    _advance_lifecycle(
        base,
        token,
        f"{base}/v1/agents/{agent_id}/lifecycle",
        agent_status,
        status_field="status",
    )
    _advance_lifecycle(
        base,
        token,
        f"{base}/v1/agent-versions/{version_id}/lifecycle",
        version_status,
        status_field="lifecycle_status",
    )


def _advance_lifecycle(
    base: str,
    token: str,
    url: str,
    status: str | None,
    *,
    status_field: str,
) -> None:
    del base
    current = status or "DRAFT"
    if current == "APPROVED":
        return
    for target in ("UNDER_REVIEW", "APPROVED"):
        if current == "APPROVED":
            return
        if current == target:
            continue
        body = request_json("POST", url, token=token, payload={"status": target})
        current = (body or {}).get(status_field) or target


def _ensure_identity(
    base: str, token: str, agent_id: str, version_id: str, system_key: str
) -> dict:
    name = f"{system_key}-dev"
    listed = request_json(
        "GET",
        f"{base}/v1/runtime-identities?agent_id={agent_id}",
        token=token,
    )
    for row in items_of(listed):
        if row.get("name") == name and row.get("agent_version_id") == version_id:
            return row
    return request_json(
        "POST",
        f"{base}/v1/runtime-identities",
        token=token,
        payload={
            "agent_id": agent_id,
            "agent_version_id": version_id,
            "name": name,
            "environment": "DEVELOPMENT",
        },
    )


def _ensure_integration(
    base: str, token: str, system_key: str, identity_id: str
) -> dict:
    key = f"{system_key}-sdk"
    listed = request_json("GET", f"{base}/v1/productization/integrations", token=token)
    for row in items_of(listed):
        if row.get("integration_key") == key:
            return row
    return request_json(
        "POST",
        f"{base}/v1/productization/integrations",
        token=token,
        payload={
            "integration_key": key,
            "name": f"{system_key} developer integration",
            "runtime_identity_id": identity_id,
            "integration_type": "SDK",
            "environment": "DEVELOPMENT",
            "auth_method": "API_KEY",
            "enforcement_mode": "HOOK_ENFORCED",
            "fail_closed": True,
        },
    )


def _query(value: str) -> str:
    from urllib.parse import quote

    return quote(value)


if __name__ == "__main__":
    raise SystemExit(main())
