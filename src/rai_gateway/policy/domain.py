"""Domain types for AI System policy collection and evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

# Effect precedence (highest wins): DENY > REQUIRE_APPROVAL > MONITOR > MARK > ALLOW
EFFECT_PRECEDENCE: dict[str, int] = {
    "DENY": 5,
    "REQUIRE_APPROVAL": 4,
    "MONITOR": 3,
    "MARK": 2,
    "ALLOW": 1,
}


class PolicyEffect(StrEnum):
    ALLOW = "ALLOW"
    MARK = "MARK"
    MONITOR = "MONITOR"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    DENY = "DENY"


class PolicyControlDomain(StrEnum):
    ACCESS = "ACCESS"
    ACTION = "ACTION"
    CONTENT = "CONTENT"
    DATA = "DATA"
    BUDGET = "BUDGET"
    RISK = "RISK"


class PolicyInterventionPoint(StrEnum):
    INPUT = "INPUT"
    PRE_MODEL = "PRE_MODEL"
    POST_MODEL = "POST_MODEL"
    PRE_TOOL = "PRE_TOOL"
    POST_TOOL = "POST_TOOL"
    OUTPUT = "OUTPUT"


class ContentEvaluationType(StrEnum):
    REGEX = "REGEX"
    KEYWORD = "KEYWORD"
    DETECTOR = "DETECTOR"
    SEMANTIC = "SEMANTIC"
    EXTERNAL = "EXTERNAL"
    LLM_JUDGE = "LLM_JUDGE"


class ContentFailureMode(StrEnum):
    INHERIT = "INHERIT"
    FAIL_OPEN = "FAIL_OPEN"
    FAIL_CLOSED = "FAIL_CLOSED"
    MONITOR_ONLY = "MONITOR_ONLY"


class ContentRemediationType(StrEnum):
    NONE = "NONE"
    MASK = "MASK"
    REDACT = "REDACT"
    REPLACE = "REPLACE"


class PolicyEnforceability(StrEnum):
    INLINE = "INLINE"
    OBSERVE_ONLY = "OBSERVE_ONLY"
    NOT_AVAILABLE = "NOT_AVAILABLE"


class MatchMode(StrEnum):
    ALL = "ALL"
    ANY = "ANY"


class ConditionOperator(StrEnum):
    EQ = "eq"
    NEQ = "neq"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    IN = "in"
    NOT_IN = "not_in"
    REGEX = "regex"
    EXISTS = "exists"
    NOT_EXISTS = "not_exists"


class ValueType(StrEnum):
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ARRAY = "array"
    NULL = "null"


NUMERIC_OPERATORS = frozenset(
    {
        ConditionOperator.GT,
        ConditionOperator.GTE,
        ConditionOperator.LT,
        ConditionOperator.LTE,
    }
)
COMPARISON_OPERATORS = frozenset(
    {ConditionOperator.EQ, ConditionOperator.NEQ, *NUMERIC_OPERATORS}
)
STRING_OPERATORS = frozenset(
    {
        ConditionOperator.EQ,
        ConditionOperator.NEQ,
        ConditionOperator.CONTAINS,
        ConditionOperator.NOT_CONTAINS,
        ConditionOperator.REGEX,
    }
)
COLLECTION_OPERATORS = frozenset(
    {
        ConditionOperator.CONTAINS,
        ConditionOperator.NOT_CONTAINS,
        ConditionOperator.IN,
        ConditionOperator.NOT_IN,
    }
)
PRESENCE_OPERATORS = frozenset({ConditionOperator.EXISTS, ConditionOperator.NOT_EXISTS})


def dominant_effect(effects: list[str]) -> str:
    if not effects:
        return PolicyEffect.ALLOW.value
    return max(effects, key=lambda e: EFFECT_PRECEDENCE.get(e, 0))


@dataclass
class PolicyDecision:
    effect: str
    matched_policy_ids: list[str] = field(default_factory=list)
    matched_rule_ids: list[str] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)
    human_explanation: str = ""
    monitoring_instruction: str | None = None
    required_approver_role: str | None = None
    matched_content_rule_ids: list[str] = field(default_factory=list)
    matched_tool_rule_ids: list[str] = field(default_factory=list)
    condition_details: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "effect": self.effect,
            "matched_policy_ids": self.matched_policy_ids,
            "matched_rule_ids": self.matched_rule_ids,
            "matched_content_rule_ids": self.matched_content_rule_ids,
            "matched_tool_rule_ids": self.matched_tool_rule_ids,
            "reason_codes": self.reason_codes,
            "human_explanation": self.human_explanation,
            "monitoring_instruction": self.monitoring_instruction,
            "required_approver_role": self.required_approver_role,
            "condition_details": self.condition_details,
        }
