"""Run developer-lab cases through RAI's execute gateway.

ALLOW calls the local MCP endpoint and changes `state/records.json`.
DENY and REQUIRE_APPROVAL do not call the tool, so the state file stays the same.

Usage:
  python examples/developer_lab/run_case.py --all
  python examples/developer_lab/run_case.py support-ai
  python examples/developer_lab/run_case.py sales-ai small-order
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any
from urllib.error import URLError
from uuid import uuid4

from actions import snapshot
from catalog import SYSTEMS, system_by_key
from http_api import ApiError, request_json
from provision import MANIFEST_PATH, _login

BLOCKING = {"DENY", "REQUIRE_APPROVAL"}


def assess_tool_case(
    *,
    expect: str,
    effect: str | None,
    execution_attempted: bool,
    execution_status: str | None,
    state_changed: bool,
) -> tuple[bool, str]:
    effect_ok = effect == expect
    if expect == "ALLOW":
        executed = (
            execution_attempted and execution_status == "SUCCEEDED" and state_changed
        )
        if effect_ok and executed:
            return True, "allowed and the MCP tool changed the workspace"
        return False, "ALLOW must execute the MCP tool and change the workspace"
    if expect in BLOCKING:
        held = (
            effect_ok
            and not execution_attempted
            and execution_status in {None, "NOT_ATTEMPTED"}
            and not state_changed
        )
        if held:
            return True, "blocked before the MCP tool ran"
        return False, f"{expect} must leave the workspace unchanged"
    return False, f"unexpected expectation {expect}"


def assess_content_case(*, expect_violated: bool, violated: bool) -> tuple[bool, str]:
    if violated == expect_violated:
        label = "matched" if violated else "clean"
        return True, f"content evaluator {label}"
    return False, "content evaluator result did not match the case"


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in {"-h", "--help"}:
        print(__doc__)
        return 0
    if args[0] == "--all":
        keys = [system["system_key"] for system in SYSTEMS]
        case_id = None
    else:
        keys = [args[0]]
        case_id = args[1] if len(args) > 1 else None
    failed = 0
    for key in keys:
        failed += main_for(key, case_id=case_id)
    return 1 if failed else 0


def main_for(system_key: str, case_id: str | None = None) -> int:
    spec = system_by_key(system_key)
    manifest = _manifest()
    system = manifest["systems"][system_key]
    base = manifest.get("base_url") or os.environ.get(
        "RAI_BASE_URL", "http://localhost:8001"
    )
    base = str(base).rstrip("/")
    _require_tool_runtime(manifest.get("tool_url"))
    cases = spec["cases"]
    if case_id:
        cases = [case for case in cases if case["id"] == case_id]
        if not cases:
            raise SystemExit(f"Unknown case {case_id!r} for {system_key}")
    print(f"\n{spec['name']} ({system_key})")
    failed = 0
    admin_token: str | None = None
    for case in cases:
        if case["kind"] == "tool":
            ok, detail = _run_tool_case(base, manifest, system, case)
        else:
            if admin_token is None:
                admin_token = _admin_token(base)
            ok, detail = _run_content_case(base, admin_token, system, case)
        mark = "PASS" if ok else "FAIL"
        print(f"  {mark}  {case['id']}: {detail}")
        if not ok:
            failed += 1
    return failed


def _run_tool_case(
    base: str,
    manifest: dict[str, Any],
    system: dict[str, Any],
    case: dict[str, Any],
) -> tuple[bool, str]:
    before = snapshot()
    payload = {
        "integration_type": "mcp",
        "integration_id": manifest["mcp_server_id"],
        "tool_id": system["tools"][case["tool"]],
        "parameters": case["parameters"],
        "environment": "DEVELOPMENT",
        "idempotency_key": f"{case['id']}-{uuid4().hex}",
    }
    try:
        body = request_json(
            "POST",
            f"{base}/v1/runtime/actions/execute",
            agent_key=system["api_key"],
            payload=payload,
        )
    except ApiError as exc:
        body = _enforcement_body(exc)
        if body is None:
            raise
    after = snapshot()
    effect = (body or {}).get("effect")
    attempted = bool((body or {}).get("execution_attempted"))
    status = (body or {}).get("execution_status")
    changed = before != after
    ok, summary = assess_tool_case(
        expect=case["expect"],
        effect=effect,
        execution_attempted=attempted,
        execution_status=status,
        state_changed=changed,
    )
    reason = (body or {}).get("human_explanation") or (body or {}).get("reason_code")
    return ok, f"{summary} (effect={effect}, execution={status}, reason={reason})"


def _run_content_case(
    base: str,
    token: str,
    system: dict[str, Any],
    case: dict[str, Any],
) -> tuple[bool, str]:
    payload = {
        "ai_system_id": system["ai_system_id"],
        "content": case["content"],
        "content_type": case.get("content_type", "OUTPUT"),
        "apply_risk": True,
        "runtime_identity_id": system.get("runtime_identity_id"),
        "agent_id": system.get("agent_id"),
        "agent_version_id": system.get("agent_version_id"),
    }
    body = request_json(
        "POST",
        f"{base}/v1/content-evaluator/evaluate",
        token=token,
        payload={key: value for key, value in payload.items() if value is not None},
    )
    evaluations = (body or {}).get("evaluations") or []
    violated = any(bool(item.get("violated")) for item in evaluations)
    ok, summary = assess_content_case(
        expect_violated=bool(case["expect_violated"]), violated=violated
    )
    risk = (body or {}).get("risk") or {}
    findings = int(risk.get("findings") or 0)
    return ok, f"{summary} (violated={violated}, findings={findings})"


def _manifest() -> dict[str, Any]:
    if not MANIFEST_PATH.exists():
        raise SystemExit(
            "Missing examples/developer_lab/.rai-lab.json. "
            "Run examples/developer_lab/provision.py first."
        )
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _require_tool_runtime(tool_url: str | None) -> None:
    del tool_url
    health = "http://127.0.0.1:8765/health"
    try:
        request_json("GET", health, timeout=3)
    except (URLError, TimeoutError, OSError) as exc:
        raise SystemExit(
            "Local MCP tool runtime is not running. Start it with "
            "python examples/developer_lab/tool_runtime.py "
            f"({exc})"
        ) from exc


def _enforcement_body(exc: ApiError) -> dict[str, Any] | None:
    body = exc.body
    if isinstance(body, dict) and "effect" not in body:
        detail = body.get("detail")
        if isinstance(detail, dict):
            body = detail
    if isinstance(body, dict) and "effect" in body:
        return body
    return None


def _admin_token(base: str) -> str:
    email = os.environ.get("RAI_ADMIN_EMAIL", "admin@raigateway.local")
    password = os.environ.get("RAI_ADMIN_PASSWORD", "ChangeMe123!")
    return _login(base, email, password)


if __name__ == "__main__":
    raise SystemExit(main())
