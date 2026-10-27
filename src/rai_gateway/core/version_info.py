"""Build and version metadata for health/readiness endpoints."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from functools import lru_cache
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version

SERVICE_NAME = "rai-control-plane-api"


@lru_cache(maxsize=1)
def get_service_version() -> str:
    """Return installed package version or fallback."""
    try:
        return pkg_version("rai-gateway")
    except PackageNotFoundError:
        return os.environ.get("SERVICE_VERSION", "0.1.0")


def get_commit_sha() -> str:
    """Return git commit SHA from environment (set at build/CI time)."""
    return os.environ.get("GIT_COMMIT_SHA", "unknown")


def get_build_time() -> str:
    """Return build timestamp from environment or current UTC time."""
    return os.environ.get(
        "BUILD_TIME",
        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def get_schema_revision() -> str:
    """Return Alembic head revision from environment or unknown."""
    return os.environ.get("SCHEMA_REVISION", "unknown")
