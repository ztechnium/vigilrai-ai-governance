"""Support AI reference.

Start here:

  python examples/support_ai_reference/main.py

This registers the Support AI system, its model, MCP server, tools, policy,
and runtime credential, then runs the cases. RAI writes a ticket only when
the decision is ALLOW.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

LAB = Path(__file__).resolve().parents[1] / "developer_lab"
sys.path.insert(0, str(LAB))

from http_api import request_json  # noqa: E402
from provision import provision_systems  # noqa: E402
from run_case import main_for  # noqa: E402

os.environ.setdefault("RAI_TOOL_URL", "http://host.docker.internal:8765/invoke")


def _tool_runtime_up() -> bool:
    try:
        request_json("GET", "http://127.0.0.1:8765/health", timeout=2)
    except (OSError, TimeoutError):
        return False
    except Exception:
        return False
    return True


def ensure_tool_runtime() -> None:
    if _tool_runtime_up():
        return
    subprocess.Popen(
        [sys.executable, str(LAB / "tool_runtime.py")],
        cwd=str(LAB),
    )
    for _ in range(40):
        if _tool_runtime_up():
            return
        time.sleep(0.25)
    raise SystemExit("Local MCP tool runtime did not start on port 8765")


def main() -> int:
    ensure_tool_runtime()
    provision_systems(["support-ai"])
    return main_for("support-ai")


if __name__ == "__main__":
    raise SystemExit(main())
