"""Deterministic deployment gate evaluation engine."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from rai_gateway.evaluations.domain import (
    LIVE_ASSURANCE_RUNNER_TYPES,
    PRODUCTION_LIVE_RUNNER_CATEGORIES,
    SEVERITY_RANK,
    ConditionEvaluation,
    ConditionResult,
    EvaluationEnvironment,
    EvaluationRunStatus,
    GateConditionType,
    GateDecision,
    GateEvaluationResult,
    WaiverStatus,
)
from rai_gateway.models.evaluations import (
    EvaluationRequirement,
    EvaluationRun,
    EvaluationWaiver,
)
from rai_gateway.models.registry import RiskAssessment
from rai_gateway.models.risk_intelligence import RuntimeRiskFinding


def evaluate_gate_conditions(
    db: Session,
    *,
    ai_system_id: UUID,
    agent_version_id: UUID,
    environment: str,
    conditions: list[dict[str, Any]],
    requirements: list[EvaluationRequirement],
    runs: list[EvaluationRun],
    waivers: list[EvaluationWaiver] | None = None,
) -> GateEvaluationResult:
    """Evaluate gate conditions deterministically against persisted state."""
    waivers = waivers or []
    active_waivers = [
        w
        for w in waivers
        if w.status == WaiverStatus.APPROVED.value
        and (w.valid_until is None or w.valid_until > datetime.now(timezone.utc))
    ]
    results: list[ConditionEvaluation] = []
    runs_by_req = {str(r.requirement_id): r for r in runs if r.requirement_id}
    latest_by_suite: dict[str, EvaluationRun] = {}
    for run in sorted(
        runs, key=lambda r: r.created_at or datetime.min.replace(tzinfo=timezone.utc)
    ):
        latest_by_suite[str(run.suite_id)] = run

    for cond in conditions:
        ctype = cond.get("type") or GateConditionType.CUSTOM.value
        name = cond.get("name") or ctype
        waivable = bool(cond.get("waivable", False))
        result = _eval_one(
            db,
            ctype=ctype,
            name=name,
            cond=cond,
            ai_system_id=ai_system_id,
            agent_version_id=agent_version_id,
            environment=environment,
            requirements=requirements,
            runs_by_req=runs_by_req,
            latest_by_suite=latest_by_suite,
            waivable=waivable,
        )
        # Apply waiver if failed and waivable
        if result.result == ConditionResult.FAIL and waivable:
            matched = _matching_waiver(active_waivers, result)
            if matched:
                result.result = ConditionResult.WAIVED
                result.waiver_id = matched.id
                result.reason = f"Waived: {result.reason}"
        results.append(result)

    # Also enforce required evaluation requirements not covered by explicit conditions
    covered_req_ids = {
        str(r.evaluation_requirement_id) for r in results if r.evaluation_requirement_id
    }
    for req in requirements:
        if not req.required or not req.enabled:
            continue
        if req.environment_scope != environment:
            continue
        if str(req.id) in covered_req_ids:
            continue
        run = runs_by_req.get(str(req.id))
        auto = _requirement_condition(req, run)
        if (
            auto.result == ConditionResult.FAIL and False
        ):  # requirements not auto-waivable
            pass
        results.append(auto)

    fails = [r for r in results if r.result == ConditionResult.FAIL]
    waived = [r for r in results if r.result == ConditionResult.WAIVED]
    non_waivable_fails = [r for r in fails if not r.waivable]
    waivable_fails = [r for r in fails if r.waivable]

    if non_waivable_fails:
        decision = GateDecision.FAIL
        reason = "; ".join(f.reason for f in non_waivable_fails)
    elif waivable_fails:
        decision = GateDecision.WAIVER_REQUIRED
        reason = "; ".join(f.reason for f in waivable_fails)
    elif waived and not fails:
        decision = GateDecision.PASS_WITH_CONDITIONS
        reason = "All conditions satisfied with approved waivers"
    elif fails:
        decision = GateDecision.FAIL
        reason = "; ".join(f.reason for f in fails)
    else:
        decision = GateDecision.PASS
        reason = "All deployment gate conditions satisfied"

    return GateEvaluationResult(
        decision=decision,
        conditions=results,
        reason=reason,
        score_summary={
            "total": len(results),
            "passed": len([r for r in results if r.result == ConditionResult.PASS]),
            "failed": len(fails),
            "waived": len(waived),
        },
    )


def default_conditions_from_requirements(
    requirements: list[EvaluationRequirement],
    *,
    include_risk: bool = True,
) -> list[dict[str, Any]]:
    """Build default gate conditions from enabled required evaluation requirements."""
    conditions: list[dict[str, Any]] = []
    for req in requirements:
        if not req.enabled or not req.required:
            continue
        conditions.append(
            {
                "type": GateConditionType.EVALUATION_SUITE_SCORE.value,
                "name": req.name,
                "requirement_id": str(req.id),
                "suite_id": str(req.evaluation_suite_id),
                "minimum_score": req.minimum_score,
                "maximum_failed_critical_cases": req.maximum_failed_critical_cases,
                # Critical privacy/safety/security/compliance/business failures are not waivable
                "waivable": req.category
                not in {
                    "PRIVACY",
                    "SAFETY",
                    "SECURITY",
                    "COMPLIANCE",
                    "BUSINESS_RULE",
                },
            }
        )
        conditions.append(
            {
                "type": GateConditionType.MAX_CRITICAL_FAILURES.value,
                "name": f"{req.name} critical failures",
                "requirement_id": str(req.id),
                "maximum": req.maximum_failed_critical_cases,
                "waivable": False,
            }
        )
        allowed = _accepted_runners_for_requirement(req)
        if allowed is not None:
            conditions.append(
                {
                    "type": GateConditionType.ACCEPTABLE_RUNNER_TYPE.value,
                    "name": f"{req.name} runner assurance",
                    "requirement_id": str(req.id),
                    "suite_id": str(req.evaluation_suite_id),
                    "allowed_runner_types": sorted(allowed),
                    "waivable": False,
                }
            )
    if include_risk:
        conditions.append(
            {
                "type": GateConditionType.RISK_ASSESSMENT_CURRENT.value,
                "name": "Risk Assessment current",
                "waivable": False,
            }
        )
        conditions.append(
            {
                "type": GateConditionType.MAX_OPEN_RISK_SEVERITY.value,
                "name": "No unresolved CRITICAL runtime findings",
                "max_severity": "HIGH",
                "waivable": False,
            }
        )
    return conditions


def _accepted_runners_for_requirement(
    req: EvaluationRequirement,
) -> set[str] | None:
    """Return allowed runner types, or None when no runner-type constraint applies."""
    explicit = getattr(req, "accepted_runner_types", None)
    if isinstance(explicit, list) and explicit:
        return {str(x) for x in explicit}
    if (
        req.environment_scope == EvaluationEnvironment.PRODUCTION.value
        and req.category in PRODUCTION_LIVE_RUNNER_CATEGORIES
    ):
        return set(LIVE_ASSURANCE_RUNNER_TYPES)
    return None


def _eval_one(
    db: Session,
    *,
    ctype: str,
    name: str,
    cond: dict[str, Any],
    ai_system_id: UUID,
    agent_version_id: UUID,
    environment: str,
    requirements: list[EvaluationRequirement],
    runs_by_req: dict[str, EvaluationRun],
    latest_by_suite: dict[str, EvaluationRun],
    waivable: bool,
) -> ConditionEvaluation:
    req_id = cond.get("requirement_id")
    suite_id = cond.get("suite_id")
    run = None
    req = None
    if req_id:
        run = runs_by_req.get(str(req_id))
        req = next((r for r in requirements if str(r.id) == str(req_id)), None)
    elif suite_id:
        run = latest_by_suite.get(str(suite_id))

    if ctype == GateConditionType.EVALUATION_SUITE_SCORE.value:
        minimum = float(cond.get("minimum_score", req.minimum_score if req else 1.0))
        if run is None:
            return ConditionEvaluation(
                condition_type=ctype,
                name=name,
                required_value=minimum,
                actual_value=None,
                result=ConditionResult.FAIL,
                reason=f"{name}: no evaluation run",
                waivable=waivable,
                evaluation_requirement_id=UUID(str(req_id)) if req_id else None,
            )
        actual = float(run.score or 0.0)
        ok = actual >= minimum and run.status == EvaluationRunStatus.PASSED.value
        if run.status not in {
            EvaluationRunStatus.PASSED.value,
            EvaluationRunStatus.FAILED.value,
        }:
            ok = False
        return ConditionEvaluation(
            condition_type=ctype,
            name=name,
            required_value=minimum,
            actual_value=actual,
            result=ConditionResult.PASS if ok else ConditionResult.FAIL,
            reason=(
                f"{name}: score {actual:.2%} >= {minimum:.2%}"
                if ok
                else f"{name}: score {actual:.2%} < required {minimum:.2%}"
                if actual < minimum
                else f"{name}: run status {run.status} is not PASSED"
            ),
            waivable=waivable,
            evaluation_requirement_id=UUID(str(req_id)) if req_id else None,
            evaluation_run_id=run.id,
            evidence_refs=[str(run.id)],
        )

    if ctype == GateConditionType.MAX_FAILED_CASES.value:
        maximum = int(cond.get("maximum", 0))
        actual = int(run.failed_cases) if run else None
        if run is None:
            return _missing_run(ctype, name, maximum, waivable, req_id)
        ok = actual <= maximum
        return ConditionEvaluation(
            condition_type=ctype,
            name=name,
            required_value=maximum,
            actual_value=actual,
            result=ConditionResult.PASS if ok else ConditionResult.FAIL,
            reason=(
                f"{name}: failed cases {actual} <= {maximum}"
                if ok
                else f"{name}: failed cases {actual} > {maximum}"
            ),
            waivable=waivable,
            evaluation_requirement_id=UUID(str(req_id)) if req_id else None,
            evaluation_run_id=run.id,
            evidence_refs=[str(run.id)],
        )

    if ctype == GateConditionType.MAX_CRITICAL_FAILURES.value:
        maximum = int(
            cond.get(
                "maximum",
                req.maximum_failed_critical_cases if req else 0,
            )
        )
        if run is None:
            return _missing_run(ctype, name, maximum, False, req_id)
        actual = int(run.critical_failures or 0)
        ok = actual <= maximum
        return ConditionEvaluation(
            condition_type=ctype,
            name=name,
            required_value=maximum,
            actual_value=actual,
            result=ConditionResult.PASS if ok else ConditionResult.FAIL,
            reason=(
                f"{name}: critical failures {actual} <= {maximum}"
                if ok
                else f"{name}: critical failures {actual} > {maximum}"
            ),
            waivable=False,  # critical failures never waivable by default
            evaluation_requirement_id=UUID(str(req_id)) if req_id else None,
            evaluation_run_id=run.id,
            evidence_refs=[str(run.id)],
        )

    if ctype == GateConditionType.RISK_ASSESSMENT_CURRENT.value:
        assessment = (
            db.query(RiskAssessment)
            .filter(RiskAssessment.agent_version_id == agent_version_id)
            .order_by(RiskAssessment.created_at.desc())
            .first()
        )
        ok = assessment is not None
        return ConditionEvaluation(
            condition_type=ctype,
            name=name,
            required_value="present",
            actual_value=str(assessment.id) if assessment else None,
            result=ConditionResult.PASS if ok else ConditionResult.FAIL,
            reason=(
                "Risk assessment present for agent version"
                if ok
                else "No risk assessment for agent version"
            ),
            waivable=waivable,
            evidence_refs=[str(assessment.id)] if assessment else [],
        )

    if ctype == GateConditionType.MAX_OPEN_RISK_SEVERITY.value:
        max_severity = cond.get("max_severity", "HIGH")
        max_rank = SEVERITY_RANK.get(max_severity, 3)
        findings = (
            db.query(RuntimeRiskFinding)
            .filter(
                RuntimeRiskFinding.ai_system_id == ai_system_id,
                RuntimeRiskFinding.status.in_(["OPEN", "ACKNOWLEDGED", "MONITORING"]),
            )
            .all()
        )
        # Prefer version-scoped; fall back to system-level
        relevant = [
            f
            for f in findings
            if f.agent_version_id is None or f.agent_version_id == agent_version_id
        ]
        blocking = [f for f in relevant if SEVERITY_RANK.get(f.severity, 0) > max_rank]
        ok = not blocking
        actual = max((f.severity for f in relevant), default="NONE")
        return ConditionEvaluation(
            condition_type=ctype,
            name=name,
            required_value=f"<= {max_severity}",
            actual_value=actual,
            result=ConditionResult.PASS if ok else ConditionResult.FAIL,
            reason=(
                "No blocking open runtime risk findings"
                if ok
                else f"{len(blocking)} open finding(s) exceed {max_severity}"
            ),
            waivable=waivable,
            evidence_refs=[str(f.id) for f in blocking[:10]],
        )

    if ctype == GateConditionType.REQUIRED_HUMAN_REVIEW.value:
        required = bool(cond.get("required", True))
        approved = bool(cond.get("approved", False))
        # External signal may be passed in condition snapshot after review
        ok = (not required) or approved
        return ConditionEvaluation(
            condition_type=ctype,
            name=name,
            required_value="approved" if required else "not_required",
            actual_value="approved" if approved else "pending",
            result=ConditionResult.PASS if ok else ConditionResult.FAIL,
            reason=(
                "Human review approved" if ok else "Required human review not approved"
            ),
            waivable=waivable,
        )

    if ctype == GateConditionType.ACCEPTABLE_RUNNER_TYPE.value:
        allowed = {str(x) for x in (cond.get("allowed_runner_types") or [])}
        if req is not None:
            derived = _accepted_runners_for_requirement(req)
            if derived is not None:
                allowed = derived if not allowed else allowed
        if run is None:
            return ConditionEvaluation(
                condition_type=ctype,
                name=name,
                required_value=sorted(allowed),
                actual_value=None,
                result=ConditionResult.FAIL,
                reason=f"{name}: no evaluation run",
                waivable=False,
                evaluation_requirement_id=UUID(str(req_id)) if req_id else None,
            )
        actual = run.runner_type
        evidence = run.evidence if isinstance(run.evidence, dict) else {}
        assurance = evidence.get("assurance_class")
        ok = actual in allowed
        # Fixture-simulated evidence never satisfies live-assurance allow-lists
        if ok and allowed.issubset(LIVE_ASSURANCE_RUNNER_TYPES):
            if assurance == "FIXTURE_SIMULATED" or actual == "DETERMINISTIC":
                ok = False
        return ConditionEvaluation(
            condition_type=ctype,
            name=name,
            required_value=sorted(allowed),
            actual_value=actual,
            result=ConditionResult.PASS if ok else ConditionResult.FAIL,
            reason=(
                f"{name}: runner {actual} accepted"
                if ok
                else (
                    f"{name}: runner {actual} not in allowed types "
                    f"{sorted(allowed)} (fixture-only insufficient for production)"
                )
            ),
            waivable=False,
            evaluation_requirement_id=UUID(str(req_id)) if req_id else None,
            evaluation_run_id=run.id,
            evidence_refs=[str(run.id)],
        )

    if ctype == GateConditionType.NO_ACTIVE_RUNTIME_SUSPENSION.value:
        # Checked via risk state require/deny overlay — soft check on findings with SUSPEND
        suspended = (
            db.query(RuntimeRiskFinding)
            .filter(
                RuntimeRiskFinding.ai_system_id == ai_system_id,
                RuntimeRiskFinding.status.in_(["OPEN", "ACKNOWLEDGED", "MONITORING"]),
                RuntimeRiskFinding.intervention_effect.in_(
                    [
                        "SUSPEND_RUNTIME_IDENTITY",
                        "SUSPEND_AGENT_VERSION",
                        "EMERGENCY_STOP",
                    ]
                ),
            )
            .count()
        )
        ok = suspended == 0
        return ConditionEvaluation(
            condition_type=ctype,
            name=name,
            required_value=0,
            actual_value=suspended,
            result=ConditionResult.PASS if ok else ConditionResult.FAIL,
            reason=(
                "No active runtime suspension"
                if ok
                else f"{suspended} active suspension intervention(s)"
            ),
            waivable=False,
        )

    # CUSTOM — pass when expected equals actual in condition payload
    expected = cond.get("required_value")
    actual = cond.get("actual_value")
    ok = expected == actual
    return ConditionEvaluation(
        condition_type=ctype,
        name=name,
        required_value=expected,
        actual_value=actual,
        result=ConditionResult.PASS if ok else ConditionResult.FAIL,
        reason=cond.get("reason")
        or (
            f"{name}: custom condition passed"
            if ok
            else f"{name}: custom condition failed"
        ),
        waivable=waivable,
    )


def _requirement_condition(
    req: EvaluationRequirement, run: EvaluationRun | None
) -> ConditionEvaluation:
    if run is None:
        return ConditionEvaluation(
            condition_type=GateConditionType.EVALUATION_SUITE_SCORE.value,
            name=req.name,
            required_value=req.minimum_score,
            actual_value=None,
            result=ConditionResult.FAIL,
            reason=f"{req.name}: required evaluation not run",
            waivable=False,
            evaluation_requirement_id=req.id,
        )
    ok = float(run.score or 0.0) >= float(req.minimum_score) and int(
        run.critical_failures or 0
    ) <= int(req.maximum_failed_critical_cases)
    return ConditionEvaluation(
        condition_type=GateConditionType.EVALUATION_SUITE_SCORE.value,
        name=req.name,
        required_value=req.minimum_score,
        actual_value=run.score,
        result=ConditionResult.PASS if ok else ConditionResult.FAIL,
        reason=(
            f"{req.name}: satisfied"
            if ok
            else f"{req.name}: score/critical failures do not meet requirement"
        ),
        waivable=False,
        evaluation_requirement_id=req.id,
        evaluation_run_id=run.id,
        evidence_refs=[str(run.id)],
    )


def _missing_run(
    ctype: str,
    name: str,
    required: Any,
    waivable: bool,
    req_id: Any,
) -> ConditionEvaluation:
    return ConditionEvaluation(
        condition_type=ctype,
        name=name,
        required_value=required,
        actual_value=None,
        result=ConditionResult.FAIL,
        reason=f"{name}: no evaluation run",
        waivable=waivable,
        evaluation_requirement_id=UUID(str(req_id)) if req_id else None,
    )


def _matching_waiver(
    waivers: list[EvaluationWaiver], condition: ConditionEvaluation
) -> EvaluationWaiver | None:
    for w in waivers:
        failed = w.failed_condition or {}
        if failed.get("name") == condition.name:
            return w
        if failed.get("type") == condition.condition_type and failed.get("name") in (
            None,
            condition.name,
        ):
            return w
        if condition.evaluation_requirement_id and str(
            failed.get("requirement_id")
        ) == str(condition.evaluation_requirement_id):
            return w
    return None


# Silence unused import warning for environment enum used by callers
_ = EvaluationEnvironment
