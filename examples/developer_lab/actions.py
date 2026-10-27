"""Real lab side effects. RAI calls these only after an ALLOW decision."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any
from uuid import uuid4

LAB_ROOT = Path(__file__).resolve().parent
SANDBOX_ROOT = LAB_ROOT / "sandbox"
KNOWLEDGE_ROOT = LAB_ROOT / "knowledge"
DEFAULT_STATE_DIR = LAB_ROOT / "state"

_LOCK = threading.Lock()

_COLLECTIONS = {
    "hr-policies": "hr-leave.md",
    "payroll": "payroll.md",
}

_SHELL_TOKEN = "python -c print-governed"


class ToolError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def state_path(state_dir: Path | None = None) -> Path:
    return (state_dir or DEFAULT_STATE_DIR) / "records.json"


def empty_state() -> dict[str, Any]:
    return {
        "tickets": [],
        "orders": [],
        "pull_requests": [],
        "processes": [],
        "citizen": {"id": "citizen-demo", "address": "12 Nile St"},
        "audit": [],
    }


def load_state(state_dir: Path | None = None) -> dict[str, Any]:
    path = state_path(state_dir)
    if not path.exists():
        return empty_state()
    data = json.loads(path.read_text(encoding="utf-8"))
    base = empty_state()
    base.update(data)
    return base


def save_state(state: dict[str, Any], state_dir: Path | None = None) -> None:
    path = state_path(state_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def snapshot(state_dir: Path | None = None) -> str:
    return json.dumps(load_state(state_dir), sort_keys=True)


def apply_action(
    tool_key: str,
    parameters: dict[str, Any] | None,
    *,
    state_dir: Path | None = None,
) -> dict[str, Any]:
    """Perform the tool and append an audit row. Raises ToolError on bad input."""
    params = dict(parameters or {})
    with _LOCK:
        state = load_state(state_dir)
        result = _dispatch(tool_key, params, state)
        state["audit"].append(
            {
                "id": f"audit-{uuid4().hex[:12]}",
                "tool_key": tool_key,
                "parameters": params,
                "artifact_id": result.get("artifact_id"),
            }
        )
        save_state(state, state_dir)
        return result


def _dispatch(
    tool_key: str, params: dict[str, Any], state: dict[str, Any]
) -> dict[str, Any]:
    if tool_key == "create_support_ticket":
        ticket_id = f"SUP-{len(state['tickets']) + 1001}"
        ticket = {
            "ticket_id": ticket_id,
            "priority": params.get("priority", "normal"),
            "summary": params.get("summary", ""),
            "notes": params.get("notes", ""),
            "status": "open",
        }
        state["tickets"].append(ticket)
        return {"artifact_id": ticket_id, "ticket": ticket}

    if tool_key == "create_order":
        order_id = f"ord_{uuid4().hex[:12]}"
        order = {
            "order_id": order_id,
            "amount": params.get("amount"),
            "currency": params.get("currency", "USD"),
            "account": params.get("account"),
            "status": "created",
        }
        state["orders"].append(order)
        return {"artifact_id": order_id, "order": order}

    if tool_key == "retrieve_documents":
        collection = str(params.get("collection") or "")
        filename = _COLLECTIONS.get(collection)
        if not filename:
            raise ToolError(f"Unknown collection {collection!r}")
        text = (KNOWLEDGE_ROOT / filename).read_text(encoding="utf-8")
        return {
            "artifact_id": collection,
            "collection": collection,
            "document": filename,
            "excerpt": text.strip(),
        }

    if tool_key == "read_file":
        relative = str(params.get("path") or "")
        path = _sandbox_file(relative)
        text = path.read_text(encoding="utf-8")
        return {"artifact_id": relative, "path": relative, "content": text}

    if tool_key == "run_shell":
        command = str(params.get("command") or "")
        if command != _SHELL_TOKEN:
            raise ToolError("This lab shell only runs the fixed governed command")
        completed = subprocess.run(
            [sys.executable, "-c", "print('governed')"],
            check=True,
            capture_output=True,
            text=True,
        )
        process_id = f"proc_{uuid4().hex[:8]}"
        record = {
            "process_id": process_id,
            "command": command,
            "stdout": completed.stdout.strip(),
        }
        state["processes"].append(record)
        return {"artifact_id": process_id, "process": record}

    if tool_key == "create_pull_request":
        pr_id = f"pr_{len(state['pull_requests']) + 1}"
        pull_request = {
            "pull_request_id": pr_id,
            "title": params.get("title", ""),
            "status": "open",
        }
        state["pull_requests"].append(pull_request)
        return {"artifact_id": pr_id, "pull_request": pull_request}

    if tool_key == "lookup_citizen_record":
        citizen = state["citizen"]
        field = str(params.get("field") or "address")
        if field not in citizen:
            raise ToolError(f"Unknown citizen field {field!r}")
        return {
            "artifact_id": citizen["id"],
            "field": field,
            "value": citizen[field],
        }

    if tool_key == "update_citizen_record":
        field = str(params.get("field") or "")
        if field != "address":
            raise ToolError("This lab only updates the address field")
        value = params.get("value")
        if not value:
            raise ToolError("address value is required")
        state["citizen"]["address"] = value
        return {
            "artifact_id": state["citizen"]["id"],
            "field": field,
            "value": value,
        }

    raise ToolError(f"Unknown tool {tool_key!r}", status_code=404)


def _sandbox_file(relative: str) -> Path:
    if not relative or relative.startswith(("/", "\\")) or ":" in relative:
        raise ToolError("Path must stay inside the lab sandbox")
    path = (SANDBOX_ROOT / relative).resolve()
    if SANDBOX_ROOT.resolve() not in path.parents and path != SANDBOX_ROOT.resolve():
        raise ToolError("Path must stay inside the lab sandbox")
    if not path.is_file():
        raise ToolError(f"Sandbox file not found: {relative}", status_code=404)
    return path
