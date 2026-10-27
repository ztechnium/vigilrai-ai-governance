"""Report snapshot generation and storage.

Report snapshots are immutable historical reports that preserve a point-in-time
view of governance, risk, and compliance metrics.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from rai_gateway.models.reporting import ReportSnapshot as ReportSnapshotRow
from rai_gateway.reporting.schemas import ReportSnapshot, ReportSnapshotCreate

if TYPE_CHECKING:
    pass


def generate_snapshot_digest(data: dict[str, Any]) -> str:
    """Generate content digest for snapshot immutability verification."""
    content_json = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(content_json.encode()).hexdigest()


def create_snapshot(
    db: Session,
    report_data: dict[str, Any],
    request: ReportSnapshotCreate,
    generated_by: str,
) -> ReportSnapshot:
    """Create an immutable report snapshot.

    Args:
        db: Database session
        report_data: Report payload data to snapshot
        request: Snapshot creation request
        generated_by: User/service that generated the snapshot

    Returns:
        Created snapshot metadata
    """
    # Generate content digest for immutability
    digest = generate_snapshot_digest(report_data)

    # Extract period from filters
    period_start = request.filters.period_start or datetime.utcnow()
    period_end = request.filters.period_end or datetime.utcnow()

    # Build source manifest if possible
    source_manifest = extract_source_manifest(report_data)
    stored_manifest = None
    if source_manifest:
        stored_manifest = {
            key: [str(item) for item in values]
            for key, values in source_manifest.items()
        }

    row = ReportSnapshotRow(
        id=uuid4(),
        report_type=request.report_type,
        scope_type=request.scope_type,
        scope_id=request.scope_id,
        period_start=period_start,
        period_end=period_end,
        filters_json=request.filters.model_dump(mode="json", exclude_none=True),
        generated_at=datetime.utcnow(),
        generated_by=generated_by,
        schema_version="1.0",
        data_snapshot=report_data,
        source_manifest=stored_manifest,
        content_digest=digest,
    )
    db.add(row)
    db.flush()
    db.refresh(row)
    return _snapshot_from_row(row)


def extract_source_manifest(
    report_data: dict[str, Any],
) -> dict[str, list[UUID]] | None:
    """Extract source entity IDs from report data for audit traceability."""
    manifest: dict[str, list[UUID]] = {}

    # Extract AI system IDs
    if "risk_by_ai_system" in report_data:
        manifest["ai_system_ids"] = [
            UUID(item["id"])
            for item in report_data["risk_by_ai_system"]
            if "id" in item
        ]

    # Could extract more source IDs here:
    # - finding_ids
    # - policy_ids
    # - budget_ids
    # - incident_ids
    # etc.

    return manifest if manifest else None


def verify_snapshot_integrity(snapshot: ReportSnapshot) -> bool:
    """Verify snapshot content digest matches stored data."""
    computed_digest = generate_snapshot_digest(snapshot.data_snapshot)
    return computed_digest == snapshot.content_digest


def _snapshot_from_row(row: ReportSnapshotRow) -> ReportSnapshot:
    return ReportSnapshot(
        id=row.id,
        report_type=row.report_type,
        scope_type=row.scope_type,
        scope_id=row.scope_id,
        period_start=row.period_start,
        period_end=row.period_end,
        filters_json=row.filters_json or {},
        generated_at=row.generated_at,
        generated_by=row.generated_by,
        schema_version=row.schema_version,
        data_snapshot=row.data_snapshot or {},
        source_manifest=row.source_manifest,
        content_digest=row.content_digest,
    )


def list_snapshots(
    db: Session,
    filters: dict[str, Any],
) -> list[ReportSnapshot]:
    """List report snapshots with filters."""
    query = db.query(ReportSnapshotRow)
    if filters.get("report_type"):
        query = query.filter(ReportSnapshotRow.report_type == filters["report_type"])
    if filters.get("scope_type"):
        query = query.filter(ReportSnapshotRow.scope_type == filters["scope_type"])
    limit = int(filters.get("limit") or 50)
    offset = int(filters.get("offset") or 0)
    rows = (
        query.order_by(ReportSnapshotRow.generated_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [_snapshot_from_row(row) for row in rows]


def get_snapshot(
    db: Session,
    snapshot_id: UUID,
) -> ReportSnapshot | None:
    """Get a specific report snapshot."""
    row = (
        db.query(ReportSnapshotRow)
        .filter(
            ReportSnapshotRow.id == snapshot_id,
        )
        .first()
    )
    if row is None:
        return None
    return _snapshot_from_row(row)
