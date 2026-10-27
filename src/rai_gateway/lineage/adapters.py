"""Per-store disposal adapters for derived assets.

Adapters delete from their store and return an acknowledgement payload.
They do not promise backup deletion — callers track backup expiry separately.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from rai_gateway.lineage.domain import StoreType
from rai_gateway.models.lineage import DerivedAsset


@dataclass
class DisposalAdapterResult:
    success: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)


class DisposalAdapter(ABC):
    store: str

    @abstractmethod
    def delete(self, asset: DerivedAsset) -> DisposalAdapterResult:
        """Delete or tombstone the asset in this store."""


class InMemoryStoreAdapter(DisposalAdapter):
    """Test/demo adapter: succeeds unless locator starts with ``fail:``."""

    def __init__(self, store: str) -> None:
        self.store = store
        self.deleted: list[str] = []

    def delete(self, asset: DerivedAsset) -> DisposalAdapterResult:
        locator = asset.locator or ""
        if locator.startswith("fail:"):
            return DisposalAdapterResult(
                success=False,
                message=f"{self.store} delete failed for {locator}",
                details={"locator": locator},
            )
        self.deleted.append(locator)
        return DisposalAdapterResult(
            success=True,
            message=f"{self.store} deleted {locator}",
            details={"locator": locator, "store": self.store},
        )


def default_adapters() -> dict[str, DisposalAdapter]:
    """Built-in adapters for each known store type."""
    return {
        StoreType.CHUNK_STORE.value: InMemoryStoreAdapter(StoreType.CHUNK_STORE.value),
        StoreType.VECTOR_STORE.value: InMemoryStoreAdapter(
            StoreType.VECTOR_STORE.value
        ),
        StoreType.CACHE.value: InMemoryStoreAdapter(StoreType.CACHE.value),
        StoreType.AGENT_MEMORY.value: InMemoryStoreAdapter(
            StoreType.AGENT_MEMORY.value
        ),
        StoreType.EVIDENCE.value: InMemoryStoreAdapter(StoreType.EVIDENCE.value),
    }
