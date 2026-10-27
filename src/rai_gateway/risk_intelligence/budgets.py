"""Runtime budget evaluation and concurrency-safe enforcement."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from rai_gateway.models.evidence import RuntimeTrajectory
from rai_gateway.models.registry import Agent, AISystem
from rai_gateway.models.risk_intelligence import (
    RuntimeBudget,
    RuntimeBudgetCheck,
    RuntimeBudgetReservation,
    RuntimeBudgetWindow,
)
from rai_gateway.risk_intelligence.budget_scope import (
    BudgetEvaluationContext,
    resolve_applicable_budgets,
    resolve_matched_scope_id,
)
from rai_gateway.risk_intelligence.domain import (
    BUDGET_EFFECT_PRECEDENCE,
    BudgetEffect,
    BudgetEnforcementMode,
    BudgetMetric,
    BudgetReservationStatus,
    BudgetStatus,
    RiskScopeType,
)

logger = logging.getLogger(__name__)


def _nested_get(data: dict[str, Any], path: str) -> Any:
    cur: Any = data
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _floor_window_start(now: datetime, window_seconds: int) -> datetime:
    epoch = int(now.timestamp())
    floored = epoch - (epoch % window_seconds)
    return datetime.fromtimestamp(floored, tz=timezone.utc)


class BudgetService:
    """Manage RuntimeBudget config and pre-execution checks."""

    def __init__(self, db: Session) -> None:
        self._db = db

    # --- CRUD -------------------------------------------------------------

    def _owned_query(self):
        return self._db.query(RuntimeBudget)

    def create_budget(self, **fields: Any) -> RuntimeBudget:
        ai_system_id = fields.get("ai_system_id")
        if ai_system_id is not None:
            owned = self._db.query(AISystem).filter(AISystem.id == ai_system_id).first()
            if not owned:
                raise LookupError("AI system not found")
        scope_type = fields.get("scope_type") or RiskScopeType.AI_SYSTEM.value
        if scope_type == RiskScopeType.ORGANIZATION.value:
            fields.setdefault("scope_id", RiskScopeType.ORGANIZATION.value)
        row = RuntimeBudget(**fields)
        self._db.add(row)
        self._db.flush()
        return row

    def get_budget(
        self,
        budget_id: UUID,
    ) -> RuntimeBudget | None:
        return self._owned_query().filter(RuntimeBudget.id == budget_id).first()

    def list_budgets(
        self,
        *,
        ai_system_id: UUID | None = None,
        enabled_only: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[RuntimeBudget]:
        q = self._owned_query()
        if ai_system_id:
            q = q.filter(RuntimeBudget.ai_system_id == ai_system_id)
        if enabled_only:
            q = q.filter(RuntimeBudget.enabled.is_(True))
        return (
            q.order_by(RuntimeBudget.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def update_budget(
        self,
        budget_id: UUID,
        **fields: Any,
    ) -> RuntimeBudget:
        row = self.get_budget(budget_id)
        if not row:
            raise LookupError("Budget not found")
        for key, value in fields.items():
            if value is not None or key in (
                "tool_name",
                "tool_id",
                "scope_id",
                "amount_parameter_path",
            ):
                setattr(row, key, value)
        self._db.flush()
        return row

    def list_checks(
        self,
        budget_id: UUID,
        *,
        status: str | None = None,
        triggers_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """Return serialized budget evaluation logs for one budget."""
        budget = self.get_budget(budget_id)
        if not budget:
            raise LookupError("Budget not found")

        q = self._db.query(RuntimeBudgetCheck).filter(
            RuntimeBudgetCheck.budget_id == budget_id
        )
        if status:
            q = q.filter(RuntimeBudgetCheck.status == status)
        elif triggers_only:
            q = q.filter(
                RuntimeBudgetCheck.status.in_(
                    [BudgetStatus.WARNING.value, BudgetStatus.EXCEEDED.value]
                )
            )

        total = q.count()
        rows = (
            q.order_by(RuntimeBudgetCheck.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        trajectory_ids = [r.trajectory_id for r in rows if r.trajectory_id]
        trajectories: dict[UUID, RuntimeTrajectory] = {}
        if trajectory_ids:
            for traj in (
                self._db.query(RuntimeTrajectory)
                .filter(RuntimeTrajectory.id.in_(trajectory_ids))
                .all()
            ):
                trajectories[traj.id] = traj

        system_ids: set[UUID] = set()
        agent_ids: set[UUID] = set()
        for row in rows:
            traj = trajectories.get(row.trajectory_id) if row.trajectory_id else None
            system_id = row.ai_system_id or (traj.ai_system_id if traj else None)
            agent_id = row.agent_id or (traj.agent_id if traj else None)
            if system_id:
                system_ids.add(system_id)
            if agent_id:
                agent_ids.add(agent_id)

        systems: dict[UUID, AISystem] = {}
        if system_ids:
            systems = {
                system.id: system
                for system in self._db.query(AISystem)
                .filter(AISystem.id.in_(system_ids))
                .all()
            }
        agents: dict[UUID, Agent] = {}
        if agent_ids:
            agents = {
                agent.id: agent
                for agent in self._db.query(Agent).filter(Agent.id.in_(agent_ids)).all()
            }

        economics: dict[str, dict[str, Any]] = {}
        if trajectory_ids:
            from rai_gateway.finops.metering import RuntimeMeteringService

            economics = RuntimeMeteringService(self._db).summarize_trajectories(
                trajectory_ids
            )

        return [
            self._serialize_check(r, trajectories, systems, agents, economics)
            for r in rows
        ], total

    def check_stats_for_budgets(
        self, budget_ids: list[UUID]
    ) -> dict[UUID, dict[str, int]]:
        """Aggregate check counts keyed by budget id."""
        if not budget_ids:
            return {}
        rows = (
            self._db.query(
                RuntimeBudgetCheck.budget_id,
                RuntimeBudgetCheck.status,
                func.count(RuntimeBudgetCheck.id),
            )
            .filter(RuntimeBudgetCheck.budget_id.in_(budget_ids))
            .group_by(RuntimeBudgetCheck.budget_id, RuntimeBudgetCheck.status)
            .all()
        )
        out: dict[UUID, dict[str, int]] = {
            bid: {
                "check_count": 0,
                "trigger_count": 0,
                "warning_count": 0,
                "exceeded_count": 0,
            }
            for bid in budget_ids
        }
        for budget_id, status, count in rows:
            stats = out.setdefault(
                budget_id,
                {
                    "check_count": 0,
                    "trigger_count": 0,
                    "warning_count": 0,
                    "exceeded_count": 0,
                },
            )
            n = int(count)
            stats["check_count"] += n
            if status == BudgetStatus.WARNING.value:
                stats["warning_count"] += n
                stats["trigger_count"] += n
            elif status == BudgetStatus.EXCEEDED.value:
                stats["exceeded_count"] += n
                stats["trigger_count"] += n
        return out

    def _serialize_check(
        self,
        check: RuntimeBudgetCheck,
        trajectories: dict[UUID, RuntimeTrajectory] | None = None,
        systems: dict[UUID, AISystem] | None = None,
        agents: dict[UUID, Agent] | None = None,
        economics: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        traj = None
        if check.trajectory_id and trajectories:
            traj = trajectories.get(check.trajectory_id)
        system_id = check.ai_system_id or (traj.ai_system_id if traj else None)
        agent_id = check.agent_id or (traj.agent_id if traj else None)
        system = systems.get(system_id) if system_id and systems else None
        agent = agents.get(agent_id) if agent_id and agents else None
        econ = (
            economics.get(str(check.trajectory_id))
            if check.trajectory_id and economics
            else None
        )
        return {
            "id": str(check.id),
            "budget_id": str(check.budget_id),
            "ai_system_id": str(system_id) if system_id else None,
            "ai_system_name": system.name if system else None,
            "agent_id": str(agent_id) if agent_id else None,
            "agent_name": agent.name if agent else None,
            "agent_avatar": agent.avatar if agent else None,
            "runtime_identity_id": str(check.runtime_identity_id)
            if check.runtime_identity_id
            else None,
            "trajectory_id": str(check.trajectory_id) if check.trajectory_id else None,
            "conversation_id": traj.conversation_id if traj else None,
            "runtime_conversation_id": str(traj.runtime_conversation_id)
            if traj and traj.runtime_conversation_id
            else None,
            "metric": check.metric,
            "window_seconds": check.window_seconds,
            "usage_before": check.usage_before,
            "attempted_increment": check.attempted_increment,
            "projected_usage": check.projected_usage,
            "limit_value": check.limit_value,
            "status": check.status,
            "decision": check.decision,
            "effect": check.effect,
            "economics": econ,
            "created_at": check.created_at.isoformat() if check.created_at else None,
        }

    # --- Evaluation -------------------------------------------------------

    def check_and_consume(
        self,
        *,
        ai_system_id: UUID | None = None,
        runtime_identity_id: UUID | None = None,
        agent_id: UUID | None = None,
        agent_version_id: UUID | None = None,
        delegation_id: UUID | None = None,
        model_resource_id: UUID | None = None,
        mcp_server_id: UUID | None = None,
        tool_name: str | None = None,
        tool_id: UUID | None = None,
        provider: str | None = None,
        model: str | None = None,
        environment: str | None = None,
        parameters: dict[str, Any] | None = None,
        amount: float | None = None,
        token_usage: float | None = None,
        cost: float | None = None,
        trajectory_id: UUID | None = None,
        idempotency_key: str | None = None,
        finops_usage_reservation_id: UUID | None = None,
        commit_usage: bool = True,
        reserve_cost_token: bool = True,
    ) -> dict[str, Any]:
        """Concurrency-safe hierarchical budget check for WP4 authorize path.

        Returns overlay flags: deny, require_approval, suspend, checks[], reservations[].
        """
        ctx = BudgetEvaluationContext(
            ai_system_id=ai_system_id,
            agent_id=agent_id,
            agent_version_id=agent_version_id,
            runtime_identity_id=runtime_identity_id,
            delegation_id=delegation_id,
            model_resource_id=model_resource_id,
            mcp_server_id=mcp_server_id,
            tool_id=tool_id,
            provider=provider,
            model=model,
            environment=environment,
            tool_name=tool_name,
        )
        budgets = resolve_applicable_budgets(self._db, ctx)
        checks: list[dict[str, Any]] = []
        reservations: list[dict[str, Any]] = []
        deny = False
        deny_reason = None
        require_approval = False
        suspend = False
        monitor = False
        warnings = 0
        exceeded = 0
        effects: list[str] = []

        for budget in budgets:
            increment, unavailable = self._resolve_increment(
                budget,
                amount=amount,
                token_usage=token_usage,
                cost=cost,
                parameters=parameters,
            )
            if unavailable:
                mode = (
                    budget.enforcement_mode or BudgetEnforcementMode.BEST_EFFORT.value
                )
                if mode == BudgetEnforcementMode.MANDATORY.value:
                    checks.append(
                        {
                            "budget_id": str(budget.id),
                            "metric": budget.metric,
                            "scope_type": budget.scope_type,
                            "status": BudgetStatus.UNAVAILABLE.value,
                            "decision": "DENY",
                            "reason": "BUDGET_MEASUREMENT_UNAVAILABLE",
                        }
                    )
                    deny = True
                    deny_reason = (
                        f"Mandatory budget measurement unavailable: {budget.name} "
                        f"({budget.metric})"
                    )
                    effects.append(BudgetEffect.DENY.value)
                else:
                    checks.append(
                        {
                            "budget_id": str(budget.id),
                            "metric": budget.metric,
                            "scope_type": budget.scope_type,
                            "status": BudgetStatus.UNAVAILABLE.value,
                            "decision": "SKIP",
                            "reason": f"{budget.metric} not measurable for this action",
                        }
                    )
                continue

            use_reserve = reserve_cost_token and budget.metric in {
                BudgetMetric.COST.value,
                BudgetMetric.TOKEN_USAGE.value,
            }
            result = self._check_one(
                budget,
                ctx=ctx,
                increment=increment,
                trajectory_id=trajectory_id,
                commit_usage=commit_usage and not use_reserve,
                reserve=use_reserve and commit_usage,
                idempotency_key=idempotency_key,
                finops_usage_reservation_id=finops_usage_reservation_id,
            )
            checks.append(result)
            if result.get("reservation"):
                reservations.append(result["reservation"])
            status = result["status"]
            if status == BudgetStatus.WARNING.value:
                warnings += 1
            if status == BudgetStatus.EXCEEDED.value:
                exceeded += 1
                effect = budget.effect_on_exceed
                effects.append(effect)
                if effect == BudgetEffect.DENY.value:
                    deny = True
                    deny_reason = (
                        f"Budget exceeded: {budget.name} "
                        f"({result['projected_usage']}/{result['limit_value']} "
                        f"{budget.metric} / {budget.window_seconds}s)"
                    )
                elif effect == BudgetEffect.REQUIRE_APPROVAL.value:
                    require_approval = True
                elif effect == BudgetEffect.SUSPEND_RUNTIME_IDENTITY.value:
                    suspend = True
                    deny = True
                    deny_reason = f"Budget exceeded — suspending runtime: {budget.name}"
                elif effect == BudgetEffect.MONITOR.value:
                    monitor = True

        # If denied, release reservations created for this attempt.
        if deny and reservations and idempotency_key:
            self.release_reservations(idempotency_key=idempotency_key, reason="denied")

        dominant = None
        for effect in BUDGET_EFFECT_PRECEDENCE:
            if effect in effects:
                dominant = effect
                break

        return {
            "deny": deny,
            "deny_reason": deny_reason,
            "require_approval": require_approval,
            "suspend": suspend,
            "monitor": monitor,
            "warnings": warnings,
            "exceeded": exceeded,
            "checks": checks,
            "reservations": reservations,
            "dominant_effect": dominant,
            "applicable_budget_count": len(budgets),
        }

    def effective_budgets(self, ctx: BudgetEvaluationContext) -> list[dict[str, Any]]:
        """Serialize all budgets that would apply to a context (for UX)."""
        budgets = resolve_applicable_budgets(self._db, ctx)
        return [self.serialize_budget(b) for b in budgets]

    def reconcile_reservations(
        self,
        *,
        idempotency_key: str,
        settled_cost: float | None = None,
        settled_tokens: float | None = None,
        metering_span_id: UUID | None = None,
    ) -> list[dict[str, Any]]:
        """Reconcile COST/TOKEN budget reservations against metered values."""
        rows = (
            self._db.query(RuntimeBudgetReservation)
            .filter(
                RuntimeBudgetReservation.idempotency_key == idempotency_key,
                RuntimeBudgetReservation.status
                == BudgetReservationStatus.RESERVED.value,
            )
            .with_for_update()
            .all()
        )
        results: list[dict[str, Any]] = []
        now = datetime.now(timezone.utc)
        for row in rows:
            settled = None
            if row.metric == BudgetMetric.COST.value:
                settled = settled_cost
            elif row.metric == BudgetMetric.TOKEN_USAGE.value:
                settled = settled_tokens
            if settled is None:
                # Missing metered value — release hold without inventing cost.
                self._release_one_reservation(row, reason="unavailable_metered")
                results.append(
                    {
                        "reservation_id": str(row.id),
                        "status": BudgetReservationStatus.RELEASED.value,
                        "reason": "unavailable_metered",
                    }
                )
                continue
            window = None
            if row.budget_window_id:
                window = (
                    self._db.query(RuntimeBudgetWindow)
                    .filter(RuntimeBudgetWindow.id == row.budget_window_id)
                    .with_for_update()
                    .first()
                )
            reserved = float(row.reserved_value or 0.0)
            delta = float(settled) - reserved
            if window:
                window.reserved_value = max(
                    0.0, float(window.reserved_value or 0.0) - reserved
                )
                window.usage_value = float(window.usage_value or 0.0) + float(settled)
                limit = None
                budget = self.get_budget(row.budget_id)
                if budget:
                    limit = float(budget.limit_value)
                    warning_at = limit * float(budget.warning_threshold or 0.8)
                    if window.usage_value > limit:
                        window.status = BudgetStatus.EXCEEDED.value
                    elif window.usage_value >= warning_at:
                        window.status = BudgetStatus.WARNING.value
                    else:
                        window.status = BudgetStatus.OK.value
            row.settled_value = float(settled)
            row.delta_value = delta
            row.status = BudgetReservationStatus.SETTLED.value
            row.settled_at = now
            results.append(
                {
                    "reservation_id": str(row.id),
                    "status": BudgetReservationStatus.SETTLED.value,
                    "reserved_value": reserved,
                    "settled_value": float(settled),
                    "delta_value": delta,
                    "metering_span_id": str(metering_span_id)
                    if metering_span_id
                    else None,
                }
            )
        self._db.flush()
        return results

    def release_reservations(
        self, *, idempotency_key: str, reason: str | None = None
    ) -> int:
        rows = (
            self._db.query(RuntimeBudgetReservation)
            .filter(
                RuntimeBudgetReservation.idempotency_key == idempotency_key,
                RuntimeBudgetReservation.status
                == BudgetReservationStatus.RESERVED.value,
            )
            .with_for_update()
            .all()
        )
        for row in rows:
            self._release_one_reservation(row, reason=reason)
        self._db.flush()
        return len(rows)

    def _release_one_reservation(
        self, row: RuntimeBudgetReservation, *, reason: str | None = None
    ) -> None:
        if row.budget_window_id:
            window = (
                self._db.query(RuntimeBudgetWindow)
                .filter(RuntimeBudgetWindow.id == row.budget_window_id)
                .with_for_update()
                .first()
            )
            if window:
                window.reserved_value = max(
                    0.0,
                    float(window.reserved_value or 0.0)
                    - float(row.reserved_value or 0),
                )
        row.status = BudgetReservationStatus.RELEASED.value
        row.settled_at = datetime.now(timezone.utc)
        if reason:
            # Store reason on delta as sentinel when released without settle.
            row.delta_value = None

    def _budget_applies(
        self,
        budget: RuntimeBudget,
        *,
        runtime_identity_id: UUID | None,
        agent_version_id: UUID | None,
        tool_name: str | None,
        tool_id: UUID | None,
    ) -> bool:
        # Kept for backward-compatible call sites; prefer resolve_applicable_budgets.
        if budget.tool_name and tool_name and budget.tool_name != tool_name:
            return False
        if budget.tool_id and tool_id and budget.tool_id != tool_id:
            return False
        if budget.tool_name and not tool_name:
            return False
        if budget.scope_type == RiskScopeType.RUNTIME_IDENTITY.value:
            if budget.scope_id and runtime_identity_id:
                return str(runtime_identity_id) == budget.scope_id
            return runtime_identity_id is not None
        if budget.scope_type == RiskScopeType.AGENT_VERSION.value:
            if budget.scope_id and agent_version_id:
                return str(agent_version_id) == budget.scope_id
            return agent_version_id is not None
        if budget.scope_type in {
            RiskScopeType.AI_SYSTEM.value,
            RiskScopeType.ORGANIZATION.value,
            RiskScopeType.AGENT.value,
            RiskScopeType.DELEGATION.value,
            RiskScopeType.MODEL.value,
            RiskScopeType.MCP_SERVER.value,
            RiskScopeType.TOOL.value,
        }:
            return True
        return True

    def _resolve_increment(
        self,
        budget: RuntimeBudget,
        *,
        amount: float | None,
        token_usage: float | None,
        cost: float | None,
        parameters: dict[str, Any] | None,
    ) -> tuple[float, bool]:
        metric = budget.metric
        if metric in (BudgetMetric.ACTION_COUNT.value, BudgetMetric.TOOL_COUNT.value):
            return 1.0, False
        if metric == BudgetMetric.AMOUNT.value:
            resolved = amount
            if resolved is None and budget.amount_parameter_path and parameters:
                raw = _nested_get(parameters, budget.amount_parameter_path)
                try:
                    resolved = float(raw) if raw is not None else None
                except (TypeError, ValueError):
                    resolved = None
            if resolved is None:
                return 0.0, True  # never invent financial amounts
            return float(resolved), False
        if metric == BudgetMetric.TOKEN_USAGE.value:
            if token_usage is None:
                return 0.0, True
            return float(token_usage), False
        if metric == BudgetMetric.COST.value:
            if cost is None:
                return 0.0, True
            return float(cost), False
        return 1.0, False

    def _scope_for_budget(
        self,
        budget: RuntimeBudget,
        *,
        runtime_identity_id: UUID | None,
        agent_version_id: UUID | None,
    ) -> tuple[str, str]:
        ctx = BudgetEvaluationContext(
            ai_system_id=budget.ai_system_id,
            agent_version_id=agent_version_id,
            runtime_identity_id=runtime_identity_id,
        )
        return resolve_matched_scope_id(budget, ctx)

    def _check_one(
        self,
        budget: RuntimeBudget,
        *,
        ctx: BudgetEvaluationContext,
        increment: float,
        trajectory_id: UUID | None,
        commit_usage: bool,
        reserve: bool = False,
        idempotency_key: str | None = None,
        finops_usage_reservation_id: UUID | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        window_start = _floor_window_start(now, budget.window_seconds)
        window_end = window_start + timedelta(seconds=budget.window_seconds)
        scope_type, scope_id = resolve_matched_scope_id(budget, ctx)

        window = (
            self._db.query(RuntimeBudgetWindow)
            .filter(
                RuntimeBudgetWindow.budget_id == budget.id,
                RuntimeBudgetWindow.window_start == window_start,
                RuntimeBudgetWindow.scope_id == scope_id,
            )
            .with_for_update()
            .first()
        )
        if not window:
            try:
                with self._db.begin_nested():
                    window = RuntimeBudgetWindow(
                        budget_id=budget.id,
                        ai_system_id=budget.ai_system_id or ctx.ai_system_id,
                        scope_type=scope_type,
                        scope_id=scope_id,
                        window_start=window_start,
                        window_end=window_end,
                        usage_value=0.0,
                        reserved_value=0.0,
                        status=BudgetStatus.OK.value,
                    )
                    self._db.add(window)
                    self._db.flush()
            except Exception:
                window = (
                    self._db.query(RuntimeBudgetWindow)
                    .filter(
                        RuntimeBudgetWindow.budget_id == budget.id,
                        RuntimeBudgetWindow.window_start == window_start,
                        RuntimeBudgetWindow.scope_id == scope_id,
                    )
                    .with_for_update()
                    .first()
                )
                if not window:
                    raise
            else:
                window = (
                    self._db.query(RuntimeBudgetWindow)
                    .filter(RuntimeBudgetWindow.id == window.id)
                    .with_for_update()
                    .first()
                )

        usage_before = float(window.usage_value or 0.0)
        reserved_before = float(window.reserved_value or 0.0)
        projected = usage_before + reserved_before + float(increment)
        limit = float(budget.limit_value)
        warning_at = limit * float(budget.warning_threshold or 0.8)

        if projected > limit:
            status = BudgetStatus.EXCEEDED.value
            decision = "BLOCK"
        elif projected >= warning_at:
            status = BudgetStatus.WARNING.value
            decision = "ALLOW"
        else:
            status = BudgetStatus.OK.value
            decision = "ALLOW"

        reservation_payload = None
        if reserve and decision != "BLOCK" and idempotency_key:
            existing = (
                self._db.query(RuntimeBudgetReservation)
                .filter(
                    RuntimeBudgetReservation.budget_id == budget.id,
                    RuntimeBudgetReservation.idempotency_key == idempotency_key,
                )
                .first()
            )
            if existing:
                reservation_payload = {
                    "id": str(existing.id),
                    "status": existing.status,
                    "reserved_value": existing.reserved_value,
                }
            else:
                window.reserved_value = reserved_before + float(increment)
                reservation = RuntimeBudgetReservation(
                    budget_id=budget.id,
                    budget_window_id=window.id,
                    runtime_identity_id=ctx.runtime_identity_id,
                    delegation_id=ctx.delegation_id,
                    trajectory_id=trajectory_id,
                    finops_usage_reservation_id=finops_usage_reservation_id,
                    idempotency_key=idempotency_key,
                    metric=budget.metric,
                    reserved_value=float(increment),
                    status=BudgetReservationStatus.RESERVED.value,
                    expires_at=now + timedelta(hours=24),
                )
                self._db.add(reservation)
                self._db.flush()
                reservation_payload = {
                    "id": str(reservation.id),
                    "status": reservation.status,
                    "reserved_value": reservation.reserved_value,
                }
        elif commit_usage and decision != "BLOCK":
            window.usage_value = usage_before + float(increment)
            if window.usage_value > limit:
                window.status = BudgetStatus.EXCEEDED.value
            elif window.usage_value >= warning_at:
                window.status = BudgetStatus.WARNING.value
            else:
                window.status = BudgetStatus.OK.value

        check = RuntimeBudgetCheck(
            budget_id=budget.id,
            ai_system_id=budget.ai_system_id or ctx.ai_system_id,
            runtime_identity_id=ctx.runtime_identity_id,
            agent_id=ctx.agent_id,
            agent_version_id=ctx.agent_version_id,
            delegation_id=ctx.delegation_id,
            model_resource_id=ctx.model_resource_id,
            tool_id=ctx.tool_id,
            trajectory_id=trajectory_id,
            reservation_id=UUID(reservation_payload["id"])
            if reservation_payload
            else None,
            metric=budget.metric,
            window_seconds=budget.window_seconds,
            usage_before=usage_before,
            attempted_increment=float(increment),
            projected_usage=projected,
            limit_value=limit,
            status=status,
            decision=decision,
            effect=budget.effect_on_exceed
            if status == BudgetStatus.EXCEEDED.value
            else None,
        )
        self._db.add(check)
        self._db.flush()

        payload = {
            "budget_id": str(budget.id),
            "budget_name": budget.name,
            "metric": budget.metric,
            "scope_type": budget.scope_type,
            "scope_id": scope_id,
            "status": status,
            "decision": decision,
            "usage_before": usage_before,
            "reserved_before": reserved_before,
            "attempted_increment": float(increment),
            "projected_usage": projected,
            "limit_value": limit,
            "check_id": str(check.id),
        }
        if reservation_payload:
            payload["reservation"] = reservation_payload
        return payload

    def serialize_budget(
        self,
        budget: RuntimeBudget,
        *,
        include_usage: bool = True,
        check_stats: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": str(budget.id),
            "ai_system_id": str(budget.ai_system_id) if budget.ai_system_id else None,
            "name": budget.name,
            "scope_type": budget.scope_type,
            "scope_id": budget.scope_id,
            "metric": budget.metric,
            "tool_name": budget.tool_name,
            "tool_id": str(budget.tool_id) if budget.tool_id else None,
            "resource_filter": budget.resource_filter,
            "limit_value": budget.limit_value,
            "window_seconds": budget.window_seconds,
            "warning_threshold": budget.warning_threshold,
            "effect_on_exceed": budget.effect_on_exceed,
            "amount_parameter_path": budget.amount_parameter_path,
            "enforcement_mode": budget.enforcement_mode
            or BudgetEnforcementMode.BEST_EFFORT.value,
            "enabled": budget.enabled,
            "created_at": budget.created_at.isoformat() if budget.created_at else None,
        }
        if include_usage:
            usage = self._current_usage_snapshot(budget)
            payload.update(usage)
        if check_stats is not None:
            payload.update(check_stats)
        else:
            payload.update(
                {
                    "check_count": 0,
                    "trigger_count": 0,
                    "warning_count": 0,
                    "exceeded_count": 0,
                }
            )
        return payload

    def _current_usage_snapshot(self, budget: RuntimeBudget) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        window_start = _floor_window_start(now, budget.window_seconds)
        windows = (
            self._db.query(RuntimeBudgetWindow)
            .filter(
                RuntimeBudgetWindow.budget_id == budget.id,
                RuntimeBudgetWindow.window_start == window_start,
            )
            .all()
        )
        usage = sum(float(w.usage_value or 0.0) for w in windows)
        limit = float(budget.limit_value)
        remaining = max(0.0, limit - usage)
        utilization = (usage / limit * 100.0) if limit else 0.0
        if usage > limit:
            status = BudgetStatus.EXCEEDED.value
        elif usage >= limit * float(budget.warning_threshold or 0.8):
            status = BudgetStatus.WARNING.value
        else:
            status = BudgetStatus.OK.value
        return {
            "current_usage": usage,
            "remaining": remaining,
            "utilization_pct": round(utilization, 2),
            "status": status,
            "window_start": window_start.isoformat(),
            "effect": budget.effect_on_exceed,
        }

    def count_by_status(
        self,
        *,
        ai_system_id: UUID | None = None,
    ) -> dict[str, int]:
        budgets = self.list_budgets(
            ai_system_id=ai_system_id,
            enabled_only=True,
            limit=500,
        )
        warning = 0
        exceeded = 0
        for b in budgets:
            snap = self._current_usage_snapshot(b)
            if snap["status"] == BudgetStatus.WARNING.value:
                warning += 1
            elif snap["status"] == BudgetStatus.EXCEEDED.value:
                exceeded += 1
        return {"warning": warning, "exceeded": exceeded}
