"""WP9 Portfolio service — read aggregations + report/decision mutations."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from rai_gateway.core.observability import log_siem_event
from rai_gateway.models.portfolio import (
    ExecutiveGovernanceDecision,
    PortfolioReportSchedule,
)
from rai_gateway.portfolio import attention as attention_mod
from rai_gateway.portfolio import projections as projections_mod
from rai_gateway.portfolio import queries
from rai_gateway.portfolio import reports as reports_mod
from rai_gateway.portfolio.domain import (
    ExecutiveDecision,
    Freshness,
    ReportCadence,
    ReportScopeType,
)
from rai_gateway.portfolio.errors import (
    PortfolioConflictError,
    PortfolioNotFoundError,
)
from rai_gateway.portfolio.queries import _ser_dt


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PortfolioService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_summary(self) -> dict[str, Any]:
        return queries.get_summary(self._db)

    def get_inventory(self, **filters: Any) -> dict[str, Any]:
        return queries.get_inventory(self._db, **filters)

    def get_risk(self) -> dict[str, Any]:
        return queries.get_risk_posture(self._db)

    def get_assurance(self) -> dict[str, Any]:
        return queries.get_assurance_posture(self._db)

    def get_controls(self) -> dict[str, Any]:
        return queries.get_control_posture(self._db)

    def get_incidents(self) -> dict[str, Any]:
        return queries.get_incident_posture(self._db)

    def get_runtime_activity(self, *, period_days: int = 30) -> dict[str, Any]:
        return queries.get_runtime_activity(self._db, period_days=period_days)

    def get_evidence(self) -> dict[str, Any]:
        return queries.get_evidence_completeness(self._db)

    def get_ownership(self) -> dict[str, Any]:
        return queries.get_ownership_view(self._db)

    def get_attention(self, *, limit: int = 200) -> dict[str, Any]:
        return attention_mod.build_attention_queue(self._db, limit=limit)

    def get_trends(self, *, period_days: int = 30) -> dict[str, Any]:
        return queries.get_trends(self._db, period_days=period_days)

    def get_changes(self, *, period_days: int = 30, limit: int = 100) -> dict[str, Any]:
        return queries.get_change_feed(self._db, period_days=period_days, limit=limit)

    def get_dashboard(self) -> dict[str, Any]:
        summary = self.get_summary()
        attention = self.get_attention(limit=25)
        risk = self.get_risk()
        assurance = self.get_assurance()
        controls = self.get_controls()
        runtime = self.get_runtime_activity(period_days=30)
        changes = self.get_changes(period_days=30, limit=20)
        now = _utcnow()
        expiring = [
            i
            for i in attention.get("items", [])
            if i.get("type")
            in (
                "ASSURANCE_EXPIRING",
                "EXPIRING_EXCEPTION",
                "EXPIRING_WAIVER",
            )
        ]
        return {
            "freshness": Freshness.LIVE.value,
            "last_refreshed_at": _ser_dt(now),
            "period_days": 30,
            "kpis": {
                "ai_systems": summary["metrics"]["total_ai_systems"],
                "critical_risk": summary["metrics"]["critical_risk_systems"]
                + summary["metrics"]["high_risk_systems"],
                "invalid_assurance": summary["metrics"]["expired_assurance"]
                + summary["metrics"]["failed_assurance"],
                "critical_incidents": summary["metrics"]["critical_incidents"],
                "attention": attention.get("count", 0),
            },
            "summary": summary,
            "risk_posture": {
                "by_severity": risk.get("by_severity"),
                "heatmaps": risk.get("heatmaps"),
            },
            "assurance_posture": {
                "by_status": assurance.get("by_status"),
                "expiring_in_30_days": assurance.get("expiring_in_30_days"),
            },
            "control_coverage": {"by_status": controls.get("by_status")},
            "runtime_activity": runtime.get("metrics"),
            "attention": attention,
            "recent_changes": changes.get("items", []),
            "upcoming_expiries": expiring[:20],
        }

    # --- Reports ----------------------------------------------------------

    def generate_report(
        self,
        *,
        generated_by: str,
        scope_type: str = ReportScopeType.ORGANIZATION.value,
        scope_id: str | None = None,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
        period_days: int = 30,
        include_html: bool = True,
    ) -> dict[str, Any]:
        if scope_type not in {s.value for s in ReportScopeType}:
            raise PortfolioConflictError(f"Invalid scope_type: {scope_type}")
        report = reports_mod.persist_report(
            self._db,
            generated_by=generated_by,
            scope_type=scope_type,
            scope_id=scope_id,
            period_start=period_start,
            period_end=period_end,
            period_days=period_days,
            include_html=include_html,
        )
        self._db.commit()
        log_siem_event(
            trace_id=str(report.id),
            event_type="portfolio.report.generated",
            decision="allow",
            metadata={
                "report_id": str(report.id),
                "digest": report.content_digest,
                "generated_by": generated_by,
            },
        )
        return reports_mod.serialize_report(report, include_html=include_html)

    def list_reports(self, *, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        return reports_mod.list_reports(self._db, limit=limit, offset=offset)

    def get_report(
        self,
        report_id: UUID,
        *,
        include_html: bool = False,
    ) -> dict[str, Any]:
        return reports_mod.get_report(
            self._db,
            report_id,
            include_html=include_html,
        )

    def create_report_schedule(
        self,
        *,
        cadence: str,
        created_by: str,
        scope_type: str = ReportScopeType.ORGANIZATION.value,
        scope_id: str | None = None,
        enabled: bool = True,
        delivery: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if cadence not in {c.value for c in ReportCadence}:
            raise PortfolioConflictError(f"Invalid cadence: {cadence}")
        existing = (
            self._db.query(PortfolioReportSchedule)
            .filter(
                PortfolioReportSchedule.cadence == cadence,
                PortfolioReportSchedule.scope_type == scope_type,
                PortfolioReportSchedule.scope_id == scope_id,
            )
            .first()
        )
        if existing:
            raise PortfolioConflictError("Matching report schedule already exists")

        days = {"WEEKLY": 7, "MONTHLY": 30, "QUARTERLY": 90}[cadence]
        schedule = PortfolioReportSchedule(
            cadence=cadence,
            scope_type=scope_type,
            scope_id=scope_id,
            enabled=enabled,
            next_run_at=_utcnow() + timedelta(days=days),
            delivery=delivery,
            created_by=created_by,
        )
        self._db.add(schedule)
        self._db.commit()
        self._db.refresh(schedule)
        log_siem_event(
            trace_id=str(schedule.id),
            event_type="portfolio.report.schedule_created",
            decision="allow",
            metadata={
                "schedule_id": str(schedule.id),
                "cadence": cadence,
                "created_by": created_by,
            },
        )
        return self._serialize_schedule(schedule)

    def list_report_schedules(self) -> dict[str, Any]:
        rows = (
            self._db.query(PortfolioReportSchedule)
            .order_by(PortfolioReportSchedule.created_at.desc())
            .all()
        )
        return {
            "items": [self._serialize_schedule(r) for r in rows],
        }

    def update_report_schedule(
        self,
        schedule_id: UUID,
        *,
        enabled: bool | None = None,
        delivery: dict[str, Any] | None = None,
        updated_by: str,
    ) -> dict[str, Any]:
        schedule = (
            self._db.query(PortfolioReportSchedule)
            .filter(PortfolioReportSchedule.id == schedule_id)
            .first()
        )
        if schedule is None:
            raise PortfolioNotFoundError(f"Schedule {schedule_id} not found")
        if enabled is not None:
            schedule.enabled = enabled
        if delivery is not None:
            schedule.delivery = delivery
        self._db.commit()
        self._db.refresh(schedule)
        log_siem_event(
            trace_id=str(schedule.id),
            event_type="portfolio.report.schedule_updated",
            decision="allow",
            metadata={
                "schedule_id": str(schedule.id),
                "updated_by": updated_by,
                "enabled": schedule.enabled,
            },
        )
        return self._serialize_schedule(schedule)

    # --- Executive decisions ----------------------------------------------

    def create_decision(
        self,
        *,
        scope_type: str,
        scope_id: str,
        decision: str,
        reason: str,
        actor: str,
        actor_role: str | None = None,
        evidence_refs: list[Any] | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if decision not in {d.value for d in ExecutiveDecision}:
            raise PortfolioConflictError(f"Invalid decision: {decision}")

        domain_actions = {
            ExecutiveDecision.SUSPEND.value: [
                "Execute suspension via WP2/WP6 authoritative controls"
            ],
            ExecutiveDecision.REQUIRE_REASSESSMENT.value: [
                "Trigger reassessment via WP7"
            ],
            ExecutiveDecision.RETIRE.value: ["Retire via WP1 lifecycle transition"],
            ExecutiveDecision.CONSTRAIN.value: [
                "Apply runtime constraints via WP4/WP6"
            ],
            ExecutiveDecision.PRIORITIZE_REMEDIATION.value: [
                "Track remediation via WP6 findings / WP8 incidents"
            ],
            ExecutiveDecision.CONTINUE.value: ["No domain mutation required"],
        }.get(decision, [])

        row = ExecutiveGovernanceDecision(
            scope_type=scope_type,
            scope_id=scope_id,
            decision=decision,
            reason=reason,
            actor=actor,
            actor_role=actor_role,
            evidence_refs=evidence_refs,
            recommended_domain_actions=domain_actions,
        )
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        log_siem_event(
            trace_id=str(row.id),
            event_type="portfolio.executive_decision.created",
            decision="allow",
            metadata={
                "decision_id": str(row.id),
                "decision": decision,
                "actor": actor,
            },
        )
        return self._serialize_decision(row)

    def list_decisions(self, *, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        q = self._db.query(ExecutiveGovernanceDecision).order_by(
            ExecutiveGovernanceDecision.created_at.desc()
        )
        total = q.count()
        rows = q.offset(offset).limit(limit).all()
        return {
            "total": total,
            "items": [self._serialize_decision(r) for r in rows],
        }

    def refresh_projection(self, projection_key: str = "summary") -> dict[str, Any]:
        summary = self.get_summary()
        return projections_mod.refresh_projection(
            self._db,
            projection_key,
            summary,
            freshness=Freshness.NEAR_REAL_TIME,
        )

    def export_portfolio(self, *, exported_by: str) -> dict[str, Any]:
        """Aggregated metadata export (data-minimized)."""
        payload = {
            "exported_at": _ser_dt(_utcnow()),
            "exported_by": exported_by,
            "summary": self.get_summary(),
            "inventory": self.get_inventory(),
            "attention": self.get_attention(limit=100),
        }
        # Strip any accidental deep payloads
        for item in payload["inventory"].get("items", []):
            item.pop("drill_down", None)
        log_siem_event(
            trace_id=exported_by,
            event_type="portfolio.exported",
            decision="allow",
            metadata={
                "exported_by": exported_by,
                "system_count": payload["summary"]["metrics"]["total_ai_systems"],
            },
        )
        return payload

    @staticmethod
    def _serialize_schedule(schedule: PortfolioReportSchedule) -> dict[str, Any]:
        return {
            "id": str(schedule.id),
            "cadence": schedule.cadence,
            "scope_type": schedule.scope_type,
            "scope_id": schedule.scope_id,
            "enabled": schedule.enabled,
            "next_run_at": _ser_dt(schedule.next_run_at),
            "last_run_at": _ser_dt(schedule.last_run_at),
            "last_report_id": str(schedule.last_report_id)
            if schedule.last_report_id
            else None,
            "delivery": schedule.delivery,
            "created_by": schedule.created_by,
            "created_at": _ser_dt(schedule.created_at),
            "updated_at": _ser_dt(schedule.updated_at),
        }

    @staticmethod
    def _serialize_decision(row: ExecutiveGovernanceDecision) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "scope_type": row.scope_type,
            "scope_id": row.scope_id,
            "decision": row.decision,
            "reason": row.reason,
            "actor": row.actor,
            "actor_role": row.actor_role,
            "evidence_refs": row.evidence_refs,
            "recommended_domain_actions": row.recommended_domain_actions,
            "created_at": _ser_dt(row.created_at),
            "note": "Decision is recorded in WP9; execute mutations in authoritative WP1–WP8 domains.",
        }
