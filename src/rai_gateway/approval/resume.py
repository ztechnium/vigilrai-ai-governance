"""Structured approval resume contract for runtime clients."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from rai_gateway.approval.domain import ApprovalStatus
from rai_gateway.models.approval import ApprovalRequest

RESUME_MODE_RETRY_EXACT_ACTION = "RETRY_EXACT_ACTION"

_TERMINAL_STATUSES = frozenset(
    {
        ApprovalStatus.REJECTED.value,
        ApprovalStatus.EXPIRED.value,
        ApprovalStatus.CANCELLED.value,
        ApprovalStatus.CONSUMED.value,
    }
)


def approval_poll_url(request_id: UUID | str) -> str:
    return f"/v1/runtime/approvals/{request_id}/status"


def build_approval_resume(request: ApprovalRequest) -> dict[str, Any]:
    """Nested approval object returned with REQUIRE_APPROVAL decisions."""
    return {
        "request_id": str(request.id),
        "status": request.status,
        "expires_at": request.expires_at.isoformat() if request.expires_at else None,
        "action_digest": request.action_digest,
        "resume_mode": RESUME_MODE_RETRY_EXACT_ACTION,
        "poll_url": approval_poll_url(request.id),
    }


def build_approval_status_response(request: ApprovalRequest) -> dict[str, Any]:
    """Minimal safe status payload for runtime / SDK poll endpoints."""
    status = request.status
    can_retry = status == ApprovalStatus.APPROVED.value
    terminal = status in _TERMINAL_STATUSES
    return {
        "request_id": str(request.id),
        "status": status,
        "expires_at": request.expires_at.isoformat() if request.expires_at else None,
        "can_retry": can_retry,
        "terminal": terminal,
        "resume_mode": RESUME_MODE_RETRY_EXACT_ACTION,
        "poll_url": approval_poll_url(request.id),
        # Compat aliases used by existing SDK clients
        "approval_request_id": str(request.id),
    }
