"""In-process FinOps counters. Labels stay low-cardinality."""

from __future__ import annotations

from threading import Lock

_LOCK = Lock()
_COUNTERS: dict[str, int] = {
    "finops_metering_spans_total": 0,
    "finops_metering_actual_total": 0,
    "finops_metering_estimated_total": 0,
    "finops_metering_unavailable_total": 0,
    "finops_settlement_total": 0,
    "finops_cost_total_micros": 0,
    "finops_tokens_total": 0,
    "finops_pricing_lookup_miss_total": 0,
    "finops_metering_ingest_errors_total": 0,
}


def inc(name: str, amount: int = 1) -> None:
    if name not in _COUNTERS:
        return
    with _LOCK:
        _COUNTERS[name] += int(amount)


def snapshot() -> dict[str, int]:
    with _LOCK:
        return dict(_COUNTERS)
