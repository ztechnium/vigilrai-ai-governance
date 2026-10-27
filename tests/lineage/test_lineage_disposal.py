"""Derived lineage registration, legal hold, and per-store disposal."""

from __future__ import annotations

import uuid

from rai_gateway.lineage.adapters import InMemoryStoreAdapter, default_adapters
from rai_gateway.lineage.domain import (
    AssetType,
    DerivedAssetStatus,
    DisposalAckStatus,
    DisposalRequestStatus,
    RetentionClass,
    StoreType,
)
from rai_gateway.lineage.service import LineageService
from rai_gateway.models.lineage import DerivedAsset
from rai_gateway.registry.service import RegistryService


def _stack(db_session):
    registry = RegistryService(db_session)
    ds = registry.create_data_source(
        data_source_key=f"ds-lin-{uuid.uuid4().hex[:8]}",
        name="Lineage Source",
        classification="INTERNAL",
        contains_personal_data=True,
    )
    svc = LineageService(db_session)
    version = svc.create_data_source_version(
        ds.id,
        created_by="tester",
        content_digest="sha256:source-v1",
        change_summary="initial ingest",
    )
    return {"registry": registry, "data_source": ds, "svc": svc, "version": version}


def test_register_lineage_chain(db_session):
    stack = _stack(db_session)
    svc = stack["svc"]
    version = stack["version"]

    chunk = svc.register_derived_asset(
        source_version_id=version.id,
        asset_type=AssetType.CHUNK.value,
        store=StoreType.CHUNK_STORE.value,
        locator="chunk://doc-1#0",
        digest="sha256:chunk-0",
        retention_class=RetentionClass.SENSITIVE.value,
    )
    embedding = svc.register_derived_asset(
        source_version_id=version.id,
        asset_type=AssetType.EMBEDDING.value,
        store=StoreType.VECTOR_STORE.value,
        locator="vec://idx/doc-1#0",
        digest="sha256:emb-0",
        parent_asset_id=chunk.id,
    )
    cache = svc.register_derived_asset(
        source_version_id=version.id,
        asset_type=AssetType.CACHE_ENTRY.value,
        store=StoreType.CACHE.value,
        locator="cache://rag/doc-1",
        parent_asset_id=embedding.id,
    )
    memory = svc.register_derived_asset(
        source_version_id=version.id,
        asset_type=AssetType.AGENT_MEMORY.value,
        store=StoreType.AGENT_MEMORY.value,
        locator="memory://agent/session-1",
        parent_asset_id=cache.id,
    )

    lineage = svc.list_lineage(version.id)
    assert len(lineage) == 4
    assert lineage[0].id == chunk.id
    assert lineage[1].parent_asset_id == chunk.id
    assert lineage[3].id == memory.id
    assert all(a.status == DerivedAssetStatus.ACTIVE.value for a in lineage)


def test_disposal_completes_with_per_store_acks(db_session):
    stack = _stack(db_session)
    version = stack["version"]
    adapters = default_adapters()
    svc = LineageService(db_session, adapters=adapters)

    svc.register_derived_asset(
        source_version_id=version.id,
        asset_type=AssetType.EMBEDDING.value,
        store=StoreType.VECTOR_STORE.value,
        locator="vec://ok/1",
        digest="d1",
    )
    svc.register_derived_asset(
        source_version_id=version.id,
        asset_type=AssetType.CACHE_ENTRY.value,
        store=StoreType.CACHE.value,
        locator="cache://ok/1",
    )
    svc.register_derived_asset(
        source_version_id=version.id,
        asset_type=AssetType.AGENT_MEMORY.value,
        store=StoreType.AGENT_MEMORY.value,
        locator="memory://ok/1",
    )

    req = svc.request_disposal(
        version.id, requested_by="tester", reason="source deleted"
    )
    assert req.status == DisposalRequestStatus.COMPLETED.value
    assert req.access_revoked_at is not None
    assert req.backup_expiry_tracked_until is not None
    assert req.evidence["acknowledged"] == 3
    assert req.evidence["failed"] == 0

    serialized = svc.serialize_disposal(req)
    assert len(serialized["acknowledgements"]) == 3
    assert all(
        a["status"] == DisposalAckStatus.ACKNOWLEDGED.value
        for a in serialized["acknowledgements"]
    )
    assert isinstance(adapters[StoreType.VECTOR_STORE.value], InMemoryStoreAdapter)
    assert "vec://ok/1" in adapters[StoreType.VECTOR_STORE.value].deleted

    lineage = svc.list_lineage(version.id)
    assert all(a.status == DerivedAssetStatus.DISPOSED.value for a in lineage)


def test_disposal_blocked_by_legal_hold(db_session):
    stack = _stack(db_session)
    svc = stack["svc"]
    version = stack["version"]
    svc.register_derived_asset(
        source_version_id=version.id,
        asset_type=AssetType.EMBEDDING.value,
        store=StoreType.VECTOR_STORE.value,
        locator="vec://held/1",
    )
    svc.set_version_legal_hold(
        version.id, legal_hold=True, actor="tester", reason="litigation"
    )

    req = svc.request_disposal(version.id, requested_by="tester")
    assert req.status == DisposalRequestStatus.BLOCKED_LEGAL_HOLD.value

    lineage = svc.list_lineage(version.id)
    assert lineage[0].status == DerivedAssetStatus.ACTIVE.value
    assert lineage[0].legal_hold is True


def test_disposal_partial_and_retry(db_session):
    stack = _stack(db_session)
    version = stack["version"]
    adapters = default_adapters()
    svc = LineageService(db_session, adapters=adapters, max_retries=2)

    svc.register_derived_asset(
        source_version_id=version.id,
        asset_type=AssetType.EMBEDDING.value,
        store=StoreType.VECTOR_STORE.value,
        locator="vec://ok/2",
    )
    svc.register_derived_asset(
        source_version_id=version.id,
        asset_type=AssetType.CACHE_ENTRY.value,
        store=StoreType.CACHE.value,
        locator="fail:cache://boom",
    )

    req = svc.request_disposal(version.id, requested_by="tester")
    assert req.status == DisposalRequestStatus.PARTIAL.value
    assert req.evidence["acknowledged"] == 1
    assert req.evidence["failed"] == 1

    # Recover failing asset and swap in a succeeding cache adapter.
    adapters[StoreType.CACHE.value] = InMemoryStoreAdapter(StoreType.CACHE.value)
    failed = (
        db_session.query(DerivedAsset)
        .filter(DerivedAsset.locator == "fail:cache://boom")
        .first()
    )
    failed.locator = "cache://recovered"
    db_session.commit()

    retried = svc.retry_disposal(req.id, actor="tester")
    assert retried.status == DisposalRequestStatus.COMPLETED.value
    assert retried.evidence["failed"] == 0
    assert all(
        a.status == DerivedAssetStatus.DISPOSED.value
        for a in svc.list_lineage(version.id)
    )
