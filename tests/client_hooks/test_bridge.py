"""Bridge stdout/stderr tests."""

from __future__ import annotations

import io
import json
from typing import Any

import pytest

from rai_gateway.client_hooks import bridge


class _CountingStdin(io.StringIO):
    def __init__(self, value: str) -> None:
        super().__init__(value)
        self.read_count = 0

    def read(self, *args, **kwargs):  # type: ignore[override]
        self.read_count += 1
        return super().read(*args, **kwargs)


class _FakeResponse:
    def __init__(self, payload: dict[str, object], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> dict[str, object]:
        return self._payload


def _fake_post(payload: dict[str, object]) -> Any:
    def _post(*args, **kwargs):
        return _FakeResponse(payload)

    return _post


def test_bridge_reads_stdin_once_and_logs_debug_to_stderr_only(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("RAI_BASE_URL", "http://localhost:8001")
    monkeypatch.setenv("RAI_AGENT_KEY", "bridge-secret")
    monkeypatch.setenv("RAI_HOOK_DEBUG", "1")
    stdin = _CountingStdin(
        json.dumps(
            {
                "mcp_server_name": "cursor-mcp",
                "tool_name": "submit_po",
                "tool_input": {
                    "authorization": "Bearer secret-token",
                    "credential_secret": "cred-123",
                    "api_key": "api-456",
                    "nested": {"password": "pw-789"},
                },
            }
        )
    )
    monkeypatch.setattr(bridge.sys, "stdin", stdin)
    monkeypatch.setattr(
        bridge.httpx,
        "post",
        _fake_post(
            {
                "allowed": True,
                "effect": "ALLOW",
                "reason_code": None,
                "human_explanation": "Authorized",
                "client_response": {"permission": "allow"},
                "enforcement_result": {"effect": "ALLOW"},
                "debug": {
                    "mapped_mcp_id": "11111111-1111-1111-1111-111111111111",
                    "mapped_tool_id": "22222222-2222-2222-2222-222222222222",
                    "mapping_failure_reason": None,
                },
                "exit_code": 0,
            }
        ),
    )

    exit_code = bridge.main(["cursor", "beforeMCPExecution"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert stdin.read_count == 1
    assert json.loads(captured.out) == {"permission": "allow"}
    assert "=== RAI HOOK DEBUG START ===" in captured.err
    assert "client=cursor" in captured.err
    assert "event=beforeMCPExecution" in captured.err
    assert "mapped_mcp_id=11111111-1111-1111-1111-111111111111" in captured.err
    assert "mapped_tool_id=22222222-2222-2222-2222-222222222222" in captured.err
    assert "decision=ALLOW" in captured.err
    assert "reason_code=None" in captured.err
    assert "secret-token" not in captured.err
    assert "cred-123" not in captured.err
    assert "api-456" not in captured.err
    assert "pw-789" not in captured.err
    assert "bridge-secret" not in captured.err
    assert "secret-token" not in captured.out


def test_bridge_debug_disabled_by_default(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("RAI_HOOK_DEBUG", raising=False)
    monkeypatch.setenv("RAI_BASE_URL", "http://localhost:8001")
    monkeypatch.setenv("RAI_AGENT_KEY", "bridge-secret")
    monkeypatch.setattr(bridge.sys, "stdin", _CountingStdin("{}"))
    monkeypatch.setattr(
        bridge.httpx,
        "post",
        _fake_post(
            {
                "allowed": False,
                "effect": "DENY",
                "reason_code": "POLICY_DENIED",
                "human_explanation": "Blocked",
                "client_response": {"permission": "deny"},
                "enforcement_result": {"effect": "DENY"},
                "debug": {
                    "mapped_mcp_id": "11111111-1111-1111-1111-111111111111",
                    "mapped_tool_id": "22222222-2222-2222-2222-222222222222",
                },
                "exit_code": 0,
            }
        ),
    )

    exit_code = bridge.main(["cursor", "beforeMCPExecution"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert json.loads(captured.out) == {"permission": "deny"}
    assert "=== RAI HOOK DEBUG START ===" not in captured.err
    assert "mapped_mcp_id=" not in captured.err
    assert "decision=" not in captured.err


def test_bridge_missing_key_exits_gemini_with_json_only_on_stdout(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("RAI_AGENT_KEY", raising=False)
    monkeypatch.setenv("RAI_BASE_URL", "http://localhost:8001")
    monkeypatch.delenv("RAI_HOOK_DEBUG", raising=False)
    monkeypatch.setattr(bridge.sys, "stdin", _CountingStdin("{}"))

    exit_code = bridge.main(["gemini", "BeforeTool"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out.strip().startswith("{")
    json.loads(captured.out)
    assert "RAI_AGENT_KEY is not set" in captured.err


def test_bridge_observation_fail_open_without_credential(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("RAI_AGENT_KEY", raising=False)
    monkeypatch.setenv("RAI_BASE_URL", "http://localhost:8001")
    monkeypatch.setattr(bridge.sys, "stdin", _CountingStdin('{"prompt":"hi"}'))

    exit_code = bridge.main(["cursor", "beforeSubmitPrompt"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert json.loads(captured.out) == {"permission": "allow"}
    assert "RAI_AGENT_KEY is not set" in captured.err
