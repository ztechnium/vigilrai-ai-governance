"""Liveness, readiness, and version endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from rai_gateway.core.database import engine
from rai_gateway.core.version_info import (
    SERVICE_NAME,
    get_build_time,
    get_commit_sha,
    get_schema_revision,
    get_service_version,
)

router = APIRouter(tags=["health"])


@router.get("/health")
async def liveness() -> dict[str, str]:
    """Process liveness probe — no dependency checks."""
    return {"status": "healthy", "service": SERVICE_NAME}


@router.get("/ready")
async def readiness() -> dict[str, Any]:
    """Readiness probe — checks critical dependencies without exposing secrets."""
    checks: dict[str, str] = {}
    all_ready = True

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["postgresql"] = "ok"
    except SQLAlchemyError:
        checks["postgresql"] = "unavailable"
        all_ready = False

    return {
        "status": "ready" if all_ready else "not_ready",
        "service": SERVICE_NAME,
        "checks": checks,
    }


@router.get("/version")
async def version_info() -> dict[str, str]:
    """Non-sensitive build and schema metadata."""
    return {
        "service": SERVICE_NAME,
        "version": get_service_version(),
        "commit": get_commit_sha(),
        "build_time": get_build_time(),
        "schema_revision": get_schema_revision(),
    }
