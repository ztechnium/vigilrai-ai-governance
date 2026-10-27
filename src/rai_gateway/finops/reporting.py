"""Server-side FinOps aggregates. Tenant scoped. Spans are the display source."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import case, cast, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from rai_gateway.finops.domain import CostState
from rai_gateway.models.evidence import EvidenceFinding, RuntimeTrajectory
from rai_gateway.models.finops import UsageReservation
from rai_gateway.models.identity import DelegationGrant
from rai_gateway.models.metering import RuntimeMeteringSpan
from rai_gateway.models.registry import Agent, AISystem
from rai_gateway.models.risk_intelligence import RuntimeBudget, RuntimeBudgetWindow
from rai_gateway.models.runtime_enforcement import RuntimeEnforcementReceipt

_INTERVENTION = ("DENY", "REQUIRE_APPROVAL", "SUSPEND")
_HIGH_RISK = ("HIGH", "CRITICAL")
_EXPORT_CAP = 5000


@dataclass
class FinOpsFilters:
    period_start: datetime
    period_end: datetime
    ai_system_id: UUID | None = None
    agent_id: UUID | None = None
    agent_version_id: UUID | None = None
    runtime_identity_id: UUID | None = None
    delegation_id: UUID | None = None
    provider: str | None = None
    model: str | None = None
    environment: str | None = None
    integration_id: UUID | None = None
    cost_state: str | None = None
    metering_source: str | None = None


def default_window(now: datetime | None = None) -> tuple[datetime, datetime]:
    end = now or datetime.now(timezone.utc)
    return end - timedelta(days=30), end


class FinOpsReportingService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def dashboard(self, filters: FinOpsFilters) -> dict[str, Any]:
        current = self._totals(filters)
        previous = self._totals(self._previous(filters))
        budgets = self._budget_pressure()
        risk = self._risk_spend(filters)
        coverage = self._coverage(filters)
        return {
            "period": _period(filters),
            "previous_period": _period(self._previous(filters)),
            "totals": current,
            "comparison": {
                "total_cost_change_pct": _change(
                    current["total_cost"], previous["total_cost"]
                ),
                "total_tokens_change_pct": _change(
                    current["total_tokens"], previous["total_tokens"]
                ),
            },
            "coverage": coverage,
            "budget_pressure": budgets,
            "risk_associated_spend": risk["risk_associated_spend"],
            "risk_breakdown": risk["breakdown"],
            "prevented_estimated_spend": self._prevented(filters),
            "definition": {
                "risk_associated_spend": (
                    "Sum of known trajectory cost where the trajectory has a HIGH or CRITICAL "
                    "finding, or an enforcement decision of DENY, REQUIRE_APPROVAL, or SUSPEND."
                ),
                "prevented_estimated_spend": (
                    "Estimated reservation cost for requests denied before execution. "
                    "This is not reported as savings."
                ),
            },
        }

    def timeseries(self, filters: FinOpsFilters) -> dict[str, Any]:
        bucket = func.date_trunc("day", RuntimeMeteringSpan.started_at)
        rows = (
            self._spans(filters)
            .with_entities(
                bucket.label("bucket"),
                func.coalesce(func.sum(self._known_cost()), 0.0),
                func.coalesce(func.sum(RuntimeMeteringSpan.total_tokens), 0),
                func.count(func.distinct(RuntimeMeteringSpan.trajectory_id)),
                func.sum(
                    case((RuntimeMeteringSpan.span_type == "MODEL_CALL", 1), else_=0)
                ),
            )
            .group_by(bucket)
            .order_by(bucket)
            .all()
        )
        return {
            "period": _period(filters),
            "points": [
                {
                    "timestamp": row[0].isoformat() if row[0] else None,
                    "cost": round(float(row[1] or 0), 8),
                    "tokens": int(row[2] or 0),
                    "trajectories": int(row[3] or 0),
                    "model_calls": int(row[4] or 0),
                }
                for row in rows
            ],
        }

    def breakdown(
        self,
        filters: FinOpsFilters,
        *,
        dimension: str,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        column = _dimension_column(dimension)
        if column is None:
            raise ValueError(f"Unsupported breakdown dimension: {dimension}")
        cost = self._known_cost()
        rows = (
            self._spans(filters)
            .with_entities(
                column,
                func.coalesce(func.sum(cost), 0.0),
                func.coalesce(func.sum(RuntimeMeteringSpan.total_tokens), 0),
                func.count(func.distinct(RuntimeMeteringSpan.trajectory_id)),
                func.count(RuntimeMeteringSpan.id),
                func.coalesce(func.sum(RuntimeMeteringSpan.input_tokens), 0),
                func.coalesce(func.sum(RuntimeMeteringSpan.output_tokens), 0),
            )
            .group_by(column)
            .order_by(func.coalesce(func.sum(cost), 0.0).desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        items = []
        for row in rows:
            key = row[0]
            items.append(
                {
                    "key": str(key) if key else None,
                    "label": self._label(dimension, key),
                    "cost": round(float(row[1] or 0), 8),
                    "tokens": int(row[2] or 0),
                    "trajectories": int(row[3] or 0),
                    "calls": int(row[4] or 0),
                    "input_tokens": int(row[5] or 0),
                    "output_tokens": int(row[6] or 0),
                    "avg_cost_per_call": round(float(row[1] or 0) / int(row[4]), 8)
                    if row[4]
                    else None,
                }
            )
        return {
            "dimension": dimension,
            "items": items,
            "limit": limit,
            "offset": offset,
        }

    def trajectories(
        self, filters: FinOpsFilters, *, limit: int = 50, offset: int = 0
    ) -> dict[str, Any]:
        cost = self._known_cost()
        grouped = (
            self._spans(filters)
            .filter(RuntimeMeteringSpan.trajectory_id.isnot(None))
            .with_entities(
                RuntimeMeteringSpan.trajectory_id,
                func.coalesce(func.sum(cost), 0.0).label("cost"),
                func.coalesce(func.sum(RuntimeMeteringSpan.total_tokens), 0).label(
                    "tokens"
                ),
                func.max(RuntimeMeteringSpan.started_at).label("started_at"),
            )
            .group_by(RuntimeMeteringSpan.trajectory_id)
            .order_by(func.coalesce(func.sum(cost), 0.0).desc())
        )
        total = grouped.count()
        rows = grouped.offset(offset).limit(limit).all()
        return {
            "items": [
                {
                    "trajectory_id": str(row.trajectory_id),
                    "cost": round(float(row.cost or 0), 8),
                    "tokens": int(row.tokens or 0),
                    "started_at": row.started_at.isoformat()
                    if row.started_at
                    else None,
                }
                for row in rows
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def export_rows(self, filters: FinOpsFilters, view: str) -> list[dict[str, Any]]:
        if view == "summary":
            return [self.dashboard(filters)["totals"]]
        if view == "trajectories":
            return self.trajectories(filters, limit=_EXPORT_CAP)["items"]
        if view == "spans":
            spans = self._spans(filters).limit(_EXPORT_CAP).all()
            from rai_gateway.finops.metering import RuntimeMeteringService

            svc = RuntimeMeteringService(self._db)
            return [svc.serialize_span(span) for span in spans]
        dimension = {
            "systems": "ai_system",
            "models": "model",
            "tenants": "delegation",
        }.get(view, view)
        return self.breakdown(filters, dimension=dimension, limit=_EXPORT_CAP)["items"]

    def _spans(self, filters: FinOpsFilters):
        query = self._db.query(RuntimeMeteringSpan).filter(
            RuntimeMeteringSpan.started_at >= filters.period_start,
            RuntimeMeteringSpan.started_at < filters.period_end,
        )
        mapping = {
            "ai_system_id": RuntimeMeteringSpan.ai_system_id,
            "agent_id": RuntimeMeteringSpan.agent_id,
            "agent_version_id": RuntimeMeteringSpan.agent_version_id,
            "runtime_identity_id": RuntimeMeteringSpan.runtime_identity_id,
            "delegation_id": RuntimeMeteringSpan.delegation_id,
            "provider": RuntimeMeteringSpan.provider,
            "model": RuntimeMeteringSpan.model,
            "environment": RuntimeMeteringSpan.environment,
            "integration_id": RuntimeMeteringSpan.integration_id,
            "cost_state": RuntimeMeteringSpan.cost_state,
            "metering_source": RuntimeMeteringSpan.metering_source,
        }
        for name, column in mapping.items():
            value = getattr(filters, name)
            if value:
                query = query.filter(column == value)
        return query

    def _known_cost(self):
        return case(
            (
                RuntimeMeteringSpan.cost_state == CostState.BILLED.value,
                func.coalesce(
                    RuntimeMeteringSpan.billed_cost, RuntimeMeteringSpan.actual_cost
                ),
            ),
            (
                RuntimeMeteringSpan.cost_state == CostState.METERED.value,
                func.coalesce(
                    RuntimeMeteringSpan.metered_cost, RuntimeMeteringSpan.actual_cost
                ),
            ),
            (
                RuntimeMeteringSpan.cost_state == CostState.ACTUAL.value,
                RuntimeMeteringSpan.actual_cost,
            ),
            (
                RuntimeMeteringSpan.cost_state == CostState.ESTIMATED.value,
                RuntimeMeteringSpan.estimated_cost,
            ),
            else_=0.0,
        )

    def _totals(self, filters: FinOpsFilters) -> dict[str, Any]:
        cost = self._known_cost()
        billed_expr = case(
            (
                RuntimeMeteringSpan.cost_state == CostState.BILLED.value,
                func.coalesce(
                    RuntimeMeteringSpan.billed_cost, RuntimeMeteringSpan.actual_cost
                ),
            ),
            else_=0.0,
        )
        metered_expr = case(
            (
                RuntimeMeteringSpan.cost_state == CostState.METERED.value,
                func.coalesce(
                    RuntimeMeteringSpan.metered_cost, RuntimeMeteringSpan.actual_cost
                ),
            ),
            (
                RuntimeMeteringSpan.cost_state == CostState.ACTUAL.value,
                RuntimeMeteringSpan.actual_cost,
            ),
            else_=0.0,
        )
        estimated_expr = case(
            (
                RuntimeMeteringSpan.cost_state == CostState.ESTIMATED.value,
                RuntimeMeteringSpan.estimated_cost,
            ),
            else_=0.0,
        )
        row = (
            self._spans(filters)
            .with_entities(
                func.coalesce(func.sum(billed_expr), 0.0),
                func.coalesce(func.sum(metered_expr), 0.0),
                func.coalesce(func.sum(estimated_expr), 0.0),
                func.coalesce(func.sum(RuntimeMeteringSpan.total_tokens), 0),
                func.coalesce(func.sum(RuntimeMeteringSpan.input_tokens), 0),
                func.coalesce(func.sum(RuntimeMeteringSpan.output_tokens), 0),
                func.coalesce(func.sum(RuntimeMeteringSpan.cached_input_tokens), 0),
                func.coalesce(func.sum(RuntimeMeteringSpan.reasoning_tokens), 0),
                func.sum(
                    case((RuntimeMeteringSpan.span_type == "MODEL_CALL", 1), else_=0)
                ),
                func.sum(
                    case((RuntimeMeteringSpan.span_type == "TOOL_CALL", 1), else_=0)
                ),
                func.count(func.distinct(RuntimeMeteringSpan.trajectory_id)),
                func.count(func.distinct(RuntimeMeteringSpan.runtime_conversation_id)),
                func.sum(
                    case(
                        (
                            RuntimeMeteringSpan.cost_state
                            == CostState.UNAVAILABLE.value,
                            1,
                        ),
                        else_=0,
                    )
                ),
                func.coalesce(func.sum(cost), 0.0),
            )
            .one()
        )
        billed = float(row[0] or 0)
        metered = float(row[1] or 0)
        estimated = float(row[2] or 0)
        total_cost = round(float(row[13] or 0), 8)
        trajectories = int(row[10] or 0)
        conversations = int(row[11] or 0)
        kinds = sum([bool(billed), bool(metered), bool(estimated)])
        if kinds > 1:
            state = CostState.MIXED.value
        elif billed:
            state = CostState.BILLED.value
        elif metered:
            state = CostState.METERED.value
        elif estimated:
            state = CostState.ESTIMATED.value
        else:
            state = CostState.UNAVAILABLE.value
            total_cost = None
        return {
            "total_cost": total_cost,
            "billed_cost": round(billed, 8),
            "metered_cost": round(metered, 8),
            "actual_cost": round(billed + metered, 8),
            "estimated_cost": round(estimated, 8),
            "unavailable_cost_count": int(row[12] or 0),
            "currency": "USD",
            "cost_state": state,
            "total_tokens": int(row[3] or 0),
            "input_tokens": int(row[4] or 0),
            "output_tokens": int(row[5] or 0),
            "cached_tokens": int(row[6] or 0),
            "reasoning_tokens": int(row[7] or 0),
            "model_calls": int(row[8] or 0),
            "tool_calls": int(row[9] or 0),
            "trajectories": trajectories,
            "conversations": conversations,
            "avg_cost_per_trajectory": round(total_cost / trajectories, 8)
            if total_cost is not None and trajectories
            else None,
            "avg_cost_per_conversation": round(total_cost / conversations, 8)
            if total_cost is not None and conversations
            else None,
            "avg_tokens_per_trajectory": round(int(row[3] or 0) / trajectories, 2)
            if trajectories
            else None,
        }

    def _coverage(self, filters: FinOpsFilters) -> dict[str, Any]:
        row = (
            self._spans(filters)
            .with_entities(
                func.count(RuntimeMeteringSpan.id),
                func.sum(
                    case(
                        (RuntimeMeteringSpan.cost_state == CostState.BILLED.value, 1),
                        else_=0,
                    )
                ),
                func.sum(
                    case(
                        (
                            RuntimeMeteringSpan.cost_state.in_(
                                [CostState.METERED.value, CostState.ACTUAL.value]
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ),
                func.sum(
                    case(
                        (
                            RuntimeMeteringSpan.cost_state == CostState.ESTIMATED.value,
                            1,
                        ),
                        else_=0,
                    )
                ),
                func.sum(
                    case(
                        (
                            RuntimeMeteringSpan.cost_state
                            == CostState.UNAVAILABLE.value,
                            1,
                        ),
                        else_=0,
                    )
                ),
                func.sum(
                    case((RuntimeMeteringSpan.total_tokens.isnot(None), 1), else_=0)
                ),
                func.sum(case((RuntimeMeteringSpan.model.isnot(None), 1), else_=0)),
                func.sum(
                    case((RuntimeMeteringSpan.delegation_id.isnot(None), 1), else_=0)
                ),
            )
            .one()
        )
        total = int(row[0] or 0)

        def pct(part: Any) -> float:
            if not total:
                return 0.0
            return round((int(part or 0) / total) * 100, 1)

        return {
            "span_count": total,
            "cost_coverage_pct": round(100 - pct(row[4]), 1) if total else 0.0,
            "billed_pct": pct(row[1]),
            "metered_pct": pct(row[2]),
            "actual_pct": pct(row[1]) + pct(row[2]),
            "estimated_pct": pct(row[3]),
            "unavailable_pct": pct(row[4]),
            "token_coverage_pct": pct(row[5]),
            "model_attribution_pct": pct(row[6]),
            "tenant_attribution_pct": pct(row[7]),
        }

    def _budget_pressure(self) -> dict[str, Any]:
        rows = (
            self._db.query(
                RuntimeBudgetWindow.status, func.count(func.distinct(RuntimeBudget.id))
            )
            .join(RuntimeBudget, RuntimeBudgetWindow.budget_id == RuntimeBudget.id)
            .filter(
                RuntimeBudget.enabled.is_(True),
            )
            .group_by(RuntimeBudgetWindow.status)
            .all()
        )
        counts = {status: int(count) for status, count in rows}
        warning = counts.get("WARNING", 0)
        exceeded = counts.get("EXCEEDED", 0)
        healthy = counts.get("OK", 0) + counts.get("HEALTHY", 0) + counts.get("OPEN", 0)
        return {
            "healthy": healthy,
            "warning": warning,
            "exceeded": exceeded,
            "budget_warning_count": warning,
            "budget_exceeded_count": exceeded,
        }

    def _risk_spend(self, filters: FinOpsFilters) -> dict[str, Any]:
        finding_ids = (
            self._db.query(EvidenceFinding.trajectory_id)
            .join(
                RuntimeTrajectory, RuntimeTrajectory.id == EvidenceFinding.trajectory_id
            )
            .join(AISystem, AISystem.id == RuntimeTrajectory.ai_system_id)
            .filter(
                EvidenceFinding.severity.in_(_HIGH_RISK),
            )
        )
        denied_ids = (
            self._db.query(RuntimeTrajectory.id)
            .join(
                RuntimeEnforcementReceipt,
                RuntimeEnforcementReceipt.correlation_id
                == RuntimeTrajectory.correlation_id,
            )
            .join(AISystem, AISystem.id == RuntimeTrajectory.ai_system_id)
            .filter(
                RuntimeEnforcementReceipt.enforcement_decision.in_(_INTERVENTION),
            )
        )
        risk_ids = finding_ids.union(denied_ids)
        cost = self._known_cost()
        amount = (
            self._spans(filters)
            .filter(RuntimeMeteringSpan.trajectory_id.in_(risk_ids))
            .with_entities(func.coalesce(func.sum(cost), 0.0))
            .scalar()
        )
        return {
            "risk_associated_spend": round(float(amount or 0), 8),
            "breakdown": {
                "spend_with_findings_or_intervention": round(float(amount or 0), 8),
            },
        }

    def _prevented(self, filters: FinOpsFilters) -> float:
        amount = (
            self._db.query(
                func.coalesce(func.sum(UsageReservation.estimated_cost), 0.0)
            )
            .join(
                RuntimeEnforcementReceipt,
                RuntimeEnforcementReceipt.id == UsageReservation.enforcement_receipt_id,
            )
            .filter(
                UsageReservation.created_at >= filters.period_start,
                UsageReservation.created_at < filters.period_end,
                RuntimeEnforcementReceipt.enforcement_decision.in_(_INTERVENTION),
                RuntimeEnforcementReceipt.execution_attempted.is_(False),
            )
            .scalar()
        )
        released = (
            self._db.query(
                func.coalesce(func.sum(UsageReservation.estimated_cost), 0.0)
            )
            .filter(
                UsageReservation.status == "RELEASED",
                UsageReservation.created_at >= filters.period_start,
                UsageReservation.created_at < filters.period_end,
                cast(UsageReservation.allocation, JSONB).contains(
                    {"release_reason": "budget_denied"}
                ),
            )
            .scalar()
        )
        return round(float(amount or 0) + float(released or 0), 8)

    def _label(self, dimension: str, key: Any) -> str | None:
        if key is None:
            return "Unattributed"
        if dimension == "ai_system":
            row = self._db.query(AISystem).filter(AISystem.id == key).first()
            return row.name if row else str(key)
        if dimension == "agent":
            row = self._db.query(Agent).filter(Agent.id == key).first()
            return row.name if row else str(key)
        if dimension == "delegation":
            row = (
                self._db.query(DelegationGrant)
                .filter(DelegationGrant.id == key)
                .first()
            )
            if row and isinstance(row.scope, dict):
                label = row.scope.get("tenant_label") or row.scope.get("name")
                if isinstance(label, str) and label.strip():
                    return label
            return str(key)
        if dimension == "model":
            return str(key)
        return str(key)

    def _previous(self, filters: FinOpsFilters) -> FinOpsFilters:
        delta = filters.period_end - filters.period_start
        return FinOpsFilters(
            period_start=filters.period_start - delta,
            period_end=filters.period_start,
            ai_system_id=filters.ai_system_id,
            agent_id=filters.agent_id,
            agent_version_id=filters.agent_version_id,
            runtime_identity_id=filters.runtime_identity_id,
            delegation_id=filters.delegation_id,
            provider=filters.provider,
            model=filters.model,
            environment=filters.environment,
            integration_id=filters.integration_id,
            cost_state=filters.cost_state,
            metering_source=filters.metering_source,
        )


def _dimension_column(dimension: str):
    return {
        "ai_system": RuntimeMeteringSpan.ai_system_id,
        "agent": RuntimeMeteringSpan.agent_id,
        "agent_version": RuntimeMeteringSpan.agent_version_id,
        "runtime_identity": RuntimeMeteringSpan.runtime_identity_id,
        "delegation": RuntimeMeteringSpan.delegation_id,
        "provider": RuntimeMeteringSpan.provider,
        "model": RuntimeMeteringSpan.model,
        "tool": RuntimeMeteringSpan.operation,
        "environment": RuntimeMeteringSpan.environment,
        "integration": RuntimeMeteringSpan.integration_id,
    }.get(dimension)


def _period(filters: FinOpsFilters) -> dict[str, str]:
    return {
        "start": filters.period_start.isoformat(),
        "end": filters.period_end.isoformat(),
    }


def _change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return round(((current - previous) / previous) * 100, 1)
