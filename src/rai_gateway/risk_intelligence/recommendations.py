"""Policy recommendation engine — drafts only, never auto-activates."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from rai_gateway.risk_intelligence.domain import (
    RecommendationStatus,
    RecommendationType,
)
from rai_gateway.risk_intelligence.repository import RiskIntelligenceRepository


class RecommendationService:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._repo = RiskIntelligenceRepository(db)

    def detect_repeated_approval_pattern(
        self,
        *,
        ai_system_id: UUID,
        tool_id: UUID | None,
        tool_name: str | None,
        condition_summary: str | None = None,
        approval_count: int,
        evidence_refs: list[dict[str, Any]] | None = None,
        min_count: int = 20,
    ) -> Any | None:
        if approval_count < min_count:
            return None
        pattern_key = f"tool-approval:{tool_id or tool_name}:{condition_summary or '*'}"
        existing = self._repo.find_recommendation_by_pattern(
            ai_system_id=ai_system_id, pattern_key=pattern_key
        )
        if existing:
            return existing

        proposed = {
            "type": "TOOL_RULE",
            "title": f"Require approval for {tool_name or tool_id}",
            "effect": "REQUIRE_APPROVAL",
            "tool_id": str(tool_id) if tool_id else None,
            "tool_name": tool_name,
            "conditions": [],
            "rationale_condition": condition_summary,
        }
        return self._repo.create_recommendation(
            ai_system_id=ai_system_id,
            recommendation_type=RecommendationType.TOOL_RULE.value,
            title=f"Draft Tool Rule after {approval_count} repeated approvals",
            rationale=(
                f"Observed {approval_count} repeated approvals for "
                f"{tool_name or tool_id}"
                + (f" with pattern {condition_summary}" if condition_summary else "")
                + ". Recommend a durable Tool Rule instead of per-action approvals."
            ),
            evidence_refs=evidence_refs or [],
            proposed_rule=proposed,
            confidence=min(0.95, 0.5 + approval_count / 100.0),
            pattern_key=pattern_key,
            status=RecommendationStatus.NEW.value,
        )

    def detect_content_refinement(
        self,
        *,
        ai_system_id: UUID,
        category: str,
        violation_count: int,
        evidence_refs: list[dict[str, Any]] | None = None,
        min_count: int = 5,
    ) -> Any | None:
        if violation_count < min_count:
            return None
        pattern_key = f"content-refine:{category}"
        existing = self._repo.find_recommendation_by_pattern(
            ai_system_id=ai_system_id, pattern_key=pattern_key
        )
        if existing:
            return existing
        proposed = {
            "type": "CONTENT_RULE",
            "title": f"Strengthen content rule for {category}",
            "effect": "DENY",
            "applies_to": "OUTPUT",
            "content": f"Do not produce content involving {category}.",
            "category": category,
        }
        return self._repo.create_recommendation(
            ai_system_id=ai_system_id,
            recommendation_type=RecommendationType.CONTENT_RULE.value,
            title=f"Refine Content Rule for {category}",
            rationale=(
                f"Observed {violation_count} repeated content violations "
                f"in category {category}."
            ),
            evidence_refs=evidence_refs or [],
            proposed_rule=proposed,
            confidence=min(0.9, 0.4 + violation_count / 20.0),
            pattern_key=pattern_key,
            status=RecommendationStatus.NEW.value,
        )

    def scan_for_recommendations(
        self,
        ai_system_id: UUID,
    ) -> list[Any]:
        """Async-style scan from recent findings/signals."""
        from rai_gateway.models.registry import AISystem

        owned = self._db.query(AISystem).filter(AISystem.id == ai_system_id).first()
        if not owned:
            raise LookupError("AI system not found")
        created: list[Any] = []
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        findings = self._repo.list_findings(
            ai_system_id=ai_system_id,
            finding_type="CONTENT_POLICY_VIOLATION",
            limit=200,
        )
        by_cat: dict[str, list[Any]] = {}
        for f in findings:
            if f.created_at and f.created_at.replace(tzinfo=timezone.utc) < since:
                continue
            cat = f.category or "uncategorized"
            by_cat.setdefault(cat, []).append(f)
        for cat, rows in by_cat.items():
            rec = self.detect_content_refinement(
                ai_system_id=ai_system_id,
                category=cat,
                violation_count=len(rows),
                evidence_refs=[{"finding_id": str(r.id)} for r in rows[:10]],
            )
            if rec and rec not in created:
                created.append(rec)
        return created

    def accept_as_draft_rule(
        self,
        recommendation_id: UUID,
        *,
        actor: str,
    ) -> dict[str, Any]:
        rec = self._repo.get_recommendation(recommendation_id)
        if not rec:
            raise LookupError("Recommendation not found")
        if rec.status not in (
            RecommendationStatus.NEW.value,
            RecommendationStatus.UNDER_REVIEW.value,
        ):
            raise ValueError(f"Cannot accept recommendation in status {rec.status}")

        proposed = rec.proposed_rule or {}
        draft_rule_id = None
        from rai_gateway.policy.service import PolicyCollectionService

        policy = PolicyCollectionService(self._db)
        if rec.recommendation_type == RecommendationType.CONTENT_RULE.value:
            rule = policy.create_content_rule(
                rec.ai_system_id,
                title=proposed.get("title") or rec.title,
                content=proposed.get("content") or rec.rationale or rec.title,
                effect=proposed.get("effect") or "MONITOR",
                enabled=False,  # draft — never auto-activate
                required_approver_role=None,
                actor=actor,
            )
            if hasattr(rule, "applies_to"):
                rule.applies_to = proposed.get("applies_to") or "BOTH"
            if hasattr(rule, "category") and proposed.get("category"):
                rule.category = proposed["category"]
            self._db.flush()
            draft_rule_id = rule.id
        elif rec.recommendation_type == RecommendationType.TOOL_RULE.value:
            tool_id = proposed.get("tool_id")
            if not tool_id:
                raise ValueError("Proposed tool rule missing tool_id")
            # Draft tool rules with REQUIRE_APPROVAL need a role placeholder
            effect = proposed.get("effect") or "REQUIRE_APPROVAL"
            approver_role = (
                "business_approver" if effect == "REQUIRE_APPROVAL" else None
            )
            rule = policy.create_tool_rule(
                rec.ai_system_id,
                title=proposed.get("title") or rec.title,
                description=rec.rationale,
                mcp_server_id=None,
                tool_id=UUID(str(tool_id)),
                match_mode="ALL",
                effect=effect,
                enabled=False,
                required_approver_role=approver_role,
                conditions=[],
                actor=actor,
            )
            draft_rule_id = rule.id
        else:
            raise ValueError(
                f"Unsupported recommendation type {rec.recommendation_type}"
            )

        rec.status = RecommendationStatus.ACCEPTED.value
        rec.draft_rule_id = draft_rule_id
        self._db.flush()
        return {
            "recommendation": self.serialize(rec),
            "draft_rule_id": str(draft_rule_id),
            "enabled": False,
            "accepted_by": actor,
        }

    def dismiss(
        self,
        recommendation_id: UUID,
        *,
        status: str = RecommendationStatus.DISMISSED.value,
    ) -> Any:
        rec = self._repo.get_recommendation(recommendation_id)
        if not rec:
            raise LookupError("Recommendation not found")
        rec.status = status
        self._db.flush()
        return rec

    @staticmethod
    def serialize(rec: Any) -> dict[str, Any]:
        return {
            "id": str(rec.id),
            "ai_system_id": str(rec.ai_system_id),
            "recommendation_type": rec.recommendation_type,
            "title": rec.title,
            "rationale": rec.rationale,
            "evidence_refs": rec.evidence_refs,
            "proposed_rule": rec.proposed_rule,
            "confidence": rec.confidence,
            "pattern_key": rec.pattern_key,
            "status": rec.status,
            "draft_rule_id": str(rec.draft_rule_id) if rec.draft_rule_id else None,
            "created_at": rec.created_at.isoformat() if rec.created_at else None,
            "updated_at": rec.updated_at.isoformat() if rec.updated_at else None,
        }
