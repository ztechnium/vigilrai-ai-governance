"""Developer lab action and case-assessment tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

LAB = Path(__file__).resolve().parents[2] / "examples" / "developer_lab"
sys.path.insert(0, str(LAB))

from actions import ToolError, apply_action, load_state  # noqa: E402
from run_case import assess_content_case, assess_tool_case  # noqa: E402


def test_allowed_ticket_is_written(tmp_path: Path) -> None:
    result = apply_action(
        "create_support_ticket",
        {"priority": "normal", "summary": "Damaged order"},
        state_dir=tmp_path,
    )
    state = load_state(tmp_path)
    assert result["artifact_id"] == "SUP-1001"
    assert state["tickets"][0]["summary"] == "Damaged order"
    assert state["audit"][0]["tool_key"] == "create_support_ticket"


def test_shell_runs_a_real_process_only_for_the_fixed_command(tmp_path: Path) -> None:
    result = apply_action(
        "run_shell",
        {"command": "python -c print-governed"},
        state_dir=tmp_path,
    )
    assert load_state(tmp_path)["processes"][0]["stdout"] == "governed"
    assert result["process"]["stdout"] == "governed"
    with pytest.raises(ToolError):
        apply_action("run_shell", {"command": "rm -rf /"}, state_dir=tmp_path)


def test_read_file_stays_in_the_sandbox(tmp_path: Path) -> None:
    text = apply_action("read_file", {"path": "README.md"}, state_dir=tmp_path)
    assert "sandbox" in text["content"].lower()
    with pytest.raises(ToolError):
        apply_action(
            "read_file", {"path": "../knowledge/payroll.md"}, state_dir=tmp_path
        )


def test_retrieve_reads_the_collection_file(tmp_path: Path) -> None:
    hr = apply_action(
        "retrieve_documents",
        {"collection": "hr-policies"},
        state_dir=tmp_path,
    )
    assert "section 4.2" in hr["excerpt"]
    payroll = apply_action(
        "retrieve_documents", {"collection": "payroll"}, state_dir=tmp_path
    )
    assert "bank account" in payroll["excerpt"]


def test_case_assessment_requires_a_real_side_effect() -> None:
    ok, _ = assess_tool_case(
        expect="ALLOW",
        effect="ALLOW",
        execution_attempted=True,
        execution_status="SUCCEEDED",
        state_changed=True,
    )
    assert ok
    blocked, _ = assess_tool_case(
        expect="ALLOW",
        effect="ALLOW",
        execution_attempted=False,
        execution_status="NOT_ATTEMPTED",
        state_changed=False,
    )
    assert not blocked
    denied, _ = assess_tool_case(
        expect="DENY",
        effect="DENY",
        execution_attempted=False,
        execution_status="NOT_ATTEMPTED",
        state_changed=False,
    )
    assert denied
    leaked, _ = assess_tool_case(
        expect="REQUIRE_APPROVAL",
        effect="REQUIRE_APPROVAL",
        execution_attempted=False,
        execution_status="NOT_ATTEMPTED",
        state_changed=True,
    )
    assert not leaked


def test_content_assessment() -> None:
    ok, _ = assess_content_case(expect_violated=True, violated=True)
    assert ok
    clean, _ = assess_content_case(expect_violated=False, violated=True)
    assert not clean
