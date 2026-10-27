"""Background job queue seam (DB-backed, worker-process friendly)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from rai_gateway.models.productization import BackgroundJob
from rai_gateway.sdk.domain import BackgroundJobStatus


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobQueue:
    def __init__(self, db: Session) -> None:
        self._db = db

    def enqueue(
        self,
        *,
        job_type: str,
        payload: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        created_by: str | None = None,
        max_attempts: int = 5,
    ) -> dict[str, Any]:
        if idempotency_key:
            existing = (
                self._db.query(BackgroundJob)
                .filter(BackgroundJob.idempotency_key == idempotency_key)
                .first()
            )
            if existing:
                return self._serialize(existing)

        job = BackgroundJob(
            job_type=job_type,
            status=BackgroundJobStatus.PENDING.value,
            idempotency_key=idempotency_key,
            payload=payload or {},
            max_attempts=max_attempts,
            next_attempt_at=_utcnow(),
            created_by=created_by,
        )
        self._db.add(job)
        self._db.flush()
        return self._serialize(job)

    def claim_next(self, *, job_types: list[str] | None = None) -> BackgroundJob | None:
        now = _utcnow()
        q = self._db.query(BackgroundJob).filter(
            BackgroundJob.status == BackgroundJobStatus.PENDING.value,
            (BackgroundJob.next_attempt_at.is_(None))
            | (BackgroundJob.next_attempt_at <= now),
        )
        if job_types:
            q = q.filter(BackgroundJob.job_type.in_(job_types))
        job = (
            q.order_by(BackgroundJob.created_at.asc())
            .with_for_update(skip_locked=True)
            .first()
        )
        if not job:
            return None
        job.status = BackgroundJobStatus.RUNNING.value
        job.started_at = now
        job.attempt_count = (job.attempt_count or 0) + 1
        self._db.flush()
        return job

    def complete(
        self, job: BackgroundJob, result: dict[str, Any] | None = None
    ) -> None:
        job.status = BackgroundJobStatus.SUCCEEDED.value
        job.result = result
        job.completed_at = _utcnow()
        job.last_error = None
        self._db.flush()

    def fail(self, job: BackgroundJob, error: str) -> None:
        job.last_error = error[:2000]
        if (job.attempt_count or 0) >= (job.max_attempts or 5):
            job.status = BackgroundJobStatus.DEAD_LETTER.value
            job.completed_at = _utcnow()
        else:
            job.status = BackgroundJobStatus.PENDING.value
            job.next_attempt_at = _utcnow() + timedelta(
                seconds=min(3600, 2 ** (job.attempt_count or 1))
            )
        self._db.flush()

    def list_jobs(
        self,
        *,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        q = self._db.query(BackgroundJob)
        if status:
            q = q.filter(BackgroundJob.status == status)
        rows = q.order_by(BackgroundJob.created_at.desc()).limit(limit).all()
        return [self._serialize(r) for r in rows]

    def _serialize(self, job: BackgroundJob) -> dict[str, Any]:
        return {
            "id": str(job.id),
            "job_type": job.job_type,
            "status": job.status,
            "idempotency_key": job.idempotency_key,
            "payload": job.payload,
            "result": job.result,
            "attempt_count": job.attempt_count,
            "max_attempts": job.max_attempts,
            "last_error": job.last_error,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        }
