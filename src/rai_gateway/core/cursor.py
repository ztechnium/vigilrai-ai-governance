"""Shared keyset/cursor pagination helpers."""

from __future__ import annotations

import base64
from datetime import datetime, timezone
from uuid import UUID


def encode_time_id_cursor(*, occurred_at: datetime, record_id: UUID | str) -> str:
    """Encode (timestamp, id) for keyset pagination."""
    raw = f"{occurred_at.isoformat()}|{record_id}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def decode_time_id_cursor(cursor: str) -> tuple[datetime, str]:
    """Decode a cursor produced by ``encode_time_id_cursor``."""
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        ts_text, id_text = raw.split("|", 1)
        ts = datetime.fromisoformat(ts_text)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts, id_text
    except (ValueError, TypeError) as exc:
        raise ValueError("Invalid cursor") from exc
