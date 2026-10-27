"""Metering cost provenance, aggregation, and tenant isolation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from rai_gateway.finops.domain import (
    CostState,
    MeteringSource,
    reject_foreign_trajectory,
)
from rai_gateway.finops.metering import RuntimeMeteringService, aggregate_spans
from rai_gateway.finops.service import FinOpsService


def test_provider_billed_cost_is_not_estimated(db_session):
    span = RuntimeMeteringService(db_session).record_model_usage(
        provider="google",
        model="gemini-test",
        usage={"input_tokens": 100, "output_tokens": 40},
        cost={"amount": 0.0023, "currency": "USD", "source": "PROVIDER_RESPONSE"},
    )
    db_session.commit()
    assert span.cost_state == CostState.BILLED.value
    assert span.billed_cost == 0.0023
    assert span.actual_cost == 0.0023
    assert span.estimated_cost is None
    assert span.metering_source == MeteringSource.PROVIDER_RESPONSE.value


def test_catalog_price_is_metered_at_execution_time(db_session):
    svc = FinOpsService(db_session)
    old = datetime.now(timezone.utc) - timedelta(days=10)
    svc.upsert_pricing(
        provider="openai",
        model="gpt-hist",
        input_token_price=1.0,
        output_token_price=2.0,
        created_by="tester",
        effective_from=old - timedelta(days=1),
        effective_to=old + timedelta(days=1),
    )
    svc.upsert_pricing(
        provider="openai",
        model="gpt-hist",
        input_token_price=9.0,
        output_token_price=9.0,
        created_by="tester",
        effective_from=old + timedelta(days=2),
    )
    span = RuntimeMeteringService(db_session).record_model_usage(
        provider="OpenAI",
        model="gpt-hist",
        usage={"input_tokens": 1000, "output_tokens": 0},
        started_at=old.isoformat(),
    )
    db_session.commit()
    assert span.cost_state == CostState.METERED.value
    assert span.estimated_cost is None
    assert abs((span.metered_cost or 0) - 1.0) < 1e-9
    assert abs((span.actual_cost or 0) - 1.0) < 1e-9
    assert span.metering_source == MeteringSource.PRICING_CATALOG_DERIVED.value
    assert span.pricing_snapshot is not None
    assert span.pricing_snapshot["input_token_price"] == 1.0


def test_unknown_model_cost_is_unavailable_not_zero(db_session):
    span = RuntimeMeteringService(db_session).record_model_usage(
        provider="unknown-vendor",
        model="mystery",
        usage={"input_tokens": 10, "output_tokens": 10},
    )
    db_session.commit()
    assert span.cost_state == CostState.UNAVAILABLE.value
    assert span.actual_cost is None
    assert span.estimated_cost is None


def test_mixed_trajectory_total_is_sum_of_spans(db_session):
    metering = RuntimeMeteringService(db_session)
    billed = metering.record_model_usage(
        provider="google",
        model="gemini-test",
        usage={"input_tokens": 10, "output_tokens": 10},
        cost={"amount": 0.004, "source": "PROVIDER_RESPONSE"},
    )
    FinOpsService(db_session).upsert_pricing(
        provider="openai",
        model="gpt-mix",
        input_token_price=1.0,
        output_token_price=1.0,
        created_by="tester",
    )
    metered = metering.record_model_usage(
        provider="openai",
        model="gpt-mix",
        usage={"input_tokens": 1000, "output_tokens": 0},
    )
    db_session.commit()
    summary = aggregate_spans([billed, metered])
    assert summary["cost_state"] == CostState.MIXED.value
    assert abs(summary["total_cost"] - 1.004) < 1e-9


def test_duplicate_external_span_is_idempotent(db_session):
    metering = RuntimeMeteringService(db_session)
    first = metering.record_model_usage(
        external_span_id="span-1",
        provider="google",
        model="gemini-test",
        cost={"amount": 0.01, "source": "PROVIDER_RESPONSE"},
    )
    second = metering.record_model_usage(
        external_span_id="span-1",
        provider="google",
        model="gemini-test",
        cost={"amount": 0.01, "source": "AGENT_SUPPLIED"},
    )
    db_session.commit()
    assert first.id == second.id
    assert second.cost_state == CostState.BILLED.value
    assert second.billed_cost == 0.01
    assert second.actual_cost == 0.01


def test_sdk_cannot_target_another_trajectory():
    with pytest.raises(PermissionError):
        reject_foreign_trajectory("traj-a", "traj-b")
    reject_foreign_trajectory("traj-a", "traj-a")
