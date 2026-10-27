"""WP7 evaluation runners — fixture, live agent, tool sandbox, model-judge, human."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from rai_gateway.evaluations.domain import (
    CaseOutcome,
    CaseResultStatus,
    EvaluationRunStatus,
    FailureSeverity,
    RunnerType,
    RunOutcome,
)

ASSURANCE_FIXTURE = "FIXTURE_SIMULATED"
ASSURANCE_LIVE_AGENT = "LIVE_AGENT"
ASSURANCE_TOOL_SANDBOX = "TOOL_SANDBOX"
ASSURANCE_MODEL_JUDGE = "MODEL_JUDGE"
ASSURANCE_HUMAN_REVIEW = "HUMAN_REVIEW"


class EvaluationRunner(ABC):
    """Abstract evaluation runner."""

    runner_type: RunnerType
    runner_version: str = "1.0.0"
    assurance_class: str = ASSURANCE_FIXTURE

    @abstractmethod
    def execute(
        self,
        *,
        cases: list[dict[str, Any]],
        agent_config: dict[str, Any] | None = None,
        runner_config: dict[str, Any] | None = None,
    ) -> RunOutcome:
        raise NotImplementedError

    def _aggregate(
        self,
        outcomes: list[CaseOutcome],
        *,
        agent_config: dict[str, Any] | None,
        extra_evidence: dict[str, Any] | None = None,
    ) -> RunOutcome:
        passed = 0
        failed = 0
        critical = 0
        scores: list[float] = []
        for outcome in outcomes:
            scores.append(outcome.score)
            if outcome.status == CaseResultStatus.PASS:
                passed += 1
            elif outcome.status in {CaseResultStatus.FAIL, CaseResultStatus.ERROR}:
                failed += 1
                if outcome.severity == FailureSeverity.CRITICAL.value:
                    critical += 1

        total = len([o for o in outcomes if o.status != CaseResultStatus.SKIPPED])
        avg = sum(scores) / len(scores) if scores else 0.0
        status = (
            EvaluationRunStatus.PASSED
            if failed == 0 and total > 0
            else EvaluationRunStatus.FAILED
            if total > 0
            else EvaluationRunStatus.ERROR
        )
        evidence = {
            "runner_type": self.runner_type.value,
            "runner_version": self.runner_version,
            "assurance_class": self.assurance_class,
            "agent_config_keys": sorted((agent_config or {}).keys()),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        if extra_evidence:
            evidence.update(extra_evidence)
        return RunOutcome(
            status=status,
            score=round(avg, 4),
            total_cases=total,
            passed_cases=passed,
            failed_cases=failed,
            critical_failures=critical,
            case_outcomes=outcomes,
            evidence=evidence,
        )


def score_case(
    *,
    case_key: str,
    method: str,
    actual: Any,
    expected: dict[str, Any],
    threshold: float,
    severity: str | None,
    evidence: dict[str, Any] | None = None,
) -> CaseOutcome:
    """Shared scoring used by all runners."""
    ok = False
    score = 0.0
    explanation = ""

    if method == "exact_match":
        expected_value = expected.get("value", expected.get("output"))
        ok = actual == expected_value
        score = 1.0 if ok else 0.0
        explanation = (
            "Exact match" if ok else f"Expected {expected_value!r}, got {actual!r}"
        )
    elif method == "contains":
        needles = expected.get("contains", expected.get("value"))
        if isinstance(needles, str):
            needles = [needles]
        text = "" if actual is None else str(actual)
        missing = [n for n in (needles or []) if str(n) not in text]
        ok = not missing
        score = 1.0 if ok else 0.0
        explanation = "Contains all expected" if ok else f"Missing {missing}"
    elif method == "threshold":
        try:
            numeric = float(actual)
        except (TypeError, ValueError):
            numeric = 0.0
        ok = numeric >= threshold
        score = max(0.0, min(1.0, numeric))
        explanation = (
            f"Score {numeric} >= {threshold}"
            if ok
            else f"Score {numeric} < {threshold}"
        )
    elif method == "json_path_equals":
        paths = expected.get("paths") or expected
        missing = []
        if isinstance(paths, dict):
            for path, want in paths.items():
                got = _dig(actual if isinstance(actual, dict) else {}, path)
                if got != want:
                    missing.append(f"{path}: expected {want!r} got {got!r}")
        ok = not missing
        score = 1.0 if ok else 0.0
        explanation = "Paths match" if ok else "; ".join(missing)
    elif method == "assert_false":
        flag_path = expected.get("flag") or "violated"
        flag_val = _dig(
            actual if isinstance(actual, dict) else {"value": actual}, flag_path
        )
        if flag_val is None and isinstance(actual, bool):
            flag_val = actual
        ok = not bool(flag_val)
        score = 1.0 if ok else 0.0
        explanation = (
            "No forbidden behavior"
            if ok
            else expected.get("message", "Forbidden behavior detected")
        )
    elif method == "max_value":
        try:
            numeric = float(actual)
        except (TypeError, ValueError):
            numeric = float("inf")
        max_allowed = float(expected.get("max", threshold))
        ok = numeric <= max_allowed
        score = 1.0 if ok else 0.0
        explanation = (
            f"{numeric} <= {max_allowed}"
            if ok
            else f"Value {numeric} exceeds maximum authorized {max_allowed}"
        )
    else:
        return CaseOutcome(
            case_key=case_key,
            status=CaseResultStatus.ERROR,
            score=0.0,
            severity=severity,
            explanation=f"Unknown scoring method: {method}",
            actual_output=actual,
            evidence=evidence or {},
        )

    if method == "threshold":
        status = CaseResultStatus.PASS if ok else CaseResultStatus.FAIL
    else:
        status = (
            CaseResultStatus.PASS
            if score >= threshold and ok
            else CaseResultStatus.FAIL
        )

    return CaseOutcome(
        case_key=case_key,
        status=status,
        score=round(score, 4),
        severity=severity if status == CaseResultStatus.FAIL else None,
        explanation=explanation,
        actual_output=actual,
        evidence={"scoring_method": method, "threshold": threshold, **(evidence or {})},
    )


class DeterministicRunner(EvaluationRunner):
    """Fixture-based runner — proves config/fixture rules, not live agent behavior."""

    runner_type = RunnerType.DETERMINISTIC
    runner_version = "1.0.0"
    assurance_class = ASSURANCE_FIXTURE

    def execute(
        self,
        *,
        cases: list[dict[str, Any]],
        agent_config: dict[str, Any] | None = None,
        runner_config: dict[str, Any] | None = None,
    ) -> RunOutcome:
        outcomes: list[CaseOutcome] = []
        for case in cases:
            if not case.get("enabled", True):
                outcomes.append(
                    CaseOutcome(
                        case_key=case["case_key"],
                        status=CaseResultStatus.SKIPPED,
                        score=0.0,
                        explanation="Case disabled",
                    )
                )
                continue
            try:
                outcomes.append(self._evaluate_case(case, agent_config or {}))
            except Exception as exc:  # noqa: BLE001 — case isolation
                outcomes.append(
                    CaseOutcome(
                        case_key=case["case_key"],
                        status=CaseResultStatus.ERROR,
                        score=0.0,
                        severity=case.get("failure_severity"),
                        explanation=str(exc),
                    )
                )
        return self._aggregate(outcomes, agent_config=agent_config)

    def _evaluate_case(
        self, case: dict[str, Any], agent_config: dict[str, Any]
    ) -> CaseOutcome:
        fixture = case.get("input_fixture") or {}
        expected = case.get("expected_behavior") or {}
        method = case.get("scoring_method") or "exact_match"
        threshold = float(case.get("threshold") or 1.0)
        severity = case.get("failure_severity")

        actual = fixture.get("simulate")
        if actual is None and "derive_from_config" in fixture:
            path = fixture["derive_from_config"]
            actual = _dig(agent_config, path)
            if "transform" in fixture:
                actual = _apply_transform(actual, fixture["transform"], agent_config)

        return score_case(
            case_key=case["case_key"],
            method=method,
            actual=actual,
            expected=expected,
            threshold=threshold,
            severity=severity,
            evidence={"assurance_class": ASSURANCE_FIXTURE},
        )


class AgentEvaluationRunner(EvaluationRunner):
    """Calls a controlled test instance of the exact Agent Version.

    runner_config:
      endpoint_url: required HTTP endpoint for the agent under test
      agent_version_id: registry version id (injected by EvaluationService)
      agent_config_digest: exact config digest (injected by EvaluationService)
      timeout_seconds: optional (default 30)
      headers: optional dict
      allowed_hosts: optional host allowlist (defaults to private/local hosts only)
    """

    runner_type = RunnerType.AGENT
    runner_version = "1.0.0"
    assurance_class = ASSURANCE_LIVE_AGENT

    def execute(
        self,
        *,
        cases: list[dict[str, Any]],
        agent_config: dict[str, Any] | None = None,
        runner_config: dict[str, Any] | None = None,
    ) -> RunOutcome:
        cfg = runner_config or {}
        endpoint = cfg.get("endpoint_url")
        if not endpoint:
            return RunOutcome(
                status=EvaluationRunStatus.ERROR,
                score=0.0,
                total_cases=0,
                passed_cases=0,
                failed_cases=0,
                critical_failures=0,
                case_outcomes=[],
                evidence={
                    "assurance_class": ASSURANCE_LIVE_AGENT,
                    "runner_type": self.runner_type.value,
                },
                error="AGENT runner requires runner_config.endpoint_url",
            )

        binding_error = self._validate_version_binding(cfg)
        if binding_error:
            return RunOutcome(
                status=EvaluationRunStatus.ERROR,
                score=0.0,
                total_cases=0,
                passed_cases=0,
                failed_cases=0,
                critical_failures=0,
                case_outcomes=[],
                evidence={
                    "assurance_class": ASSURANCE_LIVE_AGENT,
                    "runner_type": self.runner_type.value,
                    "agent_version_id": cfg.get("agent_version_id"),
                    "config_digest": cfg.get("agent_config_digest"),
                },
                error=binding_error,
            )

        outcomes: list[CaseOutcome] = []
        for case in cases:
            if not case.get("enabled", True):
                outcomes.append(
                    CaseOutcome(
                        case_key=case["case_key"],
                        status=CaseResultStatus.SKIPPED,
                        score=0.0,
                        explanation="Case disabled",
                    )
                )
                continue
            try:
                outcomes.append(
                    self._evaluate_case(case, agent_config or {}, cfg, endpoint)
                )
            except Exception as exc:  # noqa: BLE001
                outcomes.append(
                    CaseOutcome(
                        case_key=case["case_key"],
                        status=CaseResultStatus.ERROR,
                        score=0.0,
                        severity=case.get("failure_severity"),
                        explanation=str(exc),
                    )
                )
        return self._aggregate(
            outcomes,
            agent_config=agent_config,
            extra_evidence={
                "endpoint_url": endpoint,
                "agent_version_id": cfg.get("agent_version_id"),
                "config_digest": cfg.get("agent_config_digest"),
                "endpoint_binding_source": cfg.get("endpoint_binding_source"),
                "model_provider": cfg.get("model_provider")
                or (agent_config or {}).get("model_provider"),
                "model": cfg.get("model") or (agent_config or {}).get("model"),
            },
        )

    @staticmethod
    def _validate_version_binding(cfg: dict[str, Any]) -> str | None:
        """When binding fields are present, both version id and digest are required."""
        version_id = cfg.get("agent_version_id")
        digest = cfg.get("agent_config_digest")
        if version_id is None and digest is None:
            # Direct unit-test invocation without EvaluationService binding.
            return None
        if not version_id:
            return "AGENT runner binding requires agent_version_id"
        if not digest:
            return "AGENT runner binding requires agent_config_digest"
        return None

    def _evaluate_case(
        self,
        case: dict[str, Any],
        agent_config: dict[str, Any],
        cfg: dict[str, Any],
        endpoint: str,
    ) -> CaseOutcome:
        fixture = case.get("input_fixture") or {}
        # Never treat fixture.simulate as live agent output
        if "simulate" in fixture and "input" not in fixture and "prompt" not in fixture:
            return CaseOutcome(
                case_key=case["case_key"],
                status=CaseResultStatus.ERROR,
                score=0.0,
                severity=case.get("failure_severity"),
                explanation=(
                    "AGENT runner rejects fixture.simulate-only cases; "
                    "provide input/prompt for live invocation"
                ),
            )

        payload = {
            "case_key": case["case_key"],
            "input": fixture.get("input", fixture.get("prompt", fixture)),
            "agent_config": agent_config,
            "agent_version_id": cfg.get("agent_version_id"),
            "agent_config_digest": cfg.get("agent_config_digest"),
            "parameters": fixture.get("parameters") or {},
        }
        response = _http_json(
            endpoint,
            payload,
            timeout=float(cfg.get("timeout_seconds") or 30),
            headers=cfg.get("headers") or {},
            allowed_hosts=cfg.get("allowed_hosts"),
        )
        mismatch = self._response_binding_mismatch(cfg, response)
        if mismatch:
            return CaseOutcome(
                case_key=case["case_key"],
                status=CaseResultStatus.ERROR,
                score=0.0,
                severity=case.get("failure_severity"),
                explanation=mismatch,
                evidence={
                    "assurance_class": ASSURANCE_LIVE_AGENT,
                    "endpoint_url": endpoint,
                    "agent_version_id": cfg.get("agent_version_id"),
                    "config_digest": cfg.get("agent_config_digest"),
                },
            )

        actual = response.get("output", response.get("result", response))
        tool_proposals = response.get("tool_proposals")
        policy_decisions = response.get("policy_decisions")

        outcome = score_case(
            case_key=case["case_key"],
            method=case.get("scoring_method") or "exact_match",
            actual=actual,
            expected=case.get("expected_behavior") or {},
            threshold=float(case.get("threshold") or 1.0),
            severity=case.get("failure_severity"),
            evidence={
                "assurance_class": ASSURANCE_LIVE_AGENT,
                "endpoint_url": endpoint,
                "agent_version_id": cfg.get("agent_version_id"),
                "config_digest": cfg.get("agent_config_digest"),
                "tool_proposals": tool_proposals,
                "policy_decisions": policy_decisions,
                "raw_response_keys": sorted(response.keys())
                if isinstance(response, dict)
                else [],
            },
        )
        return outcome

    @staticmethod
    def _response_binding_mismatch(
        cfg: dict[str, Any], response: dict[str, Any]
    ) -> str | None:
        """Fail closed if the live agent reports a different version/digest."""
        if not isinstance(response, dict):
            return None
        expected_version = cfg.get("agent_version_id")
        expected_digest = cfg.get("agent_config_digest")
        reported_version = response.get("agent_version_id")
        reported_digest = (
            response.get("agent_config_digest")
            or response.get("configuration_digest")
            or response.get("config_digest")
        )
        if (
            expected_version
            and reported_version
            and str(reported_version) != str(expected_version)
        ):
            return (
                "AGENT response agent_version_id does not match registry binding "
                f"(expected={expected_version}, got={reported_version})"
            )
        if (
            expected_digest
            and reported_digest
            and str(reported_digest) != str(expected_digest)
        ):
            return (
                "AGENT response config digest does not match registry binding "
                f"(expected={expected_digest}, got={reported_digest})"
            )
        return None


class ToolSandboxRunner(EvaluationRunner):
    """Execute tools against a sandbox/mock/non-production endpoint."""

    runner_type = RunnerType.TOOL_SANDBOX
    runner_version = "1.0.0"
    assurance_class = ASSURANCE_TOOL_SANDBOX

    def execute(
        self,
        *,
        cases: list[dict[str, Any]],
        agent_config: dict[str, Any] | None = None,
        runner_config: dict[str, Any] | None = None,
    ) -> RunOutcome:
        cfg = runner_config or {}
        endpoint = cfg.get("endpoint_url") or cfg.get("sandbox_endpoint")
        if not endpoint:
            return RunOutcome(
                status=EvaluationRunStatus.ERROR,
                score=0.0,
                total_cases=0,
                passed_cases=0,
                failed_cases=0,
                critical_failures=0,
                case_outcomes=[],
                evidence={"assurance_class": ASSURANCE_TOOL_SANDBOX},
                error="TOOL_SANDBOX runner requires runner_config.endpoint_url",
            )

        outcomes: list[CaseOutcome] = []
        for case in cases:
            if not case.get("enabled", True):
                outcomes.append(
                    CaseOutcome(
                        case_key=case["case_key"],
                        status=CaseResultStatus.SKIPPED,
                        score=0.0,
                        explanation="Case disabled",
                    )
                )
                continue
            try:
                fixture = case.get("input_fixture") or {}
                tool_name = fixture.get("tool") or fixture.get("tool_name")
                parameters = fixture.get("parameters") or {}
                if not tool_name:
                    outcomes.append(
                        CaseOutcome(
                            case_key=case["case_key"],
                            status=CaseResultStatus.ERROR,
                            score=0.0,
                            severity=case.get("failure_severity"),
                            explanation="TOOL_SANDBOX case requires fixture.tool",
                        )
                    )
                    continue
                response = _http_json(
                    endpoint,
                    {
                        "tool": tool_name,
                        "parameters": parameters,
                        "sandbox": True,
                        "case_key": case["case_key"],
                    },
                    timeout=float(cfg.get("timeout_seconds") or 30),
                    headers=cfg.get("headers") or {},
                    allowed_hosts=cfg.get("allowed_hosts"),
                )
                actual = response.get("result", response.get("output", response))
                outcomes.append(
                    score_case(
                        case_key=case["case_key"],
                        method=case.get("scoring_method") or "exact_match",
                        actual=actual,
                        expected=case.get("expected_behavior") or {},
                        threshold=float(case.get("threshold") or 1.0),
                        severity=case.get("failure_severity"),
                        evidence={
                            "assurance_class": ASSURANCE_TOOL_SANDBOX,
                            "tool": tool_name,
                            "sandbox_endpoint": endpoint,
                        },
                    )
                )
            except Exception as exc:  # noqa: BLE001
                outcomes.append(
                    CaseOutcome(
                        case_key=case["case_key"],
                        status=CaseResultStatus.ERROR,
                        score=0.0,
                        severity=case.get("failure_severity"),
                        explanation=str(exc),
                    )
                )
        return self._aggregate(
            outcomes,
            agent_config=agent_config,
            extra_evidence={"sandbox_endpoint": endpoint},
        )


class ModelJudgeRunner(EvaluationRunner):
    """Semantic rubric judging via a configured judge endpoint."""

    runner_type = RunnerType.MODEL_JUDGE
    runner_version = "1.0.0"
    assurance_class = ASSURANCE_MODEL_JUDGE

    def execute(
        self,
        *,
        cases: list[dict[str, Any]],
        agent_config: dict[str, Any] | None = None,
        runner_config: dict[str, Any] | None = None,
    ) -> RunOutcome:
        cfg = runner_config or {}
        endpoint = cfg.get("endpoint_url") or cfg.get("judge_endpoint")
        if not endpoint:
            return RunOutcome(
                status=EvaluationRunStatus.ERROR,
                score=0.0,
                total_cases=0,
                passed_cases=0,
                failed_cases=0,
                critical_failures=0,
                case_outcomes=[],
                evidence={"assurance_class": ASSURANCE_MODEL_JUDGE},
                error="MODEL_JUDGE runner requires runner_config.endpoint_url",
            )

        outcomes: list[CaseOutcome] = []
        for case in cases:
            if not case.get("enabled", True):
                outcomes.append(
                    CaseOutcome(
                        case_key=case["case_key"],
                        status=CaseResultStatus.SKIPPED,
                        score=0.0,
                        explanation="Case disabled",
                    )
                )
                continue
            try:
                fixture = case.get("input_fixture") or {}
                expected = case.get("expected_behavior") or {}
                rubric = expected.get("rubric") or cfg.get("rubric") or {}
                subject = (
                    fixture.get("output")
                    or fixture.get("subject")
                    or fixture.get("input")
                )
                response = _http_json(
                    endpoint,
                    {
                        "case_key": case["case_key"],
                        "subject": subject,
                        "rubric": rubric,
                        "provider": cfg.get("provider"),
                        "model": cfg.get("model"),
                        "temperature": cfg.get("temperature", 0),
                    },
                    timeout=float(cfg.get("timeout_seconds") or 60),
                    headers=cfg.get("headers") or {},
                    allowed_hosts=cfg.get("allowed_hosts"),
                )
                passed = bool(response.get("pass", response.get("passed")))
                score = float(response.get("score", 1.0 if passed else 0.0))
                # Trust judge pass/fail unless the case sets an explicit score threshold.
                raw_threshold = case.get("threshold")
                if raw_threshold is None:
                    ok = passed
                else:
                    ok = passed and score >= float(raw_threshold)
                outcomes.append(
                    CaseOutcome(
                        case_key=case["case_key"],
                        status=CaseResultStatus.PASS if ok else CaseResultStatus.FAIL,
                        score=round(score, 4),
                        severity=case.get("failure_severity") if not ok else None,
                        explanation=response.get("explanation")
                        or ("Judge passed" if ok else "Judge failed"),
                        actual_output=response,
                        evidence={
                            "assurance_class": ASSURANCE_MODEL_JUDGE,
                            "rubric_digest": cfg.get("rubric_digest"),
                            "provider": cfg.get("provider"),
                            "model": cfg.get("model"),
                            "judge_endpoint": endpoint,
                        },
                    )
                )
            except Exception as exc:  # noqa: BLE001
                outcomes.append(
                    CaseOutcome(
                        case_key=case["case_key"],
                        status=CaseResultStatus.ERROR,
                        score=0.0,
                        severity=case.get("failure_severity"),
                        explanation=str(exc),
                    )
                )
        return self._aggregate(
            outcomes,
            agent_config=agent_config,
            extra_evidence={
                "judge_endpoint": endpoint,
                "provider": cfg.get("provider"),
                "model": cfg.get("model"),
                "rubric_digest": cfg.get("rubric_digest"),
            },
        )


class HumanReviewRunner(EvaluationRunner):
    """Requires an attached human decision; cannot auto-pass without one."""

    runner_type = RunnerType.HUMAN_REVIEW
    runner_version = "1.0.0"
    assurance_class = ASSURANCE_HUMAN_REVIEW

    def execute(
        self,
        *,
        cases: list[dict[str, Any]],
        agent_config: dict[str, Any] | None = None,
        runner_config: dict[str, Any] | None = None,
    ) -> RunOutcome:
        outcomes: list[CaseOutcome] = []
        for case in cases:
            if not case.get("enabled", True):
                outcomes.append(
                    CaseOutcome(
                        case_key=case["case_key"],
                        status=CaseResultStatus.SKIPPED,
                        score=0.0,
                        explanation="Case disabled",
                    )
                )
                continue
            fixture = case.get("input_fixture") or {}
            decision = fixture.get("human_decision") or (runner_config or {}).get(
                "decisions", {}
            ).get(case["case_key"])
            if not isinstance(decision, dict):
                outcomes.append(
                    CaseOutcome(
                        case_key=case["case_key"],
                        status=CaseResultStatus.ERROR,
                        score=0.0,
                        severity=case.get("failure_severity"),
                        explanation=(
                            "HUMAN_REVIEW requires human_decision on the case "
                            "(or runner_config.decisions[case_key])"
                        ),
                        evidence={"assurance_class": ASSURANCE_HUMAN_REVIEW},
                    )
                )
                continue
            passed = bool(decision.get("pass", decision.get("passed", False)))
            score = float(decision.get("score", 1.0 if passed else 0.0))
            outcomes.append(
                CaseOutcome(
                    case_key=case["case_key"],
                    status=CaseResultStatus.PASS if passed else CaseResultStatus.FAIL,
                    score=round(score, 4),
                    severity=case.get("failure_severity") if not passed else None,
                    explanation=decision.get("explanation")
                    or ("Human approved" if passed else "Human rejected"),
                    actual_output=decision,
                    evidence={
                        "assurance_class": ASSURANCE_HUMAN_REVIEW,
                        "reviewer": decision.get("reviewer"),
                        "reviewed_at": decision.get("reviewed_at"),
                    },
                )
            )
        return self._aggregate(outcomes, agent_config=agent_config)


def _http_json(
    url: str,
    payload: dict[str, Any],
    *,
    timeout: float,
    headers: dict[str, str],
    allowed_hosts: list[str] | None,
) -> dict[str, Any]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"Unsupported endpoint scheme: {parsed.scheme!r}")
    host = parsed.hostname or ""
    allow = set(allowed_hosts or ["localhost", "127.0.0.1", "::1"])
    if host not in allow and not any(
        host.endswith(suffix) for suffix in (".local", ".internal", ".test")
    ):
        # Fail closed for unexpected public hosts unless explicitly allowlisted
        if host not in allow:
            raise ValueError(
                f"Endpoint host {host!r} not in allowed_hosts; "
                "refuse outbound evaluation call"
            )

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", **headers},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Evaluation endpoint HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Evaluation endpoint unreachable: {exc}") from exc

    if not raw:
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        return {"output": data}
    return data


def _dig(data: Any, path: str) -> Any:
    if not path:
        return data
    cur = data
    for part in str(path).split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def _apply_transform(value: Any, transform: str, agent_config: dict[str, Any]) -> Any:
    if transform == "discount_percent":
        return agent_config.get("max_discount_percent", value)
    if transform == "as_bool":
        return bool(value)
    return value


def get_runner(runner_type: str) -> EvaluationRunner:
    mapping: dict[str, type[EvaluationRunner]] = {
        RunnerType.DETERMINISTIC.value: DeterministicRunner,
        RunnerType.AGENT.value: AgentEvaluationRunner,
        RunnerType.TOOL_SANDBOX.value: ToolSandboxRunner,
        RunnerType.MODEL_JUDGE.value: ModelJudgeRunner,
        RunnerType.HUMAN_REVIEW.value: HumanReviewRunner,
    }
    cls = mapping.get(runner_type)
    if cls is None:
        raise ValueError(
            f"Runner type {runner_type} is not implemented; "
            f"available: {sorted(mapping)}"
        )
    return cls()
