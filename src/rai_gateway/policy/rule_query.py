"""Unified RAI Rules read model — server-side filter + pagination."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from rai_gateway.models.policy_engine import ContentRule, PolicyCollection, ToolRule
from rai_gateway.models.registry import AISystem, ToolResource
from rai_gateway.policy.content_rule_v2 import (
    content_rule_coverage_status,
    intervention_points_from_applies_to,
)
from rai_gateway.policy.domain import ContentEvaluationType

_DEFAULT_LIMIT = 50
_MAX_LIMIT = 200


def _clamp_limit(limit: int | None) -> int:
    if limit is None:
        return _DEFAULT_LIMIT
    return max(1, min(int(limit), _MAX_LIMIT))


def _operational_status(*, enabled: bool, archived_at: Any) -> str:
    if archived_at is not None:
        return "ARCHIVED"
    return "ACTIVE" if enabled else "DISABLED"


class RaiRulesQueryService:
    """Paginated union of Content and Tool rules."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def query(
        self,
        *,
        search: str | None = None,
        ai_system_id: UUID | None = None,
        rule_type: str | None = None,
        tool_id: UUID | None = None,
        mcp_server_id: UUID | None = None,
        effect: str | None = None,
        severity: str | None = None,
        status: str | None = None,
        category: str | None = None,
        source_policy_id: str | None = None,
        intervention_point: str | None = None,
        evaluation_type: str | None = None,
        coverage_status: str | None = None,
        include_archived: bool = False,
        limit: int | None = None,
        offset: int | None = None,
        sort: str | None = None,
    ) -> dict[str, Any]:
        page_limit = _clamp_limit(limit)
        page_offset = max(0, int(offset or 0))
        search_term = (search or "").strip().lower() or None
        rt = (rule_type or "").strip().upper() or None
        if rt in ("", "ALL"):
            rt = None
        if rt and rt not in ("CONTENT", "TOOL"):
            raise ValueError(f"Invalid rule_type: {rule_type}")
        status_filter = (status or "").strip().upper() or None
        if status_filter in ("", "ALL"):
            status_filter = None
        intervention_filter = (intervention_point or "").strip().upper() or None
        evaluation_filter = (evaluation_type or "").strip().upper() or None
        coverage_filter = (coverage_status or "").strip().upper() or None
        if evaluation_filter and evaluation_filter not in {
            e.value for e in ContentEvaluationType
        }:
            raise ValueError(f"Invalid evaluation_type: {evaluation_type}")
        if coverage_filter and coverage_filter not in {
            "DISABLED",
            "NOT_CONFIGURED",
        }:
            raise ValueError(f"Invalid coverage_status: {coverage_status}")
        systems = self._db.query(AISystem).all()
        system_map = {s.id: s for s in systems}
        if ai_system_id is not None:
            if ai_system_id not in system_map:
                return {
                    "items": [],
                    "total": 0,
                    "limit": page_limit,
                    "offset": page_offset,
                }
            system_map = {ai_system_id: system_map[ai_system_id]}
        if not system_map:
            return {
                "items": [],
                "total": 0,
                "limit": page_limit,
                "offset": page_offset,
            }
        collections = (
            self._db.query(PolicyCollection)
            .filter(PolicyCollection.ai_system_id.in_(system_map.keys()))
            .all()
        )
        by_collection = {c.id: c for c in collections}
        collection_ids = list(by_collection.keys())
        if not collection_ids:
            return {
                "items": [],
                "total": 0,
                "limit": page_limit,
                "offset": page_offset,
            }
        source_links = self._source_links_by_rule(
            source_policy_id=source_policy_id,
        )
        items: list[dict[str, Any]] = []
        # Tool / MCP filters apply only to tool rules (and exclude content rows).
        # V2 content filters also exclude tool rows when set.
        content_only_filters = bool(
            intervention_filter or evaluation_filter or coverage_filter
        )
        include_content = (
            rt in (None, "CONTENT") and tool_id is None and mcp_server_id is None
        )
        include_tool = rt in (None, "TOOL") and not content_only_filters
        if include_content:
            items.extend(
                self._content_items(
                    collection_ids=collection_ids,
                    by_collection=by_collection,
                    system_map=system_map,
                    search_term=search_term,
                    effect=effect,
                    severity=severity,
                    category=category,
                    status_filter=status_filter,
                    include_archived=include_archived,
                    source_links=source_links,
                    source_policy_id=source_policy_id,
                    intervention_point=intervention_filter,
                    evaluation_type=evaluation_filter,
                    coverage_status=coverage_filter,
                )
            )
        if include_tool:
            items.extend(
                self._tool_items(
                    collection_ids=collection_ids,
                    by_collection=by_collection,
                    system_map=system_map,
                    search_term=search_term,
                    effect=effect,
                    severity=severity,
                    category=category,
                    status_filter=status_filter,
                    include_archived=include_archived,
                    tool_id=tool_id,
                    mcp_server_id=mcp_server_id,
                    source_links=source_links,
                    source_policy_id=source_policy_id,
                )
            )
        reverse = False
        sort_key = (sort or "-updated_at").strip().lower()
        if sort_key.startswith("-"):
            reverse = True
            sort_key = sort_key[1:]

        def _sort_value(item: dict[str, Any]):
            if sort_key == "title":
                return (item.get("title") or "").lower()
            if sort_key == "ai_system_name":
                return (item.get("ai_system_name") or "").lower()
            if sort_key == "effect":
                return item.get("effect") or ""
            if sort_key == "severity":
                return item.get("severity") or ""
            return item.get("updated_at") or item.get("created_at") or ""

        items.sort(key=_sort_value, reverse=reverse)
        total = len(items)
        page = items[page_offset : page_offset + page_limit]
        return {
            "items": page,
            "total": total,
            "limit": page_limit,
            "offset": page_offset,
        }

    def _source_links_by_rule(
        self, source_policy_id: str | None
    ) -> dict[tuple[str, UUID], dict[str, Any]]:
        """Load PolicyRuleLink metadata keyed by (rule_type, rule_id)."""
        try:
            from rai_gateway.models.policy_library import PolicyRuleLink, PolicySource
        except ImportError:
            return {}
        q = self._db.query(PolicyRuleLink, PolicySource).join(
            PolicySource, PolicySource.id == PolicyRuleLink.policy_source_id
        )
        if source_policy_id:
            q = q.filter(PolicySource.id == source_policy_id)
        out: dict[tuple[str, UUID], dict[str, Any]] = {}
        for link, source in q.all():
            out[(link.rule_type.upper(), link.rule_id)] = {
                "id": str(source.id),
                "title": source.title,
                "obligation_id": (
                    str(link.obligation_id) if link.obligation_id else None
                ),
            }
        return out

    def _content_items(
        self,
        *,
        collection_ids: list[UUID],
        by_collection: dict,
        system_map: dict,
        search_term: str | None,
        effect: str | None,
        severity: str | None,
        category: str | None,
        status_filter: str | None,
        include_archived: bool,
        source_links: dict,
        source_policy_id: str | None,
        intervention_point: str | None = None,
        evaluation_type: str | None = None,
        coverage_status: str | None = None,
    ) -> list[dict[str, Any]]:
        q = self._db.query(ContentRule).filter(
            ContentRule.policy_collection_id.in_(collection_ids)
        )
        if not include_archived:
            q = q.filter(ContentRule.archived_at.is_(None))
        if effect:
            q = q.filter(ContentRule.effect == effect.upper())
        if severity:
            q = q.filter(ContentRule.severity.ilike(severity))
        if category:
            q = q.filter(ContentRule.category.ilike(category))
        if evaluation_type:
            q = q.filter(ContentRule.evaluation_type == evaluation_type)
        if search_term:
            like = f"%{search_term}%"
            q = q.filter(
                or_(
                    ContentRule.title.ilike(like),
                    ContentRule.content.ilike(like),
                    ContentRule.category.ilike(like),
                )
            )
        items: list[dict[str, Any]] = []
        for rule in q.all():
            op_status = _operational_status(
                enabled=rule.enabled, archived_at=rule.archived_at
            )
            if status_filter and op_status != status_filter:
                continue
            derived_coverage = content_rule_coverage_status(enabled=bool(rule.enabled))
            if coverage_status and derived_coverage != coverage_status:
                continue
            applies_to = getattr(rule, "applies_to", None) or "BOTH"
            points = list(getattr(rule, "intervention_points", None) or [])
            if not points:
                points = intervention_points_from_applies_to(applies_to)
            if intervention_point and intervention_point not in {
                str(p).upper() for p in points
            }:
                continue
            link = source_links.get(("CONTENT", rule.id))
            if source_policy_id and not link:
                continue
            collection = by_collection.get(rule.policy_collection_id)
            system = system_map.get(collection.ai_system_id) if collection else None
            items.append(
                {
                    "id": str(rule.id),
                    "rule_type": "CONTENT",
                    "title": rule.title,
                    "ai_system_id": (
                        str(collection.ai_system_id) if collection else None
                    ),
                    "ai_system_name": system.name if system else None,
                    "effect": rule.effect,
                    "enabled": rule.enabled,
                    "status": op_status,
                    "severity": rule.severity,
                    "category": rule.category,
                    "applies_to": applies_to,
                    "target": applies_to,
                    "intervention_points": points,
                    "evaluation_type": getattr(rule, "evaluation_type", None)
                    or ContentEvaluationType.LLM_JUDGE.value,
                    "coverage_status": derived_coverage,
                    "content": rule.content,
                    "rule_version": getattr(rule, "rule_version", None) or 1,
                    "required_approver_role": rule.required_approver_role,
                    "failure_mode": getattr(rule, "failure_mode", None) or "INHERIT",
                    "remediation_type": getattr(rule, "remediation_type", None)
                    or "NONE",
                    "source_policy": link,
                    "updated_at": (
                        rule.updated_at.isoformat() if rule.updated_at else None
                    ),
                    "created_at": (
                        rule.created_at.isoformat() if rule.created_at else None
                    ),
                }
            )
        return items

    def _tool_items(
        self,
        *,
        collection_ids: list[UUID],
        by_collection: dict,
        system_map: dict,
        search_term: str | None,
        effect: str | None,
        severity: str | None,
        category: str | None,
        status_filter: str | None,
        include_archived: bool,
        tool_id: UUID | None,
        mcp_server_id: UUID | None,
        source_links: dict,
        source_policy_id: str | None,
    ) -> list[dict[str, Any]]:
        q = (
            self._db.query(ToolRule)
            .options(joinedload(ToolRule.conditions))
            .filter(ToolRule.policy_collection_id.in_(collection_ids))
        )
        if not include_archived:
            q = q.filter(ToolRule.archived_at.is_(None))
        if effect:
            q = q.filter(ToolRule.effect == effect.upper())
        if tool_id:
            q = q.filter(ToolRule.tool_id == tool_id)
        if mcp_server_id:
            q = q.filter(ToolRule.mcp_server_id == mcp_server_id)
        if severity and hasattr(ToolRule, "severity"):
            q = q.filter(ToolRule.severity.ilike(severity))
        if category and hasattr(ToolRule, "category"):
            q = q.filter(ToolRule.category.ilike(category))
        if search_term:
            like = f"%{search_term}%"
            q = q.filter(
                or_(
                    ToolRule.title.ilike(like),
                    ToolRule.description.ilike(like),
                )
            )
        tool_ids = set()
        rules = q.all()
        for rule in rules:
            tool_ids.add(rule.tool_id)
        tool_map: dict[UUID, ToolResource] = {}
        if tool_ids:
            for tool in (
                self._db.query(ToolResource).filter(ToolResource.id.in_(tool_ids)).all()
            ):
                tool_map[tool.id] = tool
        items: list[dict[str, Any]] = []
        for rule in rules:
            op_status = _operational_status(
                enabled=rule.enabled, archived_at=rule.archived_at
            )
            if status_filter and op_status != status_filter:
                continue
            link = source_links.get(("TOOL", rule.id))
            if source_policy_id and not link:
                continue
            collection = by_collection.get(rule.policy_collection_id)
            system = system_map.get(collection.ai_system_id) if collection else None
            tool = tool_map.get(rule.tool_id)
            rule_severity = getattr(rule, "severity", None)
            rule_category = getattr(rule, "category", None)
            if search_term and tool:
                # Also match tool name when searching.
                if (
                    search_term not in (rule.title or "").lower()
                    and search_term not in (rule.description or "").lower()
                ):
                    if (
                        search_term not in (tool.name or "").lower()
                        and search_term not in (tool.tool_key or "").lower()
                    ):
                        # Already filtered by title/description in SQL; name match is additive
                        # only when SQL matched — keep row.
                        pass
            items.append(
                {
                    "id": str(rule.id),
                    "rule_type": "TOOL",
                    "title": rule.title,
                    "ai_system_id": (
                        str(collection.ai_system_id) if collection else None
                    ),
                    "ai_system_name": system.name if system else None,
                    "effect": rule.effect,
                    "enabled": rule.enabled,
                    "status": op_status,
                    "severity": rule_severity,
                    "category": rule_category,
                    "applies_to": None,
                    "target": tool.tool_key if tool else str(rule.tool_id),
                    "tool_id": str(rule.tool_id),
                    "tool_name": tool.name if tool else None,
                    "mcp_server_id": (
                        str(rule.mcp_server_id) if rule.mcp_server_id else None
                    ),
                    "match_mode": rule.match_mode,
                    "description": rule.description,
                    "required_approver_role": rule.required_approver_role,
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
                    "source_policy": link,
                    "updated_at": (
                        rule.updated_at.isoformat() if rule.updated_at else None
                    ),
                    "created_at": (
                        rule.created_at.isoformat() if rule.created_at else None
                    ),
                }
            )
        return items
