"""AI FinOps — pricing catalog, reservation, settlement, trusted metering."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from rai_gateway.finops.cursor_catalog import (
    SEED_ACTOR,
    cursor_catalog_document,
    cursor_token_rate_applies,
    lookup_cursor_model,
    normalize_cursor_plan,
    pricing_metadata_for,
    published_cursor_entry,
    resolve_cursor_model_id,
)
from rai_gateway.finops.cursor_pricing_data import (
    CATALOG_VERSION,
    LEGACY_MAX_MODE_MULTIPLIER,
    PRICING_UNIT,
    REGIONAL_RESIDENCY_UPLIFT,
    SOURCE_URL,
)
from rai_gateway.finops.domain import (
    METERING_TRUST_ORDER,
    CostState,
    MeteringSource,
    ReservationStatus,
    normalize_provider,
    settled_amount,
)
from rai_gateway.finops.pricing import PricingEngine, UsageMeasurement, pricing_entry_id
from rai_gateway.models.finops import (
    PricingCatalogEntry,
    UsageReservation,
    UsageSettlement,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _close(left: Any, right: Any) -> bool:
    if left is None and right is None:
        return True
    if left is None or right is None:
        return False
    return abs(float(left) - float(right)) < 1e-6


def _cursor_row_matches(row: PricingCatalogEntry, public_spec: dict[str, Any]) -> bool:
    raw = lookup_cursor_model(public_spec["id"])
    if raw is None:
        return False
    if int(row.pricing_unit or 1000) != PRICING_UNIT:
        return False
    if not _close(row.input_token_price, raw["input"]):
        return False
    if not _close(row.output_token_price, raw["output"]):
        return False
    if not _close(row.cached_input_token_price, raw["cache_read"]):
        return False
    if not _close(row.cache_write_token_price, raw["cache_write"]):
        return False
    expected = pricing_metadata_for(raw)
    meta = row.pricing_metadata if isinstance(row.pricing_metadata, dict) else {}
    if bool(meta.get("cursor_token_rate_exempt")) != bool(
        expected["cursor_token_rate_exempt"]
    ):
        return False
    if meta.get("cursor_token_rate_per_million") != expected.get(
        "cursor_token_rate_per_million"
    ):
        return False
    return (meta.get("context_tiers") or []) == (expected.get("context_tiers") or [])


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def pick_trusted_usage(
    usage: dict[str, Any] | None,
    cost: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], str]:
    """Select the most trusted usage payload from nested or flat report metadata.

    Accepted shapes:
    - {"source": "PROVIDER_RESPONSE", "input_tokens": N, "output_tokens": M}
    - {"provider_response": {...}, "agent_supplied": {...}}  # pick best key
    - flat usage with optional cost dict
    """
    usage = dict(usage or {})
    cost = dict(cost or {})

    # Nested by source name
    for source in METERING_TRUST_ORDER:
        key = source.lower()
        nested = usage.get(key) or usage.get(source)
        if isinstance(nested, dict) and nested:
            payload = dict(nested)
            if cost and "amount" not in payload and "cost" not in payload:
                payload.setdefault("cost", cost.get("amount") or cost.get("cost"))
            return payload, source

    explicit = (
        usage.get("source")
        or usage.get("metering_source")
        or cost.get("source")
        or MeteringSource.AGENT_SUPPLIED.value
    )
    explicit = str(explicit).upper()
    if explicit not in {s.value for s in MeteringSource}:
        explicit = MeteringSource.AGENT_SUPPLIED.value

    payload = dict(usage)
    if cost:
        payload.setdefault("cost", cost.get("amount") or cost.get("cost"))
        payload.setdefault("currency", cost.get("currency"))
    return payload, explicit


class FinOpsService:
    """Trusted metering, pricing, reservation, and settlement."""

    def __init__(self, db: Session) -> None:
        self._db = db

    # --- Pricing catalog --------------------------------------------------

    def upsert_pricing(
        self,
        *,
        provider: str,
        model: str,
        input_token_price: float,
        output_token_price: float,
        created_by: str,
        currency: str = "USD",
        effective_from: datetime | None = None,
        effective_to: datetime | None = None,
        cached_input_token_price: float | None = None,
        reasoning_token_price: float | None = None,
        minimum_request_cost: float | None = None,
        cache_write_token_price: float | None = None,
        image_input_price: float | None = None,
        image_output_price: float | None = None,
        audio_input_price: float | None = None,
        audio_output_price: float | None = None,
        request_price: float | None = None,
        provider_tool_price: float | None = None,
        pricing_metadata: dict[str, Any] | None = None,
        source_url: str | None = None,
        verified_at: datetime | None = None,
        region: str | None = None,
        service_tier: str | None = None,
        pricing_unit: int = 1000,
    ) -> PricingCatalogEntry:
        now = _utcnow()
        start = effective_from or now
        # Close any open version for same provider/model/currency
        open_rows = (
            self._db.query(PricingCatalogEntry)
            .filter(
                PricingCatalogEntry.provider == provider,
                PricingCatalogEntry.model == model,
                PricingCatalogEntry.currency == currency,
                PricingCatalogEntry.effective_to.is_(None),
                PricingCatalogEntry.enabled.is_(True),
            )
            .all()
        )
        for row in open_rows:
            if row.effective_from < start:
                row.effective_to = start

        entry = PricingCatalogEntry(
            provider=provider,
            model=model,
            input_token_price=float(input_token_price),
            output_token_price=float(output_token_price),
            cached_input_token_price=cached_input_token_price,
            reasoning_token_price=reasoning_token_price,
            minimum_request_cost=minimum_request_cost,
            cache_write_token_price=cache_write_token_price,
            image_input_price=image_input_price,
            image_output_price=image_output_price,
            audio_input_price=audio_input_price,
            audio_output_price=audio_output_price,
            request_price=request_price,
            provider_tool_price=provider_tool_price,
            pricing_metadata=pricing_metadata,
            source_url=source_url,
            verified_at=verified_at,
            region=region,
            service_tier=service_tier,
            pricing_unit=pricing_unit or 1000,
            currency=currency,
            effective_from=start,
            effective_to=effective_to,
            enabled=True,
            created_by=created_by,
        )
        self._db.add(entry)
        self._db.commit()
        self._db.refresh(entry)
        return entry

    def get_pricing(self, pricing_id: UUID) -> PricingCatalogEntry | None:
        return (
            self._db.query(PricingCatalogEntry)
            .filter(PricingCatalogEntry.id == pricing_id)
            .first()
        )

    def get_active_pricing(
        self,
        *,
        provider: str,
        model: str,
        currency: str = "USD",
        at: datetime | None = None,
        fast: bool = False,
    ) -> PricingCatalogEntry | None:
        when = at or _utcnow()
        provider_key = normalize_provider(provider) or provider
        model_key = model
        if provider_key == "cursor":
            resolved = resolve_cursor_model_id(model, fast=fast)
            if resolved:
                model_key = resolved
        row = self._find_db_pricing(
            provider=provider_key,
            model=model_key,
            currency=currency,
            at=when,
        )
        if row is None and provider_key != provider:
            row = self._find_db_pricing(
                provider=provider, model=model, currency=currency, at=when
            )
        if row is not None:
            return row
        if provider_key != "cursor" or currency.upper() != "USD":
            return None
        if at is not None:
            cutoff = datetime(2026, 9, 26, tzinfo=timezone.utc)
            moment = at if at.tzinfo is not None else at.replace(tzinfo=timezone.utc)
            if moment < cutoff:
                return None
        return published_cursor_entry(model, fast=fast)

    def _find_db_pricing(
        self,
        *,
        provider: str,
        model: str,
        currency: str,
        at: datetime,
    ) -> PricingCatalogEntry | None:
        q = (
            self._db.query(PricingCatalogEntry)
            .filter(
                PricingCatalogEntry.provider == provider,
                PricingCatalogEntry.model == model,
                PricingCatalogEntry.currency == currency,
                PricingCatalogEntry.enabled.is_(True),
                PricingCatalogEntry.effective_from <= at,
            )
            .order_by(PricingCatalogEntry.effective_from.desc())
        )
        for row in q.all():
            if row.effective_to is None or row.effective_to > at:
                return row
        return None

    def seed_cursor_pricing(self, *, created_by: str | None = None) -> dict[str, Any]:
        """Persist the published Cursor catalog. Skips unchanged and admin-owned rows."""
        actor = created_by or SEED_ACTOR
        created = 0
        skipped = 0
        preserved = 0
        now = _utcnow()
        for spec in cursor_catalog_document()["models"]:
            existing = self._find_db_pricing(
                provider="cursor",
                model=spec["id"],
                currency="USD",
                at=now,
            )
            if existing is not None and _cursor_row_matches(existing, spec):
                skipped += 1
                continue
            if existing is not None and existing.created_by != SEED_ACTOR:
                preserved += 1
                continue
            raw = lookup_cursor_model(spec["id"])
            if raw is None:
                continue
            self.upsert_pricing(
                provider="cursor",
                model=spec["id"],
                input_token_price=float(spec["input_token_price"]),
                output_token_price=float(spec["output_token_price"]),
                cached_input_token_price=spec["cached_input_token_price"],
                cache_write_token_price=spec["cache_write_token_price"],
                pricing_metadata=pricing_metadata_for(raw),
                source_url=spec.get("source_url") or SOURCE_URL,
                verified_at=datetime(2026, 9, 26, tzinfo=timezone.utc),
                pricing_unit=PRICING_UNIT,
                currency="USD",
                effective_from=now,
                created_by=SEED_ACTOR,
            )
            created += 1
        return {
            "version": CATALOG_VERSION,
            "source_url": SOURCE_URL,
            "created": created,
            "skipped": skipped,
            "preserved": preserved,
            "triggered_by": actor,
        }

    def list_pricing(
        self,
        *,
        provider: str | None = None,
        model: str | None = None,
        limit: int = 100,
    ) -> list[PricingCatalogEntry]:
        q = self._db.query(PricingCatalogEntry)
        if provider:
            q = q.filter(PricingCatalogEntry.provider == provider)
        if model:
            q = q.filter(PricingCatalogEntry.model == model)
        return q.order_by(PricingCatalogEntry.effective_from.desc()).limit(limit).all()

    def estimate_cost(
        self,
        *,
        provider: str,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        currency: str = "USD",
        cached_input_tokens: int = 0,
        reasoning_tokens: int = 0,
        cache_write_tokens: int = 0,
        at: datetime | None = None,
        tokens_are_estimated: bool = True,
        fast: bool = False,
        plan: str | None = None,
        apply_cursor_token_rate: bool | None = None,
        max_mode: bool = False,
        regional_residency: bool = False,
    ) -> dict[str, Any]:
        provider_key = normalize_provider(provider) or provider
        priced_model = model
        fast_requested = fast
        plan_key = normalize_cursor_plan(plan)
        if apply_cursor_token_rate is not None and not isinstance(
            apply_cursor_token_rate, bool
        ):
            apply_cursor_token_rate = str(apply_cursor_token_rate).lower() in {
                "1",
                "true",
                "yes",
            }
        if provider_key == "cursor" and plan_key == "start" and fast:
            # Start cannot enable Fast mode; bill the non-fast Cursor model rate.
            fast_requested = False
        if provider_key == "cursor":
            resolved = resolve_cursor_model_id(model, fast=fast_requested)
            if resolved:
                priced_model = resolved
            spec = lookup_cursor_model(priced_model)
            if (
                plan_key == "start"
                and spec is not None
                and spec.get("pool") == "other_models"
            ):
                return {
                    "estimated_cost": None,
                    "currency": currency,
                    "pricing_entry_id": None,
                    "cost_state": CostState.UNAVAILABLE.value,
                    "reason": "CURSOR_OTHER_MODELS_NOT_ON_START",
                    "model": priced_model,
                }
        pricing = self.get_active_pricing(
            provider=provider,
            model=priced_model,
            currency=currency,
            at=at,
            fast=False,
        )
        spec = lookup_cursor_model(priced_model) if provider_key == "cursor" else None
        apply_rate = cursor_token_rate_applies(
            spec, plan=plan, explicit=apply_cursor_token_rate
        )
        breakdown = PricingEngine().calculate(
            usage=UsageMeasurement(
                input_tokens=input_tokens or None,
                output_tokens=output_tokens or None,
                cached_input_tokens=cached_input_tokens or None,
                cache_write_tokens=cache_write_tokens or None,
                reasoning_tokens=reasoning_tokens or None,
                tokens_are_estimated=tokens_are_estimated,
            ),
            pricing=pricing,
            currency=currency,
            apply_cursor_token_rate=apply_rate,
            max_mode_multiplier=(
                LEGACY_MAX_MODE_MULTIPLIER
                if max_mode and provider_key == "cursor"
                else None
            ),
            regional_uplift=(
                REGIONAL_RESIDENCY_UPLIFT
                if regional_residency and provider_key == "cursor"
                else None
            ),
        )
        if breakdown.reason == "NO_PRICING":
            return {
                "estimated_cost": None,
                "currency": currency,
                "pricing_entry_id": None,
                "cost_state": CostState.UNAVAILABLE.value,
                "reason": "NO_PRICING",
            }
        return {
            "estimated_cost": breakdown.total_cost,
            "currency": breakdown.currency,
            "pricing_entry_id": breakdown.pricing_entry_id,
            "input_token_price": pricing.input_token_price if pricing else None,
            "output_token_price": pricing.output_token_price if pricing else None,
            "cost_state": breakdown.state,
            "breakdown": breakdown.to_dict(),
            "reason": "OK" if breakdown.total_cost is not None else breakdown.reason,
            "model": pricing.model if pricing else priced_model,
            "cursor_token_rate_applied": apply_rate,
        }

    def estimate_from_parameters(
        self, parameters: dict[str, Any] | None
    ) -> dict[str, Any]:
        """Derive estimate from authorize parameters (model/provider/token hints)."""
        params = dict(parameters or {})
        provider = str(
            params.get("provider")
            or params.get("model_provider")
            or params.get("llm_provider")
            or ""
        ).strip()
        model = str(
            params.get("model")
            or params.get("model_name")
            or params.get("llm_model")
            or ""
        ).strip()
        currency = str(params.get("currency") or "USD")
        input_tokens = (
            _as_int(params.get("estimated_input_tokens"))
            or _as_int(params.get("input_tokens"))
            or 0
        )
        output_tokens = (
            _as_int(params.get("estimated_output_tokens"))
            or _as_int(params.get("output_tokens"))
            or 0
        )
        # Explicit cost wins as estimate source ESTIMATED
        explicit_cost = _as_float(params.get("cost") or params.get("estimated_cost"))
        if explicit_cost is not None:
            return {
                "estimated_cost": explicit_cost,
                "currency": currency,
                "pricing_entry_id": None,
                "provider": provider or None,
                "model": model or None,
                "estimated_input_tokens": input_tokens or None,
                "estimated_output_tokens": output_tokens or None,
                "reason": "EXPLICIT_COST",
            }
        if not provider or not model:
            return {
                "estimated_cost": None,
                "currency": currency,
                "pricing_entry_id": None,
                "provider": provider or None,
                "model": model or None,
                "estimated_input_tokens": input_tokens or None,
                "estimated_output_tokens": output_tokens or None,
                "reason": "MISSING_MODEL",
            }
        result = self.estimate_cost(
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            currency=currency,
            cached_input_tokens=_as_int(params.get("cached_input_tokens")) or 0,
            cache_write_tokens=_as_int(params.get("cache_write_tokens")) or 0,
            reasoning_tokens=_as_int(params.get("reasoning_tokens")) or 0,
            fast=bool(params.get("fast")),
            plan=params.get("plan") or params.get("cursor_plan"),
            apply_cursor_token_rate=params.get("apply_cursor_token_rate"),
            max_mode=bool(params.get("max_mode")),
            regional_residency=bool(params.get("regional_residency")),
        )
        result["provider"] = provider
        result["model"] = model
        result["estimated_input_tokens"] = input_tokens or None
        result["estimated_output_tokens"] = output_tokens or None
        return result

    # --- Reservation / settlement -----------------------------------------

    def reserve(
        self,
        *,
        estimated_cost: float,
        currency: str = "USD",
        ai_system_id: UUID | None = None,
        agent_id: UUID | None = None,
        agent_version_id: UUID | None = None,
        runtime_identity_id: UUID | None = None,
        delegation_id: UUID | None = None,
        runtime_conversation_id: UUID | None = None,
        trajectory_id: UUID | None = None,
        correlation_id: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        estimated_input_tokens: int | None = None,
        estimated_output_tokens: int | None = None,
        pricing_entry_id: UUID | None = None,
        allocation: dict[str, Any] | None = None,
    ) -> UsageReservation:
        row = UsageReservation(
            ai_system_id=ai_system_id,
            agent_id=agent_id,
            agent_version_id=agent_version_id,
            runtime_identity_id=runtime_identity_id,
            delegation_id=delegation_id,
            runtime_conversation_id=runtime_conversation_id,
            trajectory_id=trajectory_id,
            correlation_id=correlation_id,
            provider=provider,
            model=model,
            estimated_input_tokens=estimated_input_tokens,
            estimated_output_tokens=estimated_output_tokens,
            estimated_cost=float(estimated_cost),
            currency=currency,
            pricing_entry_id=pricing_entry_id,
            status=ReservationStatus.RESERVED.value,
            allocation=allocation,
        )
        self._db.add(row)
        self._db.flush()
        return row

    def attach_receipt(
        self, reservation_id: UUID, enforcement_receipt_id: UUID
    ) -> None:
        row = (
            self._db.query(UsageReservation)
            .filter(UsageReservation.id == reservation_id)
            .first()
        )
        if row:
            row.enforcement_receipt_id = enforcement_receipt_id
            self._db.flush()

    def release(
        self, reservation_id: UUID, *, reason: str | None = None
    ) -> UsageReservation:
        row = (
            self._db.query(UsageReservation)
            .filter(UsageReservation.id == reservation_id)
            .first()
        )
        if not row:
            raise LookupError("Reservation not found")
        if row.status == ReservationStatus.SETTLED.value:
            return row
        row.status = ReservationStatus.RELEASED.value
        if reason:
            allocation = dict(row.allocation or {})
            allocation["release_reason"] = reason
            row.allocation = allocation
        self._db.flush()
        return row

    def settle(
        self,
        *,
        usage: dict[str, Any] | None = None,
        cost: dict[str, Any] | None = None,
        reservation_id: UUID | None = None,
        enforcement_receipt_id: UUID | None = None,
        correlation_id: str | None = None,
        allocation: dict[str, Any] | None = None,
        ai_system_id: UUID | None = None,
        agent_id: UUID | None = None,
        agent_version_id: UUID | None = None,
        runtime_identity_id: UUID | None = None,
        delegation_id: UUID | None = None,
        runtime_conversation_id: UUID | None = None,
        trajectory_id: UUID | None = None,
    ) -> UsageSettlement:
        payload, source = pick_trusted_usage(usage, cost)
        input_tokens = (
            _as_int(payload.get("input_tokens"))
            or _as_int(payload.get("prompt_tokens"))
            or 0
        )
        output_tokens = (
            _as_int(payload.get("output_tokens"))
            or _as_int(payload.get("completion_tokens"))
            or 0
        )
        total_tokens = (
            _as_int(payload.get("total_tokens"))
            or (input_tokens + output_tokens)
            or None
        )

        reservation = None
        if reservation_id:
            reservation = (
                self._db.query(UsageReservation)
                .filter(UsageReservation.id == reservation_id)
                .first()
            )
        elif enforcement_receipt_id:
            reservation = (
                self._db.query(UsageReservation)
                .filter(
                    UsageReservation.enforcement_receipt_id == enforcement_receipt_id,
                    UsageReservation.status == ReservationStatus.RESERVED.value,
                )
                .order_by(UsageReservation.created_at.desc())
                .first()
            )
        elif correlation_id:
            reservation = (
                self._db.query(UsageReservation)
                .filter(
                    UsageReservation.correlation_id == correlation_id,
                    UsageReservation.status == ReservationStatus.RESERVED.value,
                )
                .order_by(UsageReservation.created_at.desc())
                .first()
            )

        provider = (
            payload.get("provider")
            if isinstance(payload.get("provider"), str)
            else None
        ) or (reservation.provider if reservation else None)
        model = (
            payload.get("model") if isinstance(payload.get("model"), str) else None
        ) or (reservation.model if reservation else None)
        currency = str(
            payload.get("currency")
            or (reservation.currency if reservation else "USD")
            or "USD"
        )

        explicit_amount = _as_float(payload.get("cost") or payload.get("amount"))
        cached_input = _as_int(payload.get("cached_input_tokens")) or _as_int(
            payload.get("cached_tokens")
        )
        reasoning = _as_int(payload.get("reasoning_tokens"))
        pricing = None
        if provider and model:
            pricing = self.get_active_pricing(
                provider=provider, model=model, currency=currency
            )
        breakdown = PricingEngine().calculate(
            usage=UsageMeasurement(
                input_tokens=input_tokens or None,
                output_tokens=output_tokens or None,
                cached_input_tokens=cached_input,
                reasoning_tokens=reasoning,
                cache_write_tokens=_as_int(payload.get("cache_write_tokens")),
                tokens_are_estimated=False,
            ),
            pricing=pricing,
            explicit_amount=explicit_amount,
            metering_source=source,
            currency=currency,
        )
        cost_state = breakdown.state
        estimated_cost = (
            breakdown.total_cost if cost_state == CostState.ESTIMATED.value else None
        )
        metered_cost = (
            breakdown.total_cost if cost_state == CostState.METERED.value else None
        )
        billed_cost = (
            breakdown.total_cost if cost_state == CostState.BILLED.value else None
        )
        amount = settled_amount(
            billed_cost=billed_cost,
            metered_cost=metered_cost,
            estimated_cost=estimated_cost,
        )
        # Do not fabricate $0 for unavailable cost; leave actual_cost None.
        pricing_id = pricing_entry_id(breakdown)
        if pricing_id is None and reservation and reservation.pricing_entry_id:
            pricing_id = reservation.pricing_entry_id

        reserved_cost = reservation.estimated_cost if reservation else None
        delta = (
            float(amount) - float(reserved_cost)
            if amount is not None and reserved_cost is not None
            else None
        )

        def _owned(name: str, explicit: Any) -> Any:
            if explicit is not None:
                return explicit
            return getattr(reservation, name, None) if reservation else None

        settlement = UsageSettlement(
            ai_system_id=_owned("ai_system_id", ai_system_id),
            agent_id=_owned("agent_id", agent_id),
            agent_version_id=_owned("agent_version_id", agent_version_id),
            runtime_identity_id=_owned("runtime_identity_id", runtime_identity_id),
            delegation_id=_owned("delegation_id", delegation_id),
            runtime_conversation_id=_owned(
                "runtime_conversation_id", runtime_conversation_id
            ),
            trajectory_id=_owned("trajectory_id", trajectory_id),
            reservation_id=reservation.id if reservation else None,
            enforcement_receipt_id=enforcement_receipt_id
            or (reservation.enforcement_receipt_id if reservation else None),
            correlation_id=correlation_id
            or (reservation.correlation_id if reservation else None),
            provider=provider,
            model=model,
            input_tokens=input_tokens or None,
            output_tokens=output_tokens or None,
            total_tokens=total_tokens,
            actual_cost=float(amount) if amount is not None else None,
            estimated_cost=estimated_cost,
            metered_cost=metered_cost,
            billed_cost=billed_cost,
            currency=currency,
            cost_state=cost_state,
            metering_source=breakdown.metering_source or source,
            pricing_entry_id=pricing_id,
            pricing_snapshot=breakdown.pricing_snapshot or None,
            reserved_cost=reserved_cost,
            delta_cost=delta,
            allocation=allocation or (reservation.allocation if reservation else None),
            raw_usage={"usage": usage, "cost": cost, "selected": payload},
        )
        self._db.add(settlement)
        if reservation:
            if cost_state == CostState.UNAVAILABLE.value and amount is None:
                # Close reservation without inventing a monetary settlement amount.
                reservation.status = ReservationStatus.SETTLED.value
            else:
                reservation.status = ReservationStatus.SETTLED.value
            if enforcement_receipt_id and not reservation.enforcement_receipt_id:
                reservation.enforcement_receipt_id = enforcement_receipt_id
        self._db.flush()
        return settlement

    def serialize_pricing(self, row: PricingCatalogEntry) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "provider": row.provider,
            "model": row.model,
            "input_token_price": row.input_token_price,
            "output_token_price": row.output_token_price,
            "cached_input_token_price": row.cached_input_token_price,
            "reasoning_token_price": row.reasoning_token_price,
            "minimum_request_cost": row.minimum_request_cost,
            "cache_write_token_price": row.cache_write_token_price,
            "image_input_price": row.image_input_price,
            "image_output_price": row.image_output_price,
            "audio_input_price": row.audio_input_price,
            "audio_output_price": row.audio_output_price,
            "request_price": row.request_price,
            "provider_tool_price": row.provider_tool_price,
            "pricing_metadata": row.pricing_metadata,
            "source_url": row.source_url,
            "verified_at": row.verified_at.isoformat() if row.verified_at else None,
            "region": row.region,
            "service_tier": row.service_tier,
            "pricing_unit": row.pricing_unit or 1000,
            "currency": row.currency,
            "effective_from": row.effective_from.isoformat()
            if row.effective_from
            else None,
            "effective_to": row.effective_to.isoformat() if row.effective_to else None,
            "enabled": row.enabled,
            "created_by": row.created_by,
        }

    def serialize_reservation(self, row: UsageReservation) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "status": row.status,
            "estimated_cost": row.estimated_cost,
            "currency": row.currency,
            "provider": row.provider,
            "model": row.model,
            "estimated_input_tokens": row.estimated_input_tokens,
            "estimated_output_tokens": row.estimated_output_tokens,
            "correlation_id": row.correlation_id,
            "enforcement_receipt_id": str(row.enforcement_receipt_id)
            if row.enforcement_receipt_id
            else None,
            "allocation": row.allocation,
        }

    def serialize_settlement(self, row: UsageSettlement) -> dict[str, Any]:
        amount = settled_amount(
            billed_cost=row.billed_cost,
            metered_cost=row.metered_cost,
            estimated_cost=row.estimated_cost,
            actual_cost=row.actual_cost,
        )
        return {
            "id": str(row.id),
            "reservation_id": str(row.reservation_id) if row.reservation_id else None,
            "metering_source": row.metering_source,
            "actual_cost": row.actual_cost,
            "estimated_cost": row.estimated_cost,
            "metered_cost": row.metered_cost,
            "billed_cost": row.billed_cost,
            "settled_amount": amount,
            "cost_state": row.cost_state,
            "reserved_cost": row.reserved_cost,
            "delta_cost": row.delta_cost,
            "currency": row.currency,
            "input_tokens": row.input_tokens,
            "output_tokens": row.output_tokens,
            "total_tokens": row.total_tokens,
            "provider": row.provider,
            "model": row.model,
            "pricing_snapshot": row.pricing_snapshot,
            "enforcement_receipt_id": str(row.enforcement_receipt_id)
            if row.enforcement_receipt_id
            else None,
        }
