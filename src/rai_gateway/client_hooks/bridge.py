"""RAI client hook bridge entry point."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import httpx

PROTOCOL_VERSION = 1
BRIDGE_VERSION = "0.1.0"


def _log(msg: str) -> None:
    print(msg, file=sys.stderr)


def _debug_enabled() -> bool:
    return os.environ.get("RAI_HOOK_DEBUG", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(
        token in lowered
        for token in (
            "authorization",
            "credential",
            "secret",
            "token",
            "password",
            "api_key",
            "apikey",
            "rai_agent_key",
        )
    )


def _redact_debug_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "***REDACTED***"
            if _is_sensitive_key(str(key))
            else _redact_debug_value(subvalue)
            for key, subvalue in value.items()
        }
    if isinstance(value, list):
        return [_redact_debug_value(item) for item in value]
    return value


def _extract_native_fields(payload: dict[str, Any]) -> tuple[Any, Any, Any]:
    """Extract native MCP/tool fields using Cursor-observed payload shape."""
    # Prefer importing shared parser when available (installed package).
    try:
        from rai_gateway.client_hooks.payload import extract_cursor_mcp_fields

        parsed = extract_cursor_mcp_fields(payload)
        return parsed.native_mcp_name, parsed.native_tool_name, parsed.parameters
    except Exception:
        native_mcp = (
            payload.get("command")
            or payload.get("mcp_server_name")
            or payload.get("mcpServerName")
            or payload.get("server_name")
            or payload.get("mcp")
        )
        native_tool = (
            payload.get("tool_name") or payload.get("toolName") or payload.get("name")
        )
        tool_input = (
            payload.get("tool_input")
            or payload.get("toolInput")
            or payload.get("arguments")
            or payload.get("input")
            or payload.get("args")
        )
        return native_mcp, native_tool, tool_input


def _emit_debug_block(
    *,
    client_type: str,
    hook_event: str,
    raw_payload: str,
    payload: dict[str, Any] | None,
    response: dict[str, Any] | None = None,
    failure_reason: str | None = None,
) -> None:
    if not _debug_enabled():
        return

    _log("=== RAI HOOK DEBUG START ===")
    _log(f"client={client_type}")
    _log(f"event={hook_event}")

    if payload is not None:
        redacted_payload = _redact_debug_value(payload)
        _log(
            f"RAW_PAYLOAD={json.dumps(redacted_payload, separators=(',', ':'), ensure_ascii=False)}"
        )
        native_mcp, native_tool, tool_input = _extract_native_fields(payload)
        _log(f"native_mcp={native_mcp}")
        _log(f"native_tool={native_tool}")
        _log(
            f"parsed_tool_input={json.dumps(_redact_debug_value(tool_input), separators=(',', ':'), ensure_ascii=False)}"
        )
        # Keep legacy key for older tests/tools.
        _log(
            f"tool_input={json.dumps(_redact_debug_value(tool_input), separators=(',', ':'), ensure_ascii=False)}"
        )
    else:
        _log(f"RAW_PAYLOAD={raw_payload}")
        _log("native_mcp=None")
        _log("native_tool=None")
        _log("parsed_tool_input=None")
        _log("tool_input=None")

    if response is not None:
        debug_info = response.get("debug") or {}
        _log(f"mapped_mcp_id={debug_info.get('mapped_mcp_id')}")
        _log(f"mapped_tool_id={debug_info.get('mapped_tool_id')}")
        if debug_info.get("mapping_failure_reason") is not None:
            _log(f"mapping_failure_reason={debug_info.get('mapping_failure_reason')}")
        decision = response.get("effect") or (
            "ALLOW" if response.get("allowed") else "DENY"
        )
        _log(f"decision={decision}")
        _log(f"reason_code={response.get('reason_code')}")
        _log(f"reason={response.get('human_explanation')}")
        correlation = response.get("receipt_id") or debug_info.get("correlation_id")
        if correlation is not None:
            _log(f"correlation_id={correlation}")
    else:
        _log("mapped_mcp_id=None")
        _log("mapped_tool_id=None")
        if failure_reason:
            _log(f"mapping_failure_reason={failure_reason}")
        _log("decision=DENY")
        _log(f"reason={failure_reason}")

    _log("=== RAI HOOK DEBUG END ===")


def _client_type_alias(raw: str) -> str:
    aliases = {
        "cursor": "cursor",
        "claude": "claude_code",
        "claude_code": "claude_code",
        "gemini": "gemini_cli",
        "gemini_cli": "gemini_cli",
    }
    return aliases.get(raw.lower(), raw.lower())


def _receipt_cache_dir() -> str:
    override = os.environ.get("RAI_HOOK_RECEIPT_CACHE")
    if override:
        return override
    return os.path.join(os.path.expanduser("~"), ".rai", "hook-receipts")


def _receipt_cache_key(client_type: str, payload: dict[str, Any]) -> str:
    native_mcp, native_tool, _ = _extract_native_fields(payload)
    session = (
        payload.get("generation_id")
        or payload.get("conversation_id")
        or payload.get("session_id")
        or "default"
    )
    tool = (
        native_tool or payload.get("tool_name") or payload.get("command") or "unknown"
    )
    mcp = native_mcp or "none"
    raw = f"{client_type}|{session}|{mcp}|{tool}"
    # Keep filesystem-safe key without hashing secrets.
    return "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in raw)[:180]


def _store_receipt_id(
    client_type: str, payload: dict[str, Any], receipt_id: str
) -> None:
    try:
        cache_dir = _receipt_cache_dir()
        os.makedirs(cache_dir, mode=0o700, exist_ok=True)
        path = os.path.join(
            cache_dir, _receipt_cache_key(client_type, payload) + ".json"
        )
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "enforcement_receipt_id": receipt_id,
                    "stored_at": __import__("time").time(),
                },
                handle,
            )
    except OSError as exc:
        _log(f"Unable to cache receipt id: {exc}")


def _load_receipt_id(client_type: str, payload: dict[str, Any]) -> str | None:
    try:
        path = os.path.join(
            _receipt_cache_dir(), _receipt_cache_key(client_type, payload) + ".json"
        )
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        receipt_id = data.get("enforcement_receipt_id")
        return str(receipt_id) if receipt_id else None
    except (OSError, json.JSONDecodeError, TypeError):
        return None


def _is_post_execution_event(client_type: str, hook_event: str) -> bool:
    mapping = {
        "cursor": {"afterMCPExecution", "afterShellExecution"},
        "claude_code": {"PostToolUse"},
        "gemini_cli": {"AfterTool"},
    }
    return hook_event in mapping.get(client_type, set())


def _is_observation_event(client_type: str, hook_event: str) -> bool:
    mapping = {
        "cursor": {
            "beforeSubmitPrompt",
            "afterAgentResponse",
            "afterAgentThought",
        },
        "claude_code": {"UserPromptSubmit", "Stop"},
        "gemini_cli": {"BeforeAgent", "BeforeModel", "AfterModel", "AfterAgent"},
    }
    return hook_event in mapping.get(client_type, set())


def _allow_response(client_type: str) -> dict[str, Any]:
    if client_type == "cursor":
        return {"permission": "allow"}
    return {"decision": "allow"}


def _call_rai(
    *,
    base_url: str,
    agent_key: str,
    client_type: str,
    hook_event: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/v1/runtime/client-hooks/authorize"
    response = httpx.post(
        url,
        json={
            "client_type": client_type,
            "hook_event": hook_event,
            "native_payload": payload,
        },
        headers={
            "Content-Type": "application/json",
            "X-RAI-Agent-Key": agent_key,
        },
        timeout=10.0,
    )
    if response.status_code == 401:
        raise RuntimeError("Runtime authentication failed")
    if response.status_code >= 500:
        raise RuntimeError(f"RAI unavailable: HTTP {response.status_code}")
    data = response.json()
    if isinstance(data, dict) and "detail" in data and response.status_code >= 400:
        raise RuntimeError(str(data["detail"]))
    return data


def _report_execution_result(
    *,
    base_url: str,
    agent_key: str,
    client_type: str,
    hook_event: str,
    payload: dict[str, Any],
    receipt_id: str | None,
) -> dict[str, Any] | None:
    if not receipt_id:
        return None
    error = (
        payload.get("error") or payload.get("error_message") or payload.get("stderr")
    )
    exit_code = payload.get("exit_code")
    success = True
    if error:
        success = False
    if exit_code not in (None, 0, "0"):
        success = False
    if payload.get("success") is False or payload.get("ok") is False:
        success = False
    status = "SUCCEEDED" if success else "FAILED"
    url = f"{base_url.rstrip('/')}/v1/runtime/client-hooks/execution-result"
    response = httpx.post(
        url,
        json={
            "enforcement_receipt_id": receipt_id,
            "client_type": client_type,
            "hook_event": hook_event,
            "status": status,
            "duration_ms": payload.get("duration_ms") or payload.get("duration"),
            "safe_result_metadata": {
                k: v
                for k, v in {
                    "error": str(error)[:200] if error else None,
                }.items()
                if v is not None
            },
            "client_event_id": payload.get("generation_id")
            or payload.get("client_event_id"),
        },
        headers={
            "Content-Type": "application/json",
            "X-RAI-Agent-Key": agent_key,
        },
        timeout=10.0,
    )
    if response.status_code >= 400:
        _log(f"execution-result report failed: HTTP {response.status_code}")
        return None
    return response.json()


def _failure_response(client_type: str, message: str) -> tuple[dict[str, Any], int]:
    if client_type == "cursor":
        return {"permission": "deny", "user_message": message}, 0
    if client_type == "claude_code":
        return {"decision": "deny", "reason": message}, 0
    return {"decision": "deny", "reason": message}, 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RAI client hook bridge")
    parser.add_argument("client_type", help="cursor | claude_code | gemini_cli")
    parser.add_argument("hook_event", help="Native hook event name")
    parser.add_argument("--protocol-version", type=int, default=PROTOCOL_VERSION)
    args = parser.parse_args(argv)

    client_type = _client_type_alias(args.client_type)
    hook_event = args.hook_event

    if args.protocol_version != PROTOCOL_VERSION:
        resp, code = _failure_response(client_type, "Unsupported protocol version")
        print(json.dumps(resp, separators=(",", ":")))
        return code

    base_url = os.environ.get("RAI_BASE_URL", "http://localhost:8001")
    raw = ""
    payload: dict[str, Any] | None = None
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        _log(f"Invalid hook JSON: {exc}")
        _emit_debug_block(
            client_type=client_type,
            hook_event=hook_event,
            raw_payload=raw,
            payload=None,
            failure_reason="Malformed hook payload",
        )
        resp, code = _failure_response(client_type, "Malformed hook payload")
        print(json.dumps(resp, separators=(",", ":")))
        return code

    agent_key = os.environ.get("RAI_AGENT_KEY", "")
    if not agent_key:
        _log("RAI_AGENT_KEY is not set")
        _emit_debug_block(
            client_type=client_type,
            hook_event=hook_event,
            raw_payload=raw,
            payload=payload if isinstance(payload, dict) else None,
            failure_reason="RAI runtime credential not configured",
        )
        # Observation hooks must never block the client when RAI is unavailable.
        if _is_observation_event(client_type, hook_event):
            print(json.dumps(_allow_response(client_type), separators=(",", ":")))
            return 0
        resp, code = _failure_response(
            client_type, "RAI runtime credential not configured"
        )
        print(json.dumps(resp, separators=(",", ":")))
        return code

    if not isinstance(payload, dict):
        _log("Invalid hook JSON: expected object payload")
        _emit_debug_block(
            client_type=client_type,
            hook_event=hook_event,
            raw_payload=raw,
            payload=None,
            failure_reason="Malformed hook payload",
        )
        resp, code = _failure_response(client_type, "Malformed hook payload")
        print(json.dumps(resp, separators=(",", ":")))
        return code

    try:
        if _is_post_execution_event(client_type, hook_event):
            receipt_id = payload.get("enforcement_receipt_id") or _load_receipt_id(
                client_type, payload
            )
            if receipt_id:
                payload = {**payload, "enforcement_receipt_id": receipt_id}
                reported = _report_execution_result(
                    base_url=base_url,
                    agent_key=agent_key,
                    client_type=client_type,
                    hook_event=hook_event,
                    payload=payload,
                    receipt_id=str(receipt_id),
                )
                if reported is not None:
                    allow = (
                        {"permission": "allow"}
                        if client_type == "cursor"
                        else {"decision": "allow"}
                    )
                    print(json.dumps(allow, separators=(",", ":")))
                    return 0

        result = _call_rai(
            base_url=base_url,
            agent_key=agent_key,
            client_type=client_type,
            hook_event=hook_event,
            payload=payload,
        )
        client_response = result.get("client_response") or {}
        exit_code = int(result.get("exit_code") or 0)
        if not result.get("allowed", False) and client_type == "gemini_cli":
            exit_code = max(exit_code, 0)
        receipt_id = result.get("receipt_id")
        if (
            receipt_id
            and result.get("allowed")
            and not _is_post_execution_event(client_type, hook_event)
        ):
            _store_receipt_id(client_type, payload, str(receipt_id))
        _emit_debug_block(
            client_type=client_type,
            hook_event=hook_event,
            raw_payload=raw,
            payload=payload,
            response=result,
        )
        print(json.dumps(client_response, separators=(",", ":")))
        return exit_code
    except Exception as exc:
        _log(f"RAI hook authorization failed: {exc}")
        _emit_debug_block(
            client_type=client_type,
            hook_event=hook_event,
            raw_payload=raw,
            payload=payload,
            failure_reason=str(exc),
        )
        if _is_observation_event(client_type, hook_event):
            print(json.dumps(_allow_response(client_type), separators=(",", ":")))
            return 0
        resp, code = _failure_response(client_type, f"RAI unavailable: {exc}")
        print(json.dumps(resp, separators=(",", ":")))
        return code


if __name__ == "__main__":
    raise SystemExit(main())
