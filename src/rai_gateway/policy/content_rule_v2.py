"""Helpers for ContentRule V2 field compatibility."""

from __future__ import annotations

from typing import Any


def intervention_points_from_applies_to(applies_to: str | None) -> list[str]:
    value = (applies_to or "BOTH").upper()
    if value == "INPUT":
        return ["INPUT"]
    if value == "OUTPUT":
        return ["OUTPUT"]
    return ["INPUT", "OUTPUT"]


def applies_to_from_intervention_points(points: list[str] | None) -> str | None:
    """Best-effort sync for legacy applies_to when points ⊆ {INPUT, OUTPUT}."""
    if not points:
        return None
    normalized = {str(p).upper() for p in points}
    if normalized == {"INPUT"}:
        return "INPUT"
    if normalized == {"OUTPUT"}:
        return "OUTPUT"
    if normalized == {"INPUT", "OUTPUT"}:
        return "BOTH"
    return None


def default_content_targets() -> dict[str, Any]:
    return {"mode": "FULL_CONTENT"}


def content_rule_coverage_status(*, enabled: bool) -> str:
    """PR1 derived coverage — full matrix lands in PR5."""
    if not enabled:
        return "DISABLED"
    return "NOT_CONFIGURED"
