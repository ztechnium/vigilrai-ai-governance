"""Domain types for WP6 continuous risk intelligence."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class RiskSignalType(StrEnum):
    CONTENT_POLICY_VIOLATION = "CONTENT_POLICY_VIOLATION"
    PII_DISCLOSURE = "PII_DISCLOSURE"
    PROMPT_INJECTION = "PROMPT_INJECTION"
    CREDENTIAL_EXPOSURE = "CREDENTIAL_EXPOSURE"
    UNSAFE_TOOL_INTENT = "UNSAFE_TOOL_INTENT"
    REPEATED_DENIAL = "REPEATED_DENIAL"
    REPEATED_APPROVAL_REQUIRED = "REPEATED_APPROVAL_REQUIRED"
    HIGH_VALUE_ACTION = "HIGH_VALUE_ACTION"
    HIGH_VALUE_BURST = "HIGH_VALUE_BURST"
    UNUSUAL_TOOL_FREQUENCY = "UNUSUAL_TOOL_FREQUENCY"
    UNUSUAL_TOOL_COMBINATION = "UNUSUAL_TOOL_COMBINATION"
    MODEL_MISMATCH = "MODEL_MISMATCH"
    REPEATED_MODEL_MISMATCH = "REPEATED_MODEL_MISMATCH"
    RISK_SCORE_SPIKE = "RISK_SCORE_SPIKE"
    BUDGET_WARNING = "BUDGET_WARNING"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    UNVERIFIED_RUNTIME = "UNVERIFIED_RUNTIME"
    MISSING_EVIDENCE = "MISSING_EVIDENCE"
    FREQUENCY_THRESHOLD = "FREQUENCY_THRESHOLD"
    AMOUNT_THRESHOLD = "AMOUNT_THRESHOLD"
    EMERGING_RISK = "EMERGING_RISK"


# Named monitoring windows for continuous oversight
MONITOR_WINDOW_PRESETS: dict[str, int] = {
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "24h": 86400,
}


def resolve_window_seconds(window: str | int | None, default: int = 600) -> int:
    """Resolve preset name (5m/15m/1h/24h) or integer seconds."""
    if window is None:
        return default
    if isinstance(window, int):
        return window
    key = str(window).strip().lower()
    if key in MONITOR_WINDOW_PRESETS:
        return MONITOR_WINDOW_PRESETS[key]
    return int(key)


class BudgetMetric(StrEnum):
    ACTION_COUNT = "ACTION_COUNT"
    TOOL_COUNT = "TOOL_COUNT"
    AMOUNT = "AMOUNT"
    TOKEN_USAGE = "TOKEN_USAGE"
    COST = "COST"


class BudgetEffect(StrEnum):
    MONITOR = "MONITOR"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    DENY = "DENY"
    SUSPEND_RUNTIME_IDENTITY = "SUSPEND_RUNTIME_IDENTITY"


class BudgetReservationStatus(StrEnum):
    RESERVED = "RESERVED"
    SETTLED = "SETTLED"
    RELEASED = "RELEASED"
    EXPIRED = "EXPIRED"


# Combined effect precedence when multiple budgets apply (highest severity wins).
BUDGET_EFFECT_PRECEDENCE: tuple[str, ...] = (
    BudgetEffect.SUSPEND_RUNTIME_IDENTITY.value,
    BudgetEffect.DENY.value,
    BudgetEffect.REQUIRE_APPROVAL.value,
    BudgetEffect.MONITOR.value,
)


class BudgetStatus(StrEnum):
    OK = "OK"
    WARNING = "WARNING"
    EXCEEDED = "EXCEEDED"
    UNAVAILABLE = "UNAVAILABLE"


class BudgetEnforcementMode(StrEnum):
    """BEST_EFFORT may skip unmeasurable metrics; MANDATORY fails closed."""

    BEST_EFFORT = "BEST_EFFORT"
    MANDATORY = "MANDATORY"


class AnomalyType(StrEnum):
    UNUSUAL_TOOL_FREQUENCY = "UNUSUAL_TOOL_FREQUENCY"
    REPEATED_DENIED_ACTION = "REPEATED_DENIED_ACTION"
    REPEATED_APPROVAL_REQUIRED = "REPEATED_APPROVAL_REQUIRED"
    HIGH_VALUE_BURST = "HIGH_VALUE_BURST"
    RISK_SCORE_SPIKE = "RISK_SCORE_SPIKE"
    REPEATED_MODEL_MISMATCH = "REPEATED_MODEL_MISMATCH"
    UNUSUAL_TOOL_COMBINATION = "UNUSUAL_TOOL_COMBINATION"


class SuspensionAuthorizationMode(StrEnum):
    RECOMMEND_ONLY = "RECOMMEND_ONLY"
    HUMAN_CONFIRM = "HUMAN_CONFIRM"
    AUTO = "AUTO"


class RiskSeverity(StrEnum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RiskSensitivity(StrEnum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


class RiskScopeType(StrEnum):
    ORGANIZATION = "ORGANIZATION"
    AI_SYSTEM = "AI_SYSTEM"
    AGENT = "AGENT"
    AGENT_VERSION = "AGENT_VERSION"
    RUNTIME_IDENTITY = "RUNTIME_IDENTITY"
    DELEGATION = "DELEGATION"
    MODEL = "MODEL"
    MCP_SERVER = "MCP_SERVER"
    TOOL = "TOOL"
    TRAJECTORY = "TRAJECTORY"


class RiskLevel(StrEnum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class MonitoringStatus(StrEnum):
    NONE = "NONE"
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"


class InterventionEffect(StrEnum):
    PASS = "PASS"
    MARK = "MARK"
    MARK_AND_MONITOR = "MARK_AND_MONITOR"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    CONSTRAIN = "CONSTRAIN"
    DENY = "DENY"
    SUSPEND_RUNTIME_IDENTITY = "SUSPEND_RUNTIME_IDENTITY"
    SUSPEND_AGENT_VERSION = "SUSPEND_AGENT_VERSION"
    EMERGENCY_STOP = "EMERGENCY_STOP"


class InterventionStatus(StrEnum):
    RECOMMENDED = "RECOMMENDED"
    PENDING_CONFIRMATION = "PENDING_CONFIRMATION"
    EXECUTED = "EXECUTED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    REVERTED = "REVERTED"


class InterventionAuthorizationMode(StrEnum):
    RECOMMEND_ONLY = "RECOMMEND_ONLY"
    AUTO_FOR_LOW_MEDIUM = "AUTO_FOR_LOW_MEDIUM"
    AUTO_FOR_CONFIGURED_SIGNALS = "AUTO_FOR_CONFIGURED_SIGNALS"
    HUMAN_CONFIRM_HIGH_CRITICAL = "HUMAN_CONFIRM_HIGH_CRITICAL"


class ContentAppliesTo(StrEnum):
    INPUT = "INPUT"
    OUTPUT = "OUTPUT"
    BOTH = "BOTH"


class ContentEvaluationMode(StrEnum):
    PRE_INPUT_ENFORCED = "PRE_INPUT_ENFORCED"
    PRE_OUTPUT_ENFORCED = "PRE_OUTPUT_ENFORCED"
    POST_OUTPUT_OBSERVED = "POST_OUTPUT_OBSERVED"
    OFFLINE_EVALUATED = "OFFLINE_EVALUATED"
    TEST_ONLY = "TEST_ONLY"


class ContentEvaluationStatus(StrEnum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CACHED = "CACHED"
    SKIPPED = "SKIPPED"


class EvaluatorFailureType(StrEnum):
    EVALUATOR_UNAVAILABLE = "EVALUATOR_UNAVAILABLE"
    EVALUATOR_TIMEOUT = "EVALUATOR_TIMEOUT"
    EVALUATOR_INVALID_RESPONSE = "EVALUATOR_INVALID_RESPONSE"
    CONTENT_UNAVAILABLE = "CONTENT_UNAVAILABLE"
    EVALUATOR_NOT_CONFIGURED = "EVALUATOR_NOT_CONFIGURED"


class ProviderHealth(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


class MonitorAggregation(StrEnum):
    COUNT = "COUNT"
    SUM = "SUM"
    MAX = "MAX"


class MonitorEffect(StrEnum):
    MARK = "MARK"
    MARK_AND_MONITOR = "MARK_AND_MONITOR"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    DENY = "DENY"
    SUSPEND_RUNTIME_IDENTITY = "SUSPEND_RUNTIME_IDENTITY"


class ConstraintType(StrEnum):
    DISABLE_TOOL = "DISABLE_TOOL"
    READ_ONLY = "READ_ONLY"
    LIMIT_AMOUNT = "LIMIT_AMOUNT"
    LIMIT_FREQUENCY = "LIMIT_FREQUENCY"


class RecommendationType(StrEnum):
    TOOL_RULE = "TOOL_RULE"
    CONTENT_RULE = "CONTENT_RULE"
    MONITOR_RULE = "MONITOR_RULE"


class RecommendationStatus(StrEnum):
    NEW = "NEW"
    UNDER_REVIEW = "UNDER_REVIEW"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    DISMISSED = "DISMISSED"


class FindingStatus(StrEnum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    MONITORING = "MONITORING"
    RESOLVED = "RESOLVED"
    FALSE_POSITIVE = "FALSE_POSITIVE"


SEVERITY_RANK: dict[str, int] = {
    RiskSeverity.INFO.value: 0,
    RiskSeverity.LOW.value: 1,
    RiskSeverity.MEDIUM.value: 2,
    RiskSeverity.HIGH.value: 3,
    RiskSeverity.CRITICAL.value: 4,
}

EFFECT_RANK: dict[str, int] = {
    InterventionEffect.PASS.value: 0,
    InterventionEffect.MARK.value: 1,
    InterventionEffect.MARK_AND_MONITOR.value: 2,
    InterventionEffect.REQUIRE_APPROVAL.value: 3,
    InterventionEffect.CONSTRAIN.value: 4,
    InterventionEffect.DENY.value: 5,
    InterventionEffect.SUSPEND_RUNTIME_IDENTITY.value: 6,
    InterventionEffect.SUSPEND_AGENT_VERSION.value: 7,
    InterventionEffect.EMERGENCY_STOP.value: 8,
}

# Map Content Rule effects → intervention effects
CONTENT_EFFECT_TO_INTERVENTION: dict[str, str] = {
    "ALLOW": InterventionEffect.PASS.value,
    "MONITOR": InterventionEffect.MARK_AND_MONITOR.value,
    "MARK": InterventionEffect.MARK.value,
    "REQUIRE_APPROVAL": InterventionEffect.REQUIRE_APPROVAL.value,
    "DENY": InterventionEffect.DENY.value,
}


@dataclass
class RiskDimensions:
    severity: str = RiskSeverity.INFO.value
    likelihood: float | None = None
    confidence: float = 0.0
    sensitivity: str = RiskSensitivity.NORMAL.value
    frequency: float | None = None
    exposure: float | None = None
    impact: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "likelihood": self.likelihood,
            "confidence": self.confidence,
            "sensitivity": self.sensitivity,
            "frequency": self.frequency,
            "exposure": self.exposure,
            "impact": self.impact,
        }


@dataclass
class ContentRuleEvaluation:
    rule_id: str
    violated: bool
    confidence: float
    category: str | None = None
    reason: str | None = None
    evidence_spans: list[str] = field(default_factory=list)
    severity: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "violated": self.violated,
            "confidence": self.confidence,
            "category": self.category,
            "reason": self.reason,
            "evidence_spans": self.evidence_spans,
            "severity": self.severity,
        }


@dataclass
class StructuredEvaluatorOutput:
    evaluations: list[ContentRuleEvaluation] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"evaluations": [e.to_dict() for e in self.evaluations]}


@dataclass
class RiskScoreBreakdown:
    score: int
    drivers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"score": self.score, "drivers": self.drivers}


def dominant_severity(severities: list[str]) -> str:
    if not severities:
        return RiskSeverity.INFO.value
    return max(severities, key=lambda s: SEVERITY_RANK.get(s, 0))


def dominant_effect(effects: list[str]) -> str:
    if not effects:
        return InterventionEffect.PASS.value
    return max(effects, key=lambda e: EFFECT_RANK.get(e, 0))


def map_content_effect(effect: str) -> str:
    return CONTENT_EFFECT_TO_INTERVENTION.get(effect, InterventionEffect.MARK.value)
