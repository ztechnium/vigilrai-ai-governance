"""WP5 evidence retention and legal-hold minimum behavior."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from rai_gateway.core.observability import generate_trace_id, log_admin_audit
from rai_gateway.evidence.repository import EvidenceRepository
from rai_gateway.models.evidence import (
    EvidenceArtifact,
    EvidenceEvent,
    EvidenceFinding,
    EvidenceRelation,
    RuntimeTrajectory,
)

DEFAULT_RETENTION_DAYS = 90


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EvidenceRetentionError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class EvidenceRetentionService:
    """Authorize and perform minimum retention / legal-hold operations."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._repo = EvidenceRepository(db)

    def compute_eligible_for_purge_at(
        self,
        *,
        anchor: datetime | None,
        retention_days: int | None,
    ) -> datetime | None:
        days = retention_days if retention_days is not None else DEFAULT_RETENTION_DAYS
        if days < 0:
            return None
        base = anchor or _utcnow()
        return base + timedelta(days=days)

    def apply_defaults(self, trajectory: RuntimeTrajectory) -> None:
        updates: dict[str, Any] = {}
        if trajectory.retention_days is None:
            updates["retention_days"] = DEFAULT_RETENTION_DAYS
        retention_days = updates.get("retention_days", trajectory.retention_days)
        if trajectory.eligible_for_purge_at is None:
            updates["eligible_for_purge_at"] = self.compute_eligible_for_purge_at(
                anchor=trajectory.ended_at
                or trajectory.last_event_at
                or trajectory.started_at,
                retention_days=retention_days,
            )
        if updates:
            self._repo.update_trajectory(trajectory, **updates)

    def is_purge_eligible(
        self, trajectory: RuntimeTrajectory, *, now: datetime | None = None
    ) -> tuple[bool, str]:
        self.apply_defaults(trajectory)
        if trajectory.legal_hold:
            return False, "LEGAL_HOLD_ACTIVE"
        eligible_at = trajectory.eligible_for_purge_at
        if eligible_at is None:
            return False, "NO_PURGE_DATE"
        current = now or _utcnow()
        if eligible_at > current:
            return False, "NOT_EXPIRED"
        return True, "ELIGIBLE"

    def set_legal_hold(
        self,
        trajectory_id: UUID,
        *,
        legal_hold: bool,
        actor: str,
        reason: str | None = None,
    ) -> RuntimeTrajectory:
        trajectory = self._repo.get_trajectory(trajectory_id)
        if not trajectory:
            raise EvidenceRetentionError("NOT_FOUND", "Trajectory not found")
        self._repo.update_trajectory(trajectory, legal_hold=legal_hold)
        self._db.commit()
        log_admin_audit(
            trace_id=generate_trace_id(),
            actor_user_id=actor,
            actor_role="member",
            action=(
                "evidence.legal_hold.applied"
                if legal_hold
                else "evidence.legal_hold.released"
            ),
            target={"trajectory_id": str(trajectory_id)},
            reason=reason,
        )
        return trajectory

    def set_retention(
        self,
        trajectory_id: UUID,
        *,
        retention_days: int,
        actor: str,
        reason: str | None = None,
    ) -> RuntimeTrajectory:
        if retention_days < 0:
            raise EvidenceRetentionError(
                "INVALID_RETENTION", "retention_days must be >= 0"
            )
        trajectory = self._repo.get_trajectory(trajectory_id)
        if not trajectory:
            raise EvidenceRetentionError("NOT_FOUND", "Trajectory not found")
        eligible = self.compute_eligible_for_purge_at(
            anchor=trajectory.ended_at
            or trajectory.last_event_at
            or trajectory.started_at,
            retention_days=retention_days,
        )
        self._repo.update_trajectory(
            trajectory,
            retention_days=retention_days,
            eligible_for_purge_at=eligible,
        )
        self._db.commit()
        log_admin_audit(
            trace_id=generate_trace_id(),
            actor_user_id=actor,
            actor_role="member",
            action="evidence.retention.updated",
            target={
                "trajectory_id": str(trajectory_id),
                "retention_days": retention_days,
                "eligible_for_purge_at": eligible.isoformat() if eligible else None,
            },
            reason=reason,
        )
        return trajectory

    def purge_trajectory(
        self,
        trajectory_id: UUID,
        *,
        actor: str,
        reason: str | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        trajectory = self._repo.get_trajectory(trajectory_id)
        if not trajectory:
            raise EvidenceRetentionError("NOT_FOUND", "Trajectory not found")

        eligible, code = self.is_purge_eligible(trajectory)
        if not eligible and not force:
            raise EvidenceRetentionError(
                code, f"Trajectory not eligible for purge ({code})"
            )
        if trajectory.legal_hold:
            raise EvidenceRetentionError(
                "LEGAL_HOLD_ACTIVE", "Cannot purge trajectory under legal hold"
            )

        log_admin_audit(
            trace_id=generate_trace_id(),
            actor_user_id=actor,
            actor_role="member",
            action="evidence.purge.requested",
            target={"trajectory_id": str(trajectory_id)},
            reason=reason,
        )

        events = self._db.query(EvidenceEvent).filter(
            EvidenceEvent.trajectory_id == trajectory_id
        )
        findings = self._db.query(EvidenceFinding).filter(
            EvidenceFinding.trajectory_id == trajectory_id
        )
        relations = self._db.query(EvidenceRelation).filter(
            EvidenceRelation.trajectory_id == trajectory_id
        )
        artifacts = self._db.query(EvidenceArtifact).filter(
            EvidenceArtifact.trajectory_id == trajectory_id
        )
        counts = {
            "events": events.count(),
            "findings": findings.count(),
            "relations": relations.count(),
            "artifacts": artifacts.count(),
        }
        artifacts.delete(synchronize_session=False)
        relations.delete(synchronize_session=False)
        findings.delete(synchronize_session=False)
        events.delete(synchronize_session=False)
        self._db.delete(trajectory)
        self._db.commit()

        log_admin_audit(
            trace_id=generate_trace_id(),
            actor_user_id=actor,
            actor_role="member",
            action="evidence.purge.completed",
            target={
                "trajectory_id": str(trajectory_id),
                "deleted_counts": counts,
            },
            reason=reason,
        )
        return {"trajectory_id": str(trajectory_id), "deleted": counts}

    def list_eligible_for_purge(
        self,
        *,
        limit: int = 100,
        now: datetime | None = None,
    ) -> list[RuntimeTrajectory]:
        current = now or _utcnow()
        query = self._db.query(RuntimeTrajectory).filter(
            RuntimeTrajectory.legal_hold.is_(False),
            RuntimeTrajectory.eligible_for_purge_at.isnot(None),
            RuntimeTrajectory.eligible_for_purge_at <= current,
        )
        return (
            query.order_by(RuntimeTrajectory.eligible_for_purge_at.asc())
            .limit(limit)
            .all()
        )
