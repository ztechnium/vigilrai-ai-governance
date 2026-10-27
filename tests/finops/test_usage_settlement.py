"""Usage settlement METERED/BILLED rules."""

from __future__ import annotations

from rai_gateway.finops.domain import CostState, MeteringSource
from rai_gateway.finops.service import FinOpsService


def test_settlement_from_catalog_is_metered(db_session):
    svc = FinOpsService(db_session)
    svc.upsert_pricing(
        provider="openai",
        model="gpt-settle",
        input_token_price=1.0,
        output_token_price=2.0,
        created_by="tester",
    )
    settlement = svc.settle(
        usage={
            "source": "PROVIDER_RESPONSE",
            "provider": "openai",
            "model": "gpt-settle",
            "input_tokens": 1000,
            "output_tokens": 1000,
        }
    )
    db_session.commit()
    assert settlement.cost_state == CostState.METERED.value
    assert settlement.metering_source == MeteringSource.PRICING_CATALOG_DERIVED.value
    assert abs((settlement.metered_cost or 0) - 3.0) < 1e-9
    assert settlement.pricing_snapshot is not None


def test_settlement_with_provider_amount_is_billed(db_session):
    svc = FinOpsService(db_session)
    settlement = svc.settle(
        usage={
            "source": "PROVIDER_RESPONSE",
            "provider": "openai",
            "model": "gpt-settle",
            "input_tokens": 10,
            "cost": 0.77,
        }
    )
    db_session.commit()
    assert settlement.cost_state == CostState.BILLED.value
    assert settlement.billed_cost == 0.77
    assert settlement.actual_cost == 0.77
