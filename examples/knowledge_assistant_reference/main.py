"""Knowledge assistant reference.

RAI retrieves the HR policy file. A payroll retrieval is denied, so that
document is never read into an audit row.

See examples/developer_lab/README.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "developer_lab"))

from run_case import main_for  # noqa: E402


def main() -> int:
    return main_for("knowledge-ai")


if __name__ == "__main__":
    raise SystemExit(main())
