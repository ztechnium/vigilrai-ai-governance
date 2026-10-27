"""Unit tests for risk state scoring."""

from __future__ import annotations

from rai_gateway.risk_intelligence.risk_state import level_from_score


def test_level_from_score_boundaries():
    assert level_from_score(0, 0) == "NONE"
    assert level_from_score(10, 0) == "LOW"
    assert level_from_score(30, 0) == "MEDIUM"
    assert level_from_score(50, 0) == "HIGH"
    assert level_from_score(80, 0) == "CRITICAL"
    assert level_from_score(50, 1) == "CRITICAL"
