"""Controlled MCP tool execution adapter for WP4."""

from __future__ import annotations

import ipaddress
import json
import socket
import uuid
from typing import Any
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

from rai_gateway.approval.domain import IntegrationType, ProposedAction
from rai_gateway.core.config import settings
from rai_gateway.identity.resolver import RuntimeAuthorityContext
from rai_gateway.models.registry import MCPServer, ToolResource
from rai_gateway.runtime_enforcement.adapters.base import RuntimeActionAdapter
from rai_gateway.runtime_enforcement.domain import DownstreamExecutionResult

DEMO_SIMULATED = "DEMO_SIMULATED"
PRODUCTION = "PRODUCTION"


class MCPToolExecutionAdapter(RuntimeActionAdapter):
    """Execute MCP tools using server-authoritative configuration only."""

    def __init__(
        self,
        db: Session,
        *,
        adapter_mode: str | None = None,
    ) -> None:
        self._db = db
        self._mode = (adapter_mode or settings.mcp_adapter_mode or PRODUCTION).upper()

    def supports(self, action: ProposedAction) -> bool:
        return action.integration_type == IntegrationType.MCP.value and bool(
            action.tool_id
        )

    def execute(
        self,
        action: ProposedAction,
        authority: RuntimeAuthorityContext,
    ) -> DownstreamExecutionResult:
        tool = (
            self._db.query(ToolResource)
            .filter(ToolResource.id == action.tool_id)
            .first()
        )
        if not tool:
            return DownstreamExecutionResult(
                success=False,
                error_message="Tool not found in registry",
            )

        mcp = None
        if action.integration_id:
            mcp = (
                self._db.query(MCPServer)
                .filter(MCPServer.id == action.integration_id)
                .first()
            )
        elif tool.mcp_server_id:
            mcp = (
                self._db.query(MCPServer)
                .filter(MCPServer.id == tool.mcp_server_id)
                .first()
            )

        if not mcp:
            return DownstreamExecutionResult(
                success=False,
                error_message="MCP server configuration not found",
            )

        if tool.mcp_server_id and tool.mcp_server_id != mcp.id:
            return DownstreamExecutionResult(
                success=False,
                error_message="Tool does not belong to the configured MCP server",
            )

        if mcp.status != "ACTIVE":
            return DownstreamExecutionResult(
                success=False,
                error_message=f"MCP server is {mcp.status}",
            )

        payload = self._build_invocation_payload(action, tool, mcp)
        endpoint = mcp.endpoint_reference
        if not endpoint:
            if self._mode == DEMO_SIMULATED:
                reference = (
                    f"mcp-sim:{mcp.server_key}:{tool.tool_key}:{uuid.uuid4().hex[:12]}"
                )
                return DownstreamExecutionResult(
                    success=True,
                    downstream_reference=reference,
                    result_payload={
                        "mode": "simulated",
                        "mcp_server_key": mcp.server_key,
                        "tool_key": tool.tool_key,
                        "invocation": payload,
                    },
                )
            return DownstreamExecutionResult(
                success=False,
                error_message=(
                    "CONFIGURATION_ERROR: MCP endpoint_reference is required "
                    "in PRODUCTION mode"
                ),
            )

        endpoint_error = self._validate_endpoint(endpoint)
        if endpoint_error:
            return DownstreamExecutionResult(
                success=False,
                error_message=endpoint_error,
            )

        try:
            response = httpx.post(
                endpoint,
                json=payload,
                timeout=30.0,
                headers={"Content-Type": "application/json"},
            )
            if response.status_code >= 400:
                return DownstreamExecutionResult(
                    success=False,
                    downstream_reference=str(response.headers.get("x-request-id", ""))
                    or None,
                    error_message=f"Downstream returned HTTP {response.status_code}",
                )
            body: dict[str, Any] | None = None
            if response.content:
                try:
                    body = response.json()
                except json.JSONDecodeError:
                    body = {"raw": response.text[:500]}
            body = self._mask_result_payload(body, action, authority)
            return DownstreamExecutionResult(
                success=True,
                downstream_reference=str(
                    response.headers.get("x-request-id", uuid.uuid4())
                ),
                result_payload=body,
            )
        except httpx.HTTPError as exc:
            return DownstreamExecutionResult(
                success=False,
                error_message=f"Downstream invocation failed: {exc}",
            )

    def _mask_result_payload(
        self,
        body: dict[str, Any] | list[Any] | None,
        action: ProposedAction,
        authority: RuntimeAuthorityContext,
    ) -> dict[str, Any] | list[Any] | None:
        """Apply data-access masking before tool results reach the agent/model."""
        if body is None:
            return None
        from rai_gateway.data_access.domain import DataAccessRequest
        from rai_gateway.data_access.service import DataAccessService

        sample: dict[str, Any] | None = None
        if isinstance(body, dict):
            sample = body
        elif isinstance(body, list) and body and isinstance(body[0], dict):
            sample = body[0]
        if sample is None:
            return body

        fields = list(sample.keys())
        # Mask dict payloads only; list-of-rows masking is via SDK authorize.
        if not isinstance(body, dict):
            return body
        request = DataAccessRequest(
            runtime_identity_id=authority.runtime_identity.id,
            agent_version_id=authority.agent_version.id,
            principal=None,
            data_source_id=None,
            resource=f"mcp:{action.tool_id}",
            fields=fields,
            purpose=(action.parameters or {}).get("purpose")
            if isinstance(action.parameters, dict)
            else None,
            access_mode="READ",
            tool_id=action.tool_id,
            ai_system_id=authority.ai_system.id,
            agent_id=authority.agent.id,
            payload=body,
        )
        decision = DataAccessService(self._db).authorize(request, persist_receipt=True)
        if decision.transformed_payload is None:
            return {"data_access_denied": True, "reason": decision.reason_code}
        return decision.transformed_payload  # type: ignore[return-value]

    def _validate_endpoint(self, endpoint: str) -> str | None:
        parsed = urlparse(endpoint)
        scheme = (parsed.scheme or "").lower()
        if scheme == "https":
            pass
        elif scheme == "http":
            if not settings.mcp_allow_http and self._mode == PRODUCTION:
                return (
                    "CONFIGURATION_ERROR: MCP endpoint must use https "
                    "(set mcp_allow_http only for non-production)"
                )
        else:
            return f"CONFIGURATION_ERROR: unsupported MCP endpoint scheme {scheme!r}"
        if not parsed.hostname:
            return "CONFIGURATION_ERROR: MCP endpoint missing host"

        host = parsed.hostname.lower().rstrip(".")
        allowlist_error = self._check_host_allowlist(host)
        if allowlist_error:
            return allowlist_error
        private_error = self._check_private_network(host)
        if private_error:
            return private_error
        return None

    def _check_host_allowlist(self, host: str) -> str | None:
        raw = (settings.mcp_allowed_hosts or "").strip()
        if not raw:
            return None
        allowed = [h.strip().lower() for h in raw.split(",") if h.strip()]
        if not allowed:
            return None
        for pattern in allowed:
            if pattern.startswith("*."):
                suffix = pattern[1:]  # ".example.com"
                if host == pattern[2:] or host.endswith(suffix):
                    return None
            elif host == pattern:
                return None
        return (
            "CONFIGURATION_ERROR: MCP endpoint host not in mcp_allowed_hosts "
            f"allowlist ({host!r})"
        )

    def _check_private_network(self, host: str) -> str | None:
        if settings.mcp_allow_private_hosts:
            return None
        # Block obvious local names without DNS.
        if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
            return (
                "CONFIGURATION_ERROR: MCP endpoint targets a private/local host "
                f"({host!r}); set mcp_allow_private_hosts for non-production"
            )
        try:
            addr = ipaddress.ip_address(host)
            if (
                addr.is_private
                or addr.is_loopback
                or addr.is_link_local
                or addr.is_reserved
                or addr.is_multicast
            ):
                return (
                    "CONFIGURATION_ERROR: MCP endpoint targets a private/reserved "
                    f"address ({host!r})"
                )
            return None
        except ValueError:
            pass

        # Resolve hostname and reject if any address is non-public.
        try:
            infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        except socket.gaierror:
            # Unresolvable at authorize time — fail closed in production.
            if self._mode == PRODUCTION:
                return (
                    f"CONFIGURATION_ERROR: MCP endpoint host could not be resolved "
                    f"({host!r})"
                )
            return None
        for info in infos:
            try:
                addr = ipaddress.ip_address(info[4][0])
            except (ValueError, IndexError):
                continue
            if (
                addr.is_private
                or addr.is_loopback
                or addr.is_link_local
                or addr.is_reserved
                or addr.is_multicast
            ):
                return (
                    "CONFIGURATION_ERROR: MCP endpoint resolves to a private/"
                    f"reserved address ({host!r} → {addr})"
                )
        return None

    def _build_invocation_payload(
        self,
        action: ProposedAction,
        tool: ToolResource,
        mcp: MCPServer,
    ) -> dict[str, Any]:
        return {
            "mcp_server_id": str(mcp.id),
            "mcp_server_key": mcp.server_key,
            "tool_id": str(tool.id),
            "tool_key": tool.tool_key,
            "target": action.target.to_dict() if action.target else None,
            "parameters": action.parameters,
            "environment": action.environment,
        }
