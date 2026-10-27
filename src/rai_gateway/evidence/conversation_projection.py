"""Runtime conversation projection — durable read model for conversation lists."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from rai_gateway.core.cursor import decode_time_id_cursor, encode_time_id_cursor
from rai_gateway.evidence.domain import AssuranceLevel, FindingSeverity
from rai_gateway.models.evidence import (
    EvidenceFinding,
    RuntimeConversation,
    RuntimeTrajectory,
)

logger = logging.getLogger(__name__)

_SEVERITY_RANK = {
    FindingSeverity.CRITICAL.value: 5,
    FindingSeverity.HIGH.value: 4,
    FindingSeverity.MEDIUM.value: 3,
    FindingSeverity.LOW.value: 2,
    FindingSeverity.INFO.value: 1,
}

_ASSURANCE_RANK = {
    AssuranceLevel.HIGH.value: 4,
    AssuranceLevel.MEDIUM.value: 3,
    AssuranceLevel.LOW.value: 2,
    AssuranceLevel.UNKNOWN.value: 1,
}


def build_conversation_key(
    *,
    client_integration_id: UUID | None,
    external_conversation_id: str,
) -> str:
    """Deterministic scoped conversation key (never a trajectory key)."""
    cid = str(client_integration_id) if client_integration_id else "_"
    return f"{cid}|{external_conversation_id}"


def encode_cursor(*, last_activity_at: datetime, conversation_id: UUID) -> str:
    return encode_time_id_cursor(
        occurred_at=last_activity_at, record_id=conversation_id
    )


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    ts, id_text = decode_time_id_cursor(cursor)
    return ts, UUID(id_text)


class ConversationProjectionService:
    """Upsert and query RuntimeConversation without blocking authorization paths."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def project_trajectory(
        self, trajectory: RuntimeTrajectory
    ) -> RuntimeConversation | None:
        """Best-effort upsert of the conversation projection for a trajectory.

        Returns None when the trajectory has no external conversation id (nothing
        to project). Failures are logged and swallowed so runtime auth is unaffected.
        """
        try:
            return self._project_trajectory(trajectory)
        except Exception:
            logger.exception(
                "conversation projection failed for trajectory %s",
                trajectory.id,
            )
            return None

    def _project_trajectory(
        self, trajectory: RuntimeTrajectory
    ) -> RuntimeConversation | None:
        external = (trajectory.conversation_id or "").strip()
        if not external:
            return None

        key = build_conversation_key(
            client_integration_id=trajectory.client_integration_id,
            external_conversation_id=external,
        )
        conversation = (
            self._db.query(RuntimeConversation)
            .filter(
                RuntimeConversation.conversation_key == key,
            )
            .first()
        )
        now = datetime.now(timezone.utc)
        activity = trajectory.last_event_at or trajectory.started_at or now

        if conversation is None:
            conversation = RuntimeConversation(
                conversation_key=key,
                external_conversation_id=external,
                client_integration_id=trajectory.client_integration_id,
                runtime_identity_id=trajectory.runtime_identity_id,
                ai_system_id=trajectory.ai_system_id,
                primary_agent_id=trajectory.agent_id,
                started_at=trajectory.started_at or activity,
                last_activity_at=activity,
                status=self._conversation_status([trajectory]),
                trajectory_count=0,
                event_count=0,
                action_count=0,
                finding_count=0,
                last_trajectory_id=trajectory.id,
            )
            self._db.add(conversation)
            self._db.flush()

        if trajectory.runtime_conversation_id != conversation.id:
            trajectory.runtime_conversation_id = conversation.id

        self._db.flush()
        self._recalculate(conversation)
        self._db.flush()
        return conversation

    def _recalculate(self, conversation: RuntimeConversation) -> None:
        trajectories = (
            self._db.query(RuntimeTrajectory)
            .filter(RuntimeTrajectory.runtime_conversation_id == conversation.id)
            .order_by(RuntimeTrajectory.last_event_at.desc())
            .all()
        )
        # Also include rows that share the external id but not yet linked.
        if not trajectories:
            trajectories = (
                self._db.query(RuntimeTrajectory)
                .filter(
                    RuntimeTrajectory.conversation_id
                    == conversation.external_conversation_id,
                    RuntimeTrajectory.ai_system_id == conversation.ai_system_id,
                )
                .order_by(RuntimeTrajectory.last_event_at.desc())
                .all()
            )
            for row in trajectories:
                row.runtime_conversation_id = conversation.id

        conversation.trajectory_count = len(trajectories)
        conversation.event_count = sum(int(t.event_count or 0) for t in trajectories)
        conversation.finding_count = sum(
            int(t.finding_count or 0) for t in trajectories
        )
        conversation.action_count = self._count_actions(trajectories)
        conversation.status = self._conversation_status(trajectories)
        conversation.highest_risk_level = self._highest_risk(trajectories)
        conversation.highest_assurance_level = self._highest_assurance(trajectories)

        if trajectories:
            latest = trajectories[0]
            conversation.last_trajectory_id = latest.id
            conversation.last_activity_at = (
                latest.last_event_at
                or latest.started_at
                or conversation.last_activity_at
            )
            if latest.runtime_identity_id:
                conversation.runtime_identity_id = latest.runtime_identity_id
            if latest.agent_id:
                conversation.primary_agent_id = latest.agent_id
            if latest.client_integration_id and not conversation.client_integration_id:
                conversation.client_integration_id = latest.client_integration_id
            started = min(
                (t.started_at for t in trajectories if t.started_at),
                default=conversation.started_at,
            )
            if started:
                conversation.started_at = started

    def _count_actions(self, trajectories: list[RuntimeTrajectory]) -> int:
        if not trajectories:
            return 0
        from rai_gateway.models.evidence import EvidenceEvent

        ids = [t.id for t in trajectories]
        return (
            self._db.query(EvidenceEvent)
            .filter(
                EvidenceEvent.trajectory_id.in_(ids),
                EvidenceEvent.event_type == "TOOL_ATTEMPTED",
            )
            .count()
        )

    def _conversation_status(self, trajectories: list[RuntimeTrajectory]) -> str:
        if not trajectories:
            return "ACTIVE"
        statuses = {t.status for t in trajectories}
        if "ACTIVE" in statuses:
            return "ACTIVE"
        if "INCOMPLETE" in statuses:
            return "INCOMPLETE"
        if statuses <= {"COMPLETED", "CLOSED"}:
            return "COMPLETED"
        return next(iter(statuses))

    def _highest_risk(self, trajectories: list[RuntimeTrajectory]) -> str | None:
        if not trajectories:
            return None
        ids = [t.id for t in trajectories]
        findings = (
            self._db.query(EvidenceFinding)
            .filter(EvidenceFinding.trajectory_id.in_(ids))
            .all()
        )
        best = None
        best_rank = 0
        for finding in findings:
            rank = _SEVERITY_RANK.get(finding.severity, 0)
            if rank > best_rank:
                best = finding.severity
                best_rank = rank
        return best

    def _highest_assurance(self, trajectories: list[RuntimeTrajectory]) -> str | None:
        best = None
        best_rank = 0
        for trajectory in trajectories:
            summary = trajectory.assurance_summary or {}
            level = summary.get("highest") if isinstance(summary, dict) else None
            if not level:
                continue
            rank = _ASSURANCE_RANK.get(str(level), 0)
            if rank > best_rank:
                best = str(level)
                best_rank = rank
        return best

    def list_conversations(
        self,
        *,
        ai_system_id: UUID | None = None,
        agent_id: UUID | None = None,
        runtime_identity_id: UUID | None = None,
        client_integration_id: UUID | None = None,
        status: str | None = None,
        risk_level: str | None = None,
        principal: str | None = None,
        conversation_id: str | None = None,
        started_after: datetime | None = None,
        started_before: datetime | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        query = self._db.query(RuntimeConversation)
        if ai_system_id:
            query = query.filter(RuntimeConversation.ai_system_id == ai_system_id)
        if agent_id:
            query = query.filter(RuntimeConversation.primary_agent_id == agent_id)
        if runtime_identity_id:
            query = query.filter(
                RuntimeConversation.runtime_identity_id == runtime_identity_id
            )
        if client_integration_id:
            query = query.filter(
                RuntimeConversation.client_integration_id == client_integration_id
            )
        if status:
            query = query.filter(RuntimeConversation.status == status)
        if risk_level:
            query = query.filter(RuntimeConversation.highest_risk_level == risk_level)
        if principal:
            query = query.filter(
                RuntimeConversation.principal_reference.ilike(f"%{principal}%")
            )
        if conversation_id:
            query = query.filter(
                RuntimeConversation.external_conversation_id == conversation_id
            )
        if started_after:
            query = query.filter(RuntimeConversation.last_activity_at >= started_after)
        if started_before:
            query = query.filter(RuntimeConversation.last_activity_at <= started_before)

        if cursor:
            cursor_ts, cursor_id = decode_cursor(cursor)
            query = query.filter(
                (RuntimeConversation.last_activity_at < cursor_ts)
                | (
                    (RuntimeConversation.last_activity_at == cursor_ts)
                    & (RuntimeConversation.id < cursor_id)
                )
            )

        rows = (
            query.order_by(
                RuntimeConversation.last_activity_at.desc(),
                RuntimeConversation.id.desc(),
            )
            .limit(limit + 1)
            .all()
        )
        has_more = len(rows) > limit
        items = rows[:limit]
        next_cursor = None
        if has_more and items:
            last = items[-1]
            next_cursor = encode_cursor(
                last_activity_at=last.last_activity_at or datetime.now(timezone.utc),
                conversation_id=last.id,
            )
        return {
            "items": [self.serialize_summary(row) for row in items],
            "next_cursor": next_cursor,
            "has_more": has_more,
            "limit": limit,
        }

    def get_conversation(
        self,
        conversation_id: UUID,
    ) -> RuntimeConversation | None:
        return (
            self._db.query(RuntimeConversation)
            .filter(
                RuntimeConversation.id == conversation_id,
            )
            .first()
        )

    def list_conversation_trajectories(
        self,
        conversation_id: UUID,
        *,
        cursor: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any] | None:
        conversation = self.get_conversation(conversation_id)
        if conversation is None:
            return None

        query = self._db.query(RuntimeTrajectory).filter(
            RuntimeTrajectory.runtime_conversation_id == conversation.id
        )
        if cursor:
            cursor_ts, cursor_id = decode_cursor(cursor)
            query = query.filter(
                (RuntimeTrajectory.started_at < cursor_ts)
                | (
                    (RuntimeTrajectory.started_at == cursor_ts)
                    & (RuntimeTrajectory.id < cursor_id)
                )
            )
        rows = (
            query.order_by(
                RuntimeTrajectory.started_at.desc(),
                RuntimeTrajectory.id.desc(),
            )
            .limit(limit + 1)
            .all()
        )
        has_more = len(rows) > limit
        items = rows[:limit]
        next_cursor = None
        if has_more and items:
            last = items[-1]
            next_cursor = encode_cursor(
                last_activity_at=last.started_at or datetime.now(timezone.utc),
                conversation_id=last.id,
            )
        from rai_gateway.evidence.service import TrajectoryService

        traj_svc = TrajectoryService(self._db)
        return {
            "conversation_id": str(conversation.id),
            "items": [
                traj_svc.serialize_trajectory_summary(row, enrich_names=True)
                for row in items
            ],
            "next_cursor": next_cursor,
            "has_more": has_more,
            "limit": limit,
        }

    def serialize_summary(self, conversation: RuntimeConversation) -> dict[str, Any]:
        names = self._resolve_display_names(conversation)
        return {
            "id": str(conversation.id),
            "conversation_key": conversation.conversation_key,
            "external_conversation_id": conversation.external_conversation_id,
            "client_integration_id": (
                str(conversation.client_integration_id)
                if conversation.client_integration_id
                else None
            ),
            "runtime_identity_id": (
                str(conversation.runtime_identity_id)
                if conversation.runtime_identity_id
                else None
            ),
            "ai_system_id": (
                str(conversation.ai_system_id) if conversation.ai_system_id else None
            ),
            "primary_agent_id": (
                str(conversation.primary_agent_id)
                if conversation.primary_agent_id
                else None
            ),
            "principal_reference": conversation.principal_reference,
            "channel": conversation.channel,
            "started_at": (
                conversation.started_at.isoformat() if conversation.started_at else None
            ),
            "last_activity_at": (
                conversation.last_activity_at.isoformat()
                if conversation.last_activity_at
                else None
            ),
            "status": conversation.status,
            "trajectory_count": conversation.trajectory_count,
            "event_count": conversation.event_count,
            "action_count": conversation.action_count,
            "finding_count": conversation.finding_count,
            "highest_risk_level": conversation.highest_risk_level,
            "highest_assurance_level": conversation.highest_assurance_level,
            "last_trajectory_id": (
                str(conversation.last_trajectory_id)
                if conversation.last_trajectory_id
                else None
            ),
            **names,
        }

    def serialize_detail(self, conversation: RuntimeConversation) -> dict[str, Any]:
        summary = self.serialize_summary(conversation)
        summary["created_at"] = (
            conversation.created_at.isoformat() if conversation.created_at else None
        )
        summary["updated_at"] = (
            conversation.updated_at.isoformat() if conversation.updated_at else None
        )
        return summary

    def list_policy_triggers(
        self,
        conversation_id: UUID,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any] | None:
        """Budget / tool / content / finding triggers across conversation turns."""
        from rai_gateway.evidence.domain import EvidenceEventType
        from rai_gateway.models.evidence import EvidenceEvent, EvidenceFinding
        from rai_gateway.models.risk_intelligence import RuntimeRiskFinding

        conversation = self.get_conversation(conversation_id)
        if conversation is None:
            return None

        trajectories = (
            self._db.query(RuntimeTrajectory)
            .filter(RuntimeTrajectory.runtime_conversation_id == conversation.id)
            .all()
        )
        traj_ids = [t.id for t in trajectories]
        if not traj_ids:
            return {
                "conversation_id": str(conversation.id),
                "items": [],
                "total": 0,
                "limit": limit,
                "offset": offset,
            }

        trigger_types = {
            EvidenceEventType.BUDGET_WARNING.value,
            EvidenceEventType.BUDGET_EXCEEDED.value,
            EvidenceEventType.ACTION_DENIED.value,
            EvidenceEventType.FINDING_CREATED.value,
            EvidenceEventType.CONTENT_EVALUATION_RESULT.value,
            EvidenceEventType.INTERVENTION_DECIDED.value,
            EvidenceEventType.APPROVAL_REQUESTED.value,
            EvidenceEventType.POLICY_EVALUATED.value,
            EvidenceEventType.DATA_SOURCE_ACCESSED.value,
            EvidenceEventType.DATA_ACCESS_DENIED.value,
        }

        events = (
            self._db.query(EvidenceEvent)
            .filter(
                EvidenceEvent.trajectory_id.in_(traj_ids),
                EvidenceEvent.event_type.in_(trigger_types),
            )
            .order_by(EvidenceEvent.occurred_at.desc())
            .all()
        )

        # POLICY_EVALUATED is noisy (default allow). Keep only non-allow / explained denies.
        filtered_events: list[EvidenceEvent] = []
        for event in events:
            if event.event_type != EvidenceEventType.POLICY_EVALUATED.value:
                filtered_events.append(event)
                continue
            payload = event.payload or {}
            effect = str(
                payload.get("policy_effect") or payload.get("effect") or ""
            ).upper()
            decision = payload.get("policy_decision")
            if isinstance(decision, dict):
                effect = str(
                    decision.get("final_effect") or decision.get("effect") or effect
                ).upper()
            if effect in {"DENY", "REQUIRE_APPROVAL", "BLOCK", "SUSPEND"}:
                filtered_events.append(event)
            elif payload.get("matched_rule_ids"):
                filtered_events.append(event)

        evidence_findings = (
            self._db.query(EvidenceFinding)
            .filter(EvidenceFinding.trajectory_id.in_(traj_ids))
            .order_by(EvidenceFinding.created_at.desc())
            .all()
        )
        risk_findings = (
            self._db.query(RuntimeRiskFinding)
            .filter(RuntimeRiskFinding.trajectory_id.in_(traj_ids))
            .order_by(RuntimeRiskFinding.created_at.desc())
            .all()
        )

        items: list[dict[str, Any]] = []
        for event in filtered_events:
            payload = event.payload or {}
            category = "policy"
            if "BUDGET" in event.event_type:
                category = "budget"
            elif "CONTENT" in event.event_type:
                category = "content"
            elif "DATA_SOURCE" in event.event_type or "DATA_ACCESS" in event.event_type:
                category = "content"
            elif event.event_type in {
                EvidenceEventType.ACTION_DENIED.value,
                EvidenceEventType.POLICY_EVALUATED.value,
            }:
                category = "tool"
            elif "FINDING" in event.event_type:
                category = "finding"
            elif "APPROVAL" in event.event_type or "INTERVENTION" in event.event_type:
                category = "governance"

            items.append(
                {
                    "id": str(event.id),
                    "kind": "event",
                    "category": category,
                    "event_type": event.event_type,
                    "title": event.event_type.replace("_", " ").title(),
                    "summary": (
                        payload.get("human_explanation")
                        or payload.get("reason")
                        or payload.get("message")
                        or payload.get("title")
                    ),
                    "severity": None,
                    "status": payload.get("status")
                    or payload.get("decision")
                    or payload.get("policy_effect"),
                    "trajectory_id": str(event.trajectory_id),
                    "occurred_at": event.occurred_at.isoformat()
                    if event.occurred_at
                    else None,
                    "payload": payload,
                }
            )

        for finding in evidence_findings:
            items.append(
                {
                    "id": str(finding.id),
                    "kind": "evidence_finding",
                    "category": "finding",
                    "event_type": finding.finding_type,
                    "title": finding.title,
                    "summary": finding.description,
                    "severity": finding.severity,
                    "status": finding.status,
                    "trajectory_id": str(finding.trajectory_id)
                    if finding.trajectory_id
                    else None,
                    "occurred_at": finding.created_at.isoformat()
                    if finding.created_at
                    else None,
                    "payload": {
                        "source_event_ids": finding.source_event_ids,
                    },
                }
            )

        for finding in risk_findings:
            items.append(
                {
                    "id": str(finding.id),
                    "kind": "risk_finding",
                    "category": "finding",
                    "event_type": finding.finding_type,
                    "title": finding.title,
                    "summary": finding.description,
                    "severity": finding.severity,
                    "status": finding.status,
                    "trajectory_id": str(finding.trajectory_id)
                    if finding.trajectory_id
                    else None,
                    "occurred_at": finding.created_at.isoformat()
                    if finding.created_at
                    else None,
                    "payload": finding.explanation
                    if isinstance(finding.explanation, dict)
                    else {},
                }
            )

        items.sort(key=lambda row: row.get("occurred_at") or "", reverse=True)
        total = len(items)
        page = items[offset : offset + limit]
        return {
            "conversation_id": str(conversation.id),
            "items": page,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def _resolve_display_names(
        self, conversation: RuntimeConversation
    ) -> dict[str, Any]:
        from rai_gateway.models.client_hooks import RuntimeClientIntegration
        from rai_gateway.models.identity import AgentRuntimeIdentity
        from rai_gateway.models.registry import Agent, AISystem

        system = (
            self._db.query(AISystem)
            .filter(AISystem.id == conversation.ai_system_id)
            .first()
            if conversation.ai_system_id
            else None
        )
        agent = (
            self._db.query(Agent)
            .filter(Agent.id == conversation.primary_agent_id)
            .first()
            if conversation.primary_agent_id
            else None
        )
        identity = (
            self._db.query(AgentRuntimeIdentity)
            .filter(AgentRuntimeIdentity.id == conversation.runtime_identity_id)
            .first()
            if conversation.runtime_identity_id
            else None
        )
        client_type = None
        if conversation.client_integration_id:
            integration = (
                self._db.query(RuntimeClientIntegration)
                .filter(
                    RuntimeClientIntegration.id == conversation.client_integration_id
                )
                .first()
            )
            client_type = integration.client_type if integration else None
        return {
            "ai_system_name": system.name if system else None,
            "agent_name": agent.name if agent else None,
            "runtime_identity_name": identity.name if identity else None,
            "client_type": client_type,
        }
