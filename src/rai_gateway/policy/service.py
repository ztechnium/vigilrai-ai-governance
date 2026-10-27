"""Policy collection CRUD and rule management."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session, joinedload

from rai_gateway.core.observability import generate_trace_id, log_admin_audit
from rai_gateway.models.policy_engine import (
    ContentRule,
    PolicyCollection,
    ToolRule,
    ToolRuleCondition,
)
from rai_gateway.models.registry import AISystem, ToolResource
from rai_gateway.policy.conditions import validate_operator_value
from rai_gateway.policy.content_rule_v2 import (
    applies_to_from_intervention_points,
    content_rule_coverage_status,
    default_content_targets,
    intervention_points_from_applies_to,
)
from rai_gateway.policy.domain import (
    ContentEvaluationType,
    ContentFailureMode,
    ContentRemediationType,
    MatchMode,
    PolicyEffect,
    PolicyInterventionPoint,
)
from rai_gateway.policy.errors import PolicyNotFoundError, PolicyValidationError

_VALID_INTERVENTION_POINTS = {p.value for p in PolicyInterventionPoint}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _audit(actor: str, action: str, target: dict[str, Any]) -> None:
    log_admin_audit(
        trace_id=generate_trace_id(),
        actor_user_id=actor,
        actor_role="admin",
        action=action,
        target=target,
    )


class PolicyCollectionService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def _get_ai_system(self, ai_system_id: UUID) -> AISystem:
        query = self._db.query(AISystem).filter(AISystem.id == ai_system_id)
        system = query.first()
        if not system:
            raise PolicyNotFoundError("AI System", str(ai_system_id))
        return system

    def get_collection_for_system(self, ai_system_id: UUID) -> PolicyCollection | None:
        return (
            self._db.query(PolicyCollection)
            .filter(PolicyCollection.ai_system_id == ai_system_id)
            .first()
        )

    def get_or_create_collection(
        self,
        ai_system_id: UUID,
        *,
        actor: str,
    ) -> PolicyCollection:
        existing = self.get_collection_for_system(ai_system_id)
        if existing:
            return existing
        self._get_ai_system(ai_system_id)
        collection = PolicyCollection(
            ai_system_id=ai_system_id,
            name="Default Policy Collection",
            status="ACTIVE",
        )
        self._db.add(collection)
        self._db.commit()
        self._db.refresh(collection)
        _audit(
            actor,
            "policy.collection.created",
            {
                "policy_collection_id": str(collection.id),
                "ai_system_id": str(ai_system_id),
            },
        )
        return collection

    def get_collection_detail(self, ai_system_id: UUID) -> dict[str, Any]:
        collection = self.get_or_create_collection(ai_system_id, actor="system")
        content_rules = (
            self._db.query(ContentRule)
            .filter(
                ContentRule.policy_collection_id == collection.id,
                ContentRule.archived_at.is_(None),
            )
            .order_by(ContentRule.created_at.desc())
            .all()
        )
        tool_rules = (
            self._db.query(ToolRule)
            .options(joinedload(ToolRule.conditions))
            .filter(
                ToolRule.policy_collection_id == collection.id,
                ToolRule.archived_at.is_(None),
            )
            .order_by(ToolRule.created_at.desc())
            .all()
        )
        return {
            "collection": self._serialize_collection(collection),
            "content_rules": [self._serialize_content_rule(r) for r in content_rules],
            "tool_rules": [self._serialize_tool_rule(r) for r in tool_rules],
        }

    def list_all_rules(self) -> dict[str, Any]:
        """List content and tool rules for every AI system."""
        systems = self._db.query(AISystem).all()
        system_map = {s.id: s for s in systems}
        if not system_map:
            return {"content_rules": [], "tool_rules": []}
        collections = (
            self._db.query(PolicyCollection)
            .filter(PolicyCollection.ai_system_id.in_(system_map.keys()))
            .all()
        )
        by_collection = {c.id: c for c in collections}
        collection_ids = list(by_collection.keys())
        if not collection_ids:
            return {"content_rules": [], "tool_rules": []}
        content_rows = (
            self._db.query(ContentRule)
            .filter(
                ContentRule.archived_at.is_(None),
                ContentRule.policy_collection_id.in_(collection_ids),
            )
            .order_by(ContentRule.created_at.desc())
            .all()
        )
        tool_rows = (
            self._db.query(ToolRule)
            .options(joinedload(ToolRule.conditions))
            .filter(
                ToolRule.archived_at.is_(None),
                ToolRule.policy_collection_id.in_(collection_ids),
            )
            .order_by(ToolRule.created_at.desc())
            .all()
        )
        content_rules: list[dict[str, Any]] = []
        for rule in content_rows:
            serialized = self._serialize_content_rule(rule)
            collection = by_collection.get(rule.policy_collection_id)
            system = system_map.get(collection.ai_system_id) if collection else None
            serialized["ai_system_id"] = (
                str(collection.ai_system_id) if collection else None
            )
            serialized["ai_system_name"] = system.name if system else None
            content_rules.append(serialized)
        tool_rules: list[dict[str, Any]] = []
        for rule in tool_rows:
            serialized = self._serialize_tool_rule(rule)
            collection = by_collection.get(rule.policy_collection_id)
            system = system_map.get(collection.ai_system_id) if collection else None
            serialized["ai_system_id"] = (
                str(collection.ai_system_id) if collection else None
            )
            serialized["ai_system_name"] = system.name if system else None
            tool_rules.append(serialized)
        return {"content_rules": content_rules, "tool_rules": tool_rules}

    def _serialize_collection(self, collection: PolicyCollection) -> dict[str, Any]:
        return {
            "id": str(collection.id),
            "ai_system_id": str(collection.ai_system_id),
            "name": collection.name,
            "description": collection.description,
            "status": collection.status,
            "created_at": collection.created_at.isoformat()
            if collection.created_at
            else None,
            "updated_at": collection.updated_at.isoformat()
            if collection.updated_at
            else None,
        }

    def _serialize_content_rule(self, rule: ContentRule) -> dict[str, Any]:
        applies_to = getattr(rule, "applies_to", None) or "BOTH"
        intervention_points = getattr(rule, "intervention_points", None)
        if not intervention_points:
            intervention_points = intervention_points_from_applies_to(applies_to)
        content_targets = (
            getattr(rule, "content_targets", None) or default_content_targets()
        )
        enabled = bool(rule.enabled)
        return {
            "id": str(rule.id),
            "policy_collection_id": str(rule.policy_collection_id),
            "title": rule.title,
            "content": rule.content,
            "effect": rule.effect,
            "enabled": enabled,
            "applies_to": applies_to,
            "rule_version": getattr(rule, "rule_version", None) or 1,
            "category": getattr(rule, "category", None),
            "severity": getattr(rule, "severity", None),
            "required_approver_role": rule.required_approver_role,
            "evaluation_type": getattr(rule, "evaluation_type", None)
            or ContentEvaluationType.LLM_JUDGE.value,
            "evaluator_profile_id": (
                str(rule.evaluator_profile_id)
                if getattr(rule, "evaluator_profile_id", None)
                else None
            ),
            "intervention_points": list(intervention_points),
            "content_targets": content_targets,
            "minimum_confidence": getattr(rule, "minimum_confidence", None),
            "failure_mode": getattr(rule, "failure_mode", None)
            or ContentFailureMode.INHERIT.value,
            "remediation_type": getattr(rule, "remediation_type", None)
            or ContentRemediationType.NONE.value,
            "remediation_config": getattr(rule, "remediation_config", None),
            "inline_enforcement_required": bool(
                getattr(rule, "inline_enforcement_required", False)
            ),
            "evaluation_timeout_ms": getattr(rule, "evaluation_timeout_ms", None),
            "coverage_status": content_rule_coverage_status(enabled=enabled),
            "created_at": rule.created_at.isoformat() if rule.created_at else None,
            "updated_at": rule.updated_at.isoformat() if rule.updated_at else None,
        }

    def _validate_evaluation_type(self, evaluation_type: str) -> None:
        if evaluation_type not in {e.value for e in ContentEvaluationType}:
            raise PolicyValidationError(f"Invalid evaluation_type: {evaluation_type}")

    def _validate_failure_mode(self, failure_mode: str) -> None:
        if failure_mode not in {e.value for e in ContentFailureMode}:
            raise PolicyValidationError(f"Invalid failure_mode: {failure_mode}")

    def _validate_remediation_type(self, remediation_type: str) -> None:
        if remediation_type not in {e.value for e in ContentRemediationType}:
            raise PolicyValidationError(f"Invalid remediation_type: {remediation_type}")

    def _normalize_intervention_points(self, points: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for raw in points:
            value = str(raw).upper()
            if value not in _VALID_INTERVENTION_POINTS:
                raise PolicyValidationError(f"Invalid intervention_point: {raw}")
            if value not in seen:
                seen.add(value)
                normalized.append(value)
        if not normalized:
            raise PolicyValidationError("intervention_points must not be empty")
        return normalized

    def _bump_rule_version(self, rule: ContentRule) -> None:
        rule.rule_version = int(getattr(rule, "rule_version", 1) or 1) + 1

    def _serialize_tool_rule(self, rule: ToolRule) -> dict[str, Any]:
        return {
            "id": str(rule.id),
            "policy_collection_id": str(rule.policy_collection_id),
            "title": rule.title,
            "description": rule.description,
            "mcp_server_id": str(rule.mcp_server_id) if rule.mcp_server_id else None,
            "tool_id": str(rule.tool_id),
            "match_mode": rule.match_mode,
            "effect": rule.effect,
            "enabled": rule.enabled,
            "required_approver_role": rule.required_approver_role,
            "severity": getattr(rule, "severity", None),
            "category": getattr(rule, "category", None),
            "conditions": [
                {
                    "id": str(c.id),
                    "parameter_path": c.parameter_path,
                    "operator": c.operator,
                    "value_type": c.value_type,
                    "value": c.value_json,
                    "sort_order": c.sort_order,
                }
                for c in (rule.conditions or [])
            ],
            "created_at": rule.created_at.isoformat() if rule.created_at else None,
            "updated_at": rule.updated_at.isoformat() if rule.updated_at else None,
        }

    def _validate_effect(self, effect: str) -> None:
        if effect not in {e.value for e in PolicyEffect}:
            raise PolicyValidationError(f"Invalid effect: {effect}")

    def _validate_tool_reference(
        self,
        *,
        tool_id: UUID,
        mcp_server_id: UUID | None,
    ) -> ToolResource:
        tool_q = self._db.query(ToolResource).filter(ToolResource.id == tool_id)
        tool = tool_q.first()
        if not tool:
            raise PolicyNotFoundError("Tool", str(tool_id))
        if tool.mcp_server_id:
            if not mcp_server_id:
                raise PolicyValidationError(
                    "Tool belongs to an MCP server; mcp_server_id is required"
                )
            if tool.mcp_server_id != mcp_server_id:
                raise PolicyValidationError(
                    "Selected MCP does not match the authoritative parent of the tool"
                )
        elif mcp_server_id:
            raise PolicyValidationError(
                "Standalone tool cannot be scoped to an MCP server"
            )
        return tool

    def _rule_owned_query(self, model: Any):
        query = self._db.query(model)
        return query

    def create_content_rule(
        self,
        ai_system_id: UUID,
        *,
        title: str,
        content: str,
        effect: str,
        enabled: bool = True,
        required_approver_role: str | None = None,
        applies_to: str = "BOTH",
        category: str | None = None,
        severity: str | None = None,
        evaluation_type: str | None = None,
        evaluator_profile_id: UUID | None = None,
        intervention_points: list[str] | None = None,
        content_targets: dict[str, Any] | None = None,
        minimum_confidence: float | None = None,
        failure_mode: str | None = None,
        remediation_type: str | None = None,
        remediation_config: dict[str, Any] | None = None,
        inline_enforcement_required: bool = False,
        evaluation_timeout_ms: int | None = None,
        actor: str,
    ) -> ContentRule:
        self._validate_effect(effect)
        if effect == PolicyEffect.REQUIRE_APPROVAL.value and not required_approver_role:
            raise PolicyValidationError(
                "required_approver_role is required when effect is REQUIRE_APPROVAL"
            )
        if applies_to not in {"INPUT", "OUTPUT", "BOTH"}:
            raise PolicyValidationError(f"Invalid applies_to: {applies_to}")
        resolved_points = (
            self._normalize_intervention_points(intervention_points)
            if intervention_points is not None
            else intervention_points_from_applies_to(applies_to)
        )
        if intervention_points is not None:
            synced = applies_to_from_intervention_points(resolved_points)
            if synced is not None:
                applies_to = synced
        resolved_eval_type = (
            evaluation_type or ContentEvaluationType.LLM_JUDGE.value
        ).upper()
        self._validate_evaluation_type(resolved_eval_type)
        resolved_failure = (failure_mode or ContentFailureMode.INHERIT.value).upper()
        self._validate_failure_mode(resolved_failure)
        resolved_remediation = (
            remediation_type or ContentRemediationType.NONE.value
        ).upper()
        self._validate_remediation_type(resolved_remediation)
        collection = self.get_or_create_collection(ai_system_id, actor=actor)
        rule = ContentRule(
            policy_collection_id=collection.id,
            title=title.strip(),
            content=content.strip(),
            effect=effect,
            enabled=enabled,
            required_approver_role=required_approver_role,
            applies_to=applies_to,
            category=category,
            severity=severity,
            evaluation_type=resolved_eval_type,
            evaluator_profile_id=evaluator_profile_id,
            intervention_points=resolved_points,
            content_targets=content_targets or default_content_targets(),
            minimum_confidence=minimum_confidence,
            failure_mode=resolved_failure,
            remediation_type=resolved_remediation,
            remediation_config=remediation_config,
            inline_enforcement_required=inline_enforcement_required,
            evaluation_timeout_ms=evaluation_timeout_ms,
        )
        self._db.add(rule)
        self._db.commit()
        self._db.refresh(rule)
        _audit(
            actor,
            "policy.content_rule.created",
            {
                "content_rule_id": str(rule.id),
                "ai_system_id": str(ai_system_id),
                "effect": effect,
            },
        )
        return rule

    def get_content_rule(self, rule_id: UUID) -> ContentRule:
        rule = (
            self._rule_owned_query(ContentRule)
            .filter(ContentRule.id == rule_id, ContentRule.archived_at.is_(None))
            .first()
        )
        if not rule:
            raise PolicyNotFoundError("Content rule", str(rule_id))
        return rule

    def update_content_rule(
        self,
        rule_id: UUID,
        *,
        actor: str,
        title: str | None = None,
        content: str | None = None,
        effect: str | None = None,
        enabled: bool | None = None,
        required_approver_role: str | None = None,
        applies_to: str | None = None,
        category: str | None = None,
        severity: str | None = None,
        evaluation_type: str | None = None,
        evaluator_profile_id: UUID | None = None,
        clear_evaluator_profile_id: bool = False,
        intervention_points: list[str] | None = None,
        content_targets: dict[str, Any] | None = None,
        minimum_confidence: float | None = None,
        failure_mode: str | None = None,
        remediation_type: str | None = None,
        remediation_config: dict[str, Any] | None = None,
        inline_enforcement_required: bool | None = None,
        evaluation_timeout_ms: int | None = None,
        ai_system_id: UUID | None = None,
    ) -> ContentRule:
        rule = self.get_content_rule(rule_id)
        bumped = False
        if effect is not None:
            self._validate_effect(effect)
            if rule.effect != effect:
                bumped = True
            rule.effect = effect
        if title is not None:
            rule.title = title.strip()
        if content is not None:
            if rule.content != content.strip():
                bumped = True
            rule.content = content.strip()
        if required_approver_role is not None:
            rule.required_approver_role = required_approver_role
        if intervention_points is not None:
            resolved_points = self._normalize_intervention_points(intervention_points)
            if (
                list(getattr(rule, "intervention_points", None) or [])
                != resolved_points
            ):
                bumped = True
            rule.intervention_points = resolved_points
            synced = applies_to_from_intervention_points(resolved_points)
            if synced is not None:
                rule.applies_to = synced
        elif applies_to is not None:
            if applies_to not in {"INPUT", "OUTPUT", "BOTH"}:
                raise PolicyValidationError(f"Invalid applies_to: {applies_to}")
            if rule.applies_to != applies_to:
                bumped = True
            rule.applies_to = applies_to
            rule.intervention_points = intervention_points_from_applies_to(applies_to)
        if category is not None:
            rule.category = category
        if severity is not None:
            rule.severity = severity
        if evaluation_type is not None:
            resolved = evaluation_type.upper()
            self._validate_evaluation_type(resolved)
            if getattr(rule, "evaluation_type", None) != resolved:
                bumped = True
            rule.evaluation_type = resolved
        if clear_evaluator_profile_id:
            if rule.evaluator_profile_id is not None:
                bumped = True
            rule.evaluator_profile_id = None
        elif evaluator_profile_id is not None:
            if rule.evaluator_profile_id != evaluator_profile_id:
                bumped = True
            rule.evaluator_profile_id = evaluator_profile_id
        if content_targets is not None:
            rule.content_targets = content_targets
        if minimum_confidence is not None:
            if getattr(rule, "minimum_confidence", None) != minimum_confidence:
                bumped = True
            rule.minimum_confidence = minimum_confidence
        if failure_mode is not None:
            resolved = failure_mode.upper()
            self._validate_failure_mode(resolved)
            if getattr(rule, "failure_mode", None) != resolved:
                bumped = True
            rule.failure_mode = resolved
        if remediation_type is not None:
            resolved = remediation_type.upper()
            self._validate_remediation_type(resolved)
            if getattr(rule, "remediation_type", None) != resolved:
                bumped = True
            rule.remediation_type = resolved
        if remediation_config is not None:
            if getattr(rule, "remediation_config", None) != remediation_config:
                bumped = True
            rule.remediation_config = remediation_config
        if inline_enforcement_required is not None:
            rule.inline_enforcement_required = inline_enforcement_required
        if evaluation_timeout_ms is not None:
            rule.evaluation_timeout_ms = evaluation_timeout_ms
        if enabled is not None:
            rule.enabled = enabled
            action = (
                "policy.content_rule.enabled"
                if enabled
                else "policy.content_rule.disabled"
            )
            _audit(actor, action, {"content_rule_id": str(rule.id)})
        if ai_system_id is not None:
            collection = self.get_or_create_collection(ai_system_id, actor=actor)
            if rule.policy_collection_id != collection.id:
                rule.policy_collection_id = collection.id
                _audit(
                    actor,
                    "policy.content_rule.reassigned",
                    {
                        "content_rule_id": str(rule.id),
                        "ai_system_id": str(ai_system_id),
                        "policy_collection_id": str(collection.id),
                    },
                )
        if (
            rule.effect == PolicyEffect.REQUIRE_APPROVAL.value
            and not rule.required_approver_role
        ):
            raise PolicyValidationError(
                "required_approver_role is required when effect is REQUIRE_APPROVAL"
            )
        if bumped:
            self._bump_rule_version(rule)
        self._db.commit()
        self._db.refresh(rule)
        _audit(actor, "policy.content_rule.updated", {"content_rule_id": str(rule.id)})
        return rule

    def delete_content_rule(self, rule_id: UUID, *, actor: str) -> None:
        rule = self.get_content_rule(rule_id)
        rule.archived_at = _utcnow()
        rule.enabled = False
        self._db.commit()
        _audit(actor, "policy.content_rule.deleted", {"content_rule_id": str(rule.id)})

    def create_tool_rule(
        self,
        ai_system_id: UUID,
        *,
        title: str,
        tool_id: UUID,
        effect: str,
        actor: str,
        description: str | None = None,
        mcp_server_id: UUID | None = None,
        match_mode: str = MatchMode.ALL.value,
        enabled: bool = True,
        required_approver_role: str | None = None,
        conditions: list[dict[str, Any]] | None = None,
        severity: str | None = None,
        category: str | None = None,
    ) -> ToolRule:
        self._validate_effect(effect)
        if match_mode not in {m.value for m in MatchMode}:
            raise PolicyValidationError(f"Invalid match_mode: {match_mode}")
        if effect == PolicyEffect.REQUIRE_APPROVAL.value and not required_approver_role:
            raise PolicyValidationError(
                "required_approver_role is required when effect is REQUIRE_APPROVAL"
            )
        self._validate_tool_reference(
            tool_id=tool_id,
            mcp_server_id=mcp_server_id,
        )
        collection = self.get_or_create_collection(ai_system_id, actor=actor)
        rule = ToolRule(
            policy_collection_id=collection.id,
            title=title.strip(),
            description=description,
            mcp_server_id=mcp_server_id,
            tool_id=tool_id,
            match_mode=match_mode,
            effect=effect,
            enabled=enabled,
            required_approver_role=required_approver_role,
            severity=severity,
            category=category,
        )
        self._db.add(rule)
        self._db.flush()
        for idx, cond in enumerate(conditions or []):
            self._add_condition(rule, cond, sort_order=idx)
        self._db.commit()
        self._db.refresh(rule)
        _audit(
            actor,
            "policy.tool_rule.created",
            {
                "tool_rule_id": str(rule.id),
                "ai_system_id": str(ai_system_id),
                "effect": effect,
            },
        )
        return rule

    def _add_condition(
        self,
        rule: ToolRule,
        cond: dict[str, Any],
        *,
        sort_order: int,
    ) -> ToolRuleCondition:
        parameter_path = (cond.get("parameter_path") or "").strip()
        if not parameter_path:
            raise PolicyValidationError("Condition parameter_path is required")
        operator = cond.get("operator", "")
        value_type = cond.get("value_type", "string")
        value = cond.get("value")
        validate_operator_value(operator, value_type, value)
        condition = ToolRuleCondition(
            tool_rule_id=rule.id,
            parameter_path=parameter_path,
            operator=operator,
            value_type=value_type,
            value_json=value,
            sort_order=sort_order,
        )
        self._db.add(condition)
        return condition

    def get_tool_rule(self, rule_id: UUID) -> ToolRule:
        rule = (
            self._rule_owned_query(ToolRule)
            .options(joinedload(ToolRule.conditions))
            .filter(ToolRule.id == rule_id, ToolRule.archived_at.is_(None))
            .first()
        )
        if not rule:
            raise PolicyNotFoundError("Tool rule", str(rule_id))
        return rule

    def update_tool_rule(
        self,
        rule_id: UUID,
        *,
        actor: str,
        title: str | None = None,
        description: str | None = None,
        mcp_server_id: UUID | None = None,
        tool_id: UUID | None = None,
        match_mode: str | None = None,
        effect: str | None = None,
        enabled: bool | None = None,
        required_approver_role: str | None = None,
        conditions: list[dict[str, Any]] | None = None,
        clear_mcp_server_id: bool = False,
        severity: str | None = None,
        category: str | None = None,
        ai_system_id: UUID | None = None,
    ) -> ToolRule:
        rule = self.get_tool_rule(rule_id)
        new_tool_id = tool_id or rule.tool_id
        new_mcp_id = (
            None
            if clear_mcp_server_id
            else (mcp_server_id if mcp_server_id is not None else rule.mcp_server_id)
        )
        if tool_id is not None or mcp_server_id is not None or clear_mcp_server_id:
            self._validate_tool_reference(
                tool_id=new_tool_id,
                mcp_server_id=new_mcp_id,
            )
            rule.tool_id = new_tool_id
            rule.mcp_server_id = new_mcp_id
        if effect is not None:
            self._validate_effect(effect)
            rule.effect = effect
        if match_mode is not None:
            if match_mode not in {m.value for m in MatchMode}:
                raise PolicyValidationError(f"Invalid match_mode: {match_mode}")
            rule.match_mode = match_mode
        if title is not None:
            rule.title = title.strip()
        if description is not None:
            rule.description = description
        if required_approver_role is not None:
            rule.required_approver_role = required_approver_role
        if severity is not None:
            rule.severity = severity
        if category is not None:
            rule.category = category
        if enabled is not None:
            rule.enabled = enabled
            action = (
                "policy.tool_rule.enabled" if enabled else "policy.tool_rule.disabled"
            )
            _audit(actor, action, {"tool_rule_id": str(rule.id)})
        if ai_system_id is not None:
            collection = self.get_or_create_collection(ai_system_id, actor=actor)
            if rule.policy_collection_id != collection.id:
                rule.policy_collection_id = collection.id
                _audit(
                    actor,
                    "policy.tool_rule.reassigned",
                    {
                        "tool_rule_id": str(rule.id),
                        "ai_system_id": str(ai_system_id),
                        "policy_collection_id": str(collection.id),
                    },
                )
        final_effect = rule.effect
        if final_effect == PolicyEffect.REQUIRE_APPROVAL.value and not (
            rule.required_approver_role or required_approver_role
        ):
            raise PolicyValidationError(
                "required_approver_role is required when effect is REQUIRE_APPROVAL"
            )
        if conditions is not None:
            for existing in list(rule.conditions or []):
                self._db.delete(existing)
            for idx, cond in enumerate(conditions):
                self._add_condition(rule, cond, sort_order=idx)
        self._db.commit()
        self._db.refresh(rule)
        _audit(actor, "policy.tool_rule.updated", {"tool_rule_id": str(rule.id)})
        return rule

    def delete_tool_rule(self, rule_id: UUID, *, actor: str) -> None:
        rule = self.get_tool_rule(rule_id)
        rule.archived_at = _utcnow()
        rule.enabled = False
        self._db.commit()
        _audit(actor, "policy.tool_rule.deleted", {"tool_rule_id": str(rule.id)})
