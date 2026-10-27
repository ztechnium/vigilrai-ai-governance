#!/usr/bin/env python3
"""Seed shared Policy Library standards (idempotent).

Usage:
  python scripts/seed_policy_library.py
  python scripts/seed_policy_library.py --path data/policy_seed_catalog.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rai_gateway.core.database import SessionLocal  # noqa: E402
from rai_gateway.policy.seed_library import (  # noqa: E402
    DEFAULT_SEED_PATH,
    PolicyLibrarySeedService,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed platform policy library")
    parser.add_argument(
        "--path",
        type=Path,
        default=DEFAULT_SEED_PATH,
        help="Path to policy_seed_catalog.json",
    )
    args = parser.parse_args(argv)

    db = SessionLocal()
    try:
        result = PolicyLibrarySeedService(db).seed(args.path)
        print(json.dumps(result.to_dict(), indent=2))
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
