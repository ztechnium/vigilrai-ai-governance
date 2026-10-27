"""Hierarchical budget scope resolution — all applicable parent+child budgets."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from rai_gateway.models.risk_intelligence import RuntimeBudget
from rai_gateway.risk_intelligence.domain import RiskScopeType


@dataclass
class BudgetEvaluationContext:
    ai_system_id: UUID | None = None
    agent_id: UUID | None = None
    agent_version_id: UUID | None = None
    runtime_identity_id: UUID | None = None
    delegation_id: UUID | None = None
    model_resource_id: UUID | None = None
    mcp_server_id: UUID | None = None
    tool_id: UUID | None = None
    provider: str | None = None
    model: str | None = None
    environment: str | None = None
    tool_name: str | None = None

    def scope_value(self, scope_type: str) -> str | None:
        mapping = {
            RiskScopeType.ORGANIZATION.value: RiskScopeType.ORGANIZATION.value,
            RiskScopeType.AI_SYSTEM.value: str(self.ai_system_id)
            if self.ai_system_id
            else None,
            RiskScopeType.AGENT.value: str(self.agent_id) if self.agent_id else None,
            RiskScopeType.AGENT_VERSION.value: str(self.agent_version_id)
            if self.agent_version_id
            else None,
            RiskScopeType.RUNTIME_IDENTITY.value: str(self.runtime_identity_id)
            if self.runtime_identity_id
            else None,
            RiskScopeType.DELEGATION.value: str(self.delegation_id)
            if self.delegation_id
            else None,
            RiskScopeType.MODEL.value: str(self.model_resource_id)
            if self.model_resource_id
            else (self.model or None),
            RiskScopeType.MCP_SERVER.value: str(self.mcp_server_id)
            if self.mcp_server_id
            else None,
            RiskScopeType.TOOL.value: str(self.tool_id)
            if self.tool_id
            else (self.tool_name or None),
        }
        return mapping.get(scope_type)


def _resource_filter_matches(
    resource_filter: dict[str, Any] | None, ctx: BudgetEvaluationContext
) -> bool:
    if not resource_filter:
        return True
    model_ids = resource_filter.get("model_ids") or resource_filter.get("models")
    if model_ids:
        allowed = {str(x) for x in model_ids}
        candidates = {
            str(ctx.model_resource_id) if ctx.model_resource_id else None,
            ctx.model,
        }
        if not any(c and c in allowed for c in candidates):
            return False
    tool_ids = resource_filter.get("tool_ids")
    if tool_ids:
        allowed = {str(x) for x in tool_ids}
        if not ctx.tool_id or str(ctx.tool_id) not in allowed:
            return False
    tool_names = resource_filter.get("tool_names")
    if tool_names:
        allowed = {str(x) for x in tool_names}
        if not ctx.tool_name or ctx.tool_name not in allowed:
            return False
    providers = resource_filter.get("providers")
    if providers:
        allowed = {str(x).lower() for x in providers}
        if not ctx.provider or ctx.provider.lower() not in allowed:
            return False
    environments = resource_filter.get("environments")
    if environments:
        allowed = {str(x) for x in environments}
        if not ctx.environment or ctx.environment not in allowed:
            return False
    return True


def budget_matches(budget: RuntimeBudget, ctx: BudgetEvaluationContext) -> bool:
    if not budget.enabled:
        return False
    if (
        budget.ai_system_id
        and ctx.ai_system_id
        and budget.ai_system_id != ctx.ai_system_id
    ):
        # Denormalized AI-system budgets only apply inside that system.
        if budget.scope_type != RiskScopeType.ORGANIZATION.value:
            return False
    if budget.tool_name and ctx.tool_name and budget.tool_name != ctx.tool_name:
        return False
    if budget.tool_id and ctx.tool_id and budget.tool_id != ctx.tool_id:
        return False
    if budget.tool_name and not ctx.tool_name:
        return False

    scope_value = ctx.scope_value(budget.scope_type)
    if budget.scope_id:
        if scope_value is None or str(budget.scope_id) != str(scope_value):
            return False
    else:
        # Unscoped type still requires the context dimension to exist
        # (except ORGANIZATION which is always present).
        if (
            budget.scope_type != RiskScopeType.ORGANIZATION.value
            and scope_value is None
            and budget.scope_type
            not in {
                RiskScopeType.AI_SYSTEM.value,
            }
        ):
            # AI_SYSTEM without scope_id applies to any action in that system when
            # budget.ai_system_id matches.
            if budget.scope_type == RiskScopeType.AI_SYSTEM.value:
                return bool(
                    budget.ai_system_id and ctx.ai_system_id == budget.ai_system_id
                )
            return False

    return _resource_filter_matches(
        budget.resource_filter if isinstance(budget.resource_filter, dict) else None,
        ctx,
    )


def resolve_matched_scope_id(
    budget: RuntimeBudget, ctx: BudgetEvaluationContext
) -> tuple[str, str]:
    """Return (scope_type, scope_id) used as the window counter identity."""
    if budget.scope_id:
        return budget.scope_type, str(budget.scope_id)
    value = ctx.scope_value(budget.scope_type)
    if value:
        return budget.scope_type, str(value)
    if budget.ai_system_id:
        return RiskScopeType.AI_SYSTEM.value, str(budget.ai_system_id)
    return RiskScopeType.ORGANIZATION.value, RiskScopeType.ORGANIZATION.value


@dataclass
class ApplicableBudgets:
    budgets: list[RuntimeBudget] = field(default_factory=list)

    def ids(self) -> list[UUID]:
        return [b.id for b in self.budgets]


def resolve_applicable_budgets(
    db: Session, ctx: BudgetEvaluationContext
) -> list[RuntimeBudget]:
    """Return all enabled budgets that apply to this evaluation context."""
    q = db.query(RuntimeBudget).filter(
        RuntimeBudget.enabled.is_(True),
    )
    # Include org-wide + this AI system (+ budgets without ai_system_id).
    if ctx.ai_system_id is not None:
        q = q.filter(
            (RuntimeBudget.ai_system_id.is_(None))
            | (RuntimeBudget.ai_system_id == ctx.ai_system_id)
            | (RuntimeBudget.scope_type == RiskScopeType.ORGANIZATION.value)
        )
    candidates = q.limit(500).all()
    return [b for b in candidates if budget_matches(b, ctx)]
