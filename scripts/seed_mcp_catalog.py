#!/usr/bin/env python3
"""Seed the enterprise MCP catalog (idempotent).

Usage:
  python scripts/seed_mcp_catalog.py
  python scripts/seed_mcp_catalog.py --path data/mcp_seed_catalog.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running from repo root without install.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rai_gateway.core.database import SessionLocal  # noqa: E402
from rai_gateway.registry.seed_mcp_catalog import (  # noqa: E402
    DEFAULT_SEED_PATH,
    MCPSeedCatalogService,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed enterprise MCP catalog")
    parser.add_argument(
        "--path",
        type=Path,
        default=DEFAULT_SEED_PATH,
        help="Path to mcp_seed_catalog.json",
    )
    args = parser.parse_args(argv)

    db = SessionLocal()
    try:
        result = MCPSeedCatalogService(db).seed(args.path)
        print(json.dumps(result.to_dict(), indent=2))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
