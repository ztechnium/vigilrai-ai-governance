"""Future seam for semantic Content Rule evaluation.

WP6 activates ContentPolicyEvaluator providers. Tool Rules remain
deterministic. The evaluator detects/classifies; the RAI Policy/Risk Engine
applies the governance effect — the LLM never unilaterally DENY/SUSPEND.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from rai_gateway.risk_intelligence.domain import ContentEvaluationStatus

CONTENT_EVALUATOR_STATUS = "NOT_ACTIVE"
CONTENT_EVALUATOR_REASON = "CONTENT_EVALUATOR_NOT_CONFIGURED"


@dataclass
class ContentFinding:
    rule_id: str | None = None
    category: str | None = None
    severity: str | None = None
    matched: bool = False
    confidence: float = 0.0
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class ContentEvaluationResult:
    status: str = CONTENT_EVALUATOR_STATUS
    reason: str = CONTENT_EVALUATOR_REASON
    findings: list[ContentFinding] = field(default_factory=list)
    provider: str | None = None
    model: str | None = None
    intervention_hints: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason": self.reason,
            "provider": self.provider,
            "model": self.model,
            "findings": [
                {
                    "rule_id": f.rule_id,
                    "category": f.category,
                    "severity": f.severity,
                    "matched": f.matched,
                    "confidence": f.confidence,
                    "detail": f.detail,
                }
                for f in self.findings
            ],
            "intervention_hints": self.intervention_hints,
        }


class ContentPolicyEvaluator(Protocol):
    def evaluate(
        self,
        *,
        input_text: str | None,
        output_text: str | None,
        applicable_rules: list[dict[str, Any]],
        ai_system_id: str | None = None,
    ) -> ContentEvaluationResult:
        """Evaluate content against applicable Content Rules."""
        ...


class NullContentPolicyEvaluator:
    """Default evaluator — always reports NOT_ACTIVE."""

    def evaluate(
        self,
        *,
        input_text: str | None,
        output_text: str | None,
        applicable_rules: list[dict[str, Any]],
        ai_system_id: str | None = None,
    ) -> ContentEvaluationResult:
        return ContentEvaluationResult()


class ActiveContentPolicyEvaluator:
    """Delegates to WP6 ContentEvaluationService / providers."""

    def __init__(self, db: Any, ai_system_id: Any | None = None) -> None:
        self._db = db
        self._ai_system_id = ai_system_id

    def evaluate(
        self,
        *,
        input_text: str | None,
        output_text: str | None,
        applicable_rules: list[dict[str, Any]],
        ai_system_id: str | None = None,
    ) -> ContentEvaluationResult:
        from uuid import UUID

        from rai_gateway.risk_intelligence.content_evaluation import (
            ContentEvaluationService,
        )
        from rai_gateway.risk_intelligence.repository import RiskIntelligenceRepository

        system_id = ai_system_id or (
            str(self._ai_system_id) if self._ai_system_id else None
        )
        if not system_id:
            return ContentEvaluationResult()

        repo = RiskIntelligenceRepository(self._db)
        config = repo.get_evaluator_config(UUID(str(system_id)))
        if not config or not config.enabled:
            return ContentEvaluationResult()

        svc = ContentEvaluationService(self._db)
        content = output_text or input_text or ""
        content_type = "OUTPUT" if output_text else "INPUT"
        # Prefer caller-supplied rules; otherwise load applicable
        result = svc.evaluate_content(
            ai_system_id=UUID(str(system_id)),
            content=content,
            content_type=content_type,
            evaluation_mode="OFFLINE_EVALUATED",
            use_cache=True,
            test_only=False,
        )
        if (
            result.get("status")
            in (
                ContentEvaluationStatus.FAILED.value,
                "FAILED",
            )
            and result.get("failure_type") == "EVALUATOR_NOT_CONFIGURED"
        ):
            return ContentEvaluationResult()

        findings = []
        for ev in result.get("evaluations") or []:
            findings.append(
                ContentFinding(
                    rule_id=ev.get("rule_id"),
                    category=ev.get("category"),
                    severity=ev.get("severity"),
                    matched=bool(ev.get("violated")),
                    confidence=float(ev.get("confidence") or 0),
                    detail={
                        "reason": ev.get("reason"),
                        "evidence_spans": ev.get("evidence_spans") or [],
                    },
                )
            )
        status = result.get("status") or CONTENT_EVALUATOR_STATUS
        if status in (
            ContentEvaluationStatus.COMPLETED.value,
            ContentEvaluationStatus.CACHED.value,
        ):
            status = "ACTIVE"
        return ContentEvaluationResult(
            status=status,
            reason=result.get("failure_type") or "OK",
            findings=findings,
            provider=result.get("provider"),
            model=result.get("model"),
            intervention_hints=result.get("intervention_hints") or [],
        )


def get_content_policy_evaluator(
    db: Any | None = None,
    ai_system_id: Any | None = None,
) -> ContentPolicyEvaluator:
    """Resolve the configured content evaluator."""
    if db is None:
        return NullContentPolicyEvaluator()
    from uuid import UUID

    from rai_gateway.risk_intelligence.repository import RiskIntelligenceRepository

    repo = RiskIntelligenceRepository(db)
    system_uuid = UUID(str(ai_system_id)) if ai_system_id else None
    config = repo.get_evaluator_config(system_uuid)
    if not config or not config.enabled:
        return NullContentPolicyEvaluator()
    return ActiveContentPolicyEvaluator(db, ai_system_id=ai_system_id)


def content_enforcement_status(
    db: Any | None = None, ai_system_id: Any | None = None
) -> dict[str, Any]:
    """Status blob for receipts / UI."""
    if db is None:
        return {
            "status": CONTENT_EVALUATOR_STATUS,
            "reason": CONTENT_EVALUATOR_REASON,
        }
    from uuid import UUID

    from rai_gateway.risk_intelligence.repository import RiskIntelligenceRepository

    repo = RiskIntelligenceRepository(db)
    system_uuid = UUID(str(ai_system_id)) if ai_system_id else None
    config = repo.get_evaluator_config(system_uuid)
    if not config or not config.enabled:
        return {
            "status": CONTENT_EVALUATOR_STATUS,
            "reason": CONTENT_EVALUATOR_REASON,
        }
    return {
        "status": "ACTIVE",
        "provider": config.provider,
        "model": config.model,
        "health_status": config.health_status,
    }
