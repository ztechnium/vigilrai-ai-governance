"""Sales AI reference.

RAI creates the order through the local MCP tool only when the amount is
inside the policy. Larger orders are held or denied, and no order is written.

See examples/developer_lab/README.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "developer_lab"))

from run_case import main_for  # noqa: E402


def main() -> int:
    return main_for("sales-ai")


if __name__ == "__main__":
    raise SystemExit(main())
