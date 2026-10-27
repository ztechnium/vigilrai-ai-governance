"""Unit tests for registry domain logic."""

from __future__ import annotations

import pytest

from rai_gateway.registry.domain import (
    AGENT_VERSION_TRANSITIONS,
    AI_SYSTEM_TRANSITIONS,
    AgentVersionStatus,
    AISystemStatus,
    validate_lifecycle_transition,
    validate_score,
)


def test_valid_lifecycle_transition_draft_to_under_review() -> None:
    validate_lifecycle_transition(
        AISystemStatus.DRAFT.value,
        AISystemStatus.UNDER_REVIEW.value,
        AI_SYSTEM_TRANSITIONS,
        AISystemStatus,
    )


def test_invalid_lifecycle_transition_retired_to_approved() -> None:
    with pytest.raises(ValueError, match="Invalid lifecycle transition"):
        validate_lifecycle_transition(
            AISystemStatus.RETIRED.value,
            AISystemStatus.APPROVED.value,
            AI_SYSTEM_TRANSITIONS,
            AISystemStatus,
        )


def test_retired_can_reactivate_to_draft() -> None:
    validate_lifecycle_transition(
        AISystemStatus.RETIRED.value,
        AISystemStatus.DRAFT.value,
        AI_SYSTEM_TRANSITIONS,
        AISystemStatus,
    )


def test_approved_version_can_require_reassessment() -> None:
    validate_lifecycle_transition(
        AgentVersionStatus.APPROVED.value,
        AgentVersionStatus.REASSESSMENT_REQUIRED.value,
        AGENT_VERSION_TRANSITIONS,
        AgentVersionStatus,
    )


def test_approved_version_cannot_suspend() -> None:
    with pytest.raises(ValueError, match="not a valid AgentVersionStatus"):
        validate_lifecycle_transition(
            AgentVersionStatus.APPROVED.value,
            "SUSPENDED",
            AGENT_VERSION_TRANSITIONS,
            AgentVersionStatus,
        )


def test_score_validation_in_range() -> None:
    validate_score(50, "overall_score")
    validate_score(0, "overall_score")
    validate_score(100, "overall_score")


def test_score_validation_out_of_range() -> None:
    with pytest.raises(ValueError, match="overall_score must be between"):
        validate_score(101, "overall_score")
    with pytest.raises(ValueError, match="overall_score must be between"):
        validate_score(-1, "overall_score")
