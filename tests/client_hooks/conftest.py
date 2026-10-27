"""Reuse WP4 runtime enforcement fixtures for client hook tests."""

from runtime_enforcement.conftest import (  # noqa: F401
    fake_adapter,
    registry,
    runtime_stack,
)
