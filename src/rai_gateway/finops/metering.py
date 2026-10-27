"""Runtime metering: span capture, cost provenance, trajectory economics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from rai_gateway.finops.cursor_catalog import (
    cursor_token_rate_applies,
    lookup_cursor_model,
    normalize_cursor_plan,
    resolve_cursor_model_id,
)
from rai_gateway.finops.cursor_pricing_data import (
    LEGACY_MAX_MODE_MULTIPLIER,
    REGIONAL_RESIDENCY_UPLIFT,
)
from rai_gateway.finops.domain import (
    METERING_SOURCE_STRENGTH,
    CostState,
    MeteringSource,
    SpanType,
    normalize_cost_state,
    normalize_model,
    normalize_provider,
    settled_amount,
)
from rai_gateway.finops.metrics import inc
from rai_gateway.finops.pricing import PricingEngine, UsageMeasurement, pricing_entry_id
from rai_gateway.models.finops import UsageSettlement
from rai_gateway.models.metering import RuntimeMeteringSpan
from rai_gateway.models.registry import AISystem

_SECRET_KEYS = {
    "prompt",
    "prompts",
    "content",
    "messages",
    "secret",
    "password",
    "api_key",
    "authorization",
    "access_token",
    "refresh_token",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def sanitize_metadata(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    if not metadata:
        return None
    clean: dict[str, Any] = {}
    for key, value in metadata.items():
        if str(key).lower() in _SECRET_KEYS:
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            clean[str(key)] = value
    return clean or None


def normalize_usage(usage: dict[str, Any] | None) -> dict[str, int | None]:
    """Normalize common provider usage aliases into canonical token fields."""
    payload = dict(usage or {})
    details = payload.get("prompt_tokens_details")
    if not isinstance(details, dict):
        details = payload.get("input_tokens_details")
    if not isinstance(details, dict):
        details = {}
    output_details = payload.get("completion_tokens_details")
    if not isinstance(output_details, dict):
        output_details = payload.get("output_tokens_details")
    if not isinstance(output_details, dict):
        output_details = {}

    input_tokens = _as_int(payload.get("input_tokens"))
    if input_tokens is None:
        input_tokens = _as_int(payload.get("prompt_tokens"))
    if input_tokens is None:
        input_tokens = _as_int(payload.get("prompt_token_count"))

    output_tokens = _as_int(payload.get("output_tokens"))
    if output_tokens is None:
        output_tokens = _as_int(payload.get("completion_tokens"))
    if output_tokens is None:
        output_tokens = _as_int(payload.get("candidates_token_count"))

    cached = _as_int(payload.get("cached_input_tokens"))
    if cached is None:
        cached = _as_int(payload.get("cached_tokens"))
    if cached is None:
        cached = _as_int(details.get("cached_tokens"))
    if cached is None:
        cached = _as_int(payload.get("cache_read_input_tokens"))

    cache_write = _as_int(payload.get("cache_write_tokens"))
    if cache_write is None:
        cache_write = _as_int(payload.get("cache_creation_input_tokens"))
    if cache_write is None:
        cache_write = _as_int(payload.get("cache_write_input_tokens"))

    reasoning = _as_int(payload.get("reasoning_tokens"))
    if reasoning is None:
        reasoning = _as_int(output_details.get("reasoning_tokens"))
    if reasoning is None:
        reasoning = _as_int(payload.get("thoughts_token_count"))

    total = _as_int(payload.get("total_tokens"))
    if total is None:
        total = _as_int(payload.get("total_token_count"))
    if total is None and (input_tokens is not None or output_tokens is not None):
        total = (input_tokens or 0) + (output_tokens or 0)
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cached_input_tokens": cached,
        "cache_write_tokens": cache_write,
        "reasoning_tokens": reasoning,
        "total_tokens": total,
        "image_inputs": _as_int(
            payload.get("image_inputs") or payload.get("image_input_units")
        ),
        "image_outputs": _as_int(
            payload.get("image_outputs") or payload.get("image_output_units")
        ),
        "audio_input_seconds": _as_float(
            payload.get("audio_input_seconds") or payload.get("audio_input_units")
        ),
        "audio_output_seconds": _as_float(
            payload.get("audio_output_seconds") or payload.get("audio_output_units")
        ),
    }


@dataclass
class ResolvedCost:
    input_tokens: int | None
    output_tokens: int | None
    cached_input_tokens: int | None
    reasoning_tokens: int | None
    total_tokens: int | None
    estimated_cost: float | None
    metered_cost: float | None
    billed_cost: float | None
    actual_cost: float | None  # legacy mirror of settled amount
    currency: str
    cost_state: str
    metering_source: str
    pricing_entry_id: UUID | None
    pricing_snapshot: dict[str, Any] | None
    provider: str | None
    model: str | None


def _explicit_amount(usage: dict[str, Any], cost: dict[str, Any]) -> float | None:
    for source in (cost, usage):
        amount = _as_float(source.get("amount"))
        if amount is None:
            amount = _as_float(source.get("cost"))
        if amount is not None:
            return amount
    return None


def _source_name(usage: dict[str, Any], cost: dict[str, Any]) -> str:
    raw = (
        cost.get("source")
        or usage.get("source")
        or usage.get("metering_source")
        or MeteringSource.UNKNOWN.value
    )
    value = str(raw).upper()
    known = {item.value for item in MeteringSource}
    return value if value in known else MeteringSource.UNKNOWN.value


class RuntimeMeteringService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def resolve_cost(
        self,
        *,
        usage: dict[str, Any] | None = None,
        cost: dict[str, Any] | None = None,
        provider: str | None = None,
        model: str | None = None,
        currency: str = "USD",
        at: datetime | None = None,
        tokens_are_estimated: bool = False,
    ) -> ResolvedCost:
        from rai_gateway.finops.service import FinOpsService

        usage = dict(usage or {})
        cost = dict(cost or {})
        tokens = normalize_usage(usage)
        provider_name = normalize_provider(
            provider or usage.get("provider") or cost.get("provider")
        )
        model_name = normalize_model(model or usage.get("model") or cost.get("model"))
        money = str(cost.get("currency") or usage.get("currency") or currency or "USD")
        source = _source_name(usage, cost)
        amount = _explicit_amount(usage, cost)
        when = at or _utcnow()

        pricing = None
        measurement = UsageMeasurement(
            input_tokens=tokens["input_tokens"],
            output_tokens=tokens["output_tokens"],
            cached_input_tokens=tokens["cached_input_tokens"],
            cache_write_tokens=tokens.get("cache_write_tokens"),
            reasoning_tokens=tokens["reasoning_tokens"],
            image_inputs=tokens.get("image_inputs"),
            image_outputs=tokens.get("image_outputs"),
            audio_input_seconds=tokens.get("audio_input_seconds"),
            audio_output_seconds=tokens.get("audio_output_seconds"),
            request_count=_as_int(usage.get("request_count")),
            provider_tool_calls=_as_int(usage.get("provider_tool_calls")),
            tokens_are_estimated=tokens_are_estimated,
        )
        if (
            amount is None
            and provider_name
            and model_name
            and measurement.has_billable_usage()
        ):
            lookup_model = model_name
            fast = bool(usage.get("fast"))
            plan = usage.get("plan") or usage.get("cursor_plan")
            if (
                provider_name == "cursor"
                and fast
                and normalize_cursor_plan(str(plan) if plan else None) == "start"
            ):
                fast = False
            if provider_name == "cursor":
                resolved_model = resolve_cursor_model_id(model_name, fast=fast)
                if resolved_model:
                    lookup_model = resolved_model
            pricing = FinOpsService(self._db).get_active_pricing(
                provider=provider_name,
                model=lookup_model,
                currency=money,
                at=when,
            )
            if pricing is None:
                inc("finops_pricing_lookup_miss_total")

        explicit_rate = usage.get(
            "apply_cursor_token_rate", cost.get("apply_cursor_token_rate")
        )
        if explicit_rate is not None and not isinstance(explicit_rate, bool):
            explicit_rate = str(explicit_rate).lower() in {"1", "true", "yes"}
        plan_name = usage.get("plan") or usage.get("cursor_plan") or cost.get("plan")
        priced_spec = None
        if provider_name == "cursor" and pricing is not None:
            priced_spec = lookup_cursor_model(pricing.model)
        apply_rate = cursor_token_rate_applies(
            priced_spec, plan=plan_name, explicit=explicit_rate
        )
        max_mode = bool(usage.get("max_mode") or cost.get("max_mode"))
        regional = bool(
            usage.get("regional_residency") or cost.get("regional_residency")
        )

        breakdown = PricingEngine().calculate(
            usage=measurement,
            pricing=pricing,
            explicit_amount=amount,
            metering_source=source,
            currency=money,
            apply_cursor_token_rate=apply_rate,
            max_mode_multiplier=(
                LEGACY_MAX_MODE_MULTIPLIER
                if max_mode and provider_name == "cursor"
                else None
            ),
            regional_uplift=(
                REGIONAL_RESIDENCY_UPLIFT
                if regional and provider_name == "cursor"
                else None
            ),
        )
        estimated = None
        metered = None
        billed = None
        if breakdown.state == CostState.ESTIMATED.value:
            estimated = breakdown.total_cost
        elif breakdown.state == CostState.METERED.value:
            metered = breakdown.total_cost
        elif breakdown.state == CostState.BILLED.value:
            billed = breakdown.total_cost
        legacy_actual = settled_amount(
            billed_cost=billed, metered_cost=metered, estimated_cost=None
        )
        return ResolvedCost(
            input_tokens=tokens["input_tokens"],
            output_tokens=tokens["output_tokens"],
            cached_input_tokens=tokens["cached_input_tokens"],
            reasoning_tokens=tokens["reasoning_tokens"],
            total_tokens=tokens["total_tokens"],
            estimated_cost=estimated,
            metered_cost=metered,
            billed_cost=billed,
            actual_cost=legacy_actual,
            currency=breakdown.currency,
            cost_state=breakdown.state,
            metering_source=breakdown.metering_source,
            pricing_entry_id=pricing_entry_id(breakdown),
            pricing_snapshot=breakdown.pricing_snapshot or None,
            provider=provider_name,
            model=model_name,
        )

    def record_span(self, **fields: Any) -> RuntimeMeteringSpan:
        external_span_id = fields.get("external_span_id")
        if external_span_id:
            existing = (
                self._db.query(RuntimeMeteringSpan)
                .filter(
                    RuntimeMeteringSpan.external_span_id == external_span_id,
                )
                .first()
            )
            if existing:
                payload = dict(fields)
                return self.complete_span(existing.id, **payload)

        self._assert_owned_refs(fields)
        resolved = self.resolve_cost(
            usage=fields.get("usage"),
            cost=fields.get("cost"),
            provider=fields.get("provider"),
            model=fields.get("model"),
            currency=fields.get("currency") or "USD",
            at=_parse_dt(fields.get("started_at")) or _utcnow(),
            tokens_are_estimated=bool(fields.get("tokens_are_estimated")),
        )
        started = _parse_dt(fields.get("started_at")) or _utcnow()
        completed = _parse_dt(fields.get("completed_at"))
        duration = fields.get("duration_ms")
        if duration is None and started and completed:
            duration = int((completed - started).total_seconds() * 1000)
        span = RuntimeMeteringSpan(
            ai_system_id=fields.get("ai_system_id"),
            agent_id=fields.get("agent_id"),
            agent_version_id=fields.get("agent_version_id"),
            runtime_identity_id=fields.get("runtime_identity_id"),
            delegation_id=fields.get("delegation_id"),
            runtime_conversation_id=fields.get("runtime_conversation_id"),
            trajectory_id=fields.get("trajectory_id"),
            enforcement_receipt_id=fields.get("enforcement_receipt_id"),
            external_span_id=external_span_id,
            parent_span_id=fields.get("parent_span_id"),
            correlation_id=fields.get("correlation_id"),
            span_type=str(fields.get("span_type") or SpanType.MODEL_CALL.value),
            operation=fields.get("operation"),
            provider=resolved.provider,
            model=resolved.model,
            environment=fields.get("environment"),
            integration_id=fields.get("integration_id"),
            input_tokens=resolved.input_tokens,
            output_tokens=resolved.output_tokens,
            cached_input_tokens=resolved.cached_input_tokens,
            reasoning_tokens=resolved.reasoning_tokens,
            total_tokens=resolved.total_tokens,
            estimated_cost=resolved.estimated_cost,
            metered_cost=resolved.metered_cost,
            billed_cost=resolved.billed_cost,
            actual_cost=resolved.actual_cost,
            currency=resolved.currency,
            cost_state=resolved.cost_state,
            pricing_entry_id=resolved.pricing_entry_id,
            pricing_snapshot=resolved.pricing_snapshot,
            metering_source=resolved.metering_source,
            model_resource_id=fields.get("model_resource_id"),
            tool_id=fields.get("tool_id"),
            mcp_server_id=fields.get("mcp_server_id"),
            external_service_id=fields.get("external_service_id"),
            cache_write_tokens=(
                (fields.get("usage") or {}).get("cache_write_tokens")
                if isinstance(fields.get("usage"), dict)
                else None
            ),
            started_at=started,
            completed_at=completed,
            duration_ms=duration,
            metadata_json=sanitize_metadata(fields.get("metadata")),
        )
        self._db.add(span)
        self._db.flush()
        self._count_span(span)
        if resolved.cost_state in {CostState.METERED.value, CostState.BILLED.value}:
            self.settle_from_span(span)
        return span

    def complete_span(self, span_id: UUID, **fields: Any) -> RuntimeMeteringSpan:
        span = (
            self._db.query(RuntimeMeteringSpan)
            .filter(
                RuntimeMeteringSpan.id == span_id,
            )
            .first()
        )
        if not span:
            raise LookupError("Metering span not found")
        incoming = self.resolve_cost(
            usage=fields.get("usage") or {},
            cost=fields.get("cost") or {},
            provider=fields.get("provider") or span.provider,
            model=fields.get("model") or span.model,
            currency=fields.get("currency") or span.currency or "USD",
            at=span.started_at,
        )
        current_strength = METERING_SOURCE_STRENGTH.get(span.metering_source or "", 0)
        incoming_strength = METERING_SOURCE_STRENGTH.get(incoming.metering_source, 0)
        if (
            incoming.cost_state != CostState.UNAVAILABLE.value
            and incoming_strength >= current_strength
        ):
            span.estimated_cost = incoming.estimated_cost
            span.metered_cost = incoming.metered_cost
            span.billed_cost = incoming.billed_cost
            span.actual_cost = incoming.actual_cost
            span.cost_state = incoming.cost_state
            span.metering_source = incoming.metering_source
            span.pricing_entry_id = incoming.pricing_entry_id
            span.pricing_snapshot = incoming.pricing_snapshot
            span.currency = incoming.currency
            for name in (
                "input_tokens",
                "output_tokens",
                "cached_input_tokens",
                "reasoning_tokens",
                "total_tokens",
                "provider",
                "model",
            ):
                value = getattr(incoming, name)
                if value is not None:
                    setattr(span, name, value)
        completed = _parse_dt(fields.get("completed_at"))
        if completed:
            span.completed_at = completed
            if span.started_at:
                span.duration_ms = int(
                    (completed - span.started_at).total_seconds() * 1000
                )
        self._db.flush()
        if span.cost_state in {CostState.METERED.value, CostState.BILLED.value}:
            self.settle_from_span(span)
        return span

    def record_model_usage(self, **fields: Any) -> RuntimeMeteringSpan:
        fields["span_type"] = SpanType.MODEL_CALL.value
        return self.record_span(**fields)

    def record_tool_usage(self, **fields: Any) -> RuntimeMeteringSpan:
        fields["span_type"] = SpanType.TOOL_CALL.value
        return self.record_span(**fields)

    def settle_from_span(self, span: RuntimeMeteringSpan) -> UsageSettlement | None:
        state = normalize_cost_state(
            span.cost_state, metering_source=span.metering_source
        )
        amount = settled_amount(
            billed_cost=span.billed_cost,
            metered_cost=span.metered_cost,
            estimated_cost=None,
            actual_cost=span.actual_cost,
        )
        if (
            state not in {CostState.METERED.value, CostState.BILLED.value}
            or amount is None
        ):
            return None
        existing = (
            self._db.query(UsageSettlement)
            .filter(UsageSettlement.metering_span_id == span.id)
            .first()
        )
        if existing:
            return existing
        settlement = UsageSettlement(
            ai_system_id=span.ai_system_id,
            agent_id=span.agent_id,
            agent_version_id=span.agent_version_id,
            runtime_identity_id=span.runtime_identity_id,
            delegation_id=span.delegation_id,
            runtime_conversation_id=span.runtime_conversation_id,
            trajectory_id=span.trajectory_id,
            metering_span_id=span.id,
            enforcement_receipt_id=span.enforcement_receipt_id,
            correlation_id=span.correlation_id,
            provider=span.provider,
            model=span.model,
            input_tokens=span.input_tokens,
            output_tokens=span.output_tokens,
            total_tokens=span.total_tokens,
            actual_cost=float(amount),
            estimated_cost=span.estimated_cost,
            metered_cost=span.metered_cost,
            billed_cost=span.billed_cost,
            currency=span.currency,
            cost_state=state,
            metering_source=span.metering_source,
            pricing_entry_id=span.pricing_entry_id,
            pricing_snapshot=span.pricing_snapshot,
        )
        self._db.add(settlement)
        self._db.flush()
        inc("finops_settlement_total")
        return settlement

    def trajectory_economics(
        self,
        trajectory_id: UUID,
    ) -> dict[str, Any]:
        spans = (
            self._db.query(RuntimeMeteringSpan)
            .filter(
                RuntimeMeteringSpan.trajectory_id == trajectory_id,
            )
            .order_by(RuntimeMeteringSpan.started_at.asc())
            .all()
        )
        return {
            "trajectory_id": str(trajectory_id),
            "conversation_id": str(spans[0].runtime_conversation_id)
            if spans and spans[0].runtime_conversation_id
            else None,
            "summary": aggregate_spans(spans),
            "spans": [self.serialize_span(span) for span in spans],
        }

    def summarize_trajectories(
        self, trajectory_ids: list[UUID]
    ) -> dict[str, dict[str, Any]]:
        if not trajectory_ids:
            return {}
        spans = (
            self._db.query(RuntimeMeteringSpan)
            .filter(
                RuntimeMeteringSpan.trajectory_id.in_(trajectory_ids),
            )
            .all()
        )
        grouped: dict[UUID, list[RuntimeMeteringSpan]] = {}
        for span in spans:
            if span.trajectory_id:
                grouped.setdefault(span.trajectory_id, []).append(span)
        return {str(key): aggregate_spans(rows) for key, rows in grouped.items()}

    def summarize_conversations(
        self, conversation_ids: list[UUID]
    ) -> dict[str, dict[str, Any]]:
        if not conversation_ids:
            return {}
        spans = (
            self._db.query(RuntimeMeteringSpan)
            .filter(
                RuntimeMeteringSpan.runtime_conversation_id.in_(conversation_ids),
            )
            .all()
        )
        grouped: dict[UUID, list[RuntimeMeteringSpan]] = {}
        for span in spans:
            if span.runtime_conversation_id:
                grouped.setdefault(span.runtime_conversation_id, []).append(span)

        missing = [cid for cid in conversation_ids if cid not in grouped]
        if missing:
            from rai_gateway.models.evidence import RuntimeTrajectory

            trajectories = (
                self._db.query(
                    RuntimeTrajectory.id,
                    RuntimeTrajectory.runtime_conversation_id,
                )
                .filter(RuntimeTrajectory.runtime_conversation_id.in_(missing))
                .all()
            )
            traj_to_conversation = {
                row.id: row.runtime_conversation_id
                for row in trajectories
                if row.runtime_conversation_id
            }
            if traj_to_conversation:
                extra = (
                    self._db.query(RuntimeMeteringSpan)
                    .filter(
                        RuntimeMeteringSpan.trajectory_id.in_(
                            list(traj_to_conversation)
                        ),
                    )
                    .all()
                )
                for span in extra:
                    conversation_id = traj_to_conversation.get(span.trajectory_id)
                    if conversation_id:
                        grouped.setdefault(conversation_id, []).append(span)
        return {str(key): aggregate_spans(rows) for key, rows in grouped.items()}

    def conversation_economics(
        self, *, runtime_conversation_id: UUID, trajectory_ids: list[UUID]
    ) -> dict[str, Any]:
        spans = (
            self._db.query(RuntimeMeteringSpan)
            .filter(
                RuntimeMeteringSpan.runtime_conversation_id == runtime_conversation_id,
            )
            .all()
        )
        if not spans and trajectory_ids:
            spans = (
                self._db.query(RuntimeMeteringSpan)
                .filter(
                    RuntimeMeteringSpan.trajectory_id.in_(trajectory_ids),
                )
                .all()
            )
        summary = aggregate_spans(spans)
        by_trajectory = self.summarize_trajectories(trajectory_ids)
        costs = [
            item.get("total_cost")
            for item in by_trajectory.values()
            if item.get("total_cost") is not None
        ]
        summary["average_cost_per_turn"] = (
            round(sum(costs) / len(costs), 8) if costs else None
        )
        summary["most_expensive_turn"] = None
        if costs:
            winner = max(
                by_trajectory.items(), key=lambda item: item[1].get("total_cost") or 0
            )
            summary["most_expensive_turn"] = {"trajectory_id": winner[0], **winner[1]}
        return summary

    def serialize_span(self, span: RuntimeMeteringSpan) -> dict[str, Any]:
        amount = display_amount(span)
        state = normalize_cost_state(
            span.cost_state, metering_source=span.metering_source
        )
        return {
            "id": str(span.id),
            "span_type": span.span_type,
            "operation": span.operation,
            "provider": span.provider,
            "model": span.model,
            "input_tokens": span.input_tokens,
            "output_tokens": span.output_tokens,
            "cached_input_tokens": span.cached_input_tokens,
            "reasoning_tokens": span.reasoning_tokens,
            "total_tokens": span.total_tokens,
            "cost": amount,
            "actual_cost": span.actual_cost,
            "estimated_cost": span.estimated_cost,
            "metered_cost": span.metered_cost,
            "billed_cost": span.billed_cost,
            "currency": span.currency,
            "cost_state": state,
            "metering_source": span.metering_source,
            "pricing_snapshot": span.pricing_snapshot,
            "duration_ms": span.duration_ms,
            "started_at": span.started_at.isoformat() if span.started_at else None,
            "completed_at": span.completed_at.isoformat()
            if span.completed_at
            else None,
            "trajectory_id": str(span.trajectory_id) if span.trajectory_id else None,
            "runtime_conversation_id": str(span.runtime_conversation_id)
            if span.runtime_conversation_id
            else None,
        }

    def _assert_owned_refs(self, fields: dict[str, Any]) -> None:
        system_id = fields.get("ai_system_id")
        if system_id:
            system = self._db.query(AISystem).filter(AISystem.id == system_id).first()
            if system is None:
                raise PermissionError("AI system is outside this organization")
        trajectory_id = fields.get("trajectory_id")
        if trajectory_id:
            from rai_gateway.models.evidence import RuntimeTrajectory

            trajectory = (
                self._db.query(RuntimeTrajectory)
                .filter(RuntimeTrajectory.id == trajectory_id)
                .first()
            )
            if trajectory is None:
                raise PermissionError("Trajectory is outside this organization")
            system = (
                self._db.query(AISystem)
                .filter(AISystem.id == trajectory.ai_system_id)
                .first()
            )
            if system is None:
                raise PermissionError("Trajectory is outside this organization")

    def _count_span(self, span: RuntimeMeteringSpan) -> None:
        inc("finops_metering_spans_total")
        state = normalize_cost_state(
            span.cost_state, metering_source=span.metering_source
        )
        amount = settled_amount(
            billed_cost=span.billed_cost,
            metered_cost=span.metered_cost,
            estimated_cost=span.estimated_cost,
            actual_cost=span.actual_cost,
        )
        if state == CostState.BILLED.value:
            inc("finops_metering_billed_total")
            if amount:
                inc("finops_cost_total_micros", int(round(amount * 1_000_000)))
        elif state == CostState.METERED.value:
            inc("finops_metering_metered_total")
            if amount:
                inc("finops_cost_total_micros", int(round(amount * 1_000_000)))
        elif state == CostState.ESTIMATED.value:
            inc("finops_metering_estimated_total")
        else:
            inc("finops_metering_unavailable_total")
        if span.total_tokens:
            inc("finops_tokens_total", span.total_tokens)


def display_amount(span: RuntimeMeteringSpan) -> float | None:
    state = normalize_cost_state(span.cost_state, metering_source=span.metering_source)
    if state == CostState.BILLED.value:
        return span.billed_cost if span.billed_cost is not None else span.actual_cost
    if state == CostState.METERED.value:
        return span.metered_cost if span.metered_cost is not None else span.actual_cost
    if state == CostState.ESTIMATED.value:
        return span.estimated_cost
    return None


def aggregate_spans(spans: list[RuntimeMeteringSpan]) -> dict[str, Any]:
    billed = 0.0
    metered = 0.0
    estimated = 0.0
    has_billed = False
    has_metered = False
    has_estimated = False
    unavailable = 0
    input_tokens = 0
    output_tokens = 0
    total_tokens = 0
    model_calls = 0
    tool_calls = 0
    currency = "USD"
    sources: set[str] = set()
    duration_ms = 0
    has_duration = False
    for span in spans:
        currency = span.currency or currency
        sources.add(span.metering_source or MeteringSource.UNKNOWN.value)
        input_tokens += span.input_tokens or 0
        output_tokens += span.output_tokens or 0
        total_tokens += span.total_tokens or 0
        if span.span_type == SpanType.MODEL_CALL.value:
            model_calls += 1
        elif span.span_type == SpanType.TOOL_CALL.value:
            tool_calls += 1
        if span.duration_ms is not None:
            duration_ms += int(span.duration_ms)
            has_duration = True
        state = normalize_cost_state(
            span.cost_state, metering_source=span.metering_source
        )
        if state == CostState.BILLED.value:
            amount = (
                span.billed_cost if span.billed_cost is not None else span.actual_cost
            )
            if amount is not None:
                billed += float(amount)
                has_billed = True
            else:
                unavailable += 1
        elif state == CostState.METERED.value:
            amount = (
                span.metered_cost if span.metered_cost is not None else span.actual_cost
            )
            if amount is not None:
                metered += float(amount)
                has_metered = True
            else:
                unavailable += 1
        elif state == CostState.ESTIMATED.value and span.estimated_cost is not None:
            estimated += float(span.estimated_cost)
            has_estimated = True
        else:
            unavailable += 1
    known_kinds = sum([has_billed, has_metered, has_estimated])
    if known_kinds > 1:
        state = CostState.MIXED.value
        total = round(billed + metered + estimated, 8)
    elif has_billed:
        state = CostState.BILLED.value
        total = round(billed, 8)
    elif has_metered:
        state = CostState.METERED.value
        total = round(metered, 8)
    elif has_estimated:
        state = CostState.ESTIMATED.value
        total = round(estimated, 8)
    else:
        state = CostState.UNAVAILABLE.value
        total = None
    return {
        "total_cost": total,
        "billed_cost": round(billed, 8) if has_billed else None,
        "metered_cost": round(metered, 8) if has_metered else None,
        "actual_cost": round(billed + metered, 8)
        if (has_billed or has_metered)
        else None,
        "estimated_cost": round(estimated, 8) if has_estimated else None,
        "currency": currency,
        "cost_state": state,
        "metering_source": next(iter(sources)) if len(sources) == 1 else "MIXED",
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "model_calls": model_calls,
        "tool_calls": tool_calls,
        "unavailable_spans": unavailable,
        "span_count": len(spans),
        "duration_ms": duration_ms if has_duration else None,
    }
