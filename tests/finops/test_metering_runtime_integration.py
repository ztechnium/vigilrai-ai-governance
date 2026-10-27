"""Runtime metering integration — tokens-only → METERED; failed still charged."""

from __future__ import annotations

from uuid import uuid4

from rai_gateway.finops.domain import CostState, ReservationStatus
from rai_gateway.finops.metering import RuntimeMeteringService, normalize_usage
from rai_gateway.finops.service import FinOpsService


def test_normalize_openai_and_anthropic_aliases():
    openaiish = normalize_usage(
        {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "prompt_tokens_details": {"cached_tokens": 3},
            "completion_tokens_details": {"reasoning_tokens": 2},
        }
    )
    assert openaiish["input_tokens"] == 10
    assert openaiish["output_tokens"] == 5
    assert openaiish["cached_input_tokens"] == 3
    assert openaiish["reasoning_tokens"] == 2

    anthropic = normalize_usage(
        {
            "input_tokens": 8,
            "output_tokens": 4,
            "cache_read_input_tokens": 2,
            "cache_creation_input_tokens": 1,
        }
    )
    assert anthropic["cached_input_tokens"] == 2
    assert anthropic["cache_write_tokens"] == 1


def test_provider_tokens_only_produce_metered_cost(db_session):
    FinOpsService(db_session).upsert_pricing(
        provider="openai",
        model="gpt-meter",
        input_token_price=0.15,
        output_token_price=0.60,
        created_by="tester",
    )
    span = RuntimeMeteringService(db_session).record_model_usage(
        provider="openai",
        model="gpt-meter",
        usage={
            "source": "PROVIDER_RESPONSE",
            "input_tokens": 1000,
            "output_tokens": 500,
        },
        tool_id=uuid4(),
    )
    db_session.commit()
    assert span.cost_state == CostState.METERED.value
    assert abs((span.metered_cost or 0) - 0.45) < 1e-9
    assert span.pricing_snapshot is not None
    assert span.tool_id is not None


def test_failed_execution_with_usage_is_still_metered(db_session):
    FinOpsService(db_session).upsert_pricing(
        provider="openai",
        model="gpt-fail",
        input_token_price=1.0,
        output_token_price=1.0,
        created_by="tester",
    )
    span = RuntimeMeteringService(db_session).record_model_usage(
        provider="openai",
        model="gpt-fail",
        usage={"input_tokens": 1000, "output_tokens": 0, "source": "PROVIDER_RESPONSE"},
        metadata={"execution_status": "FAILED"},
    )
    db_session.commit()
    assert span.cost_state == CostState.METERED.value
    assert span.metered_cost == 1.0


def test_denied_before_execution_releases_reservation(db_session):
    svc = FinOpsService(db_session)
    reservation = svc.reserve(
        estimated_cost=1.25, currency="USD", correlation_id="deny-1"
    )
    db_session.commit()
    released = svc.release(reservation.id, reason="budget_denied")
    db_session.commit()
    assert released.status == ReservationStatus.RELEASED.value
    assert (released.allocation or {}).get("release_reason") == "budget_denied"


def test_unavailable_settlement_does_not_fabricate_zero(db_session):
    svc = FinOpsService(db_session)
    reservation = svc.reserve(estimated_cost=2.0, currency="USD")
    settlement = svc.settle(
        reservation_id=reservation.id,
        usage={
            "source": "PROVIDER_RESPONSE",
            "input_tokens": 10,
            "provider": "x",
            "model": "y",
        },
    )
    db_session.commit()
    assert settlement.cost_state == CostState.UNAVAILABLE.value
    assert settlement.actual_cost is None
    assert settlement.metered_cost is None
