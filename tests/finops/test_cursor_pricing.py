"""Cursor published rates in the pricing calculator."""

from __future__ import annotations

from datetime import datetime, timezone

from rai_gateway.finops.cursor_pricing_data import MODELS
from rai_gateway.finops.service import FinOpsService
from rai_gateway.models.finops import PricingCatalogEntry


def _clear_cursor_prices(db_session) -> None:
    db_session.query(PricingCatalogEntry).filter(
        PricingCatalogEntry.provider == "cursor"
    ).delete()
    db_session.commit()


def test_cursor_catalog_covers_published_table():
    ids = {row["id"] for row in MODELS}
    assert len(ids) >= 55
    grok = next(row for row in MODELS if row["id"] == "grok-4.7")
    assert grok["input"] == 2
    assert grok["cache_read"] == 0.5
    assert grok["output"] == 6
    grok_fast_45 = next(row for row in MODELS if row["id"] == "grok-4.5-fast")
    assert grok_fast_45["output"] == 18
    composer = next(row for row in MODELS if row["id"] == "composer-2.5")
    assert composer["input"] == 0.5
    assert composer["output"] == 2.5
    sol = next(row for row in MODELS if row["id"] == "gpt-5.6-sol")
    assert sol["input"] == 4
    assert sol["cache_write"] == 5
    assert sol["output"] == 20


def test_estimate_cursor_model_without_a_database_row(db_session):
    _clear_cursor_prices(db_session)
    estimate = FinOpsService(db_session).estimate_cost(
        provider="Cursor",
        model="grok-4.7-high",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
    )
    assert estimate["reason"] == "OK"
    assert estimate["model"] == "grok-4.7"
    # $2 input + $6 output per million, doubled once input exceeds the 256k tier.
    assert abs(estimate["estimated_cost"] - 16.0) < 1e-9
    assert estimate["cursor_token_rate_applied"] is False


def test_composer_cache_read_and_grok_long_context(db_session):
    svc = FinOpsService(db_session)
    cache = svc.estimate_cost(
        provider="cursor",
        model="composer-2.5",
        cached_input_tokens=1_000_000,
    )
    assert abs(cache["estimated_cost"] - 0.2) < 1e-9

    long_context = svc.estimate_cost(
        provider="cursor",
        model="grok-4.7",
        input_tokens=300_000,
    )
    # 300k * $2/M = $0.60, then 2x because input exceeds 256k.
    assert abs(long_context["estimated_cost"] - 1.2) < 1e-9

    fast_long = svc.estimate_cost(
        provider="cursor",
        model="grok-4.7",
        input_tokens=300_000,
        fast=True,
    )
    # Fast list price is $4/M; long context is 1.5x that, equal to $6/M.
    assert fast_long["model"] == "grok-4.7-fast"
    assert abs(fast_long["estimated_cost"] - 1.8) < 1e-9


def test_teams_token_rate_applies_to_third_party_only(db_session):
    _clear_cursor_prices(db_session)
    svc = FinOpsService(db_session)
    third_party = svc.estimate_cost(
        provider="cursor",
        model="gpt-5.4-mini",
        input_tokens=1_000_000,
        plan="teams",
    )
    # $0.75 API + $0.25 Cursor token rate.
    assert abs(third_party["estimated_cost"] - 1.0) < 1e-9
    assert third_party["cursor_token_rate_applied"] is True

    first_party = svc.estimate_cost(
        provider="cursor",
        model="grok-4.7",
        input_tokens=1_000_000,
        plan="enterprise",
    )
    assert abs(first_party["estimated_cost"] - 4.0) < 1e-9
    assert first_party["cursor_token_rate_applied"] is False

    individual = svc.estimate_cost(
        provider="cursor",
        model="gpt-5.4-mini",
        input_tokens=1_000_000,
        plan="pro",
    )
    assert abs(individual["estimated_cost"] - 0.75) < 1e-9


def test_start_plan_blocks_other_models_and_fast_mode(db_session):
    _clear_cursor_prices(db_session)
    svc = FinOpsService(db_session)
    blocked = svc.estimate_cost(
        provider="cursor",
        model="claude-sonnet-5",
        input_tokens=1000,
        plan="start",
    )
    assert blocked["reason"] == "CURSOR_OTHER_MODELS_NOT_ON_START"
    assert blocked["estimated_cost"] is None

    standard = svc.estimate_cost(
        provider="cursor",
        model="grok-4.7",
        input_tokens=1_000_000,
        fast=True,
        plan="start",
    )
    assert standard["model"] == "grok-4.7"
    assert abs(standard["estimated_cost"] - 4.0) < 1e-9


def test_seed_is_idempotent_and_preserves_admin_prices(db_session):
    svc = FinOpsService(db_session)
    svc.upsert_pricing(
        provider="cursor",
        model="grok-4.7",
        input_token_price=9.0,
        output_token_price=9.0,
        pricing_unit=1_000_000,
        created_by="platform-admin",
    )
    first = svc.seed_cursor_pricing(created_by="platform-admin")
    assert first["created"] == len(MODELS) - 1
    assert first["preserved"] == 1

    custom = svc.estimate_cost(
        provider="cursor",
        model="grok-4.7",
        input_tokens=1_000_000,
    )
    assert abs(custom["estimated_cost"] - 9.0) < 1e-9

    second = svc.seed_cursor_pricing()
    assert second["created"] == 0
    assert second["skipped"] == len(MODELS) - 1
    assert second["preserved"] == 1


def test_historical_lookup_does_not_use_current_cursor_rates(db_session):
    estimate = FinOpsService(db_session).estimate_cost(
        provider="cursor",
        model="composer-2.5",
        input_tokens=1_000_000,
        at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert estimate["reason"] == "NO_PRICING"
    assert estimate["estimated_cost"] is None
