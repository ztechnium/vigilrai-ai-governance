"""FinOps pricing, reservation, settlement, trusted metering tests."""

from __future__ import annotations

from rai_gateway.finops.domain import MeteringSource, ReservationStatus
from rai_gateway.finops.service import FinOpsService, pick_trusted_usage


def test_pick_trusted_usage_prefers_provider():
    usage = {
        "agent_supplied": {"input_tokens": 1, "output_tokens": 1},
        "provider_response": {"input_tokens": 100, "output_tokens": 50},
    }
    payload, source = pick_trusted_usage(usage)
    assert source == MeteringSource.PROVIDER_RESPONSE.value
    assert payload["input_tokens"] == 100


def test_pricing_estimate_and_reserve_settle(db_session):
    svc = FinOpsService(db_session)
    pricing = svc.upsert_pricing(
        provider="openai",
        model="gpt-4o-mini",
        input_token_price=0.15,  # per 1K
        output_token_price=0.60,
        created_by="tester",
        currency="USD",
    )
    assert pricing.provider == "openai"

    estimate = svc.estimate_cost(
        provider="openai",
        model="gpt-4o-mini",
        input_tokens=1000,
        output_tokens=500,
    )
    assert estimate["reason"] == "OK"
    # 1*0.15 + 0.5*0.60 = 0.45
    assert abs(estimate["estimated_cost"] - 0.45) < 1e-9

    reservation = svc.reserve(
        estimated_cost=estimate["estimated_cost"],
        currency="USD",
        provider="openai",
        model="gpt-4o-mini",
        estimated_input_tokens=1000,
        estimated_output_tokens=500,
        correlation_id="corr-finops-1",
        allocation={"department": "sales"},
    )
    assert reservation.status == ReservationStatus.RESERVED.value
    db_session.commit()

    settlement = svc.settle(
        reservation_id=reservation.id,
        usage={
            "source": "PROVIDER_RESPONSE",
            "input_tokens": 900,
            "output_tokens": 400,
        },
    )
    db_session.commit()
    assert settlement.metering_source == MeteringSource.PRICING_CATALOG_DERIVED.value
    assert settlement.cost_state == "METERED"
    # 0.9*0.15 + 0.4*0.60 = 0.135 + 0.24 = 0.375
    assert abs(settlement.actual_cost - 0.375) < 1e-9
    assert abs((settlement.metered_cost or 0) - 0.375) < 1e-9
    assert settlement.reserved_cost == 0.45
    assert abs((settlement.delta_cost or 0) - (0.375 - 0.45)) < 1e-9

    db_session.refresh(reservation)
    assert reservation.status == ReservationStatus.SETTLED.value


def test_estimate_from_parameters_and_explicit_cost(db_session):
    svc = FinOpsService(db_session)
    svc.upsert_pricing(
        provider="anthropic",
        model="claude-3-5-sonnet",
        input_token_price=3.0,
        output_token_price=15.0,
        created_by="tester",
    )
    est = svc.estimate_from_parameters(
        {
            "provider": "anthropic",
            "model": "claude-3-5-sonnet",
            "estimated_input_tokens": 2000,
            "estimated_output_tokens": 0,
        }
    )
    assert est["reason"] == "OK"
    assert abs(est["estimated_cost"] - 6.0) < 1e-9

    explicit = svc.estimate_from_parameters({"estimated_cost": 12.5, "currency": "USD"})
    assert explicit["reason"] == "EXPLICIT_COST"
    assert explicit["estimated_cost"] == 12.5


def test_agent_supplied_ranked_below_gateway(db_session):
    payload, source = pick_trusted_usage(
        {
            "gateway_observed": {"input_tokens": 10, "output_tokens": 2, "cost": 0.01},
            "agent_supplied": {"input_tokens": 999, "cost": 9.99},
        }
    )
    assert source == MeteringSource.GATEWAY_OBSERVED.value
    assert payload["input_tokens"] == 10
