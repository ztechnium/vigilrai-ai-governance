"""Derived-data lineage & disposal domain."""

from __future__ import annotations

from enum import StrEnum


class AssetType(StrEnum):
    CHUNK = "CHUNK"
    EMBEDDING = "EMBEDDING"
    VECTOR_INDEX_ENTRY = "VECTOR_INDEX_ENTRY"
    CACHE_ENTRY = "CACHE_ENTRY"
    AGENT_MEMORY = "AGENT_MEMORY"
    EVIDENCE_REF = "EVIDENCE_REF"


class StoreType(StrEnum):
    CHUNK_STORE = "CHUNK_STORE"
    VECTOR_STORE = "VECTOR_STORE"
    CACHE = "CACHE"
    AGENT_MEMORY = "AGENT_MEMORY"
    EVIDENCE = "EVIDENCE"


class RetentionClass(StrEnum):
    STANDARD = "STANDARD"
    SENSITIVE = "SENSITIVE"
    REGULATED = "REGULATED"
    EPHEMERAL = "EPHEMERAL"


class DerivedAssetStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ACCESS_REVOKED = "ACCESS_REVOKED"
    DISPOSED = "DISPOSED"
    DISPOSAL_FAILED = "DISPOSAL_FAILED"


class DisposalRequestStatus(StrEnum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    BLOCKED_LEGAL_HOLD = "BLOCKED_LEGAL_HOLD"


class DisposalAckStatus(StrEnum):
    ACKNOWLEDGED = "ACKNOWLEDGED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    SKIPPED = "SKIPPED"
