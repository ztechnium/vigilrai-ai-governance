"""WP5 evidence projection helpers for WP6 operational events."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def project_operational_event(
    db: Session,
    *,
    event_type: str,
    source_type: str,
    payload: dict[str, Any],
    trajectory_id: UUID | None = None,
    ai_system_id: UUID | None = None,
    runtime_identity_id: UUID | None = None,
) -> None:
    """Best-effort projection into WP5 trajectory evidence when available."""
    try:
        from rai_gateway.evidence.service import TrajectoryService

        svc = TrajectoryService(db)
        if trajectory_id and hasattr(svc, "record_derived_event"):
            svc.record_derived_event(
                trajectory_id,
                event_type=event_type,
                source_type=source_type,
                payload=payload,
            )
            return

        # Fallback: admin audit only when no trajectory
        from rai_gateway.core.observability import generate_trace_id, log_admin_audit

        log_admin_audit(
            trace_id=generate_trace_id(),
            actor_user_id="risk_intelligence",
            actor_role="system",
            action=event_type.lower(),
            target={
                "ai_system_id": str(ai_system_id) if ai_system_id else None,
                "runtime_identity_id": str(runtime_identity_id)
                if runtime_identity_id
                else None,
                "trajectory_id": str(trajectory_id) if trajectory_id else None,
                **payload,
            },
        )
    except Exception:
        logger.exception("Failed to project operational event %s", event_type)
