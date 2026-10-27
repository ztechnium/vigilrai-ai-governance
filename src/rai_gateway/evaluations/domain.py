"""Domain types for WP7 evaluation, assurance, and deployment gates."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import UUID


class EvaluationCategory(StrEnum):
    SAFETY = "SAFETY"
    SECURITY = "SECURITY"
    PRIVACY = "PRIVACY"
    COMPLIANCE = "COMPLIANCE"
    QUALITY = "QUALITY"
    ROBUSTNESS = "ROBUSTNESS"
    BIAS_FAIRNESS = "BIAS_FAIRNESS"
    TOOL_USE = "TOOL_USE"
    BUSINESS_RULE = "BUSINESS_RULE"
    RELIABILITY = "RELIABILITY"
    CUSTOM = "CUSTOM"


class RunnerType(StrEnum):
    DETERMINISTIC = "DETERMINISTIC"
    AGENT = "AGENT"
    TOOL_SANDBOX = "TOOL_SANDBOX"
    MODEL_JUDGE = "MODEL_JUDGE"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    EXTERNAL_SCANNER = "EXTERNAL_SCANNER"
    CUSTOM_RUNNER = "CUSTOM_RUNNER"


# Runner types that prove real agent/tool/model behavior (not fixture.simulate).
LIVE_ASSURANCE_RUNNER_TYPES: frozenset[str] = frozenset(
    {
        RunnerType.AGENT.value,
        RunnerType.TOOL_SANDBOX.value,
        RunnerType.MODEL_JUDGE.value,
        RunnerType.HUMAN_REVIEW.value,
        RunnerType.EXTERNAL_SCANNER.value,
    }
)

# Categories that must not use fixture-only runners for PRODUCTION gates.
PRODUCTION_LIVE_RUNNER_CATEGORIES: frozenset[str] = frozenset(
    {
        EvaluationCategory.SAFETY.value,
        EvaluationCategory.SECURITY.value,
        EvaluationCategory.PRIVACY.value,
        EvaluationCategory.COMPLIANCE.value,
        EvaluationCategory.BUSINESS_RULE.value,
    }
)


class EvaluationEnvironment(StrEnum):
    DEVELOPMENT = "DEVELOPMENT"
    TEST = "TEST"
    STAGING = "STAGING"
    PRODUCTION = "PRODUCTION"


class EvaluationRunStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    ERROR = "ERROR"
    CANCELLED = "CANCELLED"


class CaseResultStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"
    SKIPPED = "SKIPPED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class FailureSeverity(StrEnum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class GateConditionType(StrEnum):
    EVALUATION_SUITE_SCORE = "EVALUATION_SUITE_SCORE"
    MAX_FAILED_CASES = "MAX_FAILED_CASES"
    MAX_CRITICAL_FAILURES = "MAX_CRITICAL_FAILURES"
    RISK_ASSESSMENT_CURRENT = "RISK_ASSESSMENT_CURRENT"
    MAX_OPEN_RISK_SEVERITY = "MAX_OPEN_RISK_SEVERITY"
    REQUIRED_HUMAN_REVIEW = "REQUIRED_HUMAN_REVIEW"
    NO_ACTIVE_RUNTIME_SUSPENSION = "NO_ACTIVE_RUNTIME_SUSPENSION"
    ACCEPTABLE_RUNNER_TYPE = "ACCEPTABLE_RUNNER_TYPE"
    CUSTOM = "CUSTOM"


class GateDecision(StrEnum):
    PASS = "PASS"
    PASS_WITH_CONDITIONS = "PASS_WITH_CONDITIONS"
    FAIL = "FAIL"
    WAIVER_REQUIRED = "WAIVER_REQUIRED"


class ConditionResult(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    WAIVED = "WAIVED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class AssuranceStatus(StrEnum):
    VALID = "VALID"
    CONDITIONAL = "CONDITIONAL"
    EXPIRED = "EXPIRED"
    INVALIDATED = "INVALIDATED"
    FAILED = "FAILED"


class WaiverStatus(StrEnum):
    REQUESTED = "REQUESTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


class ReassessmentTriggerType(StrEnum):
    MODEL_CHANGED = "MODEL_CHANGED"
    SYSTEM_PROMPT_CHANGED = "SYSTEM_PROMPT_CHANGED"
    TOOL_MCP_CHANGED = "TOOL_MCP_CHANGED"
    DATA_SOURCE_CHANGED = "DATA_SOURCE_CHANGED"
    AUTHORITY_CHANGED = "AUTHORITY_CHANGED"
    POLICY_CHANGED = "POLICY_CHANGED"
    REQUIREMENT_CHANGED = "REQUIREMENT_CHANGED"
    ENVIRONMENT_CHANGED = "ENVIRONMENT_CHANGED"
    ASSURANCE_EXPIRED = "ASSURANCE_EXPIRED"
    BLOCKING_RISK = "BLOCKING_RISK"
    MANUAL = "MANUAL"


class ReassessmentStatus(StrEnum):
    REQUIRED = "REQUIRED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


# Material-change category → impacted evaluation categories
IMPACT_MAP: dict[str, frozenset[str]] = {
    "MODEL": frozenset(
        {
            EvaluationCategory.SAFETY.value,
            EvaluationCategory.QUALITY.value,
            EvaluationCategory.SECURITY.value,
            EvaluationCategory.BUSINESS_RULE.value,
            EvaluationCategory.ROBUSTNESS.value,
        }
    ),
    "TOOL": frozenset(
        {
            EvaluationCategory.TOOL_USE.value,
            EvaluationCategory.SECURITY.value,
            EvaluationCategory.SAFETY.value,
        }
    ),
    "MCP_SERVER": frozenset(
        {
            EvaluationCategory.TOOL_USE.value,
            EvaluationCategory.SECURITY.value,
            EvaluationCategory.SAFETY.value,
        }
    ),
    "DATA_SOURCE": frozenset(
        {
            EvaluationCategory.PRIVACY.value,
            EvaluationCategory.COMPLIANCE.value,
            EvaluationCategory.SECURITY.value,
        }
    ),
    "PERMISSION": frozenset(
        {
            EvaluationCategory.SECURITY.value,
            EvaluationCategory.COMPLIANCE.value,
            EvaluationCategory.TOOL_USE.value,
        }
    ),
    "CONFIGURATION": frozenset(
        {
            EvaluationCategory.SAFETY.value,
            EvaluationCategory.QUALITY.value,
            EvaluationCategory.BUSINESS_RULE.value,
        }
    ),
    "RISK_TIER": frozenset(
        {
            EvaluationCategory.SAFETY.value,
            EvaluationCategory.SECURITY.value,
            EvaluationCategory.COMPLIANCE.value,
        }
    ),
    "SYSTEM_PROMPT": frozenset(
        {
            EvaluationCategory.SAFETY.value,
            EvaluationCategory.QUALITY.value,
            EvaluationCategory.BUSINESS_RULE.value,
            EvaluationCategory.BIAS_FAIRNESS.value,
        }
    ),
}


SEVERITY_RANK: dict[str, int] = {
    FailureSeverity.INFO.value: 0,
    FailureSeverity.LOW.value: 1,
    FailureSeverity.MEDIUM.value: 2,
    FailureSeverity.HIGH.value: 3,
    FailureSeverity.CRITICAL.value: 4,
}


@dataclass
class CaseOutcome:
    case_key: str
    status: CaseResultStatus
    score: float
    severity: str | None = None
    explanation: str | None = None
    actual_output: Any = None
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunOutcome:
    status: EvaluationRunStatus
    score: float
    total_cases: int
    passed_cases: int
    failed_cases: int
    critical_failures: int
    case_outcomes: list[CaseOutcome] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class ConditionEvaluation:
    condition_type: str
    name: str
    required_value: Any
    actual_value: Any
    result: ConditionResult
    reason: str
    waivable: bool = False
    evidence_refs: list[str] = field(default_factory=list)
    evaluation_requirement_id: UUID | None = None
    evaluation_run_id: UUID | None = None
    waiver_id: UUID | None = None


@dataclass
class GateEvaluationResult:
    decision: GateDecision
    conditions: list[ConditionEvaluation]
    reason: str
    score_summary: dict[str, Any] = field(default_factory=dict)
