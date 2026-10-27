"""Tests for deterministic action canonicalization."""

from __future__ import annotations

from uuid import UUID

from rai_gateway.approval.canonicalizer import canonicalize_action
from rai_gateway.approval.domain import ActionTarget, ProposedAction


def _sample_action(**overrides) -> ProposedAction:
    base = {
        "ai_system_id": UUID("00000000-0000-0000-0000-000000000001"),
        "agent_id": UUID("00000000-0000-0000-0000-000000000002"),
        "agent_version_id": UUID("00000000-0000-0000-0000-000000000003"),
        "runtime_identity_id": UUID("00000000-0000-0000-0000-000000000004"),
        "delegation_id": UUID("00000000-0000-0000-0000-000000000005"),
        "integration_type": "mcp",
        "integration_id": UUID("00000000-0000-0000-0000-000000000006"),
        "tool_id": UUID("00000000-0000-0000-0000-000000000007"),
        "target": ActionTarget(type="Customer", id="CUST-100"),
        "parameters": {"status": "Active", "amount": 125000},
    }
    base.update(overrides)
    return ProposedAction(**base)


def test_canonicalization_is_deterministic() -> None:
    action = _sample_action()
    payload_a, digest_a = canonicalize_action(action)
    payload_b, digest_b = canonicalize_action(action)
    assert payload_a == payload_b
    assert digest_a == digest_b
    assert len(digest_a) == 64


def test_parameter_change_changes_digest() -> None:
    action_a = _sample_action(parameters={"amount": 125000})
    action_b = _sample_action(parameters={"amount": 150000})
    _, digest_a = canonicalize_action(action_a)
    _, digest_b = canonicalize_action(action_b)
    assert digest_a != digest_b
