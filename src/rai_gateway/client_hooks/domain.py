"""Domain types for WP4 client hook adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import UUID

from rai_gateway.runtime_enforcement.domain import EnforcementMode, RuntimeActionRequest

PROTOCOL_VERSION = 1
BRIDGE_VERSION = "0.1.0"


class ClientType(StrEnum):
    CURSOR = "cursor"
    CLAUDE_CODE = "claude_code"
    GEMINI_CLI = "gemini_cli"


class IntegrationStatus(StrEnum):
    NOT_CONFIGURED = "NOT_CONFIGURED"
    WAITING_FOR_HEARTBEAT = "WAITING_FOR_HEARTBEAT"
    CONNECTED = "CONNECTED"
    DEGRADED = "DEGRADED"
    DISCONNECTED = "DISCONNECTED"


DEFAULT_COVERAGE: dict[str, dict[str, str]] = {
    ClientType.CURSOR.value: {
        "mcp_authorization": "ENFORCED",
        "shell_authorization": "ENFORCED",
        "mcp_execution_result": "REPORTED",
        "prompt": "OBSERVE_ONLY",
        "model_output": "OBSERVE_ONLY",
        # Legacy keys retained for older UI consumers.
        "mcp_tools": EnforcementMode.HOOK_ENFORCED.value,
        "shell": EnforcementMode.HOOK_ENFORCED.value,
        "output": EnforcementMode.OBSERVE_ONLY.value,
        "cloud_agents": EnforcementMode.OBSERVE_ONLY.value,
        "post_execution": "REPORTED",
    },
    ClientType.CLAUDE_CODE.value: {
        "tool_authorization": "ENFORCED",
        "tool_execution_result": "REPORTED",
        "prompt": "OBSERVE_ONLY",
        "tools": EnforcementMode.HOOK_ENFORCED.value,
        "post_execution": "REPORTED",
    },
    ClientType.GEMINI_CLI.value: {
        "tool_authorization": "ENFORCED",
        "tool_execution_result": "REPORTED",
        "prompt": "OBSERVE_ONLY",
        "agent": EnforcementMode.OBSERVE_ONLY.value,
        "model_request": EnforcementMode.OBSERVE_ONLY.value,
        "model_output": EnforcementMode.OBSERVE_ONLY.value,
        "tools": EnforcementMode.HOOK_ENFORCED.value,
        "post_execution": "REPORTED",
    },
}

COVERAGE_DISCLAIMER = (
    "CONNECTED does not imply complete enforcement. Coverage is per-capability; "
    "local hooks may be modified or removed by users with sufficient local access."
)

POST_EXECUTION_EVENTS: dict[str, frozenset[str]] = {
    ClientType.CURSOR.value: frozenset({"afterMCPExecution", "afterShellExecution"}),
    ClientType.CLAUDE_CODE.value: frozenset({"PostToolUse"}),
    ClientType.GEMINI_CLI.value: frozenset({"AfterTool"}),
}

# Observe-only lifecycle hooks — never enforcement. Mapped to WP5 evidence events.
OBSERVATION_EVENTS: dict[str, dict[str, str]] = {
    ClientType.CURSOR.value: {
        "beforeSubmitPrompt": "PROMPT_OBSERVED",
        "afterAgentResponse": "AGENT_OUTPUT_OBSERVED",
        "afterAgentThought": "MODEL_RESPONSE_OBSERVED",
    },
    ClientType.CLAUDE_CODE.value: {
        "UserPromptSubmit": "PROMPT_OBSERVED",
        "Stop": "AGENT_OUTPUT_OBSERVED",
    },
    ClientType.GEMINI_CLI.value: {
        "BeforeAgent": "PROMPT_OBSERVED",
        "BeforeModel": "MODEL_REQUEST_OBSERVED",
        "AfterModel": "MODEL_RESPONSE_OBSERVED",
        "AfterAgent": "AGENT_OUTPUT_OBSERVED",
    },
}


@dataclass
class NativeHookEvent:
    client_type: str
    hook_event: str
    payload: dict[str, Any]
    delegation_id: UUID | None = None
    correlation_id: str | None = None


@dataclass
class ResourceMappingResult:
    integration_type: str
    integration_id: UUID | None
    tool_id: UUID | None
    target_type: str | None = None
    target_id: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None

    @property
    def ok(self) -> bool:
        return self.error_code is None and self.tool_id is not None


@dataclass
class HookAuthorizeResult:
    allowed: bool
    effect: str
    reason_code: str | None
    human_explanation: str
    client_response: dict[str, Any]
    enforcement_result: dict[str, Any]
    debug: dict[str, Any] | None = None
    receipt_id: UUID | None = None
    approval_request_id: UUID | None = None
    exit_code: int = 0

    def to_dict(self) -> dict[str, Any]:
        data = {
            "allowed": self.allowed,
            "effect": self.effect,
            "reason_code": self.reason_code,
            "human_explanation": self.human_explanation,
            "client_response": self.client_response,
            "enforcement_result": self.enforcement_result,
            "receipt_id": str(self.receipt_id) if self.receipt_id else None,
            "approval_request_id": str(self.approval_request_id)
            if self.approval_request_id
            else None,
            "exit_code": self.exit_code,
        }
        if self.debug is not None:
            data["debug"] = self.debug
        return data


@dataclass
class NormalizedHookAction:
    request: RuntimeActionRequest
    native_tool_name: str | None = None
    native_mcp_name: str | None = None
