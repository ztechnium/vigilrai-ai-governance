"""WP9 portfolio transparency & executive oversight DoD tests."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from rai_gateway.evaluations.domain import AssuranceStatus
from rai_gateway.governance.domain import (
    GovernanceRole,
    IncidentSeverity,
    MembershipStatus,
)
from rai_gateway.governance.service import GovernanceService
from rai_gateway.models.evaluations import AssuranceRecord
from rai_gateway.models.governance import PeriodicReviewSchedule
from rai_gateway.models.registry import RiskAssessment
from rai_gateway.portfolio.service import PortfolioService
from rai_gateway.registry.domain import AISystemStatus
from rai_gateway.registry.service import RegistryService

_ACCOUNTABILITY_ROLES = (
    GovernanceRole.BUSINESS_OWNER,
    GovernanceRole.TECHNICAL_OWNER,
    GovernanceRole.RAI_OFFICER,
)


@pytest.fixture()
def gov(db_session) -> GovernanceService:
    return GovernanceService(db_session)


@pytest.fixture()
def registry(db_session) -> RegistryService:
    return RegistryService(db_session)


@pytest.fixture()
def portfolio(db_session) -> PortfolioService:
    return PortfolioService(db_session)


def _org(gov: GovernanceService) -> dict:
    suffix = uuid.uuid4().hex[:8]
    memberships: dict[str, dict] = {}
    for role in _ACCOUNTABILITY_ROLES:
        memberships[role.value] = gov.create_membership(
            user_id=f"user-{role.value.lower()}-{suffix}",
            role=role.value,
            created_by="tester",
            status=MembershipStatus.ACTIVE.value,
        )
    return {"suffix": suffix, "org_id": uuid.uuid4(), "memberships": memberships}


def _linked_system(
    registry: RegistryService,
    gov: GovernanceService,
    org_id: UUID,
    *,
    name: str | None = None,
    business_unit: str = "Sales",
    risk_tier: str | None = None,
) -> dict:
    suffix = uuid.uuid4().hex[:8]
    system = registry.create_ai_system(
        system_key=f"wp9-sys-{suffix}",
        name=name or f"WP9 System {suffix}",
        created_by="tester",
        business_unit=business_unit,
    )
    for status in (AISystemStatus.UNDER_REVIEW, AISystemStatus.APPROVED):
        registry.transition_ai_system(system.id, status.value, updated_by="tester")
    gov.link_ai_system(system.id, "tester")

    if risk_tier:
        ra = RiskAssessment(
            ai_system_id=system.id,
            status="COMPLETE",
            risk_tier=risk_tier,
            assessed_by="tester",
            assessed_at=datetime.now(timezone.utc),
        )
        registry._db.add(ra)
        registry._db.flush()

    return {"system": system, "id": system.id}


def _set_assurance(
    db_session,
    *,
    ai_system_id: UUID,
    status: str,
    valid_until: datetime | None = None,
    agent_version_id: UUID | None = None,
) -> AssuranceRecord:
    # Need an agent version — create a minimal stub via registry if needed
    from rai_gateway.models.registry import Agent, AgentVersion

    agent = db_session.query(Agent).filter(Agent.ai_system_id == ai_system_id).first()
    if agent is None:
        agent = Agent(
            agent_key=f"agent-{uuid.uuid4().hex[:8]}",
            ai_system_id=ai_system_id,
            name="Test Agent",
            created_by="tester",
            status="APPROVED",
        )
        db_session.add(agent)
        db_session.flush()
    if agent_version_id is None:
        version = AgentVersion(
            agent_id=agent.id,
            version_number=1,
            lifecycle_status="APPROVED",
            created_by="tester",
        )
        db_session.add(version)
        db_session.flush()
        agent.current_version_id = version.id
        agent_version_id = version.id

    rec = AssuranceRecord(
        ai_system_id=ai_system_id,
        agent_version_id=agent_version_id,
        environment="PRODUCTION",
        status=status,
        valid_from=datetime.now(timezone.utc) - timedelta(days=30),
        valid_until=valid_until,
        created_by="tester",
    )
    db_session.add(rec)
    db_session.flush()
    return rec


def test_portfolio_summary_aggregation(
    gov: GovernanceService,
    registry: RegistryService,
    portfolio: PortfolioService,
    db_session,
):
    ctx = _org(gov)
    org_id = ctx["org_id"]

    sales = _linked_system(
        registry,
        gov,
        org_id,
        name="WhatsApp Sales AI",
        business_unit="Sales",
        risk_tier="HIGH",
    )
    support = _linked_system(
        registry,
        gov,
        org_id,
        name="Customer Support AI",
        business_unit="Support",
        risk_tier="LOW",
    )
    knowledge = _linked_system(
        registry,
        gov,
        org_id,
        name="Internal Knowledge Assistant",
        business_unit="Ops",
        risk_tier="MEDIUM",
    )

    _set_assurance(
        db_session,
        ai_system_id=sales["id"],
        status=AssuranceStatus.CONDITIONAL.value,
        valid_until=datetime.now(timezone.utc) + timedelta(days=60),
    )
    _set_assurance(
        db_session,
        ai_system_id=support["id"],
        status=AssuranceStatus.VALID.value,
        valid_until=datetime.now(timezone.utc) + timedelta(days=120),
    )
    _set_assurance(
        db_session,
        ai_system_id=knowledge["id"],
        status=AssuranceStatus.VALID.value,
        valid_until=datetime.now(timezone.utc) + timedelta(days=5),
    )

    gov.request_exception(
        sales["id"],
        business_justification="Pilot exception",
        requester=ctx["memberships"][GovernanceRole.BUSINESS_OWNER.value]["user_id"],
        risk="MEDIUM",
    )
    # Approve exception for open_exceptions count
    exceptions = gov.list_exceptions()
    assert exceptions
    gov.approve_exception(
        UUID(exceptions[0]["id"]),
        approver=ctx["memberships"][GovernanceRole.RAI_OFFICER.value]["user_id"],
        decision_reason="Approved for pilot",
        valid_until=datetime.now(timezone.utc) + timedelta(days=30),
    )

    schedule = PeriodicReviewSchedule(
        ai_system_id=knowledge["id"],
        frequency_days=90,
        next_due_at=datetime.now(timezone.utc) - timedelta(days=2),
        enabled=True,
        created_by="tester",
    )
    db_session.add(schedule)
    db_session.flush()

    summary = portfolio.get_summary()
    metrics = summary["metrics"]
    assert metrics["total_ai_systems"] >= 3
    assert metrics["high_risk_systems"] >= 1
    assert metrics["conditional_assurance"] >= 1
    assert metrics["open_exceptions"] >= 1
    assert metrics["overdue_reviews"] >= 1
    assert summary["freshness"] == "LIVE"

    inventory = portfolio.get_inventory()
    assert inventory["count"] >= 3
    names = {i["name"] for i in inventory["items"]}
    assert "WhatsApp Sales AI" in names

    assurance = portfolio.get_assurance()
    assert len(assurance["expiring_in_7_days"]) >= 1

    attention = portfolio.get_attention()
    types = {i["type"] for i in attention["items"]}
    assert "ASSURANCE_EXPIRING" in types or "OVERDUE_GOVERNANCE_REVIEW" in types
    assert all("recommended_action" in i for i in attention["items"])
    assert all("drill_down" in i for i in attention["items"])


def test_risk_assurance_control_incident_aggregations(
    gov: GovernanceService,
    registry: RegistryService,
    portfolio: PortfolioService,
    db_session,
):
    ctx = _org(gov)
    org_id = ctx["org_id"]
    system = _linked_system(registry, gov, org_id, risk_tier="CRITICAL")

    risk = portfolio.get_risk()
    assert risk["by_system"]
    assert "heatmaps" in risk
    assert risk["methodology"]["aggregate_score"] is None

    _set_assurance(
        db_session,
        ai_system_id=system["id"],
        status=AssuranceStatus.EXPIRED.value,
        valid_until=datetime.now(timezone.utc) - timedelta(days=1),
    )
    assurance = portfolio.get_assurance()
    assert assurance["by_status"].get(AssuranceStatus.EXPIRED.value, 0) >= 1
    assert "disclaimer" in assurance

    controls = portfolio.get_controls()
    assert "disclaimer" in controls
    assert (
        "≠ certification" in controls["disclaimer"]
        or "certification" in controls["disclaimer"].lower()
    )

    gov.create_incident(
        system["id"],
        title="Critical outage",
        reported_by="tester",
        severity=IncidentSeverity.CRITICAL.value,
        category="MODEL_BEHAVIOR",
    )
    incidents = portfolio.get_incidents()
    assert incidents["open_incidents"] >= 1
    assert incidents["critical_incidents"] >= 1
    assert incidents["sla_compliance_claimed"] is False

    runtime = portfolio.get_runtime_activity(period_days=30)
    assert "metrics" in runtime
    assert runtime["note"]

    evidence = portfolio.get_evidence()
    assert "metrics" in evidence

    ownership = portfolio.get_ownership()
    assert "by_business_unit" in ownership


def test_trends_change_feed_and_attention_expiry(
    gov: GovernanceService,
    registry: RegistryService,
    portfolio: PortfolioService,
    db_session,
):
    ctx = _org(gov)
    org_id = ctx["org_id"]
    system = _linked_system(registry, gov, org_id, risk_tier="HIGH")

    _set_assurance(
        db_session,
        ai_system_id=system["id"],
        status=AssuranceStatus.VALID.value,
        valid_until=datetime.now(timezone.utc) + timedelta(days=3),
    )

    trends = portfolio.get_trends(period_days=30)
    assert trends["trends"]["ai_system_count"] >= 1

    changes = portfolio.get_changes(period_days=30)
    assert changes["count"] >= 1
    assert any(c["type"] == "new_ai_system" for c in changes["items"])

    attention = portfolio.get_attention()
    assert any(i["type"] == "ASSURANCE_EXPIRING" for i in attention["items"])


def test_report_snapshot_immutability_and_digest(
    gov: GovernanceService,
    registry: RegistryService,
    portfolio: PortfolioService,
    db_session,
):
    ctx = _org(gov)
    org_id = ctx["org_id"]
    system = _linked_system(
        registry, gov, org_id, name="Report System", risk_tier="LOW"
    )
    _set_assurance(
        db_session,
        ai_system_id=system["id"],
        status=AssuranceStatus.VALID.value,
        valid_until=datetime.now(timezone.utc) + timedelta(days=90),
    )

    report = portfolio.generate_report(
        generated_by="tester",
        period_days=30,
        include_html=True,
    )
    assert report["content_digest"]
    assert report["data_snapshot"]["schema_version"] == "1.0"
    assert report["source_manifest"]
    assert "executive_summary" in report["data_snapshot"]
    digest_before = report["content_digest"]
    snapshot_before = report["data_snapshot"]
    systems_before = snapshot_before["executive_summary"]["metrics"]["total_ai_systems"]

    # Mutate live state
    _linked_system(
        registry, gov, org_id, name="Post-report System", risk_tier="CRITICAL"
    )
    live = portfolio.get_summary()
    assert live["metrics"]["total_ai_systems"] == systems_before + 1

    historical = portfolio.get_report(UUID(report["id"]))
    assert historical["content_digest"] == digest_before
    assert historical["data_snapshot"] == snapshot_before
    assert (
        historical["data_snapshot"]["executive_summary"]["metrics"]["total_ai_systems"]
        == systems_before
    )


def test_report_schedule_and_executive_decision(
    gov: GovernanceService, portfolio: PortfolioService
):
    _org(gov)

    schedule = portfolio.create_report_schedule(
        cadence="MONTHLY",
        created_by="tester",
    )
    assert schedule["cadence"] == "MONTHLY"
    assert schedule["enabled"] is True

    schedules = portfolio.list_report_schedules()
    assert len(schedules["items"]) == 1

    updated = portfolio.update_report_schedule(
        UUID(schedule["id"]),
        enabled=False,
        updated_by="tester",
    )
    assert updated["enabled"] is False

    decision = portfolio.create_decision(
        scope_type="AI_SYSTEM",
        scope_id=str(uuid.uuid4()),
        decision="PRIORITIZE_REMEDIATION",
        reason="Critical findings require remediation priority",
        actor="exec-1",
        actor_role="rai_officer",
    )
    assert decision["decision"] == "PRIORITIZE_REMEDIATION"
    assert decision["recommended_domain_actions"]
    assert "WP" in decision["note"] or "authoritative" in decision["note"]


def test_projection_idempotency(
    gov: GovernanceService, portfolio: PortfolioService, db_session
):
    _org(gov)
    first = portfolio.refresh_projection(projection_key="summary")
    db_session.commit()
    second = portfolio.refresh_projection(projection_key="summary")
    db_session.commit()
    assert first["payload_digest"] == second["payload_digest"]
    assert second["refresh_count"] == first["refresh_count"]


def test_portfolio_rbac_permissions(db_session):
    from fastapi import HTTPException

    from rai_gateway.core.auth import AdminIdentity
    from rai_gateway.services.admin_console import require_admin_permission

    def _as(role: str) -> AdminIdentity:
        return AdminIdentity(email=f"{role}@example.com", user_id=role, roles=[role])

    require_admin_permission(
        db_session, "portfolio:read", "rai_officer", identity=_as("rai_officer")
    )
    require_admin_permission(
        db_session, "portfolio:report", "rai_officer", identity=_as("rai_officer")
    )
    require_admin_permission(
        db_session, "portfolio:decision", "rai_officer", identity=_as("rai_officer")
    )

    require_admin_permission(
        db_session, "portfolio:read", "auditor", identity=_as("auditor")
    )
    require_admin_permission(
        db_session, "portfolio:report", "auditor", identity=_as("auditor")
    )
    with pytest.raises(HTTPException) as denied:
        require_admin_permission(
            db_session, "portfolio:decision", "auditor", identity=_as("auditor")
        )
    assert denied.value.status_code == 403

    require_admin_permission(
        db_session, "portfolio:read", "risk_officer", identity=_as("risk_officer")
    )
    with pytest.raises(HTTPException) as no_report:
        require_admin_permission(
            db_session, "portfolio:report", "risk_officer", identity=_as("risk_officer")
        )
    assert no_report.value.status_code == 403

    require_admin_permission(
        db_session,
        "portfolio:read",
        "business_approver",
        identity=_as("business_approver"),
    )
    require_admin_permission(
        db_session,
        "portfolio:executive",
        "business_approver",
        identity=_as("business_approver"),
    )
