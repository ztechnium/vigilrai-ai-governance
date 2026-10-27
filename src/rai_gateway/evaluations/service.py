"""WP7 Evaluation, Assurance & Deployment Gates service."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from rai_gateway.core.observability import log_siem_event, logger
from rai_gateway.evaluations.domain import (
    IMPACT_MAP,
    AssuranceStatus,
    CaseResultStatus,
    EvaluationEnvironment,
    EvaluationRunStatus,
    GateDecision,
    ReassessmentStatus,
    ReassessmentTriggerType,
    RunnerType,
    WaiverStatus,
)
from rai_gateway.evaluations.errors import (
    EvaluationConflictError,
    EvaluationNotFoundError,
    SuiteImmutableError,
    WaiverDeniedError,
)
from rai_gateway.evaluations.gates import (
    default_conditions_from_requirements,
    evaluate_gate_conditions,
)
from rai_gateway.evaluations.runners import get_runner
from rai_gateway.models.evaluations import (
    AssuranceRecord,
    DeploymentGate,
    DeploymentGateEvaluation,
    EvaluationCase,
    EvaluationCaseResult,
    EvaluationPlan,
    EvaluationRequirement,
    EvaluationRun,
    EvaluationSuite,
    EvaluationWaiver,
    ReassessmentTrigger,
)
from rai_gateway.models.registry import (
    Agent,
    AgentVersion,
    AgentVersionDependency,
    AISystem,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _digest(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _ser_dt(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


class EvaluationService:
    """Authoritative evaluation / gate / assurance orchestration."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def _validate_ai_system_ownership(self, ai_system_id: UUID) -> None:
        """Validate that AI system belongs to the organization."""
        system = (
            self._db.query(AISystem)
            .filter(
                AISystem.id == ai_system_id,
            )
            .first()
        )
        if not system:
            raise EvaluationNotFoundError("AI system not found or access denied")

    def _validate_agent_version_ownership(self, version_id: UUID) -> AgentVersion:
        """Validate that agent version belongs to the organization via agent -> AI system."""
        version = (
            self._db.query(AgentVersion)
            .join(Agent, AgentVersion.agent_id == Agent.id)
            .join(AISystem, Agent.ai_system_id == AISystem.id)
            .filter(
                AgentVersion.id == version_id,
            )
            .first()
        )
        if not version:
            raise EvaluationNotFoundError("Agent version not found or access denied")
        return version

    # ------------------------------------------------------------------
    # Suites & cases
    # ------------------------------------------------------------------

    def create_suite(
        self,
        *,
        ai_system_id: UUID,
        suite_key: str,
        name: str,
        category: str,
        created_by: str,
        description: str | None = None,
        runner_type: str = RunnerType.DETERMINISTIC.value,
        runner_config: dict[str, Any] | None = None,
        version: int | None = None,
    ) -> dict[str, Any]:
        self._validate_ai_system_ownership(ai_system_id)
        if version is None:
            latest = (
                self._db.query(EvaluationSuite)
                .filter(
                    EvaluationSuite.ai_system_id == ai_system_id,
                    EvaluationSuite.suite_key == suite_key,
                )
                .order_by(EvaluationSuite.version.desc())
                .first()
            )
            version = (latest.version + 1) if latest else 1
        suite = EvaluationSuite(
            ai_system_id=ai_system_id,
            suite_key=suite_key,
            name=name,
            category=category,
            version=version,
            description=description,
            runner_type=runner_type,
            runner_config=runner_config or {},
            created_by=created_by,
            published=False,
        )
        self._db.add(suite)
        self._db.commit()
        self._db.refresh(suite)
        return self._serialize_suite(suite)

    def publish_suite(self, suite_id: UUID) -> dict[str, Any]:
        suite = self._get_suite(suite_id)
        self._validate_ai_system_ownership(suite.ai_system_id)
        if suite.published:
            return self._serialize_suite(suite)
        cases = (
            self._db.query(EvaluationCase)
            .filter(
                EvaluationCase.suite_id == suite.id, EvaluationCase.enabled.is_(True)
            )
            .count()
        )
        if cases == 0:
            raise EvaluationConflictError("Cannot publish suite with no enabled cases")
        suite.published = True
        suite.published_at = _utcnow()
        self._db.commit()
        self._db.refresh(suite)
        return self._serialize_suite(suite)

    def add_case(
        self,
        suite_id: UUID,
        *,
        case_key: str,
        name: str,
        input_fixture: dict[str, Any],
        expected_behavior: dict[str, Any],
        scoring_method: str = "exact_match",
        threshold: float = 1.0,
        failure_severity: str = "HIGH",
        description: str | None = None,
        sort_order: int = 0,
    ) -> dict[str, Any]:
        suite = self._get_suite(suite_id)
        self._validate_ai_system_ownership(suite.ai_system_id)
        if suite.published:
            raise SuiteImmutableError(
                "Published suite versions are immutable; create a new suite version"
            )
        case = EvaluationCase(
            suite_id=suite.id,
            case_key=case_key,
            name=name,
            description=description,
            input_fixture=input_fixture,
            expected_behavior=expected_behavior,
            scoring_method=scoring_method,
            threshold=threshold,
            failure_severity=failure_severity,
            sort_order=sort_order,
        )
        self._db.add(case)
        self._db.commit()
        self._db.refresh(case)
        return self._serialize_case(case)

    def list_suites(
        self,
        *,
        ai_system_id: UUID | None = None,
        published_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        q = self._db.query(EvaluationSuite).join(
            AISystem, EvaluationSuite.ai_system_id == AISystem.id
        )
        if ai_system_id:
            q = q.filter(EvaluationSuite.ai_system_id == ai_system_id)
        if published_only:
            q = q.filter(EvaluationSuite.published.is_(True))
        rows = (
            q.order_by(EvaluationSuite.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [self._serialize_suite(s) for s in rows]

    def get_suite(self, suite_id: UUID) -> dict[str, Any]:
        suite = self._get_suite(suite_id)
        self._validate_ai_system_ownership(suite.ai_system_id)
        data = self._serialize_suite(suite)
        cases = (
            self._db.query(EvaluationCase)
            .filter(EvaluationCase.suite_id == suite.id)
            .order_by(EvaluationCase.sort_order, EvaluationCase.case_key)
            .all()
        )
        data["cases"] = [self._serialize_case(c) for c in cases]
        return data

    # ------------------------------------------------------------------
    # Requirements
    # ------------------------------------------------------------------

    def create_requirement(
        self,
        *,
        ai_system_id: UUID,
        name: str,
        category: str,
        evaluation_suite_id: UUID,
        created_by: str,
        minimum_score: float = 1.0,
        maximum_failed_critical_cases: int = 0,
        required: bool = True,
        validity_days: int | None = 30,
        environment_scope: str = EvaluationEnvironment.PRODUCTION.value,
        enabled: bool = True,
        accepted_runner_types: list[str] | None = None,
    ) -> dict[str, Any]:
        self._validate_ai_system_ownership(ai_system_id)
        suite = self._get_suite(evaluation_suite_id)
        if suite.ai_system_id != ai_system_id:
            raise EvaluationConflictError("Suite does not belong to AI system")
        if not suite.published:
            raise EvaluationConflictError(
                "Requirements must reference a published suite"
            )
        req = EvaluationRequirement(
            ai_system_id=ai_system_id,
            name=name,
            category=category,
            evaluation_suite_id=evaluation_suite_id,
            minimum_score=minimum_score,
            maximum_failed_critical_cases=maximum_failed_critical_cases,
            required=required,
            validity_days=validity_days,
            environment_scope=environment_scope,
            enabled=enabled,
            accepted_runner_types=accepted_runner_types,
            created_by=created_by,
        )
        self._db.add(req)
        self._db.commit()
        self._db.refresh(req)
        return self._serialize_requirement(req)

    def list_requirements(
        self,
        *,
        ai_system_id: UUID | None = None,
        environment: str | None = None,
        enabled_only: bool = True,
    ) -> list[dict[str, Any]]:
        q = self._db.query(EvaluationRequirement).join(
            AISystem, EvaluationRequirement.ai_system_id == AISystem.id
        )
        if ai_system_id:
            q = q.filter(EvaluationRequirement.ai_system_id == ai_system_id)
        if environment:
            q = q.filter(EvaluationRequirement.environment_scope == environment)
        if enabled_only:
            q = q.filter(EvaluationRequirement.enabled.is_(True))
        return [
            self._serialize_requirement(r)
            for r in q.order_by(EvaluationRequirement.name).all()
        ]

    def resolve_requirements(
        self,
        *,
        ai_system_id: UUID,
        environment: str,
        categories: set[str] | None = None,
    ) -> list[EvaluationRequirement]:
        q = self._db.query(EvaluationRequirement).filter(
            EvaluationRequirement.ai_system_id == ai_system_id,
            EvaluationRequirement.environment_scope == environment,
            EvaluationRequirement.enabled.is_(True),
        )
        rows = q.all()
        if categories:
            rows = [r for r in rows if r.category in categories]
        return rows

    # ------------------------------------------------------------------
    # Plans
    # ------------------------------------------------------------------

    def create_plan(
        self,
        *,
        agent_version_id: UUID,
        target_environment: str,
        created_by: str,
        categories: set[str] | None = None,
    ) -> dict[str, Any]:
        version = self._validate_agent_version_ownership(agent_version_id)
        agent = self._db.query(Agent).filter(Agent.id == version.agent_id).first()
        if agent is None:
            raise EvaluationNotFoundError("Agent not found")
        requirements = self.resolve_requirements(
            ai_system_id=agent.ai_system_id,
            environment=target_environment,
            categories=categories,
        )
        dep_digest = self._dependency_digest(version.id)
        snapshot = [self._serialize_requirement(r) for r in requirements]
        plan_digest = _digest(
            {
                "agent_version_id": str(version.id),
                "environment": target_environment,
                "config_digest": version.configuration_digest,
                "dependency_digest": dep_digest,
                "requirements": snapshot,
            }
        )
        existing = (
            self._db.query(EvaluationPlan)
            .filter(
                EvaluationPlan.agent_version_id == version.id,
                EvaluationPlan.target_environment == target_environment,
                EvaluationPlan.plan_digest == plan_digest,
                EvaluationPlan.status == "ACTIVE",
            )
            .first()
        )
        if existing:
            return self._serialize_plan(existing)

        plan = EvaluationPlan(
            ai_system_id=agent.ai_system_id,
            agent_id=agent.id,
            agent_version_id=version.id,
            target_environment=target_environment,
            requirement_snapshot=snapshot,
            agent_config_digest=version.configuration_digest,
            dependency_digest=dep_digest,
            plan_digest=plan_digest,
            status="ACTIVE",
            created_by=created_by,
        )
        self._db.add(plan)
        self._db.commit()
        self._db.refresh(plan)
        return self._serialize_plan(plan)

    def list_plans(
        self,
        *,
        agent_version_id: UUID | None = None,
        ai_system_id: UUID | None = None,
    ) -> list[dict[str, Any]]:
        q = self._db.query(EvaluationPlan).join(
            AISystem, EvaluationPlan.ai_system_id == AISystem.id
        )
        if agent_version_id:
            q = q.filter(EvaluationPlan.agent_version_id == agent_version_id)
        if ai_system_id:
            q = q.filter(EvaluationPlan.ai_system_id == ai_system_id)
        return [
            self._serialize_plan(p)
            for p in q.order_by(EvaluationPlan.created_at.desc()).all()
        ]

    # ------------------------------------------------------------------
    # Runs
    # ------------------------------------------------------------------

    def start_runs_for_plan(
        self,
        plan_id: UUID,
        *,
        created_by: str,
        idempotency_key: str = "default",
        execute_inline: bool = True,
    ) -> list[dict[str, Any]]:
        plan = self._get_plan(plan_id)
        self._validate_ai_system_ownership(plan.ai_system_id)
        results = []
        for req_snap in plan.requirement_snapshot or []:
            req_id = UUID(req_snap["id"])
            suite_id = UUID(req_snap["evaluation_suite_id"])
            results.append(
                self.execute_run(
                    plan_id=plan.id,
                    suite_id=suite_id,
                    requirement_id=req_id,
                    created_by=created_by,
                    idempotency_key=idempotency_key,
                    execute_inline=execute_inline,
                )
            )
        return results

    def execute_run(
        self,
        *,
        plan_id: UUID,
        suite_id: UUID,
        created_by: str,
        requirement_id: UUID | None = None,
        idempotency_key: str = "default",
        execute_inline: bool = True,
    ) -> dict[str, Any]:
        plan = self._get_plan(plan_id)
        suite = self._get_suite(suite_id)
        if not suite.published:
            raise EvaluationConflictError("Cannot run unpublished suite")
        if suite.ai_system_id != plan.ai_system_id:
            raise EvaluationConflictError("Suite/plan AI system mismatch")

        existing = (
            self._db.query(EvaluationRun)
            .filter(
                EvaluationRun.plan_id == plan.id,
                EvaluationRun.suite_id == suite.id,
                EvaluationRun.idempotency_key == idempotency_key,
            )
            .first()
        )
        if existing and existing.status in {
            EvaluationRunStatus.PASSED.value,
            EvaluationRunStatus.FAILED.value,
            EvaluationRunStatus.RUNNING.value,
        }:
            return self._serialize_run(existing, include_cases=True)

        run = existing or EvaluationRun(
            plan_id=plan.id,
            ai_system_id=plan.ai_system_id,
            agent_version_id=plan.agent_version_id,
            suite_id=suite.id,
            suite_version=suite.version,
            requirement_id=requirement_id,
            runner_type=suite.runner_type,
            runner_version="1.0.0",
            status=EvaluationRunStatus.PENDING.value,
            idempotency_key=idempotency_key,
            created_by=created_by,
        )
        if existing is None:
            self._db.add(run)
            self._db.flush()

        if not execute_inline:
            self._db.commit()
            self._db.refresh(run)
            return self._serialize_run(run)

        return self._run_now(run, suite, plan)

    def _run_now(
        self, run: EvaluationRun, suite: EvaluationSuite, plan: EvaluationPlan
    ) -> dict[str, Any]:
        run.status = EvaluationRunStatus.RUNNING.value
        run.started_at = _utcnow()
        self._db.commit()
        log_siem_event(
            trace_id=str(run.id),
            event_type="evaluation.run.started",
            decision="allow",
            metadata={
                "run_id": str(run.id),
                "suite_id": str(suite.id),
                "agent_version_id": str(plan.agent_version_id),
            },
        )

        version = self._get_version(plan.agent_version_id)
        cases = (
            self._db.query(EvaluationCase)
            .filter(EvaluationCase.suite_id == suite.id)
            .order_by(EvaluationCase.sort_order, EvaluationCase.case_key)
            .all()
        )
        case_payloads = [
            {
                "case_key": c.case_key,
                "name": c.name,
                "input_fixture": c.input_fixture or {},
                "expected_behavior": c.expected_behavior or {},
                "scoring_method": c.scoring_method,
                "threshold": c.threshold,
                "failure_severity": c.failure_severity,
                "enabled": c.enabled,
                "id": str(c.id),
            }
            for c in cases
        ]
        try:
            runner = get_runner(suite.runner_type)
            runner_config = self._bind_runner_config(
                suite.runner_type, suite.runner_config or {}, version
            )
            if runner_config.get("_binding_error"):
                run.status = EvaluationRunStatus.ERROR.value
                run.error_message = runner_config["_binding_error"]
                run.evidence = {
                    "assurance_class": "LIVE_AGENT",
                    "runner_type": suite.runner_type,
                    "agent_version_id": str(version.id),
                    "config_digest": version.configuration_digest,
                    "binding_error": runner_config["_binding_error"],
                }
                run.completed_at = _utcnow()
                self._db.commit()
                log_siem_event(
                    trace_id=str(run.id),
                    event_type="evaluation.run.failed",
                    decision="deny",
                    metadata={
                        "run_id": str(run.id),
                        "error": runner_config["_binding_error"],
                    },
                )
                self._db.refresh(run)
                return self._serialize_run(run, include_cases=True)

            outcome = runner.execute(
                cases=case_payloads,
                agent_config=version.configuration_snapshot or {},
                runner_config=runner_config,
            )
            run.runner_version = runner.runner_version
            run.status = outcome.status.value
            run.score = outcome.score
            run.total_cases = outcome.total_cases
            run.passed_cases = outcome.passed_cases
            run.failed_cases = outcome.failed_cases
            run.critical_failures = outcome.critical_failures
            run.evidence = {
                **(outcome.evidence or {}),
                "config_digest": plan.agent_config_digest,
                "agent_version_id": str(version.id),
                "suite_version": suite.version,
                "dataset_digest": _digest(
                    [
                        {"case_key": c["case_key"], "fixture": c["input_fixture"]}
                        for c in case_payloads
                    ]
                ),
            }
            run.error_message = outcome.error
            run.completed_at = _utcnow()

            # Replace case results
            self._db.query(EvaluationCaseResult).filter(
                EvaluationCaseResult.run_id == run.id
            ).delete()
            case_id_by_key = {c.case_key: c.id for c in cases}
            for co in outcome.case_outcomes:
                self._db.add(
                    EvaluationCaseResult(
                        run_id=run.id,
                        case_id=case_id_by_key.get(co.case_key),
                        case_key=co.case_key,
                        status=co.status.value,
                        score=co.score,
                        severity=co.severity,
                        explanation=co.explanation,
                        actual_output=co.actual_output,
                        evidence_refs=co.evidence or {},
                    )
                )
            self._db.commit()
            event = (
                "evaluation.run.completed"
                if outcome.status == EvaluationRunStatus.PASSED
                else "evaluation.run.failed"
            )
            log_siem_event(
                trace_id=str(run.id),
                event_type=event,
                decision="allow"
                if outcome.status == EvaluationRunStatus.PASSED
                else "deny",
                metadata={
                    "run_id": str(run.id),
                    "score": run.score,
                    "status": run.status,
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("evaluation run failed")
            run.status = EvaluationRunStatus.ERROR.value
            run.error_message = str(exc)
            run.completed_at = _utcnow()
            self._db.commit()
            log_siem_event(
                trace_id=str(run.id),
                event_type="evaluation.run.failed",
                decision="deny",
                metadata={"run_id": str(run.id), "error": str(exc)},
            )

        self._db.refresh(run)
        return self._serialize_run(run, include_cases=True)

    def _bind_runner_config(
        self,
        runner_type: str,
        suite_config: dict[str, Any],
        version,
    ) -> dict[str, Any]:
        """Merge suite runner_config with Agent Version registry binding.

        For AGENT runners, the version's evaluation_endpoint_url is authoritative
        when set. Suite endpoint alone is accepted only as fallback when the
        version has no registered test endpoint. Digest/version id are always
        injected so live evidence is bound to the exact Agent Version.
        """
        cfg = dict(suite_config or {})
        if runner_type != RunnerType.AGENT.value:
            return cfg

        version_endpoint = (
            getattr(version, "evaluation_endpoint_url", None) or ""
        ).strip()
        suite_endpoint = (cfg.get("endpoint_url") or "").strip()
        if version_endpoint and suite_endpoint and version_endpoint != suite_endpoint:
            return {
                **cfg,
                "_binding_error": (
                    "AGENT endpoint binding mismatch: suite runner_config.endpoint_url "
                    "does not match Agent Version evaluation_endpoint_url"
                ),
            }
        endpoint = version_endpoint or suite_endpoint
        if not endpoint:
            return {
                **cfg,
                "_binding_error": (
                    "AGENT runner requires Agent Version evaluation_endpoint_url "
                    "(or suite runner_config.endpoint_url fallback)"
                ),
            }
        cfg["endpoint_url"] = endpoint
        cfg["agent_version_id"] = str(version.id)
        cfg["agent_config_digest"] = version.configuration_digest
        cfg["endpoint_binding_source"] = (
            "agent_version" if version_endpoint else "suite_fallback"
        )
        return cfg

    def list_runs(
        self,
        *,
        agent_version_id: UUID | None = None,
        ai_system_id: UUID | None = None,
        plan_id: UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        q = self._db.query(EvaluationRun).join(
            AISystem, EvaluationRun.ai_system_id == AISystem.id
        )
        if agent_version_id:
            q = q.filter(EvaluationRun.agent_version_id == agent_version_id)
        if ai_system_id:
            q = q.filter(EvaluationRun.ai_system_id == ai_system_id)
        if plan_id:
            q = q.filter(EvaluationRun.plan_id == plan_id)
        rows = (
            q.order_by(EvaluationRun.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [self._serialize_run(r) for r in rows]

    def get_run(self, run_id: UUID) -> dict[str, Any]:
        run = (
            self._db.query(EvaluationRun)
            .join(AISystem, EvaluationRun.ai_system_id == AISystem.id)
            .filter(
                EvaluationRun.id == run_id,
            )
            .first()
        )
        if not run:
            raise EvaluationNotFoundError("Evaluation run not found or access denied")
        return self._serialize_run(run, include_cases=True)

    # ------------------------------------------------------------------
    # Gates
    # ------------------------------------------------------------------

    def create_gate(
        self,
        *,
        ai_system_id: UUID,
        name: str,
        created_by: str,
        environment: str = EvaluationEnvironment.PRODUCTION.value,
        description: str | None = None,
        conditions: list[dict[str, Any]] | None = None,
        auto_from_requirements: bool = True,
    ) -> dict[str, Any]:
        self._validate_ai_system_ownership(ai_system_id)
        if conditions is None and auto_from_requirements:
            reqs = self.resolve_requirements(
                ai_system_id=ai_system_id, environment=environment
            )
            conditions = default_conditions_from_requirements(reqs)
        gate = DeploymentGate(
            ai_system_id=ai_system_id,
            name=name,
            environment=environment,
            description=description,
            conditions=conditions or [],
            enabled=True,
            created_by=created_by,
        )
        self._db.add(gate)
        self._db.commit()
        self._db.refresh(gate)
        return self._serialize_gate(gate)

    def list_gates(
        self,
        *,
        ai_system_id: UUID | None = None,
        environment: str | None = None,
    ) -> list[dict[str, Any]]:
        q = (
            self._db.query(DeploymentGate)
            .join(AISystem, DeploymentGate.ai_system_id == AISystem.id)
            .filter(
                DeploymentGate.enabled.is_(True),
            )
        )
        if ai_system_id:
            q = q.filter(DeploymentGate.ai_system_id == ai_system_id)
        if environment:
            q = q.filter(DeploymentGate.environment == environment)
        return [self._serialize_gate(g) for g in q.all()]

    def evaluate_deployment_gate(
        self,
        *,
        agent_version_id: UUID,
        environment: str = EvaluationEnvironment.PRODUCTION.value,
        evaluated_by: str,
        gate_id: UUID | None = None,
        plan_id: UUID | None = None,
    ) -> dict[str, Any]:
        version = self._validate_agent_version_ownership(agent_version_id)
        agent = self._db.query(Agent).filter(Agent.id == version.agent_id).first()
        if agent is None:
            raise EvaluationNotFoundError("Agent not found")

        requirements = self.resolve_requirements(
            ai_system_id=agent.ai_system_id, environment=environment
        )
        gate = None
        if gate_id:
            gate = (
                self._db.query(DeploymentGate)
                .filter(DeploymentGate.id == gate_id)
                .first()
            )
            if not gate:
                raise EvaluationNotFoundError("Deployment gate not found")
        else:
            gate = (
                self._db.query(DeploymentGate)
                .filter(
                    DeploymentGate.ai_system_id == agent.ai_system_id,
                    DeploymentGate.environment == environment,
                    DeploymentGate.enabled.is_(True),
                )
                .order_by(DeploymentGate.created_at.desc())
                .first()
            )

        conditions = (
            list(gate.conditions)
            if gate and gate.conditions
            else default_conditions_from_requirements(requirements)
        )

        plan = None
        if plan_id:
            plan = self._get_plan(plan_id)
        else:
            plan = (
                self._db.query(EvaluationPlan)
                .filter(
                    EvaluationPlan.agent_version_id == agent_version_id,
                    EvaluationPlan.target_environment == environment,
                    EvaluationPlan.status == "ACTIVE",
                )
                .order_by(EvaluationPlan.created_at.desc())
                .first()
            )

        runs: list[EvaluationRun] = []
        if plan:
            runs = (
                self._db.query(EvaluationRun)
                .filter(EvaluationRun.plan_id == plan.id)
                .all()
            )

        waivers = (
            self._db.query(EvaluationWaiver)
            .filter(
                EvaluationWaiver.agent_version_id == agent_version_id,
                EvaluationWaiver.environment == environment,
            )
            .all()
        )

        result = evaluate_gate_conditions(
            self._db,
            ai_system_id=agent.ai_system_id,
            agent_version_id=agent_version_id,
            environment=environment,
            conditions=conditions,
            requirements=requirements,
            runs=runs,
            waivers=waivers,
        )

        evaluation = DeploymentGateEvaluation(
            gate_id=gate.id if gate else None,
            ai_system_id=agent.ai_system_id,
            agent_version_id=agent_version_id,
            evaluation_plan_id=plan.id if plan else None,
            environment=environment,
            decision=result.decision.value,
            condition_results=[
                {
                    "condition_type": c.condition_type,
                    "name": c.name,
                    "required_value": c.required_value,
                    "actual_value": c.actual_value,
                    "result": c.result.value,
                    "reason": c.reason,
                    "waivable": c.waivable,
                    "evidence_refs": c.evidence_refs,
                    "evaluation_requirement_id": str(c.evaluation_requirement_id)
                    if c.evaluation_requirement_id
                    else None,
                    "evaluation_run_id": str(c.evaluation_run_id)
                    if c.evaluation_run_id
                    else None,
                    "waiver_id": str(c.waiver_id) if c.waiver_id else None,
                }
                for c in result.conditions
            ],
            reason=result.reason,
            evidence_refs=[str(r.id) for r in runs],
            evaluated_by=evaluated_by,
            evaluated_at=_utcnow(),
        )
        self._db.add(evaluation)
        self._db.flush()

        assurance = self._upsert_assurance_from_gate(
            evaluation=evaluation,
            plan=plan,
            version=version,
            requirements=requirements,
            created_by=evaluated_by,
        )
        self._db.commit()
        self._db.refresh(evaluation)
        if assurance:
            self._db.refresh(assurance)

        event_map = {
            GateDecision.PASS.value: "deployment_gate.passed",
            GateDecision.PASS_WITH_CONDITIONS.value: "deployment_gate.passed",
            GateDecision.FAIL.value: "deployment_gate.failed",
            GateDecision.WAIVER_REQUIRED.value: "deployment_gate.waiver_required",
        }
        log_siem_event(
            trace_id=str(evaluation.id),
            event_type=event_map.get(evaluation.decision, "deployment_gate.failed"),
            decision="allow"
            if evaluation.decision
            in {GateDecision.PASS.value, GateDecision.PASS_WITH_CONDITIONS.value}
            else "deny",
            metadata={
                "evaluation_id": str(evaluation.id),
                "decision": evaluation.decision,
                "agent_version_id": str(agent_version_id),
                "environment": environment,
            },
        )

        return {
            **self._serialize_gate_evaluation(evaluation),
            "assurance": self._serialize_assurance(assurance) if assurance else None,
            "score_summary": result.score_summary,
        }

    def _upsert_assurance_from_gate(
        self,
        *,
        evaluation: DeploymentGateEvaluation,
        plan: EvaluationPlan | None,
        version: AgentVersion,
        requirements: list[EvaluationRequirement],
        created_by: str,
    ) -> AssuranceRecord | None:
        now = _utcnow()
        # Supersede current active records for this version/env
        current = (
            self._db.query(AssuranceRecord)
            .filter(
                AssuranceRecord.agent_version_id == evaluation.agent_version_id,
                AssuranceRecord.environment == evaluation.environment,
                AssuranceRecord.status.in_(
                    [AssuranceStatus.VALID.value, AssuranceStatus.CONDITIONAL.value]
                ),
                AssuranceRecord.superseded_at.is_(None),
            )
            .all()
        )

        if evaluation.decision == GateDecision.FAIL.value:
            for row in current:
                row.status = AssuranceStatus.FAILED.value
                row.superseded_at = now
                row.reason = evaluation.reason
            record = AssuranceRecord(
                ai_system_id=evaluation.ai_system_id,
                agent_version_id=evaluation.agent_version_id,
                environment=evaluation.environment,
                status=AssuranceStatus.FAILED.value,
                gate_evaluation_id=evaluation.id,
                evaluation_plan_id=plan.id if plan else None,
                config_digest=version.configuration_digest,
                evidence_refs=evaluation.evidence_refs,
                reason=evaluation.reason,
                created_by=created_by,
            )
            self._db.add(record)
            return record

        if evaluation.decision == GateDecision.WAIVER_REQUIRED.value:
            for row in current:
                row.superseded_at = now
                row.reason = "Superseded by waiver-required gate evaluation"
            record = AssuranceRecord(
                ai_system_id=evaluation.ai_system_id,
                agent_version_id=evaluation.agent_version_id,
                environment=evaluation.environment,
                status=AssuranceStatus.FAILED.value,
                gate_evaluation_id=evaluation.id,
                evaluation_plan_id=plan.id if plan else None,
                config_digest=version.configuration_digest,
                evidence_refs=evaluation.evidence_refs,
                reason=evaluation.reason,
                created_by=created_by,
            )
            self._db.add(record)
            return record

        validity_days = None
        for req in requirements:
            if req.required and req.validity_days:
                validity_days = (
                    min(validity_days, req.validity_days)
                    if validity_days is not None
                    else req.validity_days
                )
        valid_until = now + timedelta(days=validity_days) if validity_days else None
        status = (
            AssuranceStatus.CONDITIONAL.value
            if evaluation.decision == GateDecision.PASS_WITH_CONDITIONS.value
            else AssuranceStatus.VALID.value
        )
        for row in current:
            row.superseded_at = now
            row.reason = "Superseded by newer gate evaluation"

        record = AssuranceRecord(
            ai_system_id=evaluation.ai_system_id,
            agent_version_id=evaluation.agent_version_id,
            environment=evaluation.environment,
            status=status,
            valid_from=now,
            valid_until=valid_until,
            gate_evaluation_id=evaluation.id,
            evaluation_plan_id=plan.id if plan else None,
            config_digest=version.configuration_digest,
            evidence_refs=evaluation.evidence_refs,
            reason=evaluation.reason,
            created_by=created_by,
        )
        self._db.add(record)
        log_siem_event(
            trace_id=str(evaluation.id),
            event_type="assurance.valid",
            decision="allow",
            metadata={
                "agent_version_id": str(evaluation.agent_version_id),
                "status": status,
                "valid_until": _ser_dt(valid_until),
            },
        )
        return record

    # ------------------------------------------------------------------
    # Assurance
    # ------------------------------------------------------------------

    def get_assurance(
        self,
        agent_version_id: UUID,
        *,
        environment: str = EvaluationEnvironment.PRODUCTION.value,
        include_history: bool = False,
    ) -> dict[str, Any]:
        self._validate_agent_version_ownership(agent_version_id)
        self.refresh_assurance_expiry(agent_version_id, environment=environment)
        q = self._db.query(AssuranceRecord).filter(
            AssuranceRecord.agent_version_id == agent_version_id,
            AssuranceRecord.environment == environment,
        )
        if not include_history:
            q = q.filter(AssuranceRecord.superseded_at.is_(None))
        rows = q.order_by(AssuranceRecord.created_at.desc()).all()
        current = rows[0] if rows else None
        return {
            "agent_version_id": str(agent_version_id),
            "environment": environment,
            "current": self._serialize_assurance(current) if current else None,
            "history": [self._serialize_assurance(r) for r in rows]
            if include_history
            else [],
            "reassessment_required": self._has_open_reassessment(agent_version_id),
            "deployment_eligible": self.is_environment_eligible(
                agent_version_id, environment
            ),
        }

    def is_environment_eligible(
        self,
        agent_version_id: UUID,
        environment: str = EvaluationEnvironment.PRODUCTION.value,
    ) -> bool:
        """Authoritative WP7 eligibility contribution for an environment."""
        version = (
            self._db.query(AgentVersion)
            .filter(AgentVersion.id == agent_version_id)
            .first()
        )
        if version is None:
            return False
        agent = self._db.query(Agent).filter(Agent.id == version.agent_id).first()
        if agent is None:
            return False

        requirements = self.resolve_requirements(
            ai_system_id=agent.ai_system_id, environment=environment
        )
        required = [r for r in requirements if r.required]
        # Backwards compatible: no required evaluations configured → do not block
        if not required:
            return True

        if self._has_open_reassessment(agent_version_id):
            return False

        self.refresh_assurance_expiry(agent_version_id, environment=environment)
        current = (
            self._db.query(AssuranceRecord)
            .filter(
                AssuranceRecord.agent_version_id == agent_version_id,
                AssuranceRecord.environment == environment,
                AssuranceRecord.superseded_at.is_(None),
                AssuranceRecord.status.in_(
                    [AssuranceStatus.VALID.value, AssuranceStatus.CONDITIONAL.value]
                ),
            )
            .order_by(AssuranceRecord.created_at.desc())
            .first()
        )
        if current is None:
            return False
        if current.valid_until and current.valid_until <= _utcnow():
            return False
        # Config digest must still match exact version
        if (
            current.config_digest
            and version.configuration_digest
            and current.config_digest != version.configuration_digest
        ):
            return False
        return True

    def refresh_assurance_expiry(
        self,
        agent_version_id: UUID,
        *,
        environment: str = EvaluationEnvironment.PRODUCTION.value,
    ) -> None:
        now = _utcnow()
        rows = (
            self._db.query(AssuranceRecord)
            .filter(
                AssuranceRecord.agent_version_id == agent_version_id,
                AssuranceRecord.environment == environment,
                AssuranceRecord.status.in_(
                    [AssuranceStatus.VALID.value, AssuranceStatus.CONDITIONAL.value]
                ),
                AssuranceRecord.superseded_at.is_(None),
                AssuranceRecord.valid_until.isnot(None),
                AssuranceRecord.valid_until <= now,
            )
            .all()
        )
        for row in rows:
            row.status = AssuranceStatus.EXPIRED.value
            row.reason = "Assurance validity period expired"
            self._db.add(
                ReassessmentTrigger(
                    ai_system_id=row.ai_system_id,
                    agent_version_id=agent_version_id,
                    trigger_type=ReassessmentTriggerType.ASSURANCE_EXPIRED.value,
                    status=ReassessmentStatus.REQUIRED.value,
                    reason="Assurance expired",
                    source_ref=str(row.id),
                    created_by="system",
                )
            )
            log_siem_event(
                trace_id=str(row.id),
                event_type="assurance.expired",
                decision="deny",
                metadata={"assurance_id": str(row.id)},
            )
        if rows:
            self._db.commit()

    def invalidate_assurance(
        self,
        agent_version_id: UUID,
        *,
        reason: str,
        trigger_type: str,
        change_category: str | None = None,
        created_by: str = "system",
        environment: str | None = None,
    ) -> list[dict[str, Any]]:
        q = self._db.query(AssuranceRecord).filter(
            AssuranceRecord.agent_version_id == agent_version_id,
            AssuranceRecord.status.in_(
                [AssuranceStatus.VALID.value, AssuranceStatus.CONDITIONAL.value]
            ),
            AssuranceRecord.superseded_at.is_(None),
        )
        if environment:
            q = q.filter(AssuranceRecord.environment == environment)
        rows = q.all()
        now = _utcnow()
        impacted = IMPACT_MAP.get(change_category or "", frozenset())
        out = []
        for row in rows:
            row.status = AssuranceStatus.INVALIDATED.value
            row.superseded_at = now
            row.reason = reason
            trigger = ReassessmentTrigger(
                ai_system_id=row.ai_system_id,
                agent_version_id=agent_version_id,
                trigger_type=trigger_type,
                change_category=change_category,
                impacted_categories=sorted(impacted) if impacted else None,
                status=ReassessmentStatus.REQUIRED.value,
                reason=reason,
                source_ref=str(row.id),
                created_by=created_by,
            )
            self._db.add(trigger)
            log_siem_event(
                trace_id=str(row.id),
                event_type="assurance.invalidated",
                decision="deny",
                metadata={
                    "assurance_id": str(row.id),
                    "reason": reason,
                    "trigger_type": trigger_type,
                },
            )
            log_siem_event(
                trace_id=str(row.id),
                event_type="reassessment.required",
                decision="deny",
                metadata={"agent_version_id": str(agent_version_id)},
            )
            out.append(self._serialize_assurance(row))
        if rows:
            self._db.commit()
        return out

    def deployment_readiness(
        self,
        agent_version_id: UUID,
        *,
        environment: str = EvaluationEnvironment.PRODUCTION.value,
    ) -> dict[str, Any]:
        version = self._validate_agent_version_ownership(agent_version_id)
        agent = self._db.query(Agent).filter(Agent.id == version.agent_id).first()
        assert agent is not None
        from rai_gateway.registry.eligibility import EligibilityService

        lifecycle = EligibilityService(self._db).evaluate(
            system_id=agent.ai_system_id,
            agent_id=agent.id,
            version_id=version.id,
            skip_assurance=True,
        )
        assurance = self.get_assurance(agent_version_id, environment=environment)
        requirements = self.list_requirements(
            ai_system_id=agent.ai_system_id, environment=environment
        )
        runs = self.list_runs(agent_version_id=agent_version_id, limit=100)
        checks = [
            {
                "name": "Lifecycle",
                "result": "PASS" if lifecycle.eligible else "FAIL",
                "detail": lifecycle.reason,
            },
        ]
        from rai_gateway.models.registry import RiskAssessment

        has_risk = (
            self._db.query(RiskAssessment)
            .filter(RiskAssessment.agent_version_id == agent_version_id)
            .first()
            is not None
        )
        checks.append(
            {
                "name": "Risk Assessment",
                "result": "PASS" if has_risk else "FAIL",
                "detail": "present" if has_risk else "missing",
            }
        )
        for req in requirements:
            if not req.get("required"):
                continue
            run = next(
                (
                    r
                    for r in runs
                    if r.get("requirement_id") == req["id"]
                    and r.get("status") in {"PASSED", "FAILED"}
                ),
                None,
            )
            if run is None:
                result = "FAIL"
                detail = "not run"
            elif float(run.get("score") or 0) >= float(req["minimum_score"]) and int(
                run.get("critical_failures") or 0
            ) <= int(req["maximum_failed_critical_cases"]):
                result = "PASS"
                detail = f"score={run.get('score')}"
            else:
                result = "FAIL"
                detail = (
                    f"score={run.get('score')} critical={run.get('critical_failures')}"
                )
            checks.append({"name": req["name"], "result": result, "detail": detail})

        current = assurance.get("current")
        gate_status = (current or {}).get("status") or "MISSING"
        gate_pass = gate_status in {
            AssuranceStatus.VALID.value,
            AssuranceStatus.CONDITIONAL.value,
        }
        checks.append(
            {
                "name": "Deployment Gate",
                "result": "PASS" if gate_pass else "FAIL",
                "detail": (current or {}).get("reason") or gate_status,
            }
        )
        eligible = bool(lifecycle.eligible) and self.is_environment_eligible(
            agent_version_id, environment
        )
        checks.append(
            {
                "name": f"{environment.title()} Eligible",
                "result": "PASS" if eligible else "FAIL",
                "detail": "YES" if eligible else "NO",
            }
        )
        return {
            "agent_version_id": str(agent_version_id),
            "environment": environment,
            "checks": checks,
            "eligible": eligible,
            "assurance": current,
            "reassessment_required": assurance.get("reassessment_required"),
            "open_failures": [c for c in checks if c["result"] == "FAIL"],
        }

    # ------------------------------------------------------------------
    # Waivers
    # ------------------------------------------------------------------

    def request_waiver(
        self,
        *,
        agent_version_id: UUID,
        justification: str,
        failed_condition: dict[str, Any],
        requester: str,
        environment: str = EvaluationEnvironment.PRODUCTION.value,
        compensating_controls: dict[str, Any] | list[Any] | None = None,
        valid_until: datetime | None = None,
        gate_evaluation_id: UUID | None = None,
        validity_days: int | None = 14,
    ) -> dict[str, Any]:
        if not failed_condition.get("waivable", True):
            raise WaiverDeniedError("Condition is not waivable")
        version = self._validate_agent_version_ownership(agent_version_id)
        agent = self._db.query(Agent).filter(Agent.id == version.agent_id).first()
        assert agent is not None
        until = valid_until or (
            _utcnow() + timedelta(days=validity_days) if validity_days else None
        )
        waiver = EvaluationWaiver(
            ai_system_id=agent.ai_system_id,
            agent_version_id=agent_version_id,
            gate_evaluation_id=gate_evaluation_id,
            environment=environment,
            failed_condition=failed_condition,
            justification=justification,
            compensating_controls=compensating_controls,
            status=WaiverStatus.REQUESTED.value,
            requester=requester,
            valid_until=until,
        )
        self._db.add(waiver)
        self._db.commit()
        self._db.refresh(waiver)
        log_siem_event(
            trace_id=str(waiver.id),
            event_type="waiver.requested",
            decision="allow",
            metadata={"waiver_id": str(waiver.id), "requester": requester},
        )
        return self._serialize_waiver(waiver)

    def approve_waiver(
        self,
        waiver_id: UUID,
        *,
        approver: str,
        decision_reason: str | None = None,
    ) -> dict[str, Any]:
        waiver = self._get_waiver(waiver_id)
        self._validate_ai_system_ownership(waiver.ai_system_id)
        if waiver.status != WaiverStatus.REQUESTED.value:
            raise EvaluationConflictError(f"Waiver status is {waiver.status}")
        if approver == waiver.requester:
            raise WaiverDeniedError(
                "Separation of duties: requester cannot approve their own waiver"
            )
        waiver.status = WaiverStatus.APPROVED.value
        waiver.approver = approver
        waiver.decision_reason = decision_reason
        waiver.decided_at = _utcnow()
        self._db.commit()
        self._db.refresh(waiver)
        log_siem_event(
            trace_id=str(waiver.id),
            event_type="waiver.approved",
            decision="allow",
            metadata={"waiver_id": str(waiver.id), "approver": approver},
        )
        # Re-evaluate gate to potentially yield PASS_WITH_CONDITIONS
        self.evaluate_deployment_gate(
            agent_version_id=waiver.agent_version_id,
            environment=waiver.environment,
            evaluated_by=approver,
            gate_id=None,
        )
        self._db.refresh(waiver)
        return self._serialize_waiver(waiver)

    def reject_waiver(
        self,
        waiver_id: UUID,
        *,
        approver: str,
        decision_reason: str | None = None,
    ) -> dict[str, Any]:
        waiver = self._get_waiver(waiver_id)
        self._validate_ai_system_ownership(waiver.ai_system_id)
        if waiver.status != WaiverStatus.REQUESTED.value:
            raise EvaluationConflictError(f"Waiver status is {waiver.status}")
        if approver == waiver.requester:
            raise WaiverDeniedError(
                "Separation of duties: requester cannot reject their own waiver"
            )
        waiver.status = WaiverStatus.REJECTED.value
        waiver.approver = approver
        waiver.decision_reason = decision_reason
        waiver.decided_at = _utcnow()
        self._db.commit()
        self._db.refresh(waiver)
        log_siem_event(
            trace_id=str(waiver.id),
            event_type="waiver.rejected",
            decision="deny",
            metadata={"waiver_id": str(waiver.id)},
        )
        return self._serialize_waiver(waiver)

    def revoke_waiver(
        self,
        waiver_id: UUID,
        *,
        actor: str,
        decision_reason: str | None = None,
    ) -> dict[str, Any]:
        waiver = self._get_waiver(waiver_id)
        self._validate_ai_system_ownership(waiver.ai_system_id)
        if waiver.status != WaiverStatus.APPROVED.value:
            raise EvaluationConflictError("Only approved waivers can be revoked")
        waiver.status = WaiverStatus.REVOKED.value
        waiver.decision_reason = decision_reason or waiver.decision_reason
        waiver.revoked_at = _utcnow()
        self._db.commit()
        self.invalidate_assurance(
            waiver.agent_version_id,
            reason=f"Waiver {waiver.id} revoked",
            trigger_type=ReassessmentTriggerType.MANUAL.value,
            created_by=actor,
            environment=waiver.environment,
        )
        self._db.refresh(waiver)
        return self._serialize_waiver(waiver)

    def list_waivers(
        self,
        *,
        agent_version_id: UUID | None = None,
        ai_system_id: UUID | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        q = self._db.query(EvaluationWaiver).join(
            AISystem, EvaluationWaiver.ai_system_id == AISystem.id
        )
        if agent_version_id:
            q = q.filter(EvaluationWaiver.agent_version_id == agent_version_id)
        if ai_system_id:
            q = q.filter(EvaluationWaiver.ai_system_id == ai_system_id)
        if status:
            q = q.filter(EvaluationWaiver.status == status)
        return [
            self._serialize_waiver(w)
            for w in q.order_by(EvaluationWaiver.created_at.desc()).all()
        ]

    # ------------------------------------------------------------------
    # Reassessment helpers
    # ------------------------------------------------------------------

    def list_reassessment_triggers(
        self, agent_version_id: UUID
    ) -> list[dict[str, Any]]:
        self._validate_agent_version_ownership(agent_version_id)
        rows = (
            self._db.query(ReassessmentTrigger)
            .filter(ReassessmentTrigger.agent_version_id == agent_version_id)
            .order_by(ReassessmentTrigger.created_at.desc())
            .all()
        )
        return [self._serialize_trigger(t) for t in rows]

    def impacted_categories_for_changes(self, change_categories: list[str]) -> set[str]:
        impacted: set[str] = set()
        for cat in change_categories:
            impacted |= set(IMPACT_MAP.get(cat, frozenset()))
        return impacted

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _has_open_reassessment(self, agent_version_id: UUID) -> bool:
        return (
            self._db.query(ReassessmentTrigger)
            .filter(
                ReassessmentTrigger.agent_version_id == agent_version_id,
                ReassessmentTrigger.status == ReassessmentStatus.REQUIRED.value,
            )
            .count()
            > 0
        )

    def _dependency_digest(self, version_id: UUID) -> str:
        deps = (
            self._db.query(AgentVersionDependency)
            .filter(AgentVersionDependency.agent_version_id == version_id)
            .all()
        )
        payload = sorted(
            [
                {
                    "type": d.resource_type,
                    "id": str(d.resource_id),
                    "capability": d.capability_declaration,
                }
                for d in deps
            ],
            key=lambda x: (x["type"], x["id"]),
        )
        return _digest(payload)

    def _get_suite(self, suite_id: UUID) -> EvaluationSuite:
        suite = (
            self._db.query(EvaluationSuite)
            .filter(EvaluationSuite.id == suite_id)
            .first()
        )
        if not suite:
            raise EvaluationNotFoundError("Evaluation suite not found")
        return suite

    def _get_plan(self, plan_id: UUID) -> EvaluationPlan:
        plan = (
            self._db.query(EvaluationPlan).filter(EvaluationPlan.id == plan_id).first()
        )
        if not plan:
            raise EvaluationNotFoundError("Evaluation plan not found")
        return plan

    def _get_version(self, version_id: UUID) -> AgentVersion:
        version = (
            self._db.query(AgentVersion).filter(AgentVersion.id == version_id).first()
        )
        if not version:
            raise EvaluationNotFoundError("Agent version not found")
        return version

    def _get_waiver(self, waiver_id: UUID) -> EvaluationWaiver:
        waiver = (
            self._db.query(EvaluationWaiver)
            .filter(EvaluationWaiver.id == waiver_id)
            .first()
        )
        if not waiver:
            raise EvaluationNotFoundError("Waiver not found")
        return waiver

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def _serialize_suite(self, suite: EvaluationSuite) -> dict[str, Any]:
        return {
            "id": str(suite.id),
            "ai_system_id": str(suite.ai_system_id),
            "suite_key": suite.suite_key,
            "name": suite.name,
            "category": suite.category,
            "version": suite.version,
            "description": suite.description,
            "published": suite.published,
            "published_at": _ser_dt(suite.published_at),
            "runner_type": suite.runner_type,
            "runner_config": suite.runner_config,
            "created_by": suite.created_by,
            "created_at": _ser_dt(suite.created_at),
        }

    def _serialize_case(self, case: EvaluationCase) -> dict[str, Any]:
        return {
            "id": str(case.id),
            "suite_id": str(case.suite_id),
            "case_key": case.case_key,
            "name": case.name,
            "description": case.description,
            "input_fixture": case.input_fixture,
            "expected_behavior": case.expected_behavior,
            "scoring_method": case.scoring_method,
            "threshold": case.threshold,
            "failure_severity": case.failure_severity,
            "enabled": case.enabled,
            "sort_order": case.sort_order,
        }

    def _serialize_requirement(self, req: EvaluationRequirement) -> dict[str, Any]:
        return {
            "id": str(req.id),
            "ai_system_id": str(req.ai_system_id),
            "name": req.name,
            "category": req.category,
            "evaluation_suite_id": str(req.evaluation_suite_id),
            "minimum_score": req.minimum_score,
            "maximum_failed_critical_cases": req.maximum_failed_critical_cases,
            "required": req.required,
            "validity_days": req.validity_days,
            "environment_scope": req.environment_scope,
            "enabled": req.enabled,
            "accepted_runner_types": req.accepted_runner_types,
            "created_by": req.created_by,
            "created_at": _ser_dt(req.created_at),
        }

    def _serialize_plan(self, plan: EvaluationPlan) -> dict[str, Any]:
        return {
            "id": str(plan.id),
            "ai_system_id": str(plan.ai_system_id),
            "agent_id": str(plan.agent_id),
            "agent_version_id": str(plan.agent_version_id),
            "target_environment": plan.target_environment,
            "requirement_snapshot": plan.requirement_snapshot,
            "agent_config_digest": plan.agent_config_digest,
            "dependency_digest": plan.dependency_digest,
            "plan_digest": plan.plan_digest,
            "status": plan.status,
            "created_by": plan.created_by,
            "created_at": _ser_dt(plan.created_at),
        }

    def _serialize_run(
        self, run: EvaluationRun, *, include_cases: bool = False
    ) -> dict[str, Any]:
        data = {
            "id": str(run.id),
            "plan_id": str(run.plan_id),
            "ai_system_id": str(run.ai_system_id),
            "agent_version_id": str(run.agent_version_id),
            "suite_id": str(run.suite_id),
            "suite_version": run.suite_version,
            "requirement_id": str(run.requirement_id) if run.requirement_id else None,
            "runner_type": run.runner_type,
            "runner_version": run.runner_version,
            "status": run.status,
            "score": run.score,
            "total_cases": run.total_cases,
            "passed_cases": run.passed_cases,
            "failed_cases": run.failed_cases,
            "critical_failures": run.critical_failures,
            "evidence": run.evidence,
            "error_message": run.error_message,
            "started_at": _ser_dt(run.started_at),
            "completed_at": _ser_dt(run.completed_at),
            "created_by": run.created_by,
            "created_at": _ser_dt(run.created_at),
        }
        if include_cases:
            cases = (
                self._db.query(EvaluationCaseResult)
                .filter(EvaluationCaseResult.run_id == run.id)
                .order_by(EvaluationCaseResult.case_key)
                .all()
            )
            data["case_results"] = [
                {
                    "id": str(c.id),
                    "case_key": c.case_key,
                    "case_id": str(c.case_id) if c.case_id else None,
                    "status": c.status,
                    "score": c.score,
                    "severity": c.severity,
                    "explanation": c.explanation,
                    "actual_output": c.actual_output,
                    "evidence_refs": c.evidence_refs,
                }
                for c in cases
            ]
        return data

    def _serialize_gate(self, gate: DeploymentGate) -> dict[str, Any]:
        return {
            "id": str(gate.id),
            "ai_system_id": str(gate.ai_system_id),
            "name": gate.name,
            "environment": gate.environment,
            "description": gate.description,
            "conditions": gate.conditions,
            "enabled": gate.enabled,
            "created_by": gate.created_by,
            "created_at": _ser_dt(gate.created_at),
        }

    def _serialize_gate_evaluation(
        self, evaluation: DeploymentGateEvaluation
    ) -> dict[str, Any]:
        return {
            "id": str(evaluation.id),
            "gate_id": str(evaluation.gate_id) if evaluation.gate_id else None,
            "ai_system_id": str(evaluation.ai_system_id),
            "agent_version_id": str(evaluation.agent_version_id),
            "evaluation_plan_id": str(evaluation.evaluation_plan_id)
            if evaluation.evaluation_plan_id
            else None,
            "environment": evaluation.environment,
            "decision": evaluation.decision,
            "condition_results": evaluation.condition_results,
            "reason": evaluation.reason,
            "evidence_refs": evaluation.evidence_refs,
            "evaluated_by": evaluation.evaluated_by,
            "evaluated_at": _ser_dt(evaluation.evaluated_at),
        }

    def _serialize_assurance(self, record: AssuranceRecord) -> dict[str, Any]:
        return {
            "id": str(record.id),
            "ai_system_id": str(record.ai_system_id),
            "agent_version_id": str(record.agent_version_id),
            "environment": record.environment,
            "status": record.status,
            "valid_from": _ser_dt(record.valid_from),
            "valid_until": _ser_dt(record.valid_until),
            "gate_evaluation_id": str(record.gate_evaluation_id)
            if record.gate_evaluation_id
            else None,
            "evaluation_plan_id": str(record.evaluation_plan_id)
            if record.evaluation_plan_id
            else None,
            "config_digest": record.config_digest,
            "evidence_refs": record.evidence_refs,
            "reason": record.reason,
            "superseded_at": _ser_dt(record.superseded_at),
            "created_by": record.created_by,
            "created_at": _ser_dt(record.created_at),
        }

    def _serialize_waiver(self, waiver: EvaluationWaiver) -> dict[str, Any]:
        return {
            "id": str(waiver.id),
            "ai_system_id": str(waiver.ai_system_id),
            "agent_version_id": str(waiver.agent_version_id),
            "gate_evaluation_id": str(waiver.gate_evaluation_id)
            if waiver.gate_evaluation_id
            else None,
            "environment": waiver.environment,
            "failed_condition": waiver.failed_condition,
            "justification": waiver.justification,
            "compensating_controls": waiver.compensating_controls,
            "status": waiver.status,
            "requester": waiver.requester,
            "approver": waiver.approver,
            "decision_reason": waiver.decision_reason,
            "valid_until": _ser_dt(waiver.valid_until),
            "created_at": _ser_dt(waiver.created_at),
            "decided_at": _ser_dt(waiver.decided_at),
            "revoked_at": _ser_dt(waiver.revoked_at),
        }

    def _serialize_trigger(self, trigger: ReassessmentTrigger) -> dict[str, Any]:
        return {
            "id": str(trigger.id),
            "ai_system_id": str(trigger.ai_system_id),
            "agent_version_id": str(trigger.agent_version_id),
            "trigger_type": trigger.trigger_type,
            "change_category": trigger.change_category,
            "impacted_categories": trigger.impacted_categories,
            "status": trigger.status,
            "reason": trigger.reason,
            "source_ref": trigger.source_ref,
            "created_by": trigger.created_by,
            "created_at": _ser_dt(trigger.created_at),
            "completed_at": _ser_dt(trigger.completed_at),
        }


# Silence unused import for CaseResultStatus (used by runners)
_ = CaseResultStatus
