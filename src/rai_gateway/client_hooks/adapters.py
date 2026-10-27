"""Client hook adapter boundary."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any
from uuid import UUID

from rai_gateway.client_hooks.domain import (
    ClientType,
    NativeHookEvent,
    NormalizedHookAction,
    ResourceMappingResult,
)
from rai_gateway.client_hooks.payload import extract_cursor_mcp_fields, parse_tool_input
from rai_gateway.runtime_enforcement.domain import (
    RuntimeActionRequest,
    RuntimeActionTarget,
)


class ClientHookAdapter(ABC):
    client_type: str
    supported_events: frozenset[str]

    @abstractmethod
    def normalize_event(
        self,
        event: NativeHookEvent,
        mapping: ResourceMappingResult,
        *,
        runtime_identity_id: UUID,
        delegation_id: UUID | None,
    ) -> NormalizedHookAction:
        """Convert native hook event + resource mapping to RuntimeActionRequest."""

    @abstractmethod
    def translate_allow(self, result: dict[str, Any]) -> dict[str, Any]:
        """Translate RAI ALLOW to client-native response."""

    @abstractmethod
    def translate_deny(
        self, result: dict[str, Any], *, blocked_by_failure: bool = False
    ) -> dict[str, Any]:
        """Translate RAI DENY/block to client-native response."""

    def is_enforced_event(self, hook_event: str) -> bool:
        return hook_event in self.supported_events

    def is_post_execution_event(self, hook_event: str) -> bool:
        from rai_gateway.client_hooks.domain import POST_EXECUTION_EVENTS

        return hook_event in POST_EXECUTION_EVENTS.get(self.client_type, frozenset())

    def is_observation_event(self, hook_event: str) -> bool:
        from rai_gateway.client_hooks.domain import OBSERVATION_EVENTS

        return hook_event in OBSERVATION_EVENTS.get(self.client_type, {})

    def observation_event_type(self, hook_event: str) -> str | None:
        from rai_gateway.client_hooks.domain import OBSERVATION_EVENTS

        return OBSERVATION_EVENTS.get(self.client_type, {}).get(hook_event)

    def _build_request(
        self,
        mapping: ResourceMappingResult,
        *,
        runtime_identity_id: UUID,
        delegation_id: UUID | None,
        correlation_id: str | None = None,
    ) -> RuntimeActionRequest:
        target = None
        if mapping.target_type:
            target = RuntimeActionTarget(type=mapping.target_type, id=mapping.target_id)
        return RuntimeActionRequest(
            integration_type=mapping.integration_type,
            integration_id=mapping.integration_id,
            tool_id=mapping.tool_id,
            target=target,
            parameters=mapping.parameters,
            delegation_id=delegation_id,
            correlation_id=correlation_id,
        )


class CursorHookAdapter(ClientHookAdapter):
    client_type = ClientType.CURSOR.value
    supported_events = frozenset({"beforeMCPExecution", "beforeShellExecution"})

    def normalize_event(
        self,
        event: NativeHookEvent,
        mapping: ResourceMappingResult,
        *,
        runtime_identity_id: UUID,
        delegation_id: UUID | None,
    ) -> NormalizedHookAction:
        payload = event.payload
        if event.hook_event in {"beforeShellExecution", "afterShellExecution"}:
            command = payload.get("command") or payload.get("shell_command") or ""
            mapping = ResourceMappingResult(
                integration_type="mcp",
                integration_id=mapping.integration_id,
                tool_id=mapping.tool_id,
                parameters={"command": command, **(mapping.parameters or {})},
            )
            return NormalizedHookAction(
                request=self._build_request(
                    mapping,
                    runtime_identity_id=runtime_identity_id,
                    delegation_id=delegation_id,
                    correlation_id=event.correlation_id,
                ),
                native_tool_name=payload.get("tool_name") or "shell",
            )

        parsed = extract_cursor_mcp_fields(payload)
        if not parsed.ok:
            raise ValueError(parsed.error_message or "Invalid hook payload")

        mapping.parameters = {**(mapping.parameters or {}), **parsed.parameters}
        return NormalizedHookAction(
            request=self._build_request(
                mapping,
                runtime_identity_id=runtime_identity_id,
                delegation_id=delegation_id,
                correlation_id=event.correlation_id,
            ),
            native_mcp_name=parsed.native_mcp_name,
            native_tool_name=parsed.native_tool_name,
        )

    def translate_allow(self, result: dict[str, Any]) -> dict[str, Any]:
        return {"permission": "allow"}

    def translate_deny(
        self, result: dict[str, Any], *, blocked_by_failure: bool = False
    ) -> dict[str, Any]:
        message = result.get("human_explanation") or "Action blocked by RAI governance"
        if result.get("effect") == "REQUIRE_APPROVAL":
            apr = result.get("approval_request_id")
            message = (
                f"RAI approval required: {apr or 'pending'}.\n"
                "Approve in RAI and retry this action."
            )
        return {"permission": "deny", "user_message": message}


class ClaudeCodeHookAdapter(ClientHookAdapter):
    client_type = ClientType.CLAUDE_CODE.value
    supported_events = frozenset({"PreToolUse"})

    def normalize_event(
        self,
        event: NativeHookEvent,
        mapping: ResourceMappingResult,
        *,
        runtime_identity_id: UUID,
        delegation_id: UUID | None,
    ) -> NormalizedHookAction:
        payload = event.payload
        tool_input = payload.get("tool_input") or payload.get("input") or {}
        if isinstance(tool_input, str):
            parameters, parse_error = parse_tool_input(tool_input)
            if parse_error:
                raise ValueError(parse_error)
            tool_input = parameters or {}
        if isinstance(tool_input, dict):
            mapping.parameters = {**mapping.parameters, **tool_input}
        return NormalizedHookAction(
            request=self._build_request(
                mapping,
                runtime_identity_id=runtime_identity_id,
                delegation_id=delegation_id,
                correlation_id=event.correlation_id,
            ),
            native_tool_name=payload.get("tool_name") or payload.get("name"),
        )

    def translate_allow(self, result: dict[str, Any]) -> dict[str, Any]:
        return {"decision": "allow"}

    def translate_deny(
        self, result: dict[str, Any], *, blocked_by_failure: bool = False
    ) -> dict[str, Any]:
        message = result.get("human_explanation") or "Action blocked by RAI governance"
        if result.get("effect") == "REQUIRE_APPROVAL":
            apr = result.get("approval_request_id")
            message = (
                f"Human approval required: {apr or 'pending'}.\n"
                "Approve in RAI and retry the tool action."
            )
        return {"decision": "deny", "reason": message}


class GeminiCLIHookAdapter(ClientHookAdapter):
    client_type = ClientType.GEMINI_CLI.value
    supported_events = frozenset({"BeforeTool"})

    def normalize_event(
        self,
        event: NativeHookEvent,
        mapping: ResourceMappingResult,
        *,
        runtime_identity_id: UUID,
        delegation_id: UUID | None,
    ) -> NormalizedHookAction:
        payload = event.payload
        tool_args = (
            payload.get("args")
            or payload.get("tool_input")
            or payload.get("input")
            or {}
        )
        if isinstance(tool_args, str):
            parameters, parse_error = parse_tool_input(tool_args)
            if parse_error:
                raise ValueError(parse_error)
            tool_args = parameters or {}
        if isinstance(tool_args, dict):
            mapping.parameters = {**mapping.parameters, **tool_args}
        return NormalizedHookAction(
            request=self._build_request(
                mapping,
                runtime_identity_id=runtime_identity_id,
                delegation_id=delegation_id,
                correlation_id=event.correlation_id,
            ),
            native_tool_name=payload.get("tool_name") or payload.get("name"),
        )

    def translate_allow(self, result: dict[str, Any]) -> dict[str, Any]:
        return {"decision": "allow"}

    def translate_deny(
        self, result: dict[str, Any], *, blocked_by_failure: bool = False
    ) -> dict[str, Any]:
        message = result.get("human_explanation") or "Action blocked by RAI governance"
        if result.get("effect") == "REQUIRE_APPROVAL":
            apr = result.get("approval_request_id")
            message = (
                f"Human approval required: {apr or 'pending'}.\n"
                "Approve in RAI and retry the tool action."
            )
        return {"decision": "deny", "reason": message}

    @property
    def critical_failure_exit_code(self) -> int:
        return 2


def get_adapter(client_type: str) -> ClientHookAdapter:
    adapters: dict[str, ClientHookAdapter] = {
        ClientType.CURSOR.value: CursorHookAdapter(),
        ClientType.CLAUDE_CODE.value: ClaudeCodeHookAdapter(),
        ClientType.GEMINI_CLI.value: GeminiCLIHookAdapter(),
    }
    adapter = adapters.get(client_type)
    if not adapter:
        raise ValueError(f"Unsupported client type: {client_type}")
    return adapter
