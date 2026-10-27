"""Runtime Audit Explorer — bounded, typed search over enforcement + evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.orm import Session

from rai_gateway.core.cursor import decode_time_id_cursor, encode_time_id_cursor
from rai_gateway.evidence.domain import CONTENT_PAYLOAD_FIELDS, EvidenceEventType
from rai_gateway.models.evidence import (
    EvidenceEvent,
    RuntimeConversation,
    RuntimeTrajectory,
)
from rai_gateway.models.identity import AgentRuntimeIdentity
from rai_gateway.models.registry import Agent, AISystem, ToolResource
from rai_gateway.models.runtime_enforcement import RuntimeEnforcementReceipt

RecordType = Literal["ENFORCEMENT", "EXECUTION", "EVIDENCE_EVENT"]
RecordKind = Literal["INPUT", "OUTPUT", "MODEL_REQUEST", "MODEL_RESPONSE"]

_MAX_RANGE = timedelta(days=31)
_DEFAULT_RANGE = timedelta(hours=24)

_RECORD_KIND_TO_EVENT: dict[str, str] = {
    "INPUT": EvidenceEventType.PROMPT_OBSERVED.value,
    "OUTPUT": EvidenceEventType.AGENT_OUTPUT_OBSERVED.value,
    "MODEL_REQUEST": EvidenceEventType.MODEL_REQUEST_OBSERVED.value,
    "MODEL_RESPONSE": EvidenceEventType.MODEL_RESPONSE_OBSERVED.value,
}


@dataclass(frozen=True)
class AuditSearchFilters:
    date_from: datetime
    date_to: datetime
    entity_types: tuple[RecordType, ...] = (
        "ENFORCEMENT",
        "EXECUTION",
        "EVIDENCE_EVENT",
    )
    ai_system_id: UUID | None = None
    agent_id: UUID | None = None
    runtime_identity_id: UUID | None = None
    delegation_id: UUID | None = None
    integration_id: UUID | None = None
    conversation_id: str | None = None
    trajectory_id: UUID | None = None
    tool_id: UUID | None = None
    decision: str | None = None
    execution_status: str | None = None
    assurance: str | None = None
    correlation_id: str | None = None
    receipt_id: UUID | None = None
    event_type: str | None = None
    record_kind: RecordKind | None = None
    principal: str | None = None
    channel: str | None = None
    content_search: str | None = None


class AuditSearchService:
    """Typed audit search with mandatory date bounds and keyset pagination."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def search(
        self,
        *,
        filters: AuditSearchFilters,
        cursor: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        self._validate_range(filters.date_from, filters.date_to)
        page_size = max(1, min(limit, 100))

        cursor_ts: datetime | None = None
        cursor_id: str | None = None
        if cursor:
            cursor_ts, cursor_id = decode_time_id_cursor(cursor)

        rows: list[dict[str, Any]] = []
        types = set(filters.entity_types) or {
            "ENFORCEMENT",
            "EXECUTION",
            "EVIDENCE_EVENT",
        }
        # Content / record-kind filters only apply to evidence observations.
        if filters.content_search or filters.record_kind:
            types = {"EVIDENCE_EVENT"}

        # Fetch slightly more than page_size from each source, merge, then truncate.
        per_source = page_size + 1
        if "ENFORCEMENT" in types or "EXECUTION" in types:
            rows.extend(
                self._search_receipts(
                    filters=filters,
                    record_types=types & {"ENFORCEMENT", "EXECUTION"},
                    cursor_ts=cursor_ts,
                    cursor_id=cursor_id,
                    limit=per_source,
                )
            )
        if "EVIDENCE_EVENT" in types:
            rows.extend(
                self._search_events(
                    filters=filters,
                    cursor_ts=cursor_ts,
                    cursor_id=cursor_id,
                    limit=per_source,
                )
            )

        rows.sort(
            key=lambda r: (r["_sort_at"], r["id"]),
            reverse=True,
        )
        has_more = len(rows) > page_size
        items = rows[:page_size]
        next_cursor = None
        if has_more and items:
            last = items[-1]
            next_cursor = encode_time_id_cursor(
                occurred_at=last["_sort_at"],
                record_id=last["id"],
            )
        for item in items:
            item.pop("_sort_at", None)

        return {
            "items": items,
            "next_cursor": next_cursor,
            "has_more": has_more,
            "limit": page_size,
            "filters": {
                "date_from": filters.date_from.isoformat(),
                "date_to": filters.date_to.isoformat(),
                "entity_types": list(filters.entity_types),
            },
        }

    def _validate_range(self, date_from: datetime, date_to: datetime) -> None:
        if date_to < date_from:
            raise ValueError("date_to must be >= date_from")
        if date_to - date_from > _MAX_RANGE:
            raise ValueError("date range must be at most 31 days")

    def _search_receipts(
        self,
        *,
        filters: AuditSearchFilters,
        record_types: set[str],
        cursor_ts: datetime | None,
        cursor_id: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        query = (
            self._db.query(RuntimeEnforcementReceipt)
            .join(AISystem, RuntimeEnforcementReceipt.ai_system_id == AISystem.id)
            .filter(RuntimeEnforcementReceipt.started_at >= filters.date_from)
            .filter(RuntimeEnforcementReceipt.started_at <= filters.date_to)
        )
        if filters.ai_system_id:
            query = query.filter(
                RuntimeEnforcementReceipt.ai_system_id == filters.ai_system_id
            )
        if filters.agent_id:
            query = query.filter(RuntimeEnforcementReceipt.agent_id == filters.agent_id)
        if filters.runtime_identity_id:
            query = query.filter(
                RuntimeEnforcementReceipt.runtime_identity_id
                == filters.runtime_identity_id
            )
        if filters.delegation_id:
            query = query.filter(
                RuntimeEnforcementReceipt.delegation_id == filters.delegation_id
            )
        if filters.integration_id:
            query = query.filter(
                RuntimeEnforcementReceipt.integration_id == filters.integration_id
            )
        if filters.tool_id:
            query = query.filter(RuntimeEnforcementReceipt.tool_id == filters.tool_id)
        if filters.decision:
            query = query.filter(
                RuntimeEnforcementReceipt.enforcement_decision == filters.decision
            )
        if filters.execution_status:
            query = query.filter(
                RuntimeEnforcementReceipt.execution_status == filters.execution_status
            )
        if filters.correlation_id:
            query = query.filter(
                RuntimeEnforcementReceipt.correlation_id == filters.correlation_id
            )
        if filters.receipt_id:
            query = query.filter(RuntimeEnforcementReceipt.id == filters.receipt_id)
        if filters.conversation_id:
            # client_context JSON path
            query = query.filter(
                RuntimeEnforcementReceipt.client_context["conversation_id"].as_string()
                == filters.conversation_id
            )
        if filters.principal:
            query = query.filter(
                or_(
                    RuntimeEnforcementReceipt.client_context["principal"].as_string()
                    == filters.principal,
                    RuntimeEnforcementReceipt.client_context["user_email"].as_string()
                    == filters.principal,
                )
            )
        if filters.channel:
            query = query.filter(
                RuntimeEnforcementReceipt.client_context["channel"].as_string()
                == filters.channel
            )
        if cursor_ts is not None and cursor_id is not None:
            try:
                cursor_uuid = UUID(cursor_id)
            except ValueError:
                cursor_uuid = None
            if cursor_uuid is not None:
                query = query.filter(
                    (RuntimeEnforcementReceipt.started_at < cursor_ts)
                    | (
                        (RuntimeEnforcementReceipt.started_at == cursor_ts)
                        & (RuntimeEnforcementReceipt.id < cursor_uuid)
                    )
                )
            else:
                query = query.filter(RuntimeEnforcementReceipt.started_at < cursor_ts)

        receipts = (
            query.order_by(
                RuntimeEnforcementReceipt.started_at.desc(),
                RuntimeEnforcementReceipt.id.desc(),
            )
            .limit(limit * 2)
            .all()
        )
        names = self._resolve_names(
            system_ids={r.ai_system_id for r in receipts},
            agent_ids={r.agent_id for r in receipts},
            identity_ids={r.runtime_identity_id for r in receipts},
            tool_ids={r.tool_id for r in receipts if r.tool_id},
        )
        out: list[dict[str, Any]] = []
        for receipt in receipts:
            ctx = (
                receipt.client_context
                if isinstance(receipt.client_context, dict)
                else {}
            )
            conversation = ctx.get("conversation_id")
            principal = ctx.get("principal") or ctx.get("user_email")
            base = {
                "id": str(receipt.id),
                "occurred_at": (
                    receipt.started_at.isoformat() if receipt.started_at else None
                ),
                "conversation_id": conversation,
                "trajectory_id": None,
                "action": self._action_label(receipt, names["tools"]),
                "decision": receipt.enforcement_decision,
                "execution_status": receipt.execution_status,
                "principal": principal,
                "agent_id": str(receipt.agent_id),
                "agent_name": names["agents"].get(receipt.agent_id),
                "ai_system_id": str(receipt.ai_system_id),
                "ai_system_name": names["systems"].get(receipt.ai_system_id),
                "runtime_identity_id": str(receipt.runtime_identity_id),
                "runtime_identity_name": names["identities"].get(
                    receipt.runtime_identity_id
                ),
                "delegation_id": (
                    str(receipt.delegation_id) if receipt.delegation_id else None
                ),
                "correlation_id": receipt.correlation_id,
                "assurance": None,
                "risk": None,
                "_sort_at": receipt.started_at
                or datetime.min.replace(tzinfo=timezone.utc),
            }
            if "ENFORCEMENT" in record_types:
                out.append(
                    {
                        **base,
                        "record_type": "ENFORCEMENT",
                        "status": receipt.enforcement_decision,
                        "detail_reference": f"/runtime/enforcement/{receipt.id}",
                    }
                )
            if "EXECUTION" in record_types and receipt.execution_attempted:
                out.append(
                    {
                        **base,
                        "id": f"exec:{receipt.id}",
                        "record_type": "EXECUTION",
                        "status": receipt.execution_status,
                        "detail_reference": f"/runtime/enforcement/{receipt.id}",
                    }
                )
        return out

    def _search_events(
        self,
        *,
        filters: AuditSearchFilters,
        cursor_ts: datetime | None,
        cursor_id: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        query = (
            self._db.query(EvidenceEvent, RuntimeTrajectory)
            .join(
                RuntimeTrajectory,
                EvidenceEvent.trajectory_id == RuntimeTrajectory.id,
            )
            .join(AISystem, RuntimeTrajectory.ai_system_id == AISystem.id)
            .filter(EvidenceEvent.occurred_at >= filters.date_from)
            .filter(EvidenceEvent.occurred_at <= filters.date_to)
        )
        if filters.ai_system_id:
            query = query.filter(RuntimeTrajectory.ai_system_id == filters.ai_system_id)
        if filters.agent_id:
            query = query.filter(RuntimeTrajectory.agent_id == filters.agent_id)
        if filters.runtime_identity_id:
            query = query.filter(
                RuntimeTrajectory.runtime_identity_id == filters.runtime_identity_id
            )
        if filters.delegation_id:
            query = query.filter(
                RuntimeTrajectory.delegation_id == filters.delegation_id
            )
        if filters.conversation_id:
            query = query.filter(
                RuntimeTrajectory.conversation_id == filters.conversation_id
            )
        if filters.trajectory_id:
            query = query.filter(RuntimeTrajectory.id == filters.trajectory_id)
        if filters.correlation_id:
            query = query.filter(EvidenceEvent.correlation_id == filters.correlation_id)
        if filters.assurance:
            query = query.filter(EvidenceEvent.assurance_level == filters.assurance)
        resolved_event_type = filters.event_type
        if not resolved_event_type and filters.record_kind:
            resolved_event_type = _RECORD_KIND_TO_EVENT.get(filters.record_kind.upper())
        if resolved_event_type:
            query = query.filter(EvidenceEvent.event_type == resolved_event_type)
        if filters.receipt_id:
            query = query.filter(
                EvidenceEvent.source_reference.ilike(f"%{filters.receipt_id}%")
            )
        if filters.principal or filters.channel:
            query = query.outerjoin(
                RuntimeConversation,
                RuntimeTrajectory.runtime_conversation_id == RuntimeConversation.id,
            )
            if filters.principal:
                query = query.filter(
                    RuntimeConversation.principal_reference == filters.principal
                )
            if filters.channel:
                query = query.filter(RuntimeConversation.channel == filters.channel)
        if filters.content_search:
            term = self._escape_like(filters.content_search.strip())
            if term:
                # Match only known content fields — never return raw content in results.
                content_clauses = [
                    EvidenceEvent.payload[key]
                    .as_string()
                    .ilike(f"%{term}%", escape="\\")
                    for key in sorted(CONTENT_PAYLOAD_FIELDS)
                ]
                query = query.filter(or_(*content_clauses))
        if cursor_ts is not None and cursor_id is not None:
            try:
                cursor_uuid = UUID(cursor_id)
            except ValueError:
                cursor_uuid = None
            if cursor_uuid is not None:
                query = query.filter(
                    (EvidenceEvent.occurred_at < cursor_ts)
                    | (
                        (EvidenceEvent.occurred_at == cursor_ts)
                        & (EvidenceEvent.id < cursor_uuid)
                    )
                )
            else:
                query = query.filter(EvidenceEvent.occurred_at < cursor_ts)

        pairs = (
            query.order_by(EvidenceEvent.occurred_at.desc(), EvidenceEvent.id.desc())
            .limit(limit)
            .all()
        )
        names = self._resolve_names(
            system_ids={t.ai_system_id for _, t in pairs},
            agent_ids={t.agent_id for _, t in pairs},
            identity_ids={t.runtime_identity_id for _, t in pairs},
            tool_ids=set(),
        )
        out: list[dict[str, Any]] = []
        for event, trajectory in pairs:
            payload = event.payload if isinstance(event.payload, dict) else {}
            out.append(
                {
                    "id": str(event.id),
                    "record_type": "EVIDENCE_EVENT",
                    "occurred_at": (
                        event.occurred_at.isoformat() if event.occurred_at else None
                    ),
                    "conversation_id": trajectory.conversation_id,
                    "trajectory_id": str(trajectory.id),
                    "action": event.event_type,
                    "decision": payload.get("decision") or payload.get("effect"),
                    "execution_status": None,
                    "status": event.event_type,
                    "principal": None,
                    "agent_id": str(trajectory.agent_id),
                    "agent_name": names["agents"].get(trajectory.agent_id),
                    "ai_system_id": str(trajectory.ai_system_id),
                    "ai_system_name": names["systems"].get(trajectory.ai_system_id),
                    "runtime_identity_id": str(trajectory.runtime_identity_id),
                    "runtime_identity_name": names["identities"].get(
                        trajectory.runtime_identity_id
                    ),
                    "delegation_id": (
                        str(trajectory.delegation_id)
                        if trajectory.delegation_id
                        else None
                    ),
                    "correlation_id": event.correlation_id or trajectory.correlation_id,
                    "assurance": event.assurance_level,
                    "risk": None,
                    # Open trajectory lifecycle (not an isolated prompt detail page).
                    "detail_reference": (
                        f"/runtime/trajectories/{trajectory.id}?event={event.id}"
                    ),
                    "_sort_at": event.occurred_at
                    or datetime.min.replace(tzinfo=timezone.utc),
                }
            )
        return out

    @staticmethod
    def _escape_like(value: str) -> str:
        return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    def _resolve_names(
        self,
        *,
        system_ids: set[UUID],
        agent_ids: set[UUID],
        identity_ids: set[UUID],
        tool_ids: set[UUID],
    ) -> dict[str, dict[UUID, str]]:
        systems: dict[UUID, str] = {}
        if system_ids:
            systems = {
                row.id: row.name
                for row in self._db.query(AISystem)
                .filter(AISystem.id.in_(system_ids))
                .all()
            }
        agents: dict[UUID, str] = {}
        if agent_ids:
            agents = {
                row.id: row.name
                for row in self._db.query(Agent).filter(Agent.id.in_(agent_ids)).all()
            }
        identities: dict[UUID, str] = {}
        if identity_ids:
            identities = {
                row.id: row.name
                for row in self._db.query(AgentRuntimeIdentity)
                .filter(AgentRuntimeIdentity.id.in_(identity_ids))
                .all()
            }
        tools: dict[UUID, str] = {}
        if tool_ids:
            tools = {
                row.id: row.name or row.tool_key
                for row in self._db.query(ToolResource)
                .filter(ToolResource.id.in_(tool_ids))
                .all()
            }
        return {
            "systems": systems,
            "agents": agents,
            "identities": identities,
            "tools": tools,
        }

    def _action_label(
        self, receipt: RuntimeEnforcementReceipt, tools: dict[UUID, str]
    ) -> str | None:
        if receipt.tool_id and receipt.tool_id in tools:
            return tools[receipt.tool_id]
        summary = receipt.action_summary
        if isinstance(summary, dict):
            return (
                summary.get("tool_key")
                or summary.get("tool_name")
                or summary.get("action")
            )
        if isinstance(summary, str) and summary.strip():
            return summary
        return receipt.action_digest[:12] if receipt.action_digest else None


def default_audit_window(*, now: datetime | None = None) -> tuple[datetime, datetime]:
    """Strict default 24h window for Audit Explorer searches."""
    end = now or datetime.now(timezone.utc)
    return end - _DEFAULT_RANGE, end
