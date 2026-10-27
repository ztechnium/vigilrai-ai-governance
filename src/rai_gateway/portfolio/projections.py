"""Optional projection freshness tracking (idempotent, tenant-safe)."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from rai_gateway.models.portfolio import PortfolioProjectionState
from rai_gateway.portfolio.domain import Freshness
from rai_gateway.portfolio.queries import _ser_dt
from rai_gateway.portfolio.reports import content_digest

# Timestamps / freshness markers change every refresh and must not affect digest identity.
_VOLATILE_DIGEST_KEYS = frozenset(
    {
        "freshness",
        "last_refreshed_at",
        "last_success_at",
        "generated_at",
        "exported_at",
    }
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _stable_payload_for_digest(payload: Any) -> Any:
    """Strip volatile freshness fields so identical business state digests identically."""
    if isinstance(payload, dict):
        return {
            key: _stable_payload_for_digest(value)
            for key, value in payload.items()
            if key not in _VOLATILE_DIGEST_KEYS
        }
    if isinstance(payload, list):
        return [_stable_payload_for_digest(item) for item in payload]
    return payload


def refresh_projection(
    db: Session,
    projection_key: str,
    payload: dict[str, Any],
    *,
    freshness: Freshness = Freshness.NEAR_REAL_TIME,
) -> dict[str, Any]:
    """Idempotent projection refresh: same digest does not inflate refresh semantics incorrectly."""
    digest = content_digest(_stable_payload_for_digest(deepcopy(payload)))
    now = _utcnow()
    row = (
        db.query(PortfolioProjectionState)
        .filter(
            PortfolioProjectionState.projection_key == projection_key,
        )
        .first()
    )
    if row is None:
        row = PortfolioProjectionState(
            projection_key=projection_key,
            freshness=freshness.value,
            last_refreshed_at=now,
            last_success_at=now,
            refresh_count=1,
            payload_digest=digest,
        )
        db.add(row)
    else:
        row.last_refreshed_at = now
        row.freshness = freshness.value
        if row.payload_digest != digest:
            row.refresh_count = (row.refresh_count or 0) + 1
            row.payload_digest = digest
            row.last_success_at = now
            row.last_error = None
        # Identical digest → idempotent no-op on count
    db.flush()
    return {
        "projection_key": projection_key,
        "freshness": row.freshness,
        "last_refreshed_at": _ser_dt(row.last_refreshed_at),
        "last_success_at": _ser_dt(row.last_success_at),
        "refresh_count": row.refresh_count,
        "payload_digest": row.payload_digest,
    }


def get_projection_state(db: Session, projection_key: str) -> dict[str, Any] | None:
    row = (
        db.query(PortfolioProjectionState)
        .filter(
            PortfolioProjectionState.projection_key == projection_key,
        )
        .first()
    )
    if row is None:
        return None
    return {
        "projection_key": row.projection_key,
        "freshness": row.freshness,
        "last_refreshed_at": _ser_dt(row.last_refreshed_at),
        "last_success_at": _ser_dt(row.last_success_at),
        "refresh_count": row.refresh_count,
        "payload_digest": row.payload_digest,
        "last_error": row.last_error,
    }
