"""Unit tests for policy condition evaluation."""

from __future__ import annotations

import pytest

from rai_gateway.policy.conditions import evaluate_condition, validate_regex_pattern
from rai_gateway.policy.errors import PolicyValidationError


def test_numeric_gte_match() -> None:
    ok, _ = evaluate_condition(
        parameters={"amount": 150000},
        parameter_path="amount",
        operator="gte",
        value_type="number",
        expected=100000,
    )
    assert ok is True


def test_numeric_gte_no_match() -> None:
    ok, _ = evaluate_condition(
        parameters={"amount": 50000},
        parameter_path="amount",
        operator="gte",
        value_type="number",
        expected=100000,
    )
    assert ok is False


def test_string_eq() -> None:
    ok, _ = evaluate_condition(
        parameters={"currency": "EGP"},
        parameter_path="currency",
        operator="eq",
        value_type="string",
        expected="EGP",
    )
    assert ok is True


def test_nested_path() -> None:
    ok, _ = evaluate_condition(
        parameters={"supplier": {"country": "EG"}},
        parameter_path="supplier.country",
        operator="eq",
        value_type="string",
        expected="EG",
    )
    assert ok is True


def test_exists() -> None:
    ok, _ = evaluate_condition(
        parameters={"amount": 1},
        parameter_path="amount",
        operator="exists",
        value_type="null",
        expected=None,
    )
    assert ok is True


def test_regex_validated_at_create() -> None:
    with pytest.raises(PolicyValidationError):
        validate_regex_pattern("[invalid")


def test_regex_match() -> None:
    ok, _ = evaluate_condition(
        parameters={"email": "user@example.com"},
        parameter_path="email",
        operator="regex",
        value_type="string",
        expected=r".+@example\.com",
    )
    assert ok is True
