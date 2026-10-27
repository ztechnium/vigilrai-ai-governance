"""Citizen assistant reference.

RAI allows a record lookup. An address change waits for approval, so the
stored address is not updated. A reply that repeats a national identifier
is flagged by the content evaluator.

See examples/developer_lab/README.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "developer_lab"))

from run_case import main_for  # noqa: E402


def main() -> int:
    return main_for("citizen-assistant")


if __name__ == "__main__":
    raise SystemExit(main())
