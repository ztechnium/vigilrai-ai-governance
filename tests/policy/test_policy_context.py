"""Policy evaluation context and capability contracts."""

from __future__ import annotations

from uuid import uuid4

import pytest

from rai_gateway.policy.content_rule_v2 import (
    applies_to_from_intervention_points,
    content_rule_coverage_status,
    intervention_points_from_applies_to,
)
from rai_gateway.policy.context import (
    PolicyEvaluationContext,
    RuntimePolicyCapabilities,
)
from rai_gateway.policy.domain import (
    ContentEvaluationType,
    ContentFailureMode,
    ContentRemediationType,
    PolicyControlDomain,
    PolicyEnforceability,
    PolicyInterventionPoint,
)


def test_enum_values_stable() -> None:
    assert PolicyControlDomain.ACTION.value == "ACTION"
    assert PolicyInterventionPoint.PRE_TOOL.value == "PRE_TOOL"
    assert ContentEvaluationType.LLM_JUDGE.value == "LLM_JUDGE"
    assert ContentFailureMode.INHERIT.value == "INHERIT"
    assert ContentRemediationType.NONE.value == "NONE"
    assert PolicyEnforceability.OBSERVE_ONLY.value == "OBSERVE_ONLY"


def test_runtime_capabilities_supports_point() -> None:
    caps = RuntimePolicyCapabilities(
        intervention_points={PolicyInterventionPoint.PRE_TOOL.value},
        can_block_tool_call=True,
    )
    assert caps.supports_point("PRE_TOOL")
    assert not caps.supports_point("OUTPUT")


def test_policy_evaluation_context_requires_valid_point() -> None:
    with pytest.raises(ValueError, match="intervention_point"):
        PolicyEvaluationContext(
            intervention_point="NOT_A_POINT",
            ai_system_id=uuid4(),
        )


def test_policy_evaluation_context_defaults() -> None:
    system = uuid4()
    ctx = PolicyEvaluationContext(
        intervention_point=PolicyInterventionPoint.INPUT.value,
        ai_system_id=system,
    )
    assert ctx.parameters == {}
    assert ctx.content is None
    assert ctx.capabilities.can_report_after_fact is True


def test_applies_to_intervention_point_mapping() -> None:
    assert intervention_points_from_applies_to("INPUT") == ["INPUT"]
    assert intervention_points_from_applies_to("OUTPUT") == ["OUTPUT"]
    assert intervention_points_from_applies_to("BOTH") == ["INPUT", "OUTPUT"]
    assert applies_to_from_intervention_points(["INPUT"]) == "INPUT"
    assert applies_to_from_intervention_points(["OUTPUT"]) == "OUTPUT"
    assert applies_to_from_intervention_points(["INPUT", "OUTPUT"]) == "BOTH"
    assert applies_to_from_intervention_points(["PRE_TOOL"]) is None


def test_pr1_coverage_status_derivation() -> None:
    assert content_rule_coverage_status(enabled=False) == "DISABLED"
    assert content_rule_coverage_status(enabled=True) == "NOT_CONFIGURED"
