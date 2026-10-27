"""Lightweight metric helpers for portfolio aggregations."""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable


def count_by(
    values: Iterable[str | None], *, default: str = "UNKNOWN"
) -> dict[str, int]:
    return dict(Counter((v or default) for v in values))


def pct(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(100.0 * numerator / denominator, 2)


def merge_count_maps(*maps: dict[str, int]) -> dict[str, int]:
    out: Counter[str] = Counter()
    for m in maps:
        out.update(m)
    return dict(out)


def safe_avg(values: Iterable[float]) -> float | None:
    data = list(values)
    if not data:
        return None
    return round(sum(data) / len(data), 2)


def posture_block(
    *,
    freshness: str,
    last_refreshed_at: str | None,
    **payload: Any,
) -> dict[str, Any]:
    return {
        "freshness": freshness,
        "last_refreshed_at": last_refreshed_at,
        **payload,
    }
