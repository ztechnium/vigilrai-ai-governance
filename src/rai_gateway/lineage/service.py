"""Derived-data lineage registration and disposal workflow."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from rai_gateway.core.observability import generate_trace_id, log_admin_audit
from rai_gateway.lineage.adapters import DisposalAdapter, default_adapters
from rai_gateway.lineage.domain import (
    AssetType,
    DerivedAssetStatus,
    DisposalAckStatus,
    DisposalRequestStatus,
    RetentionClass,
    StoreType,
)
from rai_gateway.models.lineage import (
    DataSourceVersion,
    DerivedAsset,
    DisposalAcknowledgement,
    DisposalRequest,
)
from rai_gateway.models.registry import DataSource

DEFAULT_BACKUP_EXPIRY_DAYS = 30
DEFAULT_MAX_RETRIES = 3


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class LineageError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class LineageService:
    """Track DataSourceVersion → derived assets and dispose per store."""

    def __init__(
        self,
        db: Session,
        *,
        adapters: dict[str, DisposalAdapter] | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backup_expiry_days: int = DEFAULT_BACKUP_EXPIRY_DAYS,
    ) -> None:
        self._db = db
        self._adapters = adapters or default_adapters()
        self._max_retries = max_retries
        self._backup_expiry_days = backup_expiry_days

    # ------------------------------------------------------------------
    # Data source versions (lineage root)
    # ------------------------------------------------------------------

    def create_data_source_version(
        self,
        data_source_id: UUID,
        *,
        created_by: str,
        content_digest: str | None = None,
        change_summary: str | None = None,
    ) -> DataSourceVersion:
        ds = self._db.query(DataSource).filter(DataSource.id == data_source_id).first()
        if not ds:
            raise LineageError("NOT_FOUND", "Data source not found")
        max_n = (
            self._db.query(func.max(DataSourceVersion.version_number))
            .filter(DataSourceVersion.data_source_id == data_source_id)
            .scalar()
        )
        version = DataSourceVersion(
            data_source_id=data_source_id,
            version_number=(max_n or 0) + 1,
            content_digest=content_digest,
            change_summary=change_summary,
            status="ACTIVE",
            created_by=created_by,
        )
        self._db.add(version)
        self._db.commit()
        self._db.refresh(version)
        return version

    def get_data_source_version(self, version_id: UUID) -> DataSourceVersion:
        row = (
            self._db.query(DataSourceVersion)
            .filter(DataSourceVersion.id == version_id)
            .first()
        )
        if not row:
            raise LineageError("NOT_FOUND", "Data source version not found")
        return row

    def set_version_legal_hold(
        self,
        version_id: UUID,
        *,
        legal_hold: bool,
        actor: str,
        reason: str | None = None,
        cascade_assets: bool = True,
    ) -> DataSourceVersion:
        version = self.get_data_source_version(version_id)
        version.legal_hold = legal_hold
        if cascade_assets:
            assets = (
                self._db.query(DerivedAsset)
                .filter(DerivedAsset.source_version_id == version_id)
                .all()
            )
            for asset in assets:
                asset.legal_hold = legal_hold
        self._db.commit()
        self._db.refresh(version)
        log_admin_audit(
            trace_id=generate_trace_id(),
            actor_user_id=actor,
            actor_role="admin",
            action=(
                "lineage.legal_hold.applied"
                if legal_hold
                else "lineage.legal_hold.released"
            ),
            target={"source_version_id": str(version_id)},
            reason=reason,
        )
        return version

    # ------------------------------------------------------------------
    # Derived assets
    # ------------------------------------------------------------------

    def register_derived_asset(
        self,
        *,
        source_version_id: UUID,
        asset_type: str,
        store: str,
        locator: str,
        digest: str | None = None,
        retention_class: str = RetentionClass.STANDARD.value,
        parent_asset_id: UUID | None = None,
        ai_system_id: UUID | None = None,
        agent_version_id: UUID | None = None,
        evidence_ref: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DerivedAsset:
        version = self.get_data_source_version(source_version_id)
        if asset_type not in {t.value for t in AssetType}:
            raise LineageError("INVALID_REQUEST", f"Unknown asset_type: {asset_type}")
        if store not in {s.value for s in StoreType}:
            raise LineageError("INVALID_REQUEST", f"Unknown store: {store}")
        if parent_asset_id:
            parent = (
                self._db.query(DerivedAsset)
                .filter(DerivedAsset.id == parent_asset_id)
                .first()
            )
            if not parent:
                raise LineageError("NOT_FOUND", "Parent derived asset not found")
            if parent.source_version_id != source_version_id:
                raise LineageError(
                    "INVALID_REQUEST",
                    "Parent asset must belong to the same source version",
                )

        asset = DerivedAsset(
            source_version_id=source_version_id,
            parent_asset_id=parent_asset_id,
            asset_type=asset_type,
            store=store,
            locator=locator,
            digest=digest,
            retention_class=retention_class,
            status=DerivedAssetStatus.ACTIVE.value,
            legal_hold=bool(version.legal_hold),
            ai_system_id=ai_system_id,
            agent_version_id=agent_version_id,
            evidence_ref=evidence_ref,
            metadata_=metadata,
        )
        self._db.add(asset)
        self._db.commit()
        self._db.refresh(asset)
        return asset

    def list_lineage(
        self,
        source_version_id: UUID,
        *,
        include_disposed: bool = True,
    ) -> list[DerivedAsset]:
        self.get_data_source_version(source_version_id)
        q = self._db.query(DerivedAsset).filter(
            DerivedAsset.source_version_id == source_version_id
        )
        if not include_disposed:
            q = q.filter(DerivedAsset.status != DerivedAssetStatus.DISPOSED.value)
        return q.order_by(DerivedAsset.created_at.asc()).all()

    def set_asset_legal_hold(
        self,
        asset_id: UUID,
        *,
        legal_hold: bool,
        actor: str,
        reason: str | None = None,
    ) -> DerivedAsset:
        asset = self._db.query(DerivedAsset).filter(DerivedAsset.id == asset_id).first()
        if not asset:
            raise LineageError("NOT_FOUND", "Derived asset not found")
        asset.legal_hold = legal_hold
        self._db.commit()
        self._db.refresh(asset)
        log_admin_audit(
            trace_id=generate_trace_id(),
            actor_user_id=actor,
            actor_role="admin",
            action=(
                "lineage.asset.legal_hold.applied"
                if legal_hold
                else "lineage.asset.legal_hold.released"
            ),
            target={"derived_asset_id": str(asset_id)},
            reason=reason,
        )
        return asset

    # ------------------------------------------------------------------
    # Disposal workflow
    # ------------------------------------------------------------------

    def request_disposal(
        self,
        source_version_id: UUID,
        *,
        requested_by: str,
        reason: str | None = None,
        execute: bool = True,
        max_retries: int | None = None,
    ) -> DisposalRequest:
        """Request disposal of all active derivatives for a source version.

        Workflow:
          legal-hold check → revoke access → delete per store →
          retry failures → per-store acknowledgement → disposal evidence

        Does not promise immediate deletion from backups; tracks
        ``backup_expiry_tracked_until`` separately.
        """
        version = self.get_data_source_version(source_version_id)
        assets = (
            self._db.query(DerivedAsset)
            .filter(
                DerivedAsset.source_version_id == source_version_id,
                DerivedAsset.status.in_(
                    [
                        DerivedAssetStatus.ACTIVE.value,
                        DerivedAssetStatus.ACCESS_REVOKED.value,
                        DerivedAssetStatus.DISPOSAL_FAILED.value,
                    ]
                ),
            )
            .all()
        )

        if version.legal_hold or any(a.legal_hold for a in assets):
            req = DisposalRequest(
                source_version_id=source_version_id,
                status=DisposalRequestStatus.BLOCKED_LEGAL_HOLD.value,
                requested_by=requested_by,
                reason=reason,
                evidence={
                    "blocked": True,
                    "legal_hold_version": bool(version.legal_hold),
                    "legal_hold_assets": [str(a.id) for a in assets if a.legal_hold],
                },
                backup_expiry_tracked_until=_utcnow()
                + timedelta(days=self._backup_expiry_days),
            )
            self._db.add(req)
            self._db.commit()
            self._db.refresh(req)
            log_admin_audit(
                trace_id=generate_trace_id(),
                actor_user_id=requested_by,
                actor_role="admin",
                action="lineage.disposal.blocked_legal_hold",
                target={
                    "disposal_request_id": str(req.id),
                    "source_version_id": str(source_version_id),
                },
                reason=reason,
            )
            return req

        req = DisposalRequest(
            source_version_id=source_version_id,
            status=DisposalRequestStatus.IN_PROGRESS.value,
            requested_by=requested_by,
            reason=reason,
            backup_expiry_tracked_until=_utcnow()
            + timedelta(days=self._backup_expiry_days),
        )
        self._db.add(req)
        self._db.flush()

        # Revoke access before store deletion.
        now = _utcnow()
        for asset in assets:
            asset.status = DerivedAssetStatus.ACCESS_REVOKED.value
        req.access_revoked_at = now
        self._db.flush()

        log_admin_audit(
            trace_id=generate_trace_id(),
            actor_user_id=requested_by,
            actor_role="admin",
            action="lineage.disposal.access_revoked",
            target={
                "disposal_request_id": str(req.id),
                "source_version_id": str(source_version_id),
                "asset_count": len(assets),
            },
            reason=reason,
        )

        if execute:
            self._execute_disposals(req, assets, max_retries=max_retries)
        else:
            self._db.commit()
            self._db.refresh(req)
        return req

    def retry_disposal(
        self,
        disposal_request_id: UUID,
        *,
        actor: str,
        max_retries: int | None = None,
    ) -> DisposalRequest:
        req = (
            self._db.query(DisposalRequest)
            .filter(DisposalRequest.id == disposal_request_id)
            .first()
        )
        if not req:
            raise LineageError("NOT_FOUND", "Disposal request not found")
        if req.status == DisposalRequestStatus.BLOCKED_LEGAL_HOLD.value:
            raise LineageError(
                "LEGAL_HOLD_ACTIVE", "Cannot retry disposal under legal hold"
            )
        if req.status == DisposalRequestStatus.COMPLETED.value:
            return req

        failed_acks = (
            self._db.query(DisposalAcknowledgement)
            .filter(
                DisposalAcknowledgement.disposal_request_id == req.id,
                DisposalAcknowledgement.status.in_(
                    [DisposalAckStatus.FAILED.value, DisposalAckStatus.RETRYING.value]
                ),
            )
            .all()
        )
        asset_ids = {a.derived_asset_id for a in failed_acks}
        assets = (
            self._db.query(DerivedAsset).filter(DerivedAsset.id.in_(asset_ids)).all()
            if asset_ids
            else []
        )
        # Also pick up revoked assets with no ack yet.
        pending = (
            self._db.query(DerivedAsset)
            .filter(
                DerivedAsset.source_version_id == req.source_version_id,
                DerivedAsset.status.in_(
                    [
                        DerivedAssetStatus.ACCESS_REVOKED.value,
                        DerivedAssetStatus.DISPOSAL_FAILED.value,
                    ]
                ),
            )
            .all()
        )
        by_id = {a.id: a for a in assets}
        for a in pending:
            by_id[a.id] = a

        req.status = DisposalRequestStatus.IN_PROGRESS.value
        self._db.flush()
        log_admin_audit(
            trace_id=generate_trace_id(),
            actor_user_id=actor,
            actor_role="admin",
            action="lineage.disposal.retry",
            target={"disposal_request_id": str(req.id)},
        )
        self._execute_disposals(req, list(by_id.values()), max_retries=max_retries)
        return req

    def _execute_disposals(
        self,
        req: DisposalRequest,
        assets: list[DerivedAsset],
        *,
        max_retries: int | None = None,
    ) -> None:
        retries = max_retries if max_retries is not None else self._max_retries
        acks: list[DisposalAcknowledgement] = []

        for asset in assets:
            existing = (
                self._db.query(DisposalAcknowledgement)
                .filter(
                    DisposalAcknowledgement.disposal_request_id == req.id,
                    DisposalAcknowledgement.derived_asset_id == asset.id,
                )
                .first()
            )
            ack = existing or DisposalAcknowledgement(
                disposal_request_id=req.id,
                derived_asset_id=asset.id,
                store=asset.store,
                status=DisposalAckStatus.RETRYING.value,
                attempts=0,
            )
            if not existing:
                self._db.add(ack)
                self._db.flush()

            adapter = self._adapters.get(asset.store)
            if not adapter:
                ack.status = DisposalAckStatus.FAILED.value
                ack.error_message = f"No disposal adapter for store {asset.store}"
                ack.attempts += 1
                asset.status = DerivedAssetStatus.DISPOSAL_FAILED.value
                acks.append(ack)
                continue

            success = False
            last_error: str | None = None
            last_details: dict[str, Any] = {}
            for _ in range(max(1, retries)):
                ack.attempts += 1
                result = adapter.delete(asset)
                last_details = result.details or {}
                if result.success:
                    success = True
                    ack.status = DisposalAckStatus.ACKNOWLEDGED.value
                    ack.error_message = None
                    ack.adapter_response = {
                        "message": result.message,
                        **last_details,
                    }
                    ack.acknowledged_at = _utcnow()
                    asset.status = DerivedAssetStatus.DISPOSED.value
                    asset.disposed_at = _utcnow()
                    break
                last_error = result.message
                ack.status = DisposalAckStatus.RETRYING.value
                ack.error_message = last_error
                ack.adapter_response = {"message": last_error, **last_details}

            if not success:
                ack.status = DisposalAckStatus.FAILED.value
                ack.error_message = last_error or "Disposal failed"
                asset.status = DerivedAssetStatus.DISPOSAL_FAILED.value
            acks.append(ack)

        acknowledged = sum(
            1 for a in acks if a.status == DisposalAckStatus.ACKNOWLEDGED.value
        )
        failed = sum(1 for a in acks if a.status == DisposalAckStatus.FAILED.value)
        if failed == 0 and (acknowledged > 0 or not assets):
            req.status = DisposalRequestStatus.COMPLETED.value
        elif acknowledged > 0 and failed > 0:
            req.status = DisposalRequestStatus.PARTIAL.value
        elif failed > 0:
            req.status = DisposalRequestStatus.FAILED.value
        else:
            req.status = DisposalRequestStatus.COMPLETED.value

        if req.status in (
            DisposalRequestStatus.COMPLETED.value,
            DisposalRequestStatus.PARTIAL.value,
            DisposalRequestStatus.FAILED.value,
        ):
            req.completed_at = _utcnow()

        req.evidence = {
            "asset_count": len(assets),
            "acknowledged": acknowledged,
            "failed": failed,
            "stores": sorted({a.store for a in assets}),
            "backup_note": (
                "Immediate deletion from backups is not promised; "
                "backup_expiry_tracked_until records expected backup retention."
            ),
            "acknowledgements": [
                {
                    "derived_asset_id": str(a.derived_asset_id),
                    "store": a.store,
                    "status": a.status,
                    "attempts": a.attempts,
                    "error_message": a.error_message,
                }
                for a in acks
            ],
        }
        self._db.commit()
        self._db.refresh(req)
        log_admin_audit(
            trace_id=generate_trace_id(),
            actor_user_id=req.requested_by,
            actor_role="admin",
            action="lineage.disposal.completed",
            target={
                "disposal_request_id": str(req.id),
                "status": req.status,
                "acknowledged": acknowledged,
                "failed": failed,
            },
        )

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def serialize_version(self, row: DataSourceVersion) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "data_source_id": str(row.data_source_id),
            "version_number": row.version_number,
            "content_digest": row.content_digest,
            "change_summary": row.change_summary,
            "status": row.status,
            "legal_hold": row.legal_hold,
            "created_by": row.created_by,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "retired_at": row.retired_at.isoformat() if row.retired_at else None,
        }

    def serialize_asset(self, row: DerivedAsset) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "derived_asset_id": str(row.id),
            "source_version_id": str(row.source_version_id),
            "parent_asset_id": str(row.parent_asset_id)
            if row.parent_asset_id
            else None,
            "asset_type": row.asset_type,
            "store": row.store,
            "locator": row.locator,
            "digest": row.digest,
            "retention_class": row.retention_class,
            "status": row.status,
            "legal_hold": row.legal_hold,
            "ai_system_id": str(row.ai_system_id) if row.ai_system_id else None,
            "agent_version_id": str(row.agent_version_id)
            if row.agent_version_id
            else None,
            "evidence_ref": row.evidence_ref,
            "metadata": row.metadata_ or {},
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "disposed_at": row.disposed_at.isoformat() if row.disposed_at else None,
        }

    def serialize_disposal(self, row: DisposalRequest) -> dict[str, Any]:
        acks = (
            self._db.query(DisposalAcknowledgement)
            .filter(DisposalAcknowledgement.disposal_request_id == row.id)
            .all()
        )
        return {
            "id": str(row.id),
            "source_version_id": str(row.source_version_id),
            "status": row.status,
            "requested_by": row.requested_by,
            "reason": row.reason,
            "access_revoked_at": row.access_revoked_at.isoformat()
            if row.access_revoked_at
            else None,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
            "backup_expiry_tracked_until": row.backup_expiry_tracked_until.isoformat()
            if row.backup_expiry_tracked_until
            else None,
            "evidence": row.evidence or {},
            "acknowledgements": [
                {
                    "id": str(a.id),
                    "derived_asset_id": str(a.derived_asset_id),
                    "store": a.store,
                    "status": a.status,
                    "attempts": a.attempts,
                    "error_message": a.error_message,
                    "adapter_response": a.adapter_response,
                    "acknowledged_at": a.acknowledged_at.isoformat()
                    if a.acknowledged_at
                    else None,
                }
                for a in acks
            ],
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
