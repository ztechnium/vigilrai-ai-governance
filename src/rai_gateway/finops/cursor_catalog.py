"""Resolve Cursor's published model rates for the pricing calculator."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid5

from rai_gateway.finops.cursor_pricing_data import (
    CATALOG_VERSION,
    CURSOR_TOKEN_RATE_PER_MILLION,
    LEGACY_MAX_MODE_MULTIPLIER,
    MODELS,
    PLANS,
    PRICING_UNIT,
    REGIONAL_RESIDENCY_UPLIFT,
    SOURCE_URL,
    TOKEN_RATE_PLANS,
)
from rai_gateway.models.finops import PricingCatalogEntry

SEED_ACTOR = "cursor-pricing-catalog"
_ENTRY_NAMESPACE = UUID("a3f1c2e4-7b89-4d01-9e55-0c1a2b3d4e5f")
_EFFECTIVE_FROM = datetime(2026, 9, 26, tzinfo=timezone.utc)


class CursorPricingCatalogError(ValueError):
    """Published Cursor catalog failed validation."""


def _index() -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for spec in MODELS:
        model_id = str(spec["id"]).strip().lower()
        if not model_id:
            raise CursorPricingCatalogError("Cursor model id is required")
        if model_id in index:
            raise CursorPricingCatalogError(f"Duplicate Cursor model id: {model_id}")
        if float(spec["input"]) < 0 or float(spec["output"]) < 0:
            raise CursorPricingCatalogError(f"Negative price for {model_id}")
        index[model_id] = spec
        for alias in spec.get("aliases") or []:
            key = str(alias).strip().lower()
            if not key or key == model_id:
                continue
            if key in index:
                raise CursorPricingCatalogError(
                    f"Cursor model alias {key} collides with {index[key]['id']}"
                )
            index[key] = spec
    return index


_MODEL_INDEX = _index()


def cursor_catalog_document() -> dict[str, Any]:
    """Public catalog payload for the pricing API and UI."""
    return {
        "version": CATALOG_VERSION,
        "source_url": SOURCE_URL,
        "currency": "USD",
        "pricing_unit": PRICING_UNIT,
        "cursor_token_rate_per_million": CURSOR_TOKEN_RATE_PER_MILLION,
        "cursor_token_rate_plans": sorted(TOKEN_RATE_PLANS),
        "regional_residency_uplift": REGIONAL_RESIDENCY_UPLIFT,
        "legacy_max_mode_multiplier": LEGACY_MAX_MODE_MULTIPLIER,
        "plans": PLANS,
        "models": [
            {
                "id": spec["id"],
                "display_name": spec["display_name"],
                "vendor": spec["vendor"],
                "pool": spec["pool"],
                "input_token_price": spec["input"],
                "output_token_price": spec["output"],
                "cached_input_token_price": spec["cache_read"],
                "cache_write_token_price": spec["cache_write"],
                "cursor_token_rate_exempt": spec["cursor_token_rate_exempt"],
                "hidden": spec["hidden"],
                "derived": spec["derived"],
                "aliases": spec["aliases"],
                "notes": spec["notes"],
                "source_url": spec["source_url"],
            }
            for spec in MODELS
        ],
    }


def lookup_cursor_model(model: str | None) -> dict[str, Any] | None:
    if not model or not str(model).strip():
        return None
    return _MODEL_INDEX.get(str(model).strip().lower())


def resolve_cursor_model_id(model: str, *, fast: bool = False) -> str | None:
    """Map a Cursor model id or alias to the canonical priced id."""
    spec = lookup_cursor_model(model)
    if spec is None:
        return None
    canonical = str(spec["id"])
    if fast and not canonical.endswith("-fast"):
        fast_spec = _MODEL_INDEX.get(f"{canonical}-fast")
        if fast_spec is not None:
            return str(fast_spec["id"])
    return canonical


def normalize_cursor_plan(plan: str | None) -> str | None:
    if not plan or not str(plan).strip():
        return None
    return str(plan).strip().lower().replace("-", "_").replace(" ", "_")


def cursor_token_rate_applies(
    spec: dict[str, Any] | None,
    *,
    plan: str | None = None,
    explicit: bool | None = None,
) -> bool:
    if spec is None or spec.get("cursor_token_rate_exempt"):
        return False
    if explicit is not None:
        return bool(explicit)
    normalized = normalize_cursor_plan(plan)
    return normalized in TOKEN_RATE_PLANS


def pricing_metadata_for(spec: dict[str, Any]) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "display_name": spec["display_name"],
        "vendor": spec["vendor"],
        "pool": spec["pool"],
        "catalog_version": CATALOG_VERSION,
        "cursor_token_rate_exempt": bool(spec["cursor_token_rate_exempt"]),
        "hidden": bool(spec["hidden"]),
        "derived": bool(spec["derived"]),
        "aliases": list(spec.get("aliases") or []),
        "notes": spec.get("notes") or "",
    }
    if not spec["cursor_token_rate_exempt"]:
        meta["cursor_token_rate_per_million"] = CURSOR_TOKEN_RATE_PER_MILLION
    tiers = spec.get("context_tiers") or []
    if tiers:
        meta["context_tiers"] = tiers
    return meta


def stable_cursor_pricing_id(model_id: str) -> UUID:
    return uuid5(_ENTRY_NAMESPACE, model_id)


def build_cursor_pricing_entry(spec: dict[str, Any]) -> PricingCatalogEntry:
    """Detached catalog row. Not added to a session."""
    return PricingCatalogEntry(
        id=stable_cursor_pricing_id(str(spec["id"])),
        provider="cursor",
        model=str(spec["id"]),
        input_token_price=float(spec["input"]),
        output_token_price=float(spec["output"]),
        cached_input_token_price=spec["cache_read"],
        cache_write_token_price=spec["cache_write"],
        pricing_unit=PRICING_UNIT,
        currency="USD",
        pricing_metadata=pricing_metadata_for(spec),
        source_url=spec.get("source_url") or SOURCE_URL,
        verified_at=_EFFECTIVE_FROM,
        effective_from=_EFFECTIVE_FROM,
        enabled=True,
        created_by=SEED_ACTOR,
    )


def published_cursor_entry(
    model: str,
    *,
    fast: bool = False,
) -> PricingCatalogEntry | None:
    canonical = resolve_cursor_model_id(model, fast=fast)
    if canonical is None:
        return None
    spec = _MODEL_INDEX.get(canonical)
    if spec is None:
        return None
    return build_cursor_pricing_entry(spec)
