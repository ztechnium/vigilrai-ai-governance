"""Metering idempotency — retries must not double-settle."""

from __future__ import annotations

from rai_gateway.finops.domain import CostState, MeteringSource
from rai_gateway.finops.metering import RuntimeMeteringService
from rai_gateway.finops.service import FinOpsService
from rai_gateway.models.finops import UsageSettlement


def test_sdk_retry_same_external_span_no_duplicate_settlement(db_session):
    FinOpsService(db_session).upsert_pricing(
        provider="openai",
        model="gpt-idem",
        input_token_price=1.0,
        output_token_price=1.0,
        created_by="tester",
    )
    metering = RuntimeMeteringService(db_session)
    first = metering.record_model_usage(
        external_span_id="exec-1",
        provider="openai",
        model="gpt-idem",
        usage={"input_tokens": 1000, "output_tokens": 0, "source": "PROVIDER_RESPONSE"},
    )
    second = metering.record_model_usage(
        external_span_id="exec-1",
        provider="openai",
        model="gpt-idem",
        usage={"input_tokens": 1000, "output_tokens": 0, "source": "PROVIDER_RESPONSE"},
    )
    db_session.commit()
    assert first.id == second.id
    assert second.cost_state == CostState.METERED.value
    settlements = (
        db_session.query(UsageSettlement)
        .filter(UsageSettlement.metering_span_id == first.id)
        .all()
    )
    assert len(settlements) == 1
    assert (
        settlements[0].metering_source == MeteringSource.PRICING_CATALOG_DERIVED.value
    )
