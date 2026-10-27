"""FinOps domain enums and helpers."""

from __future__ import annotations

from enum import StrEnum


class MeteringSource(StrEnum):
    """Provenance of usage/cost data. Trust order is separate from financial state."""

    PROVIDER_RESPONSE = "PROVIDER_RESPONSE"
    GATEWAY_OBSERVED = "GATEWAY_OBSERVED"
    SIGNED_SERVICE = "SIGNED_SERVICE"
    SDK_REPORTED = "SDK_REPORTED"
    AGENT_SUPPLIED = "AGENT_SUPPLIED"
    ESTIMATED = "ESTIMATED"
    PRICING_CATALOG_DERIVED = "PRICING_CATALOG_DERIVED"
    PROVIDER_BILLING_API = "PROVIDER_BILLING_API"
    INVOICE_IMPORT = "INVOICE_IMPORT"
    EXPLICIT_COST = "EXPLICIT_COST"
    UNKNOWN = "UNKNOWN"


# Prefer provider/gateway over agent-declared usage.
METERING_TRUST_ORDER: tuple[str, ...] = (
    MeteringSource.SIGNED_SERVICE.value,
    MeteringSource.PROVIDER_RESPONSE.value,
    MeteringSource.GATEWAY_OBSERVED.value,
    MeteringSource.SDK_REPORTED.value,
    MeteringSource.AGENT_SUPPLIED.value,
    MeteringSource.ESTIMATED.value,
)


class ReservationStatus(StrEnum):
    RESERVED = "RESERVED"
    SETTLED = "SETTLED"
    RELEASED = "RELEASED"
    EXPIRED = "EXPIRED"


class CostState(StrEnum):
    UNAVAILABLE = "UNAVAILABLE"
    ESTIMATED = "ESTIMATED"
    METERED = "METERED"
    BILLED = "BILLED"
    MIXED = "MIXED"
    # Legacy — accepted on read only; prefer normalize_cost_state().
    ACTUAL = "ACTUAL"


class SpanType(StrEnum):
    MODEL_CALL = "MODEL_CALL"
    TOOL_CALL = "TOOL_CALL"
    EMBEDDING = "EMBEDDING"
    RERANK = "RERANK"
    IMAGE_GENERATION = "IMAGE_GENERATION"
    AUDIO = "AUDIO"
    EXTERNAL_API = "EXTERNAL_API"
    OTHER = "OTHER"


# Stronger sources must not be replaced by a later weaker report.
METERING_SOURCE_STRENGTH: dict[str, int] = {
    MeteringSource.PROVIDER_BILLING_API.value: 90,
    MeteringSource.INVOICE_IMPORT.value: 85,
    MeteringSource.PROVIDER_RESPONSE.value: 70,
    MeteringSource.GATEWAY_OBSERVED.value: 60,
    MeteringSource.SIGNED_SERVICE.value: 50,
    MeteringSource.EXPLICIT_COST.value: 40,
    MeteringSource.SDK_REPORTED.value: 35,
    MeteringSource.AGENT_SUPPLIED.value: 30,
    MeteringSource.PRICING_CATALOG_DERIVED.value: 20,
    MeteringSource.ESTIMATED.value: 10,
    MeteringSource.UNKNOWN.value: 0,
}

# Sources that carry authoritative monetary amounts (BILLED provenance).
BILLED_COST_SOURCES: frozenset[str] = frozenset(
    {
        MeteringSource.PROVIDER_RESPONSE.value,
        MeteringSource.GATEWAY_OBSERVED.value,
        MeteringSource.SIGNED_SERVICE.value,
        MeteringSource.PROVIDER_BILLING_API.value,
        MeteringSource.INVOICE_IMPORT.value,
    }
)

# Sources that report actual provider usage tokens (not preflight estimates).
ACTUAL_USAGE_SOURCES: frozenset[str] = frozenset(
    {
        MeteringSource.PROVIDER_RESPONSE.value,
        MeteringSource.GATEWAY_OBSERVED.value,
        MeteringSource.SIGNED_SERVICE.value,
        MeteringSource.SDK_REPORTED.value,
    }
)

# Backward-compat alias used by older call sites.
ACTUAL_COST_SOURCES: frozenset[str] = BILLED_COST_SOURCES


def is_actual_usage_source(source: str | None) -> bool:
    return str(source or "").upper() in ACTUAL_USAGE_SOURCES


def is_billed_cost_source(source: str | None) -> bool:
    return str(source or "").upper() in BILLED_COST_SOURCES


def is_catalog_derived(source: str | None) -> bool:
    return str(source or "").upper() == MeteringSource.PRICING_CATALOG_DERIVED.value


def normalize_cost_state(
    state: str | None,
    *,
    metering_source: str | None = None,
) -> str:
    """Map legacy ACTUAL and unknown values onto the V2 cost states."""
    value = str(state or CostState.UNAVAILABLE.value).upper()
    if value == CostState.ACTUAL.value:
        if is_catalog_derived(metering_source):
            return CostState.METERED.value
        if is_billed_cost_source(metering_source):
            return CostState.BILLED.value
        # Ambiguous legacy actual without billed provenance → METERED
        return CostState.METERED.value
    if value in {s.value for s in CostState}:
        return value
    return CostState.UNAVAILABLE.value


def settled_amount(
    *,
    billed_cost: float | None = None,
    metered_cost: float | None = None,
    estimated_cost: float | None = None,
    actual_cost: float | None = None,
) -> float | None:
    """Prefer billed > metered > estimated. actual_cost is legacy fallback."""
    if billed_cost is not None:
        return float(billed_cost)
    if metered_cost is not None:
        return float(metered_cost)
    if estimated_cost is not None:
        return float(estimated_cost)
    if actual_cost is not None:
        return float(actual_cost)
    return None


_PROVIDER_ALIASES: dict[str, str] = {
    "openai": "openai",
    "azure": "azure_openai",
    "azure_openai": "azure_openai",
    "azureopenai": "azure_openai",
    "anthropic": "anthropic",
    "google": "google",
    "gemini": "google",
    "vertex": "google",
    "vertexai": "google",
    "vertex_ai": "google",
    "mistral": "mistral",
    "bedrock": "bedrock",
    "amazon": "bedrock",
    "aws": "bedrock",
    "cursor": "cursor",
    "cursor_ai": "cursor",
    "cursor_ide": "cursor",
    "cursorai": "cursor",
}


def normalize_provider(value: str | None) -> str | None:
    if not value or not str(value).strip():
        return None
    key = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    return _PROVIDER_ALIASES.get(key, key)


def normalize_model(value: str | None) -> str | None:
    if not value or not str(value).strip():
        return None
    return str(value).strip()


def reject_foreign_trajectory(
    session_trajectory_id: str | None,
    requested_trajectory_id: str | None,
) -> None:
    """SDK callers may only meter the trajectory bound to their session."""
    if not requested_trajectory_id:
        return
    if not session_trajectory_id or requested_trajectory_id != session_trajectory_id:
        raise PermissionError("Metering span cannot attach to another trajectory")
