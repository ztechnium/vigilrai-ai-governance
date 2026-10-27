"""CLI for VigilRAI background workers."""

from __future__ import annotations

from rai_gateway.workers.runtime_events import main

if __name__ == "__main__":
    raise SystemExit(main())
