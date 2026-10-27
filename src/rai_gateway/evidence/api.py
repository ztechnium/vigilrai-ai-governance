"""WP5 Runtime Trajectory Evidence REST API."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

import rai_gateway.models.evidence  # noqa: F401
from rai_gateway.core.authorization import require_any_permission, require_permission
from rai_gateway.core.database import get_db
from rai_gateway.core.tenant_context import TenantContext
from rai_gateway.evidence.content_access import (
    CONTENT_EXPORT_PERMISSION,
    CONTENT_READ_PERMISSION,
    apply_content_permission,
    apply_export_content_permission,
    apply_trajectory_content_permission,
    strip_artifact_content,
    strip_event_content,
    strip_lifecycle_content,
    strip_observed_prompt_content,
)
from rai_gateway.evidence.service import TrajectoryService

router = APIRouter(
    prefix="/v1",
    tags=["evidence"],
)


@router.get("/trajectories")
def list_trajectories(
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("evidence:read")),
    ai_system_id: UUID | None = Query(default=None),
    agent_id: UUID | None = Query(default=None),
    runtime_identity_id: UUID | None = Query(default=None),
    client_integration_id: UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    started_after: datetime | None = Query(default=None),
    started_before: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    svc = TrajectoryService(db)
    rows = svc.list_trajectories(
        ai_system_id=ai_system_id,
        agent_id=agent_id,
        runtime_identity_id=runtime_identity_id,
        client_integration_id=client_integration_id,
        status=status,
        started_after=started_after,
        started_before=started_before,
        limit=limit,
        offset=offset,
    )
    total = svc.count_trajectories(
        ai_system_id=ai_system_id,
        agent_id=agent_id,
        runtime_identity_id=runtime_identity_id,
        client_integration_id=client_integration_id,
        status=status,
        started_after=started_after,
        started_before=started_before,
    )
    items = [svc.serialize_trajectory_summary(row) for row in rows]
    from rai_gateway.finops.metering import RuntimeMeteringService

    economics = RuntimeMeteringService(db).summarize_trajectories(
        [row.id for row in rows]
    )
    for item in items:
        item["economics"] = economics.get(item["id"])
    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/observed-prompts")
def list_observed_prompts(
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("evidence:read")),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    svc = TrajectoryService(db)
    items = svc.list_observed_prompts(limit=limit, offset=offset)
    allowed = tenant.has_permission(CONTENT_READ_PERMISSION)
    if not allowed:
        items = [strip_observed_prompt_content(item) for item in items]
    return {
        "items": items,
        "limit": limit,
        "offset": offset,
        "content_access": "ALLOWED" if allowed else "DENIED",
    }


@router.get("/observed-prompts/{event_id}")
def get_observed_prompt(
    event_id: UUID,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("evidence:read")),
):
    svc = TrajectoryService(db)
    detail = svc.get_observed_prompt(event_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Observed prompt not found")
    if not tenant.has_permission(CONTENT_READ_PERMISSION):
        return strip_observed_prompt_content(detail)
    detail = dict(detail)
    detail["content_access"] = "ALLOWED"
    return detail


@router.get("/evidence/retention/eligible")
def list_purge_eligible_trajectories(
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("evidence:manage")),
    limit: int = Query(default=100, ge=1, le=500),
):
    from rai_gateway.evidence.retention import EvidenceRetentionService

    svc = TrajectoryService(db)
    rows = EvidenceRetentionService(db).list_eligible_for_purge(limit=limit)
    return {
        "items": [svc.serialize_trajectory_summary(row) for row in rows],
        "limit": limit,
    }


@router.get("/trajectories/{trajectory_id}")
def get_trajectory(
    trajectory_id: UUID,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("evidence:read")),
):
    svc = TrajectoryService(db)
    trajectory = svc.get_trajectory(trajectory_id)
    if not trajectory:
        raise HTTPException(status_code=404, detail="Trajectory not found")
    return apply_trajectory_content_permission(
        svc.serialize_trajectory_detail(trajectory),
        allowed=tenant.has_permission(CONTENT_READ_PERMISSION),
    )


@router.get("/trajectories/{trajectory_id}/lifecycle")
def get_trajectory_lifecycle(
    trajectory_id: UUID,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("evidence:read")),
):
    """Business-readable lifecycle projection over immutable evidence events."""
    from rai_gateway.evidence.lifecycle_projection import LifecycleProjectionService

    svc = TrajectoryService(db)
    trajectory = svc.get_trajectory(trajectory_id)
    if not trajectory:
        raise HTTPException(status_code=404, detail="Trajectory not found")
    events = svc.list_events(trajectory_id, limit=2000)
    lifecycle = LifecycleProjectionService(db).project(trajectory, events=events)
    if tenant.has_permission(CONTENT_READ_PERMISSION):
        lifecycle = dict(lifecycle)
        lifecycle["content_access"] = "ALLOWED"
        return lifecycle
    return strip_lifecycle_content(lifecycle)


@router.get("/trajectories/{trajectory_id}/economics")
def get_trajectory_economics(
    trajectory_id: UUID,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(
        require_any_permission("finops:read", "evidence:read")
    ),
):
    from rai_gateway.finops.metering import RuntimeMeteringService

    svc = TrajectoryService(db)
    trajectory = svc.get_trajectory(trajectory_id)
    if not trajectory:
        raise HTTPException(status_code=404, detail="Trajectory not found")
    return RuntimeMeteringService(db).trajectory_economics(trajectory.id)


@router.get("/trajectories/{trajectory_id}/risk-findings")
def get_trajectory_risk_findings(
    trajectory_id: UUID,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("evidence:read")),
):
    """Combined evidence findings + WP6 risk bundle for one trajectory detail tab."""
    svc = TrajectoryService(db)
    trajectory = svc.get_trajectory(trajectory_id)
    if not trajectory:
        raise HTTPException(status_code=404, detail="Trajectory not found")

    evidence_findings = [
        svc.serialize_finding(f) for f in svc.list_findings(trajectory_id)
    ]
    risk_bundle: dict = {
        "signals": [],
        "findings": [],
        "interventions": [],
        "evaluations": [],
        "risk_state": None,
    }
    try:
        from rai_gateway.risk_intelligence.service import RiskIntelligenceService

        risk_bundle = RiskIntelligenceService(db).trajectory_risk(trajectory_id)
    except Exception:
        # Risk domain is optional for evidence readers; keep evidence findings.
        pass

    highest = None
    severities = [f.get("severity") for f in evidence_findings if f.get("severity")]
    for risk_finding in risk_bundle.get("findings") or []:
        if isinstance(risk_finding, dict) and risk_finding.get("severity"):
            severities.append(risk_finding["severity"])
    rank = {"CRITICAL": 5, "HIGH": 4, "MEDIUM": 3, "LOW": 2, "INFO": 1}
    if severities:
        highest = max(severities, key=lambda s: rank.get(str(s), 0))

    return {
        "trajectory_id": str(trajectory_id),
        "highest_risk_level": highest,
        "evidence_findings": evidence_findings,
        "risk": risk_bundle,
    }


@router.get("/runtime-audit/search")
def search_runtime_audit(
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("evidence:read")),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    entity_types: str | None = Query(
        default=None,
        description="Comma-separated: ENFORCEMENT,EXECUTION,EVIDENCE_EVENT",
    ),
    ai_system_id: UUID | None = Query(default=None),
    agent_id: UUID | None = Query(default=None),
    runtime_identity_id: UUID | None = Query(default=None),
    delegation_id: UUID | None = Query(default=None),
    integration_id: UUID | None = Query(default=None),
    conversation_id: str | None = Query(default=None),
    trajectory_id: UUID | None = Query(default=None),
    tool_id: UUID | None = Query(default=None),
    decision: str | None = Query(default=None),
    execution_status: str | None = Query(default=None),
    assurance: str | None = Query(default=None),
    correlation_id: str | None = Query(default=None),
    receipt_id: UUID | None = Query(default=None),
    event_type: str | None = Query(default=None),
    record_kind: str | None = Query(
        default=None,
        description="INPUT | OUTPUT | MODEL_REQUEST | MODEL_RESPONSE",
    ),
    principal: str | None = Query(default=None),
    channel: str | None = Query(default=None),
    content_search: str | None = Query(
        default=None,
        description="Search observed content fields (requires evidence:content:read)",
    ),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
):
    """Bounded Audit Explorer search. Date range required (defaults to last 24h)."""
    from rai_gateway.evidence.audit_search import (
        AuditSearchFilters,
        AuditSearchService,
        default_audit_window,
    )

    if content_search and content_search.strip():
        if not tenant.has_permission(CONTENT_READ_PERMISSION):
            raise HTTPException(
                status_code=403,
                detail="content_search requires evidence:content:read",
            )

    if date_from is None or date_to is None:
        default_from, default_to = default_audit_window()
        date_from = date_from or default_from
        date_to = date_to or default_to

    parsed_types: tuple[str, ...] = ("ENFORCEMENT", "EXECUTION", "EVIDENCE_EVENT")
    if entity_types:
        parsed_types = tuple(
            part.strip().upper() for part in entity_types.split(",") if part.strip()
        )
        allowed = {"ENFORCEMENT", "EXECUTION", "EVIDENCE_EVENT"}
        if not parsed_types or any(t not in allowed for t in parsed_types):
            raise HTTPException(
                status_code=400,
                detail="entity_types must be ENFORCEMENT, EXECUTION, and/or EVIDENCE_EVENT",
            )

    kind = record_kind.strip().upper() if record_kind else None
    if kind and kind not in {"INPUT", "OUTPUT", "MODEL_REQUEST", "MODEL_RESPONSE"}:
        raise HTTPException(
            status_code=400,
            detail="record_kind must be INPUT, OUTPUT, MODEL_REQUEST, or MODEL_RESPONSE",
        )

    filters = AuditSearchFilters(
        date_from=date_from,
        date_to=date_to,
        entity_types=parsed_types,  # type: ignore[arg-type]
        ai_system_id=ai_system_id,
        agent_id=agent_id,
        runtime_identity_id=runtime_identity_id,
        delegation_id=delegation_id,
        integration_id=integration_id,
        conversation_id=conversation_id,
        trajectory_id=trajectory_id,
        tool_id=tool_id,
        decision=decision,
        execution_status=execution_status,
        assurance=assurance,
        correlation_id=correlation_id,
        receipt_id=receipt_id,
        event_type=event_type,
        record_kind=kind,  # type: ignore[arg-type]
        principal=principal,
        channel=channel,
        content_search=content_search.strip() if content_search else None,
    )
    try:
        return AuditSearchService(db).search(
            filters=filters,
            cursor=cursor,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/ai-systems/{ai_system_id}/configuration-provenance")
def get_ai_system_configuration_provenance(
    ai_system_id: UUID,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("evidence:read")),
):
    """Last observed external configuration provenance for an AI system.

    Application-reported only — RAI does not store or edit persona/system prompts.
    """
    from rai_gateway.evidence.lifecycle_projection import LifecycleProjectionService

    result = LifecycleProjectionService(db).last_observed_for_system(
        ai_system_id=ai_system_id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="AI system not found")
    return result


@router.get("/conversations")
def list_conversations(
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("evidence:read")),
    ai_system_id: UUID | None = Query(default=None),
    agent_id: UUID | None = Query(default=None),
    runtime_identity_id: UUID | None = Query(default=None),
    client_integration_id: UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    risk_level: str | None = Query(default=None),
    principal: str | None = Query(default=None),
    conversation_id: str | None = Query(default=None),
    started_after: datetime | None = Query(default=None),
    started_before: datetime | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
):
    from rai_gateway.evidence.conversation_projection import (
        ConversationProjectionService,
    )

    try:
        result = ConversationProjectionService(db).list_conversations(
            ai_system_id=ai_system_id,
            agent_id=agent_id,
            runtime_identity_id=runtime_identity_id,
            client_integration_id=client_integration_id,
            status=status,
            risk_level=risk_level,
            principal=principal,
            conversation_id=conversation_id,
            started_after=started_after,
            started_before=started_before,
            cursor=cursor,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    from rai_gateway.finops.metering import RuntimeMeteringService

    economics = RuntimeMeteringService(db).summarize_conversations(
        [UUID(item["id"]) for item in result["items"]],
    )
    for item in result["items"]:
        item["economics"] = economics.get(item["id"])
    return result


@router.get("/conversations/{conversation_id}")
def get_conversation(
    conversation_id: UUID,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("evidence:read")),
):
    from rai_gateway.evidence.conversation_projection import (
        ConversationProjectionService,
    )

    svc = ConversationProjectionService(db)
    row = svc.get_conversation(conversation_id)
    if not row:
        raise HTTPException(status_code=404, detail="Conversation not found")
    payload = svc.serialize_detail(row)
    from rai_gateway.finops.metering import RuntimeMeteringService
    from rai_gateway.models.evidence import RuntimeTrajectory

    trajectory_ids = [
        item[0]
        for item in db.query(RuntimeTrajectory.id)
        .filter(RuntimeTrajectory.runtime_conversation_id == row.id)
        .all()
    ]
    payload["economics"] = RuntimeMeteringService(db).conversation_economics(
        runtime_conversation_id=row.id,
        trajectory_ids=trajectory_ids,
    )
    return payload


@router.get("/conversations/{conversation_id}/trajectories")
def list_conversation_trajectories(
    conversation_id: UUID,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("evidence:read")),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
):
    from rai_gateway.evidence.conversation_projection import (
        ConversationProjectionService,
    )

    try:
        result = ConversationProjectionService(db).list_conversation_trajectories(
            conversation_id,
            cursor=cursor,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    from rai_gateway.finops.metering import RuntimeMeteringService

    economics = RuntimeMeteringService(db).summarize_trajectories(
        [UUID(item["id"]) for item in result["items"]],
    )
    for item in result["items"]:
        item["economics"] = economics.get(item["id"])
    return result


@router.get("/conversations/{conversation_id}/policy-triggers")
def list_conversation_policy_triggers(
    conversation_id: UUID,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("evidence:read")),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Budget, tool, content, and finding triggers across conversation turns."""
    from rai_gateway.evidence.conversation_projection import (
        ConversationProjectionService,
    )

    result = ConversationProjectionService(db).list_policy_triggers(
        conversation_id,
        limit=limit,
        offset=offset,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return result


@router.get("/trajectories/{trajectory_id}/events")
def get_trajectory_events(
    trajectory_id: UUID,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("evidence:read")),
    limit: int = Query(default=500, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
):
    svc = TrajectoryService(db)
    trajectory = svc.get_trajectory(trajectory_id)
    if not trajectory:
        raise HTTPException(status_code=404, detail="Trajectory not found")
    events = svc.list_events(trajectory_id, limit=limit, offset=offset)
    allowed = tenant.has_permission(CONTENT_READ_PERMISSION)
    items = [svc.serialize_event(event) for event in events]
    if not allowed:
        items = [strip_event_content(item) for item in items]
    return {
        "trajectory_id": str(trajectory_id),
        "items": items,
        "limit": limit,
        "offset": offset,
        "content_access": "ALLOWED" if allowed else "DENIED",
    }


@router.get("/trajectories/{trajectory_id}/events/{event_id}")
def get_trajectory_event(
    trajectory_id: UUID,
    event_id: UUID,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("evidence:read")),
):
    """Fetch a single evidence event with content (when handling policy permits)."""
    svc = TrajectoryService(db)
    trajectory = svc.get_trajectory(trajectory_id)
    if not trajectory:
        raise HTTPException(status_code=404, detail="Trajectory not found")
    event = svc.get_event(trajectory_id, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Evidence event not found")
    return apply_content_permission(
        svc.serialize_event_detail(trajectory, event),
        allowed=tenant.has_permission(CONTENT_READ_PERMISSION),
    )


@router.get("/trajectories/{trajectory_id}/artifacts/{artifact_id}")
def get_trajectory_artifact(
    trajectory_id: UUID,
    artifact_id: UUID,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("evidence:read")),
):
    """Fetch a single evidence artifact scoped to its trajectory."""
    svc = TrajectoryService(db)
    trajectory = svc.get_trajectory(trajectory_id)
    if not trajectory:
        raise HTTPException(status_code=404, detail="Trajectory not found")
    artifact = svc.get_artifact(trajectory_id, artifact_id)
    if not artifact:
        raise HTTPException(status_code=404, detail="Evidence artifact not found")
    serialized = svc.serialize_artifact(artifact)
    if tenant.has_permission(CONTENT_READ_PERMISSION):
        serialized = dict(serialized)
        serialized["content_access"] = "ALLOWED"
        return serialized
    return strip_artifact_content(serialized)


@router.get("/trajectories/{trajectory_id}/graph")
def get_trajectory_graph(
    trajectory_id: UUID,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("evidence:read")),
):
    svc = TrajectoryService(db)
    trajectory = svc.get_trajectory(trajectory_id)
    if not trajectory:
        raise HTTPException(status_code=404, detail="Trajectory not found")
    events = svc.list_events(trajectory_id)
    relations = svc.list_relations(trajectory_id)
    findings = svc.list_findings(trajectory_id)
    nodes: dict[str, dict] = {}
    for event in events:
        key = f"EVENT:{event.id}"
        nodes[key] = {
            "id": str(event.id),
            "entity_type": "EVENT",
            "label": event.event_type,
            "source_type": event.source_type,
            "assurance_level": event.assurance_level,
            "occurred_at": event.occurred_at.isoformat() if event.occurred_at else None,
        }
    for finding in findings:
        key = f"FINDING:{finding.id}"
        nodes[key] = {
            "id": str(finding.id),
            "entity_type": "FINDING",
            "label": finding.finding_type,
            "severity": finding.severity,
            "title": finding.title,
        }
    for relation in relations:
        for entity_type, entity_id in (
            (relation.source_entity_type, relation.source_entity_id),
            (relation.target_entity_type, relation.target_entity_id),
        ):
            key = f"{entity_type}:{entity_id}"
            if key not in nodes:
                nodes[key] = {
                    "id": entity_id,
                    "entity_type": entity_type,
                    "label": entity_type,
                }
    return {
        "trajectory_id": str(trajectory_id),
        "nodes": list(nodes.values()),
        "edges": [svc.serialize_relation(rel) for rel in relations],
    }


@router.get("/trajectories/{trajectory_id}/findings")
def get_trajectory_findings(
    trajectory_id: UUID,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("evidence:read")),
):
    svc = TrajectoryService(db)
    trajectory = svc.get_trajectory(trajectory_id)
    if not trajectory:
        raise HTTPException(status_code=404, detail="Trajectory not found")
    return {
        "trajectory_id": str(trajectory_id),
        "items": [svc.serialize_finding(f) for f in svc.list_findings(trajectory_id)],
    }


@router.get("/trajectories/{trajectory_id}/artifacts")
def get_trajectory_artifacts(
    trajectory_id: UUID,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("evidence:read")),
):
    svc = TrajectoryService(db)
    trajectory = svc.get_trajectory(trajectory_id)
    if not trajectory:
        raise HTTPException(status_code=404, detail="Trajectory not found")
    allowed = tenant.has_permission(CONTENT_READ_PERMISSION)
    items = [svc.serialize_artifact(a) for a in svc.list_artifacts(trajectory_id)]
    if not allowed:
        items = [strip_artifact_content(a) for a in items]
    return {
        "trajectory_id": str(trajectory_id),
        "items": items,
        "content_access": "ALLOWED" if allowed else "DENIED",
    }


@router.post("/trajectories/{trajectory_id}/export")
def export_trajectory(
    trajectory_id: UUID,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("evidence:export")),
):
    svc = TrajectoryService(db)
    trajectory = svc.get_trajectory(trajectory_id)
    if not trajectory:
        raise HTTPException(status_code=404, detail="Trajectory not found")
    return apply_export_content_permission(
        svc.export_trajectory(trajectory),
        allowed=tenant.has_permission(CONTENT_EXPORT_PERMISSION),
    )


@router.post("/trajectories/project/receipt/{receipt_id}")
def project_receipt_into_trajectory(
    receipt_id: UUID,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("evidence:manage")),
):
    """Explicit projection/backfill from a WP4 enforcement receipt."""
    svc = TrajectoryService(db)
    trajectory = svc.project_receipt(receipt_id)
    if not trajectory:
        raise HTTPException(status_code=404, detail="Receipt not found")
    db.commit()
    return svc.serialize_trajectory_summary(trajectory)


@router.post("/trajectories/project/approval/{approval_request_id}")
def project_approval_into_trajectory(
    approval_request_id: UUID,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("evidence:manage")),
):
    """Explicit projection/backfill from a WP3 approval request."""
    svc = TrajectoryService(db)
    trajectory = svc.project_approval(approval_request_id)
    if not trajectory:
        raise HTTPException(status_code=404, detail="Approval request not found")
    db.commit()
    return svc.serialize_trajectory_summary(trajectory)


class LegalHoldBody(BaseModel):
    legal_hold: bool
    reason: str | None = None


class RetentionBody(BaseModel):
    retention_days: int
    reason: str | None = None


class PurgeBody(BaseModel):
    reason: str | None = None
    force: bool = False


@router.post("/trajectories/{trajectory_id}/legal-hold")
def set_trajectory_legal_hold(
    trajectory_id: UUID,
    body: LegalHoldBody,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("evidence:manage")),
):
    from rai_gateway.evidence.retention import (
        EvidenceRetentionError,
        EvidenceRetentionService,
    )

    try:
        trajectory = EvidenceRetentionService(db).set_legal_hold(
            trajectory_id,
            legal_hold=body.legal_hold,
            actor=tenant.user_id,
            reason=body.reason,
        )
    except EvidenceRetentionError as exc:
        status = 404 if exc.code == "NOT_FOUND" else 409
        raise HTTPException(
            status_code=status, detail={"error": exc.code, "message": exc.message}
        )
    return TrajectoryService(db).serialize_trajectory_summary(trajectory)


@router.post("/trajectories/{trajectory_id}/retention")
def set_trajectory_retention(
    trajectory_id: UUID,
    body: RetentionBody,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("evidence:manage")),
):
    from rai_gateway.evidence.retention import (
        EvidenceRetentionError,
        EvidenceRetentionService,
    )

    try:
        trajectory = EvidenceRetentionService(db).set_retention(
            trajectory_id,
            retention_days=body.retention_days,
            actor=tenant.user_id,
            reason=body.reason,
        )
    except EvidenceRetentionError as exc:
        status = 404 if exc.code == "NOT_FOUND" else 400
        raise HTTPException(
            status_code=status, detail={"error": exc.code, "message": exc.message}
        )
    return TrajectoryService(db).serialize_trajectory_summary(trajectory)


@router.post("/trajectories/{trajectory_id}/purge")
def purge_trajectory(
    trajectory_id: UUID,
    body: PurgeBody,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("evidence:manage")),
):
    from rai_gateway.evidence.retention import (
        EvidenceRetentionError,
        EvidenceRetentionService,
    )

    try:
        return EvidenceRetentionService(db).purge_trajectory(
            trajectory_id,
            actor=tenant.user_id,
            reason=body.reason,
            force=body.force,
        )
    except EvidenceRetentionError as exc:
        status = 404 if exc.code == "NOT_FOUND" else 409
        raise HTTPException(
            status_code=status, detail={"error": exc.code, "message": exc.message}
        )
