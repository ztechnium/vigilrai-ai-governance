"""Content rule evaluation orchestration (detection only — not governance)."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from rai_gateway.models.policy_engine import ContentRule, PolicyCollection
from rai_gateway.risk_intelligence.domain import (
    ContentAppliesTo,
    ContentEvaluationMode,
    ContentEvaluationStatus,
    ContentRuleEvaluation,
    EvaluatorFailureType,
    StructuredEvaluatorOutput,
)
from rai_gateway.risk_intelligence.providers import (
    ContentEvaluatorError,
    EvaluatorRequest,
    ProviderConfig,
    get_provider,
)
from rai_gateway.risk_intelligence.repository import RiskIntelligenceRepository

logger = logging.getLogger(__name__)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def rule_set_digest(rules: list[dict[str, Any]]) -> str:
    canonical = [
        {
            "id": str(r.get("id")),
            "version": r.get("rule_version", 1),
            "content": r.get("content"),
            "effect": r.get("effect"),
            "applies_to": r.get("applies_to"),
        }
        for r in sorted(rules, key=lambda x: str(x.get("id")))
    ]
    return _sha256(json.dumps(canonical, sort_keys=True, default=str))


def serialize_content_rule(rule: ContentRule) -> dict[str, Any]:
    return {
        "id": str(rule.id),
        "title": rule.title,
        "content": rule.content,
        "effect": rule.effect,
        "enabled": rule.enabled,
        "applies_to": getattr(rule, "applies_to", None) or ContentAppliesTo.BOTH.value,
        "rule_version": getattr(rule, "rule_version", None) or 1,
        "category": getattr(rule, "category", None),
        "severity": getattr(rule, "severity", None),
        "required_approver_role": rule.required_approver_role,
    }


class ContentEvaluationService:
    """Loads applicable Content Rules and runs a provider evaluator."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._repo = RiskIntelligenceRepository(db)

    def get_applicable_rules(
        self,
        ai_system_id: UUID,
        *,
        content_type: str,
    ) -> list[dict[str, Any]]:
        collection = (
            self._db.query(PolicyCollection)
            .filter(PolicyCollection.ai_system_id == ai_system_id)
            .first()
        )
        if not collection:
            return []
        rules = (
            self._db.query(ContentRule)
            .filter(
                ContentRule.policy_collection_id == collection.id,
                ContentRule.enabled.is_(True),
                ContentRule.archived_at.is_(None),
            )
            .all()
        )
        content_type_u = content_type.upper()
        # Map content_type to applies_to
        if content_type_u in ("INPUT", "PROMPT", "USER_PROMPT"):
            needed = {ContentAppliesTo.INPUT.value, ContentAppliesTo.BOTH.value}
        elif content_type_u in ("OUTPUT", "MODEL_RESPONSE", "AGENT_OUTPUT"):
            needed = {ContentAppliesTo.OUTPUT.value, ContentAppliesTo.BOTH.value}
        else:
            needed = {
                ContentAppliesTo.INPUT.value,
                ContentAppliesTo.OUTPUT.value,
                ContentAppliesTo.BOTH.value,
            }

        result = []
        for rule in rules:
            applies = getattr(rule, "applies_to", None) or ContentAppliesTo.BOTH.value
            if applies in needed:
                result.append(serialize_content_rule(rule))
        return result

    def evaluate_content(
        self,
        *,
        ai_system_id: UUID,
        content: str,
        content_type: str,
        evaluation_mode: str = ContentEvaluationMode.OFFLINE_EVALUATED.value,
        trajectory_id: UUID | None = None,
        use_cache: bool = True,
        test_only: bool = False,
    ) -> dict[str, Any]:
        config_row = self._repo.get_evaluator_config(ai_system_id)
        if not config_row or not config_row.enabled:
            return {
                "status": ContentEvaluationStatus.FAILED.value,
                "failure_type": EvaluatorFailureType.EVALUATOR_NOT_CONFIGURED.value,
                "evaluations": [],
                "intervention_hints": [],
                "provider": None,
                "model": None,
                "cached": False,
            }

        rules = self.get_applicable_rules(ai_system_id, content_type=content_type)
        if not rules:
            return {
                "status": ContentEvaluationStatus.SKIPPED.value,
                "failure_type": None,
                "evaluations": [],
                "intervention_hints": [],
                "provider": config_row.provider,
                "model": config_row.model,
                "cached": False,
                "reason": "NO_APPLICABLE_CONTENT_RULES",
            }

        content_digest = _sha256(content)
        rs_digest = rule_set_digest(rules)
        cache_key = _sha256(
            f"{content_digest}|{rs_digest}|{config_row.provider}|{config_row.model}"
        )

        if use_cache and not test_only:
            cached = self._repo.get_cached_evaluation(cache_key)
            if cached and cached.status == ContentEvaluationStatus.COMPLETED.value:
                return self._result_from_row(
                    cached, cached_hit=True, config_row=config_row
                )

        provider_cfg = ProviderConfig(
            provider=config_row.provider,
            model=config_row.model,
            temperature=config_row.temperature or 0.0,
            timeout_seconds=config_row.timeout_seconds or 30,
            max_rules_per_call=config_row.max_rules_per_call or 20,
            api_key=config_row.api_key_encrypted,
        )
        request = EvaluatorRequest(
            content=content,
            content_type=content_type,
            applicable_rules=rules[: provider_cfg.max_rules_per_call],
            ai_system_context={"ai_system_id": str(ai_system_id)},
        )

        started = time.monotonic()
        try:
            provider = get_provider(config_row.provider)
            structured = provider.evaluate(request, provider_cfg)
            latency_ms = int((time.monotonic() - started) * 1000)
            self._record_provider_success(config_row, latency_ms)
        except ContentEvaluatorError as exc:
            latency_ms = int((time.monotonic() - started) * 1000)
            self._record_provider_failure(config_row, str(exc))
            row = None
            if not test_only:
                row = self._repo.create_evaluation_result(
                    ai_system_id=ai_system_id,
                    trajectory_id=trajectory_id,
                    content_type=content_type,
                    evaluation_mode=evaluation_mode,
                    status=ContentEvaluationStatus.FAILED.value,
                    failure_type=exc.failure_type,
                    provider=config_row.provider,
                    model=config_row.model,
                    content_digest=content_digest,
                    rule_set_digest=rs_digest,
                    cache_key=f"fail-{cache_key}-{datetime.now(timezone.utc).timestamp()}",
                    evaluations=[],
                    rule_ids=[r["id"] for r in rules],
                    latency_ms=latency_ms,
                )
            return {
                "id": str(row.id) if row else None,
                "status": ContentEvaluationStatus.FAILED.value,
                "failure_type": exc.failure_type,
                "evaluations": [],
                "intervention_hints": [],
                "provider": config_row.provider,
                "model": config_row.model,
                "cached": False,
                "fail_closed": bool(config_row.fail_closed),
                "latency_ms": latency_ms,
            }

        hints = self._intervention_hints(structured, rules, config_row)
        row = None
        if not test_only:
            # Avoid unique constraint collision on cache_key for concurrent inserts
            existing = self._repo.get_cached_evaluation(cache_key)
            if existing:
                row = existing
            else:
                row = self._repo.create_evaluation_result(
                    ai_system_id=ai_system_id,
                    trajectory_id=trajectory_id,
                    content_type=content_type,
                    evaluation_mode=evaluation_mode,
                    status=ContentEvaluationStatus.COMPLETED.value,
                    failure_type=None,
                    provider=config_row.provider,
                    model=config_row.model,
                    content_digest=content_digest,
                    rule_set_digest=rs_digest,
                    cache_key=cache_key,
                    evaluations=structured.to_dict()["evaluations"],
                    rule_ids=[r["id"] for r in rules],
                    latency_ms=latency_ms,
                )

        return {
            "id": str(row.id) if row else None,
            "status": ContentEvaluationStatus.COMPLETED.value,
            "failure_type": None,
            "evaluations": structured.to_dict()["evaluations"],
            "intervention_hints": hints,
            "provider": config_row.provider,
            "model": config_row.model,
            "cached": False,
            "content_digest": content_digest,
            "rule_set_digest": rs_digest,
            "latency_ms": latency_ms,
            "applicable_rules": rules,
        }

    def _intervention_hints(
        self,
        structured: StructuredEvaluatorOutput,
        rules: list[dict[str, Any]],
        config_row: Any,
    ) -> list[dict[str, Any]]:
        """Map detections + stored rule effects + confidence thresholds → hints.

        The LLM never chooses DENY/SUSPEND; RAI maps configured rule effects.
        """
        by_id = {str(r["id"]): r for r in rules}
        hints: list[dict[str, Any]] = []
        for ev in structured.evaluations:
            if not ev.violated:
                continue
            rule = by_id.get(ev.rule_id)
            if not rule:
                continue
            effect = rule.get("effect", "MONITOR")
            conf = ev.confidence
            suggested = "MARK"
            if conf >= (config_row.minimum_confidence_to_intervene or 0.9):
                if effect == "DENY":
                    suggested = "DENY"
                elif effect == "REQUIRE_APPROVAL":
                    suggested = "REQUIRE_APPROVAL"
                elif effect in ("MONITOR", "MARK"):
                    suggested = "MARK_AND_MONITOR"
                else:
                    suggested = effect
            elif conf >= (config_row.minimum_confidence_to_monitor or 0.7):
                suggested = "MARK_AND_MONITOR"
            elif conf >= (config_row.minimum_confidence_to_mark or 0.5):
                suggested = "MARK"
            else:
                continue
            hints.append(
                {
                    "rule_id": ev.rule_id,
                    "rule_effect": effect,
                    "suggested_intervention": suggested,
                    "confidence": conf,
                    "severity": ev.severity or rule.get("severity") or "MEDIUM",
                    "category": ev.category or rule.get("category"),
                    "reason": ev.reason,
                    "evidence_spans": ev.evidence_spans,
                }
            )
        return hints

    def _result_from_row(
        self, row: Any, *, cached_hit: bool, config_row: Any
    ) -> dict[str, Any]:
        evaluations = row.evaluations or []
        # Rebuild hints from cached evaluations
        structured = StructuredEvaluatorOutput(
            evaluations=[
                ContentRuleEvaluation(
                    rule_id=str(e.get("rule_id")),
                    violated=bool(e.get("violated")),
                    confidence=float(e.get("confidence") or 0),
                    category=e.get("category"),
                    reason=e.get("reason"),
                    evidence_spans=e.get("evidence_spans") or [],
                    severity=e.get("severity"),
                )
                for e in evaluations
            ]
        )
        rules = [{"id": rid, "effect": "MONITOR"} for rid in (row.rule_ids or [])]
        # Prefer live rule effects when available
        if row.ai_system_id:
            live = self.get_applicable_rules(
                row.ai_system_id, content_type=row.content_type
            )
            if live:
                rules = live
        hints = self._intervention_hints(structured, rules, config_row)
        return {
            "id": str(row.id),
            "status": ContentEvaluationStatus.CACHED.value
            if cached_hit
            else row.status,
            "failure_type": row.failure_type,
            "evaluations": evaluations,
            "intervention_hints": hints,
            "provider": row.provider,
            "model": row.model,
            "cached": cached_hit,
            "content_digest": row.content_digest,
            "rule_set_digest": row.rule_set_digest,
            "latency_ms": row.latency_ms,
        }

    def _record_provider_success(self, config_row: Any, latency_ms: int) -> None:
        config_row.health_status = "HEALTHY"
        config_row.last_success_at = datetime.now(timezone.utc)
        if config_row.latency_ms_avg is None:
            config_row.latency_ms_avg = float(latency_ms)
        else:
            config_row.latency_ms_avg = 0.8 * float(
                config_row.latency_ms_avg
            ) + 0.2 * float(latency_ms)
        config_row.error_rate = max(0.0, float(config_row.error_rate or 0) * 0.9)
        self._db.flush()

    def _record_provider_failure(self, config_row: Any, error: str) -> None:
        config_row.last_error_at = datetime.now(timezone.utc)
        config_row.last_error = error[:2000]
        rate = float(config_row.error_rate or 0)
        config_row.error_rate = min(1.0, rate * 0.9 + 0.1)
        if config_row.error_rate > 0.5:
            config_row.health_status = "UNAVAILABLE"
        else:
            config_row.health_status = "DEGRADED"
        self._db.flush()
