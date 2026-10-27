"""Legacy ACTUAL cost-state normalization helpers."""

from __future__ import annotations

from rai_gateway.finops.domain import (
    CostState,
    normalize_cost_state,
    settled_amount,
)


def test_legacy_actual_maps_by_source():
    assert (
        normalize_cost_state("ACTUAL", metering_source="PROVIDER_RESPONSE")
        == CostState.BILLED.value
    )
    assert (
        normalize_cost_state("ACTUAL", metering_source="PRICING_CATALOG_DERIVED")
        == CostState.METERED.value
    )
    assert normalize_cost_state("METERED") == CostState.METERED.value


def test_settled_amount_precedence():
    assert settled_amount(billed_cost=3.0, metered_cost=2.0, estimated_cost=1.0) == 3.0
    assert settled_amount(metered_cost=2.0, estimated_cost=1.0) == 2.0
    assert settled_amount(estimated_cost=1.0, actual_cost=9.0) == 1.0
    assert settled_amount(actual_cost=9.0) == 9.0
    assert settled_amount() is None
