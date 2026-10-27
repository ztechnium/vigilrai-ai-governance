"""Deterministic condition evaluation for tool rules."""

from __future__ import annotations

import re
from typing import Any

from rai_gateway.policy.domain import (
    COLLECTION_OPERATORS,
    NUMERIC_OPERATORS,
    PRESENCE_OPERATORS,
    STRING_OPERATORS,
    ConditionOperator,
)
from rai_gateway.policy.errors import PolicyValidationError


def resolve_parameter_path(parameters: dict[str, Any], path: str) -> Any:
    """Resolve dotted parameter path from proposed action parameters."""
    if not path:
        return None
    current: Any = parameters
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        if part not in current:
            return None
        current = current[part]
    return current


def validate_regex_pattern(pattern: str) -> None:
    try:
        re.compile(pattern)
    except re.error as exc:
        raise PolicyValidationError(f"Invalid regex pattern: {exc}") from exc


def validate_operator_value(operator: str, value_type: str, value: Any) -> None:
    op = ConditionOperator(operator)
    if op in PRESENCE_OPERATORS:
        return
    if value is None and value_type != "null":
        raise PolicyValidationError(f"Operator {operator} requires a value")
    if op == ConditionOperator.REGEX:
        validate_regex_pattern(str(value))
    if op in NUMERIC_OPERATORS and value_type != "number":
        raise PolicyValidationError(f"Operator {operator} requires numeric value type")
    if op in COLLECTION_OPERATORS and value_type not in ("string", "array"):
        raise PolicyValidationError(
            f"Operator {operator} requires string or array value type"
        )


def _coerce_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def evaluate_condition(
    *,
    parameters: dict[str, Any],
    parameter_path: str,
    operator: str,
    value_type: str,
    expected: Any,
) -> tuple[bool, str]:
    actual = resolve_parameter_path(parameters, parameter_path)
    op = ConditionOperator(operator)

    if op == ConditionOperator.EXISTS:
        ok = actual is not None
        return ok, f"{parameter_path} exists={ok}"
    if op == ConditionOperator.NOT_EXISTS:
        ok = actual is None
        return ok, f"{parameter_path} not_exists={ok}"

    if op in NUMERIC_OPERATORS:
        left = _coerce_number(actual)
        right = _coerce_number(expected)
        if left is None or right is None:
            return False, f"{parameter_path}: non-numeric comparison"
        if op == ConditionOperator.GT:
            ok = left > right
        elif op == ConditionOperator.GTE:
            ok = left >= right
        elif op == ConditionOperator.LT:
            ok = left < right
        else:
            ok = left <= right
        return ok, f"{parameter_path} {actual} {operator} {expected} → {ok}"

    if op in (ConditionOperator.EQ, ConditionOperator.NEQ):
        left_num = _coerce_number(actual)
        right_num = _coerce_number(expected)
        if left_num is not None and right_num is not None:
            ok = (
                left_num == right_num
                if op == ConditionOperator.EQ
                else left_num != right_num
            )
            return ok, f"{parameter_path} {actual} {operator} {expected} → {ok}"
        left = "" if actual is None else str(actual)
        right = "" if expected is None else str(expected)
        ok = left == right if op == ConditionOperator.EQ else left != right
        return ok, f"{parameter_path} {left!r} {operator} {right!r} → {ok}"

    if op == ConditionOperator.REGEX:
        if actual is None:
            return False, f"{parameter_path}: missing for regex"
        try:
            ok = bool(re.match(str(expected), str(actual)))
        except re.error:
            return False, f"{parameter_path}: regex evaluation failed"
        return ok, f"{parameter_path} matches regex → {ok}"

    if op == ConditionOperator.IN:
        options = expected if isinstance(expected, list) else [expected]
        ok = actual in options
        return ok, f"{parameter_path} in {options} → {ok}"

    if op == ConditionOperator.NOT_IN:
        options = expected if isinstance(expected, list) else [expected]
        ok = actual not in options
        return ok, f"{parameter_path} not_in {options} → {ok}"

    if op in (ConditionOperator.CONTAINS, ConditionOperator.NOT_CONTAINS):
        if isinstance(actual, list):
            target = expected
            ok = target in actual
            if op == ConditionOperator.NOT_CONTAINS:
                ok = not ok
            return ok, f"{parameter_path} contains {expected} → {ok}"
        left = str(actual) if actual is not None else ""
        right = str(expected)
        ok = right in left
        if op == ConditionOperator.NOT_CONTAINS:
            ok = not ok
        return ok, f"{parameter_path} contains '{expected}' → {ok}"

    # String equality operators (contains, regex handled above)
    if op in STRING_OPERATORS:
        left = "" if actual is None else str(actual)
        right = "" if expected is None else str(expected)
        if op == ConditionOperator.EQ:
            ok = left == right
        else:
            ok = left != right
        return ok, f"{parameter_path} {left!r} {operator} {right!r} → {ok}"

    return False, f"unsupported operator {operator}"
