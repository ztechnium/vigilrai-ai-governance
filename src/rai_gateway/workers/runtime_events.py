"""Runtime events worker: approval expiration + outbox → webhook delivery."""

from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from rai_gateway.approval.service import ApprovalService
from rai_gateway.core.config import settings
from rai_gateway.core.database import SessionLocal
from rai_gateway.models.events import EventOutbox


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def claim_outbox_rows(db: Session, *, limit: int = 50) -> list[EventOutbox]:
    now = _utcnow()
    query = (
        db.query(EventOutbox)
        .filter(
            EventOutbox.processed_at.is_(None),
            EventOutbox.available_at <= now,
        )
        .order_by(EventOutbox.available_at.asc())
        .limit(limit)
    )
    try:
        return query.with_for_update(skip_locked=True).all()
    except Exception:  # noqa: BLE001
        return query.all()


def process_outbox_to_webhooks(db: Session, *, limit: int = 50) -> int:
    """Bridge outbox rows into WebhookDelivery records, then attempt delivery."""
    if not getattr(settings, "approval_webhooks_enabled", True):
        return 0

    from rai_gateway.sdk.webhooks import WebhookService

    rows = claim_outbox_rows(db, limit=limit)
    if not rows:
        return 0

    webhook = WebhookService(db)
    processed = 0
    for row in rows:
        try:
            webhook.enqueue(
                event_type=row.event_type,
                payload=row.payload if isinstance(row.payload, dict) else {},
                event_id=str(row.id),
            )
            row.processed_at = _utcnow()
            row.last_error = None
            processed += 1
        except Exception as exc:  # noqa: BLE001 — worker must continue
            row.attempt_count = int(row.attempt_count or 0) + 1
            row.last_error = str(exc)[:2000]
            # Retry later
            from datetime import timedelta

            delay = min(3600, 30 * (2 ** min(row.attempt_count, 6)))
            row.available_at = _utcnow() + timedelta(seconds=delay)
    db.commit()

    # Deliver pending webhook rows (notification only; never affects approval state)
    webhook.process_pending(limit=limit)
    db.commit()
    return processed


def run_once(db: Session | None = None) -> dict[str, int]:
    own_session = db is None
    session = db or SessionLocal()
    try:
        expired = ApprovalService(session).expire_due_approvals(limit=100)
        outbox = process_outbox_to_webhooks(session, limit=50)
        return {"expired": expired, "outbox_processed": outbox}
    finally:
        if own_session:
            session.close()


def run_loop(*, interval_seconds: float = 5.0) -> None:
    while True:
        stats = run_once()
        if stats["expired"] or stats["outbox_processed"]:
            print(
                f"[runtime-events] expired={stats['expired']} "
                f"outbox={stats['outbox_processed']}"
            )
        time.sleep(interval_seconds)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="VigilRAI runtime events worker")
    parser.add_argument(
        "command",
        nargs="?",
        default="runtime-events",
        choices=["runtime-events"],
    )
    parser.add_argument("--once", action="store_true", help="Run a single pass")
    parser.add_argument(
        "--interval",
        type=float,
        default=5.0,
        help="Loop interval seconds (default 5)",
    )
    args = parser.parse_args(argv)
    if args.once:
        stats = run_once()
        print(stats)
        return 0
    run_loop(interval_seconds=args.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
