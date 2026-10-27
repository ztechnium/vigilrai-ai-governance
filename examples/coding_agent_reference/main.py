"""Coding agent reference.

RAI allows a sandbox file read. Shell execution is denied before any process
starts. Opening a pull request waits for approval and does not write a PR.

See examples/developer_lab/README.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "developer_lab"))

from run_case import main_for  # noqa: E402


def main() -> int:
    return main_for("coding-agent")


if __name__ == "__main__":
    raise SystemExit(main())
