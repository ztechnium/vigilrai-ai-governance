"""Idempotent platform Policy Library seed.
Standard sources are shared across organizations. They are source text and
obligations, not executable RAI rules.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from rai_gateway.models.policy_library import PolicySource, PolicySourceObligation


def _register_model_metadata() -> None:
    """Load every model so foreign keys resolve when the seed flushes."""
    import importlib
    import pkgutil

    import rai_gateway.models as models_pkg

    for module in pkgutil.iter_modules(models_pkg.__path__):
        importlib.import_module(f"rai_gateway.models.{module.name}")


_register_model_metadata()
DEFAULT_SEED_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "policy_seed_catalog.json"
)


@dataclass
class PolicySeedResult:
    sources_created: int = 0
    sources_updated: int = 0
    obligations_created: int = 0
    obligations_updated: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "sources_created": self.sources_created,
            "sources_updated": self.sources_updated,
            "obligations_created": self.obligations_created,
            "obligations_updated": self.obligations_updated,
        }


def load_policy_seed(path: Path | None = None) -> dict[str, Any]:
    seed_path = path or DEFAULT_SEED_PATH
    data = json.loads(seed_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("policies"), list):
        raise ValueError("Policy seed must be an object with a 'policies' array")
    keys: set[str] = set()
    for policy in data["policies"]:
        key = str(policy.get("source_key") or "").strip()
        if not key:
            raise ValueError("Each seeded policy requires source_key")
        if key in keys:
            raise ValueError(f"Duplicate policy source_key: {key}")
        keys.add(key)
        if not str(policy.get("title") or "").strip():
            raise ValueError(f"Policy {key} requires title")
        if not str(policy.get("content_text") or "").strip():
            raise ValueError(f"Policy {key} requires content_text")
    return data


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class PolicyLibrarySeedService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def seed(self, path: Path | None = None) -> PolicySeedResult:
        catalog = load_policy_seed(path)
        result = PolicySeedResult()
        for policy in catalog["policies"]:
            self._upsert(policy, catalog.get("version"), result)
        self._db.commit()
        return result

    def _upsert(
        self,
        policy: dict[str, Any],
        seed_version: str | None,
        result: PolicySeedResult,
    ) -> None:
        source_key = str(policy["source_key"]).strip()
        text = str(policy["content_text"]).strip()
        existing = (
            self._db.query(PolicySource)
            .filter(
                PolicySource.scope == "PLATFORM",
                PolicySource.source_key == source_key,
            )
            .first()
        )
        metadata = {
            "seed_version": seed_version,
            "source_type": "SEEDED_STANDARD",
        }
        if existing:
            existing.title = policy["title"]
            existing.authority = policy.get("authority")
            existing.jurisdiction = policy.get("jurisdiction")
            existing.policy_type = policy.get("policy_type")
            existing.version = policy.get("version")
            existing.content_text = text
            existing.content_digest = _digest(text)
            existing.status = "ACTIVE"
            existing.ingestion_status = "READY"
            existing.crawl_metadata = metadata
            result.sources_updated += 1
            source = existing
        else:
            source = PolicySource(
                scope="PLATFORM",
                source_key=source_key,
                title=policy["title"],
                source_type="MANUAL_TEXT",
                authority=policy.get("authority"),
                jurisdiction=policy.get("jurisdiction"),
                policy_type=policy.get("policy_type"),
                version=policy.get("version"),
                status="ACTIVE",
                content_text=text,
                content_digest=_digest(text),
                ingestion_status="READY",
                crawl_metadata=metadata,
            )
            self._db.add(source)
            result.sources_created += 1
        self._db.flush()
        for obligation in policy.get("obligations") or []:
            section_ref = str(obligation.get("section_ref") or "").strip()
            if not section_ref:
                raise ValueError(f"Policy {source_key} obligation requires section_ref")
            row = (
                self._db.query(PolicySourceObligation)
                .filter(
                    PolicySourceObligation.policy_source_id == source.id,
                    PolicySourceObligation.section_ref == section_ref,
                )
                .first()
            )
            if row:
                row.topic = obligation.get("topic")
                row.text = obligation.get("text")
                row.structured = obligation.get("structured")
                row.status = "published"
                result.obligations_updated += 1
            else:
                self._db.add(
                    PolicySourceObligation(
                        policy_source_id=source.id,
                        section_ref=section_ref,
                        topic=obligation.get("topic"),
                        text=obligation.get("text"),
                        structured=obligation.get("structured"),
                        status="published",
                    )
                )
                result.obligations_created += 1
        self._db.flush()
