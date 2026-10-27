"""Policy Library service — source ingestion and listing (not runtime rules)."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from rai_gateway.models.policy_library import (
    PolicyRuleLink,
    PolicySource,
    PolicySourceObligation,
)

_DEFAULT_LIMIT = 50
_MAX_LIMIT = 200
_VALID_SOURCE_TYPES = {"FILE", "URL", "MANUAL_TEXT"}


class PolicyLibraryError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: int = 400,
        error_code: str = "POLICY_LIBRARY_ERROR",
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code


def _clamp_limit(limit: int | None) -> int:
    if limit is None:
        return _DEFAULT_LIMIT
    return max(1, min(int(limit), _MAX_LIMIT))


def _digest(text: str | None) -> str | None:
    if not text:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class PolicyLibraryService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def list_sources(
        self,
        *,
        search: str | None = None,
        source_type: str | None = None,
        authority: str | None = None,
        jurisdiction: str | None = None,
        policy_type: str | None = None,
        status: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> dict[str, Any]:
        page_limit = _clamp_limit(limit)
        page_offset = max(0, int(offset or 0))
        q = self._db.query(PolicySource)
        if source_type:
            q = q.filter(PolicySource.source_type == source_type.upper())
        if authority:
            q = q.filter(PolicySource.authority.ilike(authority))
        if jurisdiction:
            q = q.filter(PolicySource.jurisdiction.ilike(jurisdiction))
        if policy_type:
            q = q.filter(PolicySource.policy_type.ilike(policy_type))
        if status:
            q = q.filter(PolicySource.status == status.upper())
        if search:
            like = f"%{search.strip()}%"
            q = q.filter(
                or_(
                    PolicySource.title.ilike(like),
                    PolicySource.authority.ilike(like),
                    PolicySource.jurisdiction.ilike(like),
                    PolicySource.policy_type.ilike(like),
                )
            )
        total = q.count()
        rows = (
            q.order_by(PolicySource.updated_at.desc())
            .offset(page_offset)
            .limit(page_limit)
            .all()
        )
        source_ids = [r.id for r in rows]
        obligation_counts: dict[UUID, int] = {}
        rule_counts: dict[UUID, int] = {}
        if source_ids:
            for sid, count in (
                self._db.query(
                    PolicySourceObligation.policy_source_id,
                    func.count(PolicySourceObligation.id),
                )
                .filter(PolicySourceObligation.policy_source_id.in_(source_ids))
                .group_by(PolicySourceObligation.policy_source_id)
                .all()
            ):
                obligation_counts[sid] = int(count)
            for sid, count in (
                self._db.query(
                    PolicyRuleLink.policy_source_id, func.count(PolicyRuleLink.id)
                )
                .filter(PolicyRuleLink.policy_source_id.in_(source_ids))
                .group_by(PolicyRuleLink.policy_source_id)
                .all()
            ):
                rule_counts[sid] = int(count)
        return {
            "items": [
                {
                    **self._serialize_source(r, include_content=False),
                    "obligation_count": obligation_counts.get(r.id, 0),
                    "derived_rule_count": rule_counts.get(r.id, 0),
                }
                for r in rows
            ],
            "total": total,
            "limit": page_limit,
            "offset": page_offset,
        }

    def get_source(self, source_id: UUID) -> dict[str, Any]:
        source = self._get(source_id)
        obligations = (
            self._db.query(PolicySourceObligation)
            .filter(PolicySourceObligation.policy_source_id == source.id)
            .order_by(PolicySourceObligation.created_at.asc())
            .all()
        )
        links = (
            self._db.query(PolicyRuleLink)
            .filter(PolicyRuleLink.policy_source_id == source.id)
            .all()
        )
        return {
            **self._serialize_source(source, include_content=True),
            "obligations": [self._serialize_obligation(o) for o in obligations],
            "derived_rules": [
                {
                    "id": str(link.id),
                    "rule_type": link.rule_type,
                    "rule_id": str(link.rule_id),
                    "obligation_id": (
                        str(link.obligation_id) if link.obligation_id else None
                    ),
                    "relationship_type": link.relationship_type,
                }
                for link in links
            ],
        }

    def create_source(
        self,
        *,
        title: str,
        source_type: str,
        authority: str | None = None,
        owner: str | None = None,
        jurisdiction: str | None = None,
        policy_type: str | None = None,
        version: str | None = None,
        effective_date: datetime | str | None = None,
        source_uri: str | None = None,
        content_text: str | None = None,
        content_ref: str | None = None,
        crawl_metadata: dict[str, Any] | None = None,
        actor: str | None = None,
    ) -> dict[str, Any]:
        st = source_type.strip().upper()
        if st not in _VALID_SOURCE_TYPES:
            raise PolicyLibraryError(
                f"Invalid source_type: {source_type}. Expected FILE, URL, or MANUAL_TEXT"
            )
        if not title or not title.strip():
            raise PolicyLibraryError("title is required")
        if st == "URL" and not source_uri:
            raise PolicyLibraryError("source_uri is required for URL sources")
        if st == "MANUAL_TEXT" and not (content_text or "").strip():
            raise PolicyLibraryError("content_text is required for MANUAL_TEXT sources")
        parsed_effective = self._parse_date(effective_date)
        text = content_text
        digest = _digest(text) if text else _digest(source_uri or content_ref or title)
        # Website ingestion stores URL + metadata; full crawl is async later.
        ingestion_status = "READY"
        if st == "URL":
            ingestion_status = "READY"
            crawl_metadata = {
                **(crawl_metadata or {}),
                "source_url": source_uri,
                "retrieved_at": datetime.utcnow().isoformat() + "Z",
                "crawl_scope": (crawl_metadata or {}).get("crawl_scope", "SINGLE_URL"),
            }
        source = PolicySource(
            scope="ORGANIZATION",
            title=title.strip(),
            source_type=st,
            authority=authority,
            owner=owner,
            jurisdiction=jurisdiction,
            policy_type=policy_type,
            version=version,
            effective_date=parsed_effective,
            status="ACTIVE",
            source_uri=source_uri or content_ref,
            content_digest=digest,
            content_text=text,
            ingestion_status=ingestion_status,
            crawl_metadata=crawl_metadata,
        )
        self._db.add(source)
        self._db.flush()
        # Manual text: create a single reviewable obligation stub from the body.
        if st == "MANUAL_TEXT" and text:
            self._db.add(
                PolicySourceObligation(
                    policy_source_id=source.id,
                    section_ref="body",
                    topic="manual",
                    text=text[:4000],
                    status="draft",
                )
            )
        self._db.commit()
        self._db.refresh(source)
        return self._serialize_source(source, include_content=True)

    def link_rule(
        self,
        *,
        policy_source_id: UUID,
        rule_type: str,
        rule_id: UUID,
        obligation_id: UUID | None = None,
        relationship_type: str = "DERIVED_FROM",
    ) -> dict[str, Any]:
        source = self._get(policy_source_id)
        rt = rule_type.strip().upper()
        if rt not in ("CONTENT", "TOOL"):
            raise PolicyLibraryError(f"Invalid rule_type: {rule_type}")
        if obligation_id is not None:
            obl = (
                self._db.query(PolicySourceObligation)
                .filter(
                    PolicySourceObligation.id == obligation_id,
                    PolicySourceObligation.policy_source_id == source.id,
                )
                .first()
            )
            if not obl:
                raise PolicyLibraryError(
                    "Obligation not found for this policy source",
                    status_code=404,
                    error_code="OBLIGATION_NOT_FOUND",
                )
        existing = (
            self._db.query(PolicyRuleLink)
            .filter(
                PolicyRuleLink.policy_source_id == source.id,
                PolicyRuleLink.rule_type == rt,
                PolicyRuleLink.rule_id == rule_id,
            )
            .first()
        )
        if existing:
            return {
                "id": str(existing.id),
                "policy_source_id": str(source.id),
                "rule_type": existing.rule_type,
                "rule_id": str(existing.rule_id),
                "obligation_id": (
                    str(existing.obligation_id) if existing.obligation_id else None
                ),
                "relationship_type": existing.relationship_type,
            }
        link = PolicyRuleLink(
            policy_source_id=source.id,
            obligation_id=obligation_id,
            rule_type=rt,
            rule_id=rule_id,
            relationship_type=relationship_type,
        )
        self._db.add(link)
        self._db.commit()
        self._db.refresh(link)
        return {
            "id": str(link.id),
            "policy_source_id": str(source.id),
            "rule_type": link.rule_type,
            "rule_id": str(link.rule_id),
            "obligation_id": str(link.obligation_id) if link.obligation_id else None,
            "relationship_type": link.relationship_type,
        }

    def _get(self, source_id: UUID) -> PolicySource:
        source = (
            self._db.query(PolicySource).filter(PolicySource.id == source_id).first()
        )
        if not source:
            raise PolicyLibraryError(
                "Policy source not found",
                status_code=404,
                error_code="POLICY_SOURCE_NOT_FOUND",
            )
        return source

    def _parse_date(self, value: datetime | str | None) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        text = str(value).strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise PolicyLibraryError(f"Invalid effective_date: {value}") from exc

    def _serialize_source(
        self, source: PolicySource, *, include_content: bool
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": str(source.id),
            "scope": source.scope or "ORGANIZATION",
            "source_key": source.source_key,
            "title": source.title,
            "source_type": source.source_type,
            "authority": source.authority,
            "owner": source.owner,
            "jurisdiction": source.jurisdiction,
            "policy_type": source.policy_type,
            "version": source.version,
            "effective_date": (
                source.effective_date.isoformat() if source.effective_date else None
            ),
            "status": source.status,
            "source_uri": source.source_uri,
            "content_digest": source.content_digest,
            "ingestion_status": source.ingestion_status,
            "crawl_metadata": source.crawl_metadata,
            "legacy_doc_id": source.legacy_doc_id,
            "created_at": source.created_at.isoformat() if source.created_at else None,
            "updated_at": source.updated_at.isoformat() if source.updated_at else None,
        }
        if include_content:
            payload["content_text"] = source.content_text
        return payload

    def _serialize_obligation(self, o: PolicySourceObligation) -> dict[str, Any]:
        return {
            "id": str(o.id),
            "policy_source_id": str(o.policy_source_id),
            "section_ref": o.section_ref,
            "topic": o.topic,
            "scope": o.scope,
            "constraint_action": o.constraint_action,
            "text": o.text,
            "status": o.status,
            "structured": o.structured,
            "created_at": o.created_at.isoformat() if o.created_at else None,
        }
