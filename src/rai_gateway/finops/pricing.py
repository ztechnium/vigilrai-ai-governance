"""Centralized pricing calculator — ESTIMATED / METERED / BILLED cost stages."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from rai_gateway.finops.domain import (
    CostState,
    MeteringSource,
    is_billed_cost_source,
)
from rai_gateway.models.finops import PricingCatalogEntry


class PricingValidationError(ValueError):
    """Negative usage/cost or other invalid pricing input."""


@dataclass
class PricingContext:
    provider: str | None = None
    model: str | None = None
    currency: str = "USD"
    at: datetime | None = None
    region: str | None = None
    service_tier: str | None = None


@dataclass
class UsageMeasurement:
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_input_tokens: int | None = None
    cache_write_tokens: int | None = None
    reasoning_tokens: int | None = None
    image_inputs: int | None = None
    image_outputs: int | None = None
    audio_input_seconds: float | None = None
    audio_output_seconds: float | None = None
    request_count: int | None = None
    provider_tool_calls: int | None = None
    tokens_are_estimated: bool = False

    def validate(self) -> None:
        for name in (
            "input_tokens",
            "output_tokens",
            "cached_input_tokens",
            "cache_write_tokens",
            "reasoning_tokens",
            "image_inputs",
            "image_outputs",
            "request_count",
            "provider_tool_calls",
        ):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise PricingValidationError(f"{name} cannot be negative")
        for name in ("audio_input_seconds", "audio_output_seconds"):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise PricingValidationError(f"{name} cannot be negative")

    def has_billable_usage(self) -> bool:
        return any(
            getattr(self, name)
            for name in (
                "input_tokens",
                "output_tokens",
                "cached_input_tokens",
                "cache_write_tokens",
                "reasoning_tokens",
                "image_inputs",
                "image_outputs",
                "audio_input_seconds",
                "audio_output_seconds",
                "request_count",
                "provider_tool_calls",
            )
        )


@dataclass
class CostBreakdown:
    state: str
    currency: str
    input_cost: float = 0.0
    output_cost: float = 0.0
    cached_input_cost: float = 0.0
    cache_write_cost: float = 0.0
    reasoning_cost: float = 0.0
    image_cost: float = 0.0
    audio_cost: float = 0.0
    request_cost: float = 0.0
    provider_tool_cost: float = 0.0
    surcharge_cost: float = 0.0
    total_cost: float | None = None
    pricing_entry_id: str | None = None
    metering_source: str = MeteringSource.UNKNOWN.value
    pricing_snapshot: dict[str, Any] = field(default_factory=dict)
    reason: str = "OK"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def snapshot_pricing(entry: PricingCatalogEntry) -> dict[str, Any]:
    return {
        "pricing_entry_id": str(entry.id),
        "pricing_unit": entry.pricing_unit or 1000,
        "input_token_price": entry.input_token_price,
        "output_token_price": entry.output_token_price,
        "cached_input_token_price": entry.cached_input_token_price,
        "cache_write_token_price": entry.cache_write_token_price,
        "reasoning_token_price": entry.reasoning_token_price,
        "minimum_request_cost": entry.minimum_request_cost,
        "image_input_price": entry.image_input_price,
        "image_output_price": entry.image_output_price,
        "audio_input_price": entry.audio_input_price,
        "audio_output_price": entry.audio_output_price,
        "request_price": entry.request_price,
        "provider_tool_price": entry.provider_tool_price,
        "service_tier": entry.service_tier,
        "region": entry.region,
        "currency": entry.currency,
        "pricing_metadata": entry.pricing_metadata,
    }


class PricingEngine:
    """Compute cost from usage + catalog or authoritative monetary amounts."""

    def calculate(
        self,
        *,
        usage: UsageMeasurement,
        pricing: PricingCatalogEntry | None = None,
        explicit_amount: float | None = None,
        metering_source: str | None = None,
        currency: str = "USD",
        apply_cursor_token_rate: bool = False,
        max_mode_multiplier: float | None = None,
        regional_uplift: float | None = None,
    ) -> CostBreakdown:
        usage.validate()
        source = str(metering_source or MeteringSource.UNKNOWN.value).upper()

        if explicit_amount is not None:
            if explicit_amount < 0:
                raise PricingValidationError("explicit cost cannot be negative")
            if is_billed_cost_source(source):
                return CostBreakdown(
                    state=CostState.BILLED.value,
                    currency=currency,
                    total_cost=round(explicit_amount, 8),
                    metering_source=source,
                    reason="BILLED_EXPLICIT",
                )
            return CostBreakdown(
                state=CostState.ESTIMATED.value,
                currency=currency,
                total_cost=round(explicit_amount, 8),
                metering_source=(
                    MeteringSource.EXPLICIT_COST.value
                    if source
                    in {
                        MeteringSource.UNKNOWN.value,
                        MeteringSource.ESTIMATED.value,
                    }
                    else source
                ),
                reason="ESTIMATED_EXPLICIT",
            )

        if pricing is None:
            return CostBreakdown(
                state=CostState.UNAVAILABLE.value,
                currency=currency,
                total_cost=None,
                metering_source=MeteringSource.UNKNOWN.value,
                reason="NO_PRICING",
            )

        if pricing.currency and currency and pricing.currency != currency:
            return CostBreakdown(
                state=CostState.UNAVAILABLE.value,
                currency=currency,
                total_cost=None,
                metering_source=MeteringSource.UNKNOWN.value,
                reason="CURRENCY_MISMATCH",
            )

        if not usage.has_billable_usage():
            return CostBreakdown(
                state=CostState.UNAVAILABLE.value,
                currency=pricing.currency,
                total_cost=None,
                pricing_entry_id=str(pricing.id),
                metering_source=MeteringSource.UNKNOWN.value,
                pricing_snapshot=snapshot_pricing(pricing),
                reason="NO_USAGE",
            )

        unit = float(pricing.pricing_unit or 1000)
        input_cost = ((usage.input_tokens or 0) / unit) * float(
            pricing.input_token_price
        )
        output_cost = ((usage.output_tokens or 0) / unit) * float(
            pricing.output_token_price
        )
        cached_input_cost = 0.0
        if pricing.cached_input_token_price is not None:
            cached_input_cost = ((usage.cached_input_tokens or 0) / unit) * float(
                pricing.cached_input_token_price
            )
        cache_write_cost = 0.0
        if pricing.cache_write_token_price is not None:
            cache_write_cost = ((usage.cache_write_tokens or 0) / unit) * float(
                pricing.cache_write_token_price
            )
        reasoning_cost = 0.0
        if pricing.reasoning_token_price is not None:
            reasoning_cost = ((usage.reasoning_tokens or 0) / unit) * float(
                pricing.reasoning_token_price
            )
        image_cost = 0.0
        if pricing.image_input_price is not None:
            image_cost += (usage.image_inputs or 0) * float(pricing.image_input_price)
        if pricing.image_output_price is not None:
            image_cost += (usage.image_outputs or 0) * float(pricing.image_output_price)
        audio_cost = 0.0
        if pricing.audio_input_price is not None:
            audio_cost += (usage.audio_input_seconds or 0) * float(
                pricing.audio_input_price
            )
        if pricing.audio_output_price is not None:
            audio_cost += (usage.audio_output_seconds or 0) * float(
                pricing.audio_output_price
            )
        request_cost = 0.0
        if pricing.request_price is not None:
            request_cost = (usage.request_count or 0) * float(pricing.request_price)
        provider_tool_cost = 0.0
        if pricing.provider_tool_price is not None:
            provider_tool_cost = (usage.provider_tool_calls or 0) * float(
                pricing.provider_tool_price
            )

        (
            input_cost,
            output_cost,
            cached_input_cost,
            cache_write_cost,
            reasoning_cost,
        ) = self._apply_input_context_tiers(
            usage,
            pricing,
            input_cost,
            output_cost,
            cached_input_cost,
            cache_write_cost,
            reasoning_cost,
        )

        total = (
            input_cost
            + output_cost
            + cached_input_cost
            + cache_write_cost
            + reasoning_cost
            + image_cost
            + audio_cost
            + request_cost
            + provider_tool_cost
        )
        if (
            pricing.minimum_request_cost is not None
            and total < pricing.minimum_request_cost
            and usage.has_billable_usage()
        ):
            total = float(pricing.minimum_request_cost)

        # Apply optional metadata multipliers (batch / priority / blended context tiers).
        total = self._apply_metadata_multipliers(total, usage, pricing)
        if max_mode_multiplier is not None and max_mode_multiplier > 0:
            total *= float(max_mode_multiplier)
        if regional_uplift is not None and regional_uplift > 0:
            total *= 1.0 + float(regional_uplift)
        surcharge_cost = self._cursor_token_rate_surcharge(
            usage, pricing, enabled=apply_cursor_token_rate
        )
        total += surcharge_cost

        if usage.tokens_are_estimated:
            state = CostState.ESTIMATED.value
            metering = MeteringSource.ESTIMATED.value
            reason = "ESTIMATED_USAGE"
        else:
            state = CostState.METERED.value
            metering = MeteringSource.PRICING_CATALOG_DERIVED.value
            reason = "METERED_CATALOG"

        return CostBreakdown(
            state=state,
            currency=pricing.currency,
            input_cost=round(input_cost, 8),
            output_cost=round(output_cost, 8),
            cached_input_cost=round(cached_input_cost, 8),
            cache_write_cost=round(cache_write_cost, 8),
            reasoning_cost=round(reasoning_cost, 8),
            image_cost=round(image_cost, 8),
            audio_cost=round(audio_cost, 8),
            request_cost=round(request_cost, 8),
            provider_tool_cost=round(provider_tool_cost, 8),
            surcharge_cost=round(surcharge_cost, 8),
            total_cost=round(total, 8),
            pricing_entry_id=str(pricing.id),
            metering_source=metering,
            pricing_snapshot=snapshot_pricing(pricing),
            reason=reason,
        )

    def _apply_input_context_tiers(
        self,
        usage: UsageMeasurement,
        pricing: PricingCatalogEntry,
        input_cost: float,
        output_cost: float,
        cached_input_cost: float,
        cache_write_cost: float,
        reasoning_cost: float,
    ) -> tuple[float, float, float, float, float]:
        """Scale token components when input length crosses a published tier.

        Cursor bills some long-context windows from input length alone, with
        separate input, output, and cache multipliers. Those tiers are not a
        blended multiplier on the whole request.
        """
        meta = (
            pricing.pricing_metadata
            if isinstance(pricing.pricing_metadata, dict)
            else {}
        )
        tiers = meta.get("context_tiers")
        if not isinstance(tiers, list):
            return (
                input_cost,
                output_cost,
                cached_input_cost,
                cache_write_cost,
                reasoning_cost,
            )
        input_tokens = usage.input_tokens or 0
        for tier in tiers:
            if not isinstance(tier, dict) or tier.get("above_input_tokens") is None:
                continue
            try:
                if input_tokens <= int(tier["above_input_tokens"]):
                    continue
                input_multiplier = float(tier.get("input_multiplier") or 1.0)
                output_multiplier = float(tier.get("output_multiplier") or 1.0)
                cache_multiplier = float(
                    tier.get("cache_multiplier") or input_multiplier
                )
            except (TypeError, ValueError):
                continue
            return (
                input_cost * input_multiplier,
                output_cost * output_multiplier,
                cached_input_cost * cache_multiplier,
                cache_write_cost * cache_multiplier,
                reasoning_cost * output_multiplier,
            )
        return (
            input_cost,
            output_cost,
            cached_input_cost,
            cache_write_cost,
            reasoning_cost,
        )

    def _cursor_token_rate_surcharge(
        self,
        usage: UsageMeasurement,
        pricing: PricingCatalogEntry,
        *,
        enabled: bool,
    ) -> float:
        if not enabled:
            return 0.0
        meta = (
            pricing.pricing_metadata
            if isinstance(pricing.pricing_metadata, dict)
            else {}
        )
        if meta.get("cursor_token_rate_exempt"):
            return 0.0
        rate = meta.get("cursor_token_rate_per_million")
        if rate is None:
            return 0.0
        try:
            per_million = float(rate)
        except (TypeError, ValueError):
            return 0.0
        if per_million <= 0:
            return 0.0
        tokens = (
            (usage.input_tokens or 0)
            + (usage.output_tokens or 0)
            + (usage.cached_input_tokens or 0)
            + (usage.cache_write_tokens or 0)
            + (usage.reasoning_tokens or 0)
        )
        return tokens / 1_000_000 * per_million

    def _apply_metadata_multipliers(
        self,
        total: float,
        usage: UsageMeasurement,
        pricing: PricingCatalogEntry,
    ) -> float:
        meta = (
            pricing.pricing_metadata
            if isinstance(pricing.pricing_metadata, dict)
            else {}
        )
        if not meta:
            return total
        batch = meta.get("batch_multiplier")
        if batch is not None:
            try:
                total *= float(batch)
            except (TypeError, ValueError):
                pass
        priority = meta.get("priority_multiplier")
        if priority is not None:
            try:
                total *= float(priority)
            except (TypeError, ValueError):
                pass
        tiers = meta.get("context_tiers")
        if isinstance(tiers, list) and tiers:
            token_total = (usage.input_tokens or 0) + (usage.output_tokens or 0)
            for tier in tiers:
                if not isinstance(tier, dict):
                    continue
                if (
                    tier.get("above_input_tokens") is not None
                    and tier.get("above_tokens") is None
                    and tier.get("up_to_tokens") is None
                ):
                    continue
                above = tier.get("above_tokens")
                up_to = tier.get("up_to_tokens")
                applies = False
                if above is not None and token_total > int(above):
                    applies = True
                if up_to is not None and token_total <= int(up_to):
                    applies = True
                if not applies:
                    continue
                try:
                    # Prefer distinct input/output multipliers when present.
                    inp_m = float(tier.get("input_multiplier") or 1.0)
                    out_m = float(tier.get("output_multiplier") or 1.0)
                    # Approximate blended multiplier for the aggregate total.
                    if (usage.input_tokens or 0) + (usage.output_tokens or 0) > 0:
                        weight_in = (usage.input_tokens or 0) / max(token_total, 1)
                        weight_out = (usage.output_tokens or 0) / max(token_total, 1)
                        total *= weight_in * inp_m + weight_out * out_m
                    break
                except (TypeError, ValueError):
                    continue
        return total


def pricing_entry_id(breakdown: CostBreakdown) -> UUID | None:
    if not breakdown.pricing_entry_id:
        return None
    return UUID(breakdown.pricing_entry_id)
