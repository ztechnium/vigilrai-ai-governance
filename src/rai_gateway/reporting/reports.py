"""Report payload composition."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from rai_gateway.models.approval import ApprovalRequest
from rai_gateway.models.evaluations import (
    AssuranceRecord,
    DeploymentGateEvaluation,
    EvaluationWaiver,
)
from rai_gateway.models.evidence import RuntimeConversation, RuntimeTrajectory
from rai_gateway.models.finops import UsageReservation, UsageSettlement
from rai_gateway.models.governance import GovernanceException
from rai_gateway.models.registry import AISystem, RiskAssessment
from rai_gateway.models.risk_intelligence import RuntimeBudgetCheck, RuntimeRiskFinding
from rai_gateway.models.runtime_enforcement import RuntimeEnforcementReceipt
from rai_gateway.reporting import metrics, queries, trends
from rai_gateway.reporting.filters import (
    calculate_change_pct,
    get_default_period,
    get_previous_period,
    get_trend_direction,
)
from rai_gateway.reporting.schemas import (
    AISystemReport,
    AssuranceReport,
    AttentionItem,
    BudgetReport,
    BudgetStatus,
    ConversationReport,
    EffectDistribution,
    Freshness,
    FreshnessMode,
    PolicyReport,
    RankedItem,
    ReportPeriod,
    ReportScope,
    ReportSummary,
    RiskReport,
    RuntimeReport,
    SeverityDistribution,
)

if TYPE_CHECKING:
    from rai_gateway.reporting.schemas import ReportFilters

# Runtime findings use ACKNOWLEDGED and MONITORING; design-time findings use INVESTIGATING.
OPEN_FINDING_STATUSES = ["OPEN", "INVESTIGATING", "ACKNOWLEDGED", "MONITORING"]


def _severity_distribution(data: dict[str, int]) -> SeverityDistribution:
    return SeverityDistribution(
        critical=data.get("CRITICAL", 0),
        high=data.get("HIGH", 0),
        medium=data.get("MEDIUM", 0),
        low=data.get("LOW", 0),
        info=data.get("INFO", 0),
    )


def build_report_summary(
    db: Session,
    filters: ReportFilters,
) -> ReportSummary:
    """Build executive summary report."""
    # Determine period
    if filters.period_start and filters.period_end:
        start, end = filters.period_start, filters.period_end
    else:
        start, end = get_default_period(days=30)

    # Get previous period for comparison
    prev_start, prev_end = get_previous_period(start, end)

    # Set up previous period filters
    prev_filters = filters.model_copy()
    prev_filters.period_start = prev_start
    prev_filters.period_end = prev_end

    # AI Systems
    current_systems = queries.count_ai_systems(db, filters)
    prev_systems = queries.count_ai_systems(db, prev_filters)

    # Governed Actions
    current_actions = queries.count_governed_actions(db, filters)
    prev_actions = queries.count_governed_actions(db, prev_filters)

    # Risk Exposure (open findings)
    risk_filters = filters.model_copy()
    risk_filters.finding_status = list(OPEN_FINDING_STATUSES)
    current_risk = queries.count_risk_findings(db, risk_filters)
    prev_risk_filters = prev_filters.model_copy()
    prev_risk_filters.finding_status = list(OPEN_FINDING_STATUSES)
    prev_risk = queries.count_risk_findings(db, prev_risk_filters)

    # Policy Intervention Rate
    policy_triggers = queries.count_policy_triggers(db, filters)
    policy_evaluations = queries.count_policy_evaluations(db, filters)
    intervention_rate = metrics.calculate_rate(policy_triggers, policy_evaluations)

    prev_triggers = queries.count_policy_triggers(db, prev_filters)
    prev_evaluations = queries.count_policy_evaluations(db, prev_filters)
    prev_intervention_rate = metrics.calculate_rate(prev_triggers, prev_evaluations)

    # Budget Utilization
    budgets_data = queries.get_budget_utilization(db, filters)
    avg_utilization = (
        sum(b["utilization_pct"] for b in budgets_data) / len(budgets_data)
        if budgets_data
        else 0.0
    )

    # Assurance Coverage
    total_systems = queries.count_ai_systems(db, filters)
    systems_with_assurance = queries.count_assurance_records(
        db, filters, status_filter="VALID"
    )
    assurance_coverage = metrics.calculate_assurance_coverage(
        systems_with_assurance, total_systems
    )

    # Critical Findings
    critical_filters = filters.model_copy()
    critical_filters.risk_severity = ["CRITICAL"]
    critical_filters.finding_status = ["OPEN"]
    critical_findings = queries.count_risk_findings(db, critical_filters)

    # Severity Distribution
    severity_dist_data = queries.get_severity_distribution(db, risk_filters)

    # Effect Distribution
    effects_data = queries.get_effect_distribution(db, filters)

    # Build attention items
    attention_items = build_attention_items(db, filters)

    return ReportSummary(
        scope=ReportScope(
            ai_system_id=filters.ai_system_id,
            agent_id=filters.agent_id,
            runtime_identity_id=filters.runtime_identity_id,
        ),
        period=ReportPeriod(start=start, end=end),
        freshness=Freshness(
            mode=FreshnessMode.LIVE, last_refreshed_at=datetime.utcnow()
        ),
        ai_systems_governed=metrics.build_comparison_metric(
            current_systems, prev_systems
        ),
        governed_actions=metrics.build_comparison_metric(current_actions, prev_actions),
        current_risk_exposure=metrics.build_comparison_metric(current_risk, prev_risk),
        policy_intervention_rate=metrics.build_comparison_metric(
            intervention_rate, prev_intervention_rate
        ),
        budget_utilization_pct=metrics.build_comparison_metric(avg_utilization),
        assurance_coverage_pct=metrics.build_comparison_metric(assurance_coverage),
        open_critical_findings=metrics.build_comparison_metric(critical_findings),
        risk_by_severity=_severity_distribution(severity_dist_data),
        policy_effects=EffectDistribution(
            allow=effects_data.get("allow", 0),
            monitor=effects_data.get("monitor", 0),
            require_approval=effects_data.get("require_approval", 0),
            deny=effects_data.get("deny", 0),
            suspend=effects_data.get("suspend", 0),
        ),
        attention=attention_items,
    )


def build_risk_report(
    db: Session,
    filters: ReportFilters,
) -> RiskReport:
    """Build risk analysis report."""
    # Determine period
    if filters.period_start and filters.period_end:
        start, end = filters.period_start, filters.period_end
    else:
        start, end = get_default_period(days=30)

    # Open findings
    open_filters = filters.model_copy()
    open_filters.finding_status = list(OPEN_FINDING_STATUSES)
    open_findings = queries.count_risk_findings(db, open_filters)

    # New findings
    new_filters = filters.model_copy()
    new_filters.period_start = start
    new_filters.period_end = end
    new_findings = queries.count_risk_findings(db, new_filters)

    # Resolved findings
    # Note: Would need resolved_at timestamp for accurate count
    # For now, use difference between total and open as proxy
    total_findings = queries.count_risk_findings(db, filters)
    resolved_findings = max(0, total_findings - open_findings)

    # Critical and High findings
    critical_filters = filters.model_copy()
    critical_filters.risk_severity = ["CRITICAL"]
    critical_filters.finding_status = ["OPEN"]
    critical_findings = queries.count_risk_findings(db, critical_filters)

    high_filters = filters.model_copy()
    high_filters.risk_severity = ["HIGH"]
    high_filters.finding_status = ["OPEN"]
    high_findings = queries.count_risk_findings(db, high_filters)

    # Severity distribution
    severity_dist_data = queries.get_severity_distribution(db, open_filters)

    # Risk by AI System
    risk_by_system_data = queries.get_risk_by_ai_system(db, open_filters, limit=10)
    risk_by_ai_system = [
        RankedItem(
            id=system_id,
            name=name,
            value=finding_count,
            severity=highest_severity,
            link=f"/governance/registry/{system_id}",
        )
        for system_id, name, finding_count, highest_severity in risk_by_system_data
    ]

    # Trends
    finding_trends_data = trends.get_finding_trends(db, filters, start, end)

    # Attention items
    attention_items = build_attention_items(db, filters, risk_focused=True)

    return RiskReport(
        scope=ReportScope(
            ai_system_id=filters.ai_system_id,
            agent_id=filters.agent_id,
            runtime_identity_id=filters.runtime_identity_id,
        ),
        period=ReportPeriod(start=start, end=end),
        freshness=Freshness(
            mode=FreshnessMode.LIVE, last_refreshed_at=datetime.utcnow()
        ),
        open_findings=open_findings,
        new_findings=new_findings,
        resolved_findings=resolved_findings,
        critical_findings=critical_findings,
        high_findings=high_findings,
        severity_distribution=_severity_distribution(severity_dist_data),
        status_distribution=queries.get_finding_status_distribution(db, filters),
        risk_by_ai_system=risk_by_ai_system,
        finding_trends=finding_trends_data.get("new_findings", []),
        attention=attention_items,
    )


def build_policy_report(
    db: Session,
    filters: ReportFilters,
) -> PolicyReport:
    """Build policy effectiveness report."""
    # Determine period
    if filters.period_start and filters.period_end:
        start, end = filters.period_start, filters.period_end
    else:
        start, end = get_default_period(days=30)

    # Policy metrics
    evaluations = queries.count_policy_evaluations(db, filters)
    triggers = queries.count_policy_triggers(db, filters)
    trigger_rate = metrics.calculate_rate(triggers, evaluations)

    # Denied actions
    denied = queries.count_denied_actions(db, filters)
    deny_rate = metrics.calculate_rate(denied, evaluations)

    # Effect distribution
    effects_data = queries.get_effect_distribution(db, filters)

    # Intervention rate
    intervention_rate = metrics.calculate_intervention_rate(
        effects_data.get("monitor", 0),
        effects_data.get("require_approval", 0),
        effects_data.get("deny", 0),
        effects_data.get("suspend", 0),
        evaluations,
    )

    # Trends
    eval_trends = trends.get_policy_evaluation_trends(db, filters, start, end)
    trigger_trends = trends.get_policy_trigger_trends(db, filters, start, end)

    return PolicyReport(
        scope=ReportScope(
            ai_system_id=filters.ai_system_id,
            agent_id=filters.agent_id,
            runtime_identity_id=filters.runtime_identity_id,
        ),
        period=ReportPeriod(start=start, end=end),
        freshness=Freshness(
            mode=FreshnessMode.LIVE, last_refreshed_at=datetime.utcnow()
        ),
        evaluations=evaluations,
        triggers=triggers,
        trigger_rate=round(trigger_rate, 2),
        intervention_rate=round(intervention_rate, 2),
        deny_rate=round(deny_rate, 2),
        effects=EffectDistribution(
            allow=effects_data.get("allow", 0),
            monitor=effects_data.get("monitor", 0),
            require_approval=effects_data.get("require_approval", 0),
            deny=effects_data.get("deny", 0),
            suspend=effects_data.get("suspend", 0),
        ),
        evaluation_trends=eval_trends,
        trigger_trends=trigger_trends,
    )


def build_budget_report(
    db: Session,
    filters: ReportFilters,
) -> BudgetReport:
    """Build budget and cost report."""
    scoped, start, end = _with_default_period(filters)

    # Budget counts
    total_budgets = queries.count_budgets(db, scoped)
    budgets_warning = queries.count_budgets_by_status(db, scoped, "WARNING")
    budgets_exceeded = queries.count_budgets_by_status(db, scoped, "EXCEEDED")

    # Cost and tokens from the same metering spans trajectories display.
    total_cost = queries.get_total_cost(db, scoped)
    total_tokens = queries.get_total_tokens(db, scoped)
    cost_trends, token_trends = trends.get_spend_trends(db, scoped, start, end)

    # Budget details
    budgets_data = queries.get_budget_utilization(db, filters)
    budget_statuses = [
        BudgetStatus(
            id=b["id"],
            name=b["name"],
            metric=b["metric"],
            current_usage=b["current_usage"],
            limit_value=b["limit_value"],
            warning_threshold=b["warning_threshold"],
            utilization_pct=b["utilization_pct"],
            status=b["status"],
            window=b["window"],
        )
        for b in budgets_data
    ]

    return BudgetReport(
        scope=ReportScope(
            ai_system_id=filters.ai_system_id,
            agent_id=filters.agent_id,
            runtime_identity_id=filters.runtime_identity_id,
        ),
        period=ReportPeriod(start=start, end=end),
        freshness=Freshness(
            mode=FreshnessMode.LIVE, last_refreshed_at=datetime.utcnow()
        ),
        total_budgets=total_budgets,
        budgets_warning=budgets_warning,
        budgets_exceeded=budgets_exceeded,
        total_cost=round(total_cost, 2),
        total_tokens=total_tokens,
        budgets=budget_statuses,
        cost_trends=cost_trends,
        token_trends=token_trends,
    )


def build_ai_system_report(
    db: Session,
    ai_system_id: UUID,
    filters: ReportFilters,
) -> AISystemReport:
    """Build a live report for one AI system in the caller's organization."""
    system = (
        db.query(AISystem)
        .filter(
            AISystem.id == ai_system_id,
        )
        .first()
    )
    if system is None:
        raise LookupError("AI system not found")

    scoped = filters.model_copy()
    scoped.ai_system_id = ai_system_id
    if scoped.period_start and scoped.period_end:
        start, end = scoped.period_start, scoped.period_end
    else:
        start, end = get_default_period(days=30)
        scoped.period_start = start
        scoped.period_end = end

    open_filters = scoped.model_copy()
    open_filters.period_start = None
    open_filters.period_end = None
    open_filters.finding_status = list(OPEN_FINDING_STATUSES)

    critical_filters = open_filters.model_copy()
    critical_filters.risk_severity = ["CRITICAL"]
    critical_filters.finding_status = ["OPEN"]

    evaluations = queries.count_policy_evaluations(db, scoped)
    triggers = queries.count_policy_triggers(db, scoped)
    denied = queries.count_denied_actions(db, scoped)
    effects = queries.get_effect_distribution(db, scoped)
    budgets = queries.get_budget_utilization(db, scoped)

    prev_start, prev_end = get_previous_period(start, end)
    prev_filters = scoped.model_copy()
    prev_filters.period_start = prev_start
    prev_filters.period_end = prev_end
    prev_filters.finding_status = list(OPEN_FINDING_STATUSES)
    current_open = queries.count_risk_findings(db, open_filters)
    previous_open = queries.count_risk_findings(db, prev_filters)

    latest_score = (
        db.query(RiskAssessment.overall_score)
        .filter(RiskAssessment.ai_system_id == ai_system_id)
        .order_by(RiskAssessment.created_at.desc())
        .limit(1)
        .scalar()
    )
    latest_assurance = (
        db.query(AssuranceRecord.status)
        .filter(AssuranceRecord.ai_system_id == ai_system_id)
        .order_by(AssuranceRecord.created_at.desc())
        .limit(1)
        .scalar()
    )
    evidence_completeness = (
        db.query(func.avg(RuntimeTrajectory.completeness_pct))
        .filter(
            RuntimeTrajectory.ai_system_id == ai_system_id,
            RuntimeTrajectory.started_at >= start,
            RuntimeTrajectory.started_at <= end,
        )
        .scalar()
    )

    return AISystemReport(
        scope=ReportScope(
            ai_system_id=ai_system_id,
        ),
        period=ReportPeriod(start=start, end=end),
        freshness=Freshness(
            mode=FreshnessMode.LIVE, last_refreshed_at=datetime.utcnow()
        ),
        executions=queries.count_executions(db, scoped),
        conversations=queries.count_conversations(db, scoped),
        governed_actions=queries.count_governed_actions(db, scoped),
        execution_success_rate=round(queries.get_execution_success_rate(db, scoped), 2),
        open_findings=current_open,
        critical_findings=queries.count_risk_findings(db, critical_filters),
        risk_score=float(latest_score) if latest_score is not None else None,
        risk_trend=get_trend_direction(
            calculate_change_pct(current_open, previous_open)
        ),
        policy_trigger_rate=round(metrics.calculate_rate(triggers, evaluations), 2),
        deny_rate=round(metrics.calculate_rate(denied, evaluations), 2),
        approval_rate=round(
            metrics.calculate_rate(effects.get("require_approval", 0), evaluations), 2
        ),
        budget_usage=round(
            sum(item["current_usage"] or 0 for item in budgets) / len(budgets), 2
        )
        if budgets
        else 0.0,
        token_usage=queries.get_total_tokens(db, scoped),
        cost=round(queries.get_total_cost(db, scoped), 2),
        assurance_status=latest_assurance,
        evidence_completeness_pct=round(float(evidence_completeness), 2)
        if evidence_completeness is not None
        else None,
        incidents=queries.count_incidents(db, open_filters, status_filter="OPEN"),
        exceptions=queries.count_exceptions(db, open_filters, status_filter="APPROVED"),
        evaluation_waivers=queries.count_waivers(db, open_filters),
        risk_by_agent=[
            RankedItem(id=agent_id, name=name, value=count)
            for agent_id, name, count in queries.get_risk_by_agent(db, open_filters)
        ],
    )


def _with_default_period(
    filters: ReportFilters,
) -> tuple[ReportFilters, datetime, datetime]:
    scoped = filters.model_copy()
    if scoped.period_start and scoped.period_end:
        return scoped, scoped.period_start, scoped.period_end
    start, end = get_default_period(days=30)
    scoped.period_start = start
    scoped.period_end = end
    return scoped, start, end


def _scope_header(filters: ReportFilters, start: datetime, end: datetime):
    return (
        ReportScope(
            ai_system_id=filters.ai_system_id,
            agent_id=filters.agent_id,
            runtime_identity_id=filters.runtime_identity_id,
        ),
        ReportPeriod(start=start, end=end),
        Freshness(mode=FreshnessMode.LIVE, last_refreshed_at=datetime.utcnow()),
    )


def build_runtime_report(
    db: Session,
    filters: ReportFilters,
) -> RuntimeReport:
    """Build runtime governance activity for the organization."""
    scoped, start, end = _with_default_period(filters)
    scope, period, freshness = _scope_header(scoped, start, end)
    effects = queries.get_effect_distribution(db, scoped)
    return RuntimeReport(
        scope=scope,
        period=period,
        freshness=freshness,
        governed_actions=queries.count_governed_actions(db, scoped),
        executions=queries.count_executions(db, scoped),
        conversations=queries.count_conversations(db, scoped),
        execution_success_rate=round(queries.get_execution_success_rate(db, scoped), 2),
        policy_evaluations=queries.count_policy_evaluations(db, scoped),
        interventions=int(
            effects.get("monitor", 0)
            + effects.get("require_approval", 0)
            + effects.get("deny", 0)
            + effects.get("suspend", 0)
        ),
        approvals_required=int(effects.get("require_approval", 0)),
        denied=queries.count_denied_actions(db, scoped),
        runtime_suspensions=int(effects.get("suspend", 0)),
    )


def _count_gate_decisions(
    db: Session,
    filters: ReportFilters,
    decision: str | None = None,
) -> int:
    query = db.query(func.count(DeploymentGateEvaluation.id)).join(
        AISystem, DeploymentGateEvaluation.ai_system_id == AISystem.id
    )
    if decision is not None:
        query = query.filter(DeploymentGateEvaluation.decision == decision)
    if filters.ai_system_id:
        query = query.filter(
            DeploymentGateEvaluation.ai_system_id == filters.ai_system_id
        )
    return query.scalar() or 0


def _count_expiring(
    db: Session,
    model,
    filters: ReportFilters,
    *,
    approved_status: str,
) -> int:
    now = datetime.utcnow()
    horizon = now + timedelta(days=14)
    query = (
        db.query(func.count(model.id))
        .join(AISystem, model.ai_system_id == AISystem.id)
        .filter(
            model.status == approved_status,
            model.valid_until.isnot(None),
            model.valid_until >= now,
            model.valid_until <= horizon,
        )
    )
    if filters.ai_system_id:
        query = query.filter(model.ai_system_id == filters.ai_system_id)
    return query.scalar() or 0


def build_assurance_report(
    db: Session,
    filters: ReportFilters,
) -> AssuranceReport:
    """Build assurance coverage from assurance records, gates, waivers, and exceptions."""
    scoped, start, end = _with_default_period(filters)
    scope, period, freshness = _scope_header(scoped, start, end)
    total_systems = queries.count_ai_systems(db, scoped)
    valid = queries.count_assurance_records(db, scoped, status_filter="VALID")
    passed = _count_gate_decisions(db, scoped, "PASS")
    failed = _count_gate_decisions(db, scoped, "FAIL")
    scored = passed + failed
    open_exceptions = (
        db.query(func.count(GovernanceException.id))
        .join(AISystem, GovernanceException.ai_system_id == AISystem.id)
        .filter(
            GovernanceException.status.in_(["REQUESTED", "UNDER_REVIEW"]),
        )
    )
    if scoped.ai_system_id:
        open_exceptions = open_exceptions.filter(
            GovernanceException.ai_system_id == scoped.ai_system_id
        )
    return AssuranceReport(
        scope=scope,
        period=period,
        freshness=freshness,
        assurance_coverage_pct=round(
            metrics.calculate_assurance_coverage(valid, total_systems), 2
        ),
        valid_assurance=valid,
        conditional_assurance=queries.count_assurance_records(
            db, scoped, status_filter="CONDITIONAL"
        ),
        expired_assurance=queries.count_assurance_records(
            db, scoped, status_filter="EXPIRED"
        ),
        failed_assurance=queries.count_assurance_records(
            db, scoped, status_filter="FAILED"
        ),
        evaluation_pass_rate=round((passed / scored) * 100, 2) if scored else 0.0,
        failed_deployment_gates=failed,
        active_waivers=queries.count_waivers(db, scoped),
        expiring_waivers=_count_expiring(
            db, EvaluationWaiver, scoped, approved_status="APPROVED"
        ),
        open_exceptions=open_exceptions.scalar() or 0,
        expiring_exceptions=_count_expiring(
            db, GovernanceException, scoped, approved_status="APPROVED"
        ),
    )


def build_conversation_report(
    db: Session,
    conversation_id: UUID,
    filters: ReportFilters,
) -> ConversationReport:
    del filters
    """Build a report for one conversation in the caller's organization."""
    conversation = (
        db.query(RuntimeConversation)
        .filter(
            RuntimeConversation.id == conversation_id,
        )
        .first()
    )
    if conversation is None:
        raise LookupError("Conversation not found")

    start = conversation.started_at or conversation.created_at
    end = conversation.last_activity_at or datetime.utcnow()
    trajectories = (
        db.query(RuntimeTrajectory)
        .filter(RuntimeTrajectory.runtime_conversation_id == conversation.id)
        .order_by(RuntimeTrajectory.started_at.asc())
        .all()
    )
    trajectory_ids = [row.id for row in trajectories]
    receipts = []
    if trajectory_ids:
        correlation_ids = [
            row.correlation_id for row in trajectories if row.correlation_id
        ]
        receipt_query = db.query(RuntimeEnforcementReceipt).filter(
            RuntimeEnforcementReceipt.ai_system_id == conversation.ai_system_id
        )
        if correlation_ids:
            receipts = receipt_query.filter(
                RuntimeEnforcementReceipt.correlation_id.in_(correlation_ids)
            ).all()
        else:
            receipts = []

    findings = 0
    if trajectory_ids:
        findings = (
            db.query(func.count(RuntimeRiskFinding.id))
            .filter(RuntimeRiskFinding.trajectory_id.in_(trajectory_ids))
            .scalar()
            or 0
        )
    budget_events = 0
    if trajectory_ids:
        budget_events = (
            db.query(func.count(RuntimeBudgetCheck.id))
            .filter(RuntimeBudgetCheck.trajectory_id.in_(trajectory_ids))
            .scalar()
            or 0
        )

    receipt_ids = [row.id for row in receipts]
    token_usage = None
    cost = None
    if receipt_ids:
        usage = (
            db.query(
                func.sum(UsageSettlement.total_tokens),
                func.sum(UsageSettlement.actual_cost),
            )
            .join(
                UsageReservation, UsageSettlement.reservation_id == UsageReservation.id
            )
            .filter(UsageReservation.enforcement_receipt_id.in_(receipt_ids))
            .one()
        )
        if usage[0] is not None:
            token_usage = int(usage[0])
        if usage[1] is not None:
            cost = round(float(usage[1]), 2)

    completeness_values = [
        row.completeness_pct for row in trajectories if row.completeness_pct is not None
    ]
    completeness = (
        round(sum(completeness_values) / len(completeness_values), 2)
        if completeness_values
        else None
    )
    triggers = [
        row
        for row in receipts
        if (row.policy_effect or "").upper()
        in {"MONITOR", "REQUIRE_APPROVAL", "DENY", "SUSPEND"}
    ]
    approval_ids = [
        row.approval_request_id for row in receipts if row.approval_request_id
    ]
    approvals = []
    if approval_ids:
        approvals = (
            db.query(ApprovalRequest).filter(ApprovalRequest.id.in_(approval_ids)).all()
        )

    events = [
        {
            "type": "trajectory",
            "id": str(row.id),
            "occurred_at": row.started_at.isoformat() if row.started_at else None,
            "status": row.status,
            "finding_count": row.finding_count,
        }
        for row in trajectories[:50]
    ]

    return ConversationReport(
        scope=ReportScope(
            ai_system_id=conversation.ai_system_id,
        ),
        period=ReportPeriod(start=start, end=end),
        freshness=Freshness(
            mode=FreshnessMode.LIVE, last_refreshed_at=datetime.utcnow()
        ),
        turns=len(trajectories) or int(conversation.trajectory_count or 0),
        actions=len(receipts) or int(conversation.action_count or 0),
        tool_calls=sum(1 for row in receipts if row.tool_id is not None),
        policy_evaluations=len(receipts),
        policy_triggers=len(triggers),
        findings=int(findings or conversation.finding_count or 0),
        highest_risk=conversation.highest_risk_level,
        approvals_requested=len(approvals),
        approvals_approved=sum(1 for row in approvals if row.status == "APPROVED"),
        approvals_rejected=sum(1 for row in approvals if row.status == "REJECTED"),
        denied_actions=sum(1 for row in receipts if row.enforcement_decision == "DENY"),
        budget_events=int(budget_events),
        token_usage=token_usage,
        cost=cost,
        evidence_completeness_pct=completeness,
        events=events,
    )


def build_attention_items(
    db: Session,
    filters: ReportFilters,
    risk_focused: bool = False,
    limit: int = 10,
) -> list[AttentionItem]:
    """Build executive attention queue items."""
    # This is a simplified version. Full implementation would query:
    # - CRITICAL findings
    # - Expired assurance
    # - Budget exceeded
    # - Open critical incidents
    # - Expiring exceptions/waivers

    items: list[AttentionItem] = []

    # Critical findings
    critical_filters = filters.model_copy()
    critical_filters.risk_severity = ["CRITICAL"]
    critical_filters.finding_status = ["OPEN"]

    # This would need to fetch actual finding records with details
    # For now, just return empty list as placeholder

    return items[:limit]
