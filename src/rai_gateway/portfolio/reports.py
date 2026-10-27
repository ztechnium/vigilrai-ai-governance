"""Immutable transparency report snapshots + HTML/JSON."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from rai_gateway.models.portfolio import PortfolioReport
from rai_gateway.portfolio.attention import build_attention_queue
from rai_gateway.portfolio.domain import SCHEMA_VERSION, Freshness, ReportScopeType
from rai_gateway.portfolio.errors import PortfolioNotFoundError
from rai_gateway.portfolio.queries import (
    _ser_dt,
    get_assurance_posture,
    get_change_feed,
    get_control_posture,
    get_evidence_completeness,
    get_incident_posture,
    get_inventory,
    get_risk_posture,
    get_runtime_activity,
    get_summary,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def content_digest(payload: Any) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _build_html(snapshot: dict[str, Any], digest: str) -> str:
    metrics = snapshot.get("executive_summary", {}).get("metrics", {})
    rows = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in metrics.items())
    attention = snapshot.get("priority_actions", {}).get("items", [])[:15]
    attention_rows = "".join(
        f"<tr><td>{a.get('severity')}</td><td>{a.get('title')}</td>"
        f"<td>{a.get('recommended_action')}</td></tr>"
        for a in attention
    )
    return (
        "<html><head><title>Portfolio Transparency Report</title></head><body>"
        f"<h1>{snapshot.get('title', 'Portfolio Transparency Report')}</h1>"
        f"<p>Generated: {snapshot.get('generated_at')}</p>"
        f"<p>Schema: {snapshot.get('schema_version')}</p>"
        f"<p>Digest: {digest}</p>"
        "<p><em>This report is an executive/portfolio summary. "
        "It does not state legal or regulatory compliance unless a validated "
        "framework assessment explicitly supports it.</em></p>"
        "<h2>1. Executive Summary</h2>"
        "<table border='1'><tr><th>Metric</th><th>Value</th></tr>"
        f"{rows}</table>"
        "<h2>11. Priority Actions</h2>"
        "<table border='1'><tr><th>Severity</th><th>Title</th><th>Action</th></tr>"
        f"{attention_rows}</table>"
        "</body></html>"
    )


def build_report_payload(
    db: Session,
    *,
    generated_by: str,
    scope_type: str = ReportScopeType.ORGANIZATION.value,
    scope_id: str | None = None,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
    period_days: int = 30,
) -> dict[str, Any]:
    summary = get_summary(db)
    inventory = get_inventory(db)
    risk = get_risk_posture(db)
    assurance = get_assurance_posture(db)
    controls = get_control_posture(db)
    incidents = get_incident_posture(db)
    runtime = get_runtime_activity(db, period_days=period_days)
    evidence = get_evidence_completeness(db)
    changes = get_change_feed(db, period_days=period_days)
    attention = build_attention_queue(db)

    if scope_type == ReportScopeType.AI_SYSTEM.value and scope_id:
        inventory["items"] = [
            i for i in inventory["items"] if i["ai_system_id"] == scope_id
        ]
        inventory["count"] = len(inventory["items"])
    elif scope_type == ReportScopeType.BUSINESS_UNIT.value and scope_id:
        inventory["items"] = [
            i for i in inventory["items"] if (i.get("business_unit") or "") == scope_id
        ]
        inventory["count"] = len(inventory["items"])

    generated_at = _utcnow()
    snapshot = {
        "title": "Organization AI Portfolio Transparency Report",
        "scope_type": scope_type,
        "scope_id": scope_id,
        "period_start": _ser_dt(period_start),
        "period_end": _ser_dt(period_end),
        "period_days": period_days,
        "generated_at": _ser_dt(generated_at),
        "generated_by": generated_by,
        "schema_version": SCHEMA_VERSION,
        "executive_summary": summary,
        "ai_inventory": {
            "count": inventory["count"],
            "items": [
                {
                    "ai_system_id": i["ai_system_id"],
                    "name": i["name"],
                    "business_unit": i.get("business_unit"),
                    "risk": i.get("risk"),
                    "assurance": i.get("assurance"),
                    "controls": i.get("controls"),
                    "open_incidents": i.get("open_incidents"),
                }
                for i in inventory["items"]
            ],
        },
        "risk_posture": {
            "by_severity": risk.get("by_severity"),
            "by_category": risk.get("by_category"),
            "heatmaps": risk.get("heatmaps"),
            "methodology": risk.get("methodology"),
        },
        "assurance_posture": {
            "by_status": assurance.get("by_status"),
            "expiring_in_30_days": assurance.get("expiring_in_30_days"),
            "invalid_or_expired_production": assurance.get(
                "invalid_or_expired_production"
            ),
            "disclaimer": assurance.get("disclaimer"),
        },
        "control_coverage": {
            "by_status": controls.get("by_status"),
            "repeated_control_gaps": controls.get("repeated_control_gaps"),
            "disclaimer": controls.get("disclaimer"),
        },
        "runtime_governance": runtime.get("metrics"),
        "incidents": {
            "open_incidents": incidents.get("open_incidents"),
            "critical_incidents": incidents.get("critical_incidents"),
            "by_category": incidents.get("by_category"),
        },
        "exceptions_waivers": {
            "active_exceptions": incidents.get("active_exceptions"),
            "expiring_exceptions": incidents.get("expiring_exceptions"),
            "active_evaluation_waivers": incidents.get("active_evaluation_waivers"),
            "expiring_waivers": incidents.get("expiring_waivers"),
        },
        "evidence_quality": evidence.get("metrics"),
        "material_changes": changes.get("items", [])[:50],
        "priority_actions": {
            "count": attention.get("count"),
            "items": attention.get("items", [])[:50],
        },
        "data_minimization": {
            "includes_full_prompts": False,
            "includes_full_outputs": False,
            "includes_sensitive_tool_payloads": False,
        },
    }

    # Manifest of important source object IDs (aggregated, not full payloads)
    source_manifest = {
        "ai_system_ids": [i["ai_system_id"] for i in inventory["items"]],
        "attention_source_ids": [
            {"source_type": a["source_type"], "source_id": a["source_id"]}
            for a in attention.get("items", [])[:100]
        ],
        "open_incident_ids": [i["id"] for i in incidents.get("items", [])],
        "schema_version": SCHEMA_VERSION,
        "freshness": Freshness.SNAPSHOT.value,
    }
    digest_input = {"data_snapshot": snapshot, "source_manifest": source_manifest}
    digest = content_digest(digest_input)
    snapshot["content_digest"] = digest
    return {
        "data_snapshot": snapshot,
        "source_manifest": source_manifest,
        "content_digest": digest,
        "generated_at": generated_at,
        "report_html": _build_html(snapshot, digest),
    }


def persist_report(
    db: Session,
    *,
    generated_by: str,
    scope_type: str = ReportScopeType.ORGANIZATION.value,
    scope_id: str | None = None,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
    period_days: int = 30,
    include_html: bool = True,
) -> PortfolioReport:
    built = build_report_payload(
        db,
        generated_by=generated_by,
        scope_type=scope_type,
        scope_id=scope_id,
        period_start=period_start,
        period_end=period_end,
        period_days=period_days,
    )
    report = PortfolioReport(
        scope_type=scope_type,
        scope_id=scope_id,
        period_start=period_start,
        period_end=period_end,
        generated_at=built["generated_at"],
        generated_by=generated_by,
        schema_version=SCHEMA_VERSION,
        title=built["data_snapshot"]["title"],
        data_snapshot=built["data_snapshot"],
        source_manifest=built["source_manifest"],
        content_digest=built["content_digest"],
        report_html=built["report_html"] if include_html else None,
    )
    db.add(report)
    db.flush()
    return report


def serialize_report(
    report: PortfolioReport, *, include_html: bool = False
) -> dict[str, Any]:
    payload = {
        "id": str(report.id),
        "scope_type": report.scope_type,
        "scope_id": report.scope_id,
        "period_start": _ser_dt(report.period_start),
        "period_end": _ser_dt(report.period_end),
        "generated_at": _ser_dt(report.generated_at),
        "generated_by": report.generated_by,
        "schema_version": report.schema_version,
        "title": report.title,
        "content_digest": report.content_digest,
        "data_snapshot": report.data_snapshot,
        "source_manifest": report.source_manifest,
        "freshness": Freshness.SNAPSHOT.value,
    }
    if include_html:
        payload["report_html"] = report.report_html
    return payload


def get_report(
    db: Session,
    report_id: UUID,
    *,
    include_html: bool = False,
) -> dict[str, Any]:
    report = db.query(PortfolioReport).filter(PortfolioReport.id == report_id).first()
    if report is None:
        raise PortfolioNotFoundError(f"Portfolio report {report_id} not found")
    return serialize_report(report, include_html=include_html)


def list_reports(
    db: Session,
    *,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    q = db.query(PortfolioReport).order_by(PortfolioReport.generated_at.desc())
    total = q.count()
    rows = q.offset(offset).limit(limit).all()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "id": str(r.id),
                "title": r.title,
                "scope_type": r.scope_type,
                "scope_id": r.scope_id,
                "generated_at": _ser_dt(r.generated_at),
                "generated_by": r.generated_by,
                "content_digest": r.content_digest,
                "schema_version": r.schema_version,
            }
            for r in rows
        ],
    }
