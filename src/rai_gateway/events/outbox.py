"""Transactional outbox helpers — never send HTTP inside the domain transaction."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from rai_gateway.models.approval import ApprovalRequest
from rai_gateway.models.events import EventOutbox


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def approval_event_payload(request: ApprovalRequest) -> dict[str, Any]:
    """Safe webhook/outbox payload — no raw action parameters."""
    return {
        "approval_request_id": str(request.id),
        "status": request.status,
        "ai_system_id": str(request.ai_system_id),
        "agent_id": str(request.agent_id),
        "agent_version_id": str(request.agent_version_id),
        "runtime_identity_id": str(request.runtime_identity_id),
        "delegation_id": str(request.delegation_id) if request.delegation_id else None,
        "action_digest": request.action_digest,
        "risk_tier": request.risk_tier,
        "expires_at": request.expires_at.isoformat() if request.expires_at else None,
        "correlation_id": request.correlation_id,
        "runtime_idempotency_key": getattr(request, "runtime_idempotency_key", None),
    }


def enqueue_outbox_event(
    db: Session,
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: UUID,
    payload: dict[str, Any],
    available_at: datetime | None = None,
) -> EventOutbox:
    now = _utcnow()
    row = EventOutbox(
        id=uuid4(),
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload=payload,
        occurred_at=now,
        available_at=available_at or now,
        processed_at=None,
        attempt_count=0,
    )
    db.add(row)
    db.flush()
    return row


def enqueue_approval_event(
    db: Session,
    request: ApprovalRequest,
    event_type: str,
) -> EventOutbox | None:
    return enqueue_outbox_event(
        db,
        event_type=event_type,
        aggregate_type="approval_request",
        aggregate_id=request.id,
        payload=approval_event_payload(request),
    )
