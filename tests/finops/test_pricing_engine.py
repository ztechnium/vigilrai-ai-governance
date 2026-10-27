"""PricingEngine cost-state and catalog pricing tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from rai_gateway.finops.domain import CostState, MeteringSource, normalize_cost_state
from rai_gateway.finops.pricing import (
    PricingEngine,
    PricingValidationError,
    UsageMeasurement,
)
from rai_gateway.finops.service import FinOpsService
from rai_gateway.models.finops import PricingCatalogEntry


def _entry(**overrides) -> PricingCatalogEntry:
    now = datetime.now(timezone.utc)
    defaults = dict(
        provider="openai",
        model="gpt-test",
        input_token_price=1.0,
        output_token_price=2.0,
        cached_input_token_price=0.1,
        reasoning_token_price=3.0,
        minimum_request_cost=None,
        pricing_unit=1000,
        currency="USD",
        effective_from=now,
        enabled=True,
        created_by="tester",
    )
    defaults.update(overrides)
    return PricingCatalogEntry(**defaults)


def test_actual_usage_plus_catalog_is_metered():
    breakdown = PricingEngine().calculate(
        usage=UsageMeasurement(input_tokens=1000, output_tokens=500),
        pricing=_entry(),
        metering_source=MeteringSource.PROVIDER_RESPONSE.value,
    )
    assert breakdown.state == CostState.METERED.value
    assert abs((breakdown.total_cost or 0) - 2.0) < 1e-9  # 1 + 1
    assert breakdown.metering_source == MeteringSource.PRICING_CATALOG_DERIVED.value
    assert breakdown.pricing_snapshot["input_token_price"] == 1.0


def test_estimated_usage_plus_catalog_is_estimated():
    breakdown = PricingEngine().calculate(
        usage=UsageMeasurement(
            input_tokens=1000, output_tokens=0, tokens_are_estimated=True
        ),
        pricing=_entry(),
    )
    assert breakdown.state == CostState.ESTIMATED.value
    assert breakdown.total_cost == 1.0


def test_provider_authoritative_amount_is_billed():
    breakdown = PricingEngine().calculate(
        usage=UsageMeasurement(input_tokens=10),
        explicit_amount=0.42,
        metering_source=MeteringSource.PROVIDER_RESPONSE.value,
        currency="USD",
    )
    assert breakdown.state == CostState.BILLED.value
    assert breakdown.total_cost == 0.42


def test_missing_pricing_is_unavailable():
    breakdown = PricingEngine().calculate(
        usage=UsageMeasurement(input_tokens=10, output_tokens=10),
        pricing=None,
    )
    assert breakdown.state == CostState.UNAVAILABLE.value
    assert breakdown.total_cost is None


def test_cached_and_reasoning_priced_separately():
    breakdown = PricingEngine().calculate(
        usage=UsageMeasurement(
            input_tokens=0,
            output_tokens=0,
            cached_input_tokens=1000,
            reasoning_tokens=1000,
        ),
        pricing=_entry(),
    )
    assert abs((breakdown.cached_input_cost or 0) - 0.1) < 1e-9
    assert abs((breakdown.reasoning_cost or 0) - 3.0) < 1e-9
    assert abs((breakdown.total_cost or 0) - 3.1) < 1e-9


def test_minimum_request_cost():
    breakdown = PricingEngine().calculate(
        usage=UsageMeasurement(input_tokens=1, output_tokens=0),
        pricing=_entry(minimum_request_cost=0.05, input_token_price=0.001),
    )
    assert breakdown.total_cost == 0.05


def test_negative_usage_rejected():
    with pytest.raises(PricingValidationError):
        PricingEngine().calculate(
            usage=UsageMeasurement(input_tokens=-1),
            pricing=_entry(),
        )


def test_currency_mismatch_unavailable():
    breakdown = PricingEngine().calculate(
        usage=UsageMeasurement(input_tokens=10),
        pricing=_entry(currency="USD"),
        currency="EUR",
    )
    assert breakdown.state == CostState.UNAVAILABLE.value
    assert breakdown.reason == "CURRENCY_MISMATCH"


def test_normalize_legacy_actual(db_session):
    assert (
        normalize_cost_state(
            "ACTUAL", metering_source=MeteringSource.PROVIDER_RESPONSE.value
        )
        == CostState.BILLED.value
    )
    assert (
        normalize_cost_state(
            "ACTUAL", metering_source=MeteringSource.PRICING_CATALOG_DERIVED.value
        )
        == CostState.METERED.value
    )


def test_pricing_version_selected_by_execution_timestamp(db_session):
    svc = FinOpsService(db_session)
    old = datetime.now(timezone.utc) - timedelta(days=10)
    first = svc.upsert_pricing(
        provider="openai",
        model="gpt-hist-v2",
        input_token_price=1.0,
        output_token_price=2.0,
        created_by="tester",
        effective_from=old - timedelta(days=1),
        effective_to=old + timedelta(days=1),
    )
    svc.upsert_pricing(
        provider="openai",
        model="gpt-hist-v2",
        input_token_price=9.0,
        output_token_price=9.0,
        created_by="tester",
        effective_from=old + timedelta(days=2),
    )
    active = svc.get_active_pricing(
        provider="openai", model="gpt-hist-v2", currency="USD", at=old
    )
    assert active is not None
    assert active.id == first.id
    breakdown = PricingEngine().calculate(
        usage=UsageMeasurement(input_tokens=1000, output_tokens=0),
        pricing=active,
    )
    assert breakdown.state == CostState.METERED.value
    assert breakdown.total_cost == 1.0
    assert breakdown.pricing_snapshot["input_token_price"] == 1.0
