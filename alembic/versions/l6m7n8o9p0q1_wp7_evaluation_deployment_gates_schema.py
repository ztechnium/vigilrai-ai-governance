"""wp7_evaluation_deployment_gates_schema

Revision ID: l6m7n8o9p0q1
Revises: l6m7n8o9p0qa
Create Date: 2026-09-14 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "l6m7n8o9p0q1"
down_revision: Union[str, None] = "l6m7n8o9p0qa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "evaluation_suites",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ai_system_id", sa.UUID(), nullable=False),
        sa.Column("suite_key", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("published", sa.Boolean(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("runner_type", sa.String(), nullable=False),
        sa.Column("runner_config", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "ai_system_id",
            "suite_key",
            "version",
            name="uq_evaluation_suite_key_version",
        ),
    )
    op.create_index(
        "ix_evaluation_suites_ai_system_id", "evaluation_suites", ["ai_system_id"]
    )
    op.create_index(
        "ix_evaluation_suites_suite_key", "evaluation_suites", ["suite_key"]
    )
    op.create_index("ix_evaluation_suites_category", "evaluation_suites", ["category"])
    op.create_index(
        "ix_evaluation_suites_published", "evaluation_suites", ["published"]
    )

    op.create_table(
        "evaluation_cases",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("suite_id", sa.UUID(), nullable=False),
        sa.Column("case_key", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("input_fixture", sa.JSON(), nullable=False),
        sa.Column("expected_behavior", sa.JSON(), nullable=False),
        sa.Column("scoring_method", sa.String(), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("failure_severity", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["suite_id"], ["evaluation_suites.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("suite_id", "case_key", name="uq_evaluation_case_key"),
    )
    op.create_index("ix_evaluation_cases_suite_id", "evaluation_cases", ["suite_id"])
    op.create_index("ix_evaluation_cases_case_key", "evaluation_cases", ["case_key"])

    op.create_table(
        "evaluation_requirements",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ai_system_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("evaluation_suite_id", sa.UUID(), nullable=False),
        sa.Column("minimum_score", sa.Float(), nullable=False),
        sa.Column("maximum_failed_critical_cases", sa.Integer(), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("validity_days", sa.Integer(), nullable=True),
        sa.Column("environment_scope", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"]),
        sa.ForeignKeyConstraint(["evaluation_suite_id"], ["evaluation_suites.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_evaluation_requirements_ai_system_id",
        "evaluation_requirements",
        ["ai_system_id"],
    )
    op.create_index(
        "ix_evaluation_requirements_category", "evaluation_requirements", ["category"]
    )
    op.create_index(
        "ix_evaluation_requirements_evaluation_suite_id",
        "evaluation_requirements",
        ["evaluation_suite_id"],
    )
    op.create_index(
        "ix_evaluation_requirements_environment_scope",
        "evaluation_requirements",
        ["environment_scope"],
    )
    op.create_index(
        "ix_evaluation_requirements_enabled", "evaluation_requirements", ["enabled"]
    )

    op.create_table(
        "evaluation_plans",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ai_system_id", sa.UUID(), nullable=False),
        sa.Column("agent_id", sa.UUID(), nullable=False),
        sa.Column("agent_version_id", sa.UUID(), nullable=False),
        sa.Column("target_environment", sa.String(), nullable=False),
        sa.Column("requirement_snapshot", sa.JSON(), nullable=False),
        sa.Column("agent_config_digest", sa.String(), nullable=True),
        sa.Column("dependency_digest", sa.String(), nullable=True),
        sa.Column("plan_digest", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"]),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
        sa.ForeignKeyConstraint(["agent_version_id"], ["agent_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "agent_version_id",
            "target_environment",
            "plan_digest",
            name="uq_evaluation_plan_digest",
        ),
    )
    op.create_index(
        "ix_evaluation_plans_ai_system_id", "evaluation_plans", ["ai_system_id"]
    )
    op.create_index(
        "ix_evaluation_plans_agent_version_id", "evaluation_plans", ["agent_version_id"]
    )
    op.create_index(
        "ix_evaluation_plans_target_environment",
        "evaluation_plans",
        ["target_environment"],
    )
    op.create_index(
        "ix_evaluation_plans_plan_digest", "evaluation_plans", ["plan_digest"]
    )
    op.create_index("ix_evaluation_plans_status", "evaluation_plans", ["status"])

    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("plan_id", sa.UUID(), nullable=False),
        sa.Column("ai_system_id", sa.UUID(), nullable=False),
        sa.Column("agent_version_id", sa.UUID(), nullable=False),
        sa.Column("suite_id", sa.UUID(), nullable=False),
        sa.Column("suite_version", sa.Integer(), nullable=False),
        sa.Column("requirement_id", sa.UUID(), nullable=True),
        sa.Column("runner_type", sa.String(), nullable=False),
        sa.Column("runner_version", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("total_cases", sa.Integer(), nullable=False),
        sa.Column("passed_cases", sa.Integer(), nullable=False),
        sa.Column("failed_cases", sa.Integer(), nullable=False),
        sa.Column("critical_failures", sa.Integer(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["plan_id"], ["evaluation_plans.id"]),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"]),
        sa.ForeignKeyConstraint(["agent_version_id"], ["agent_versions.id"]),
        sa.ForeignKeyConstraint(["suite_id"], ["evaluation_suites.id"]),
        sa.ForeignKeyConstraint(["requirement_id"], ["evaluation_requirements.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "plan_id",
            "suite_id",
            "idempotency_key",
            name="uq_evaluation_run_idempotency",
        ),
    )
    op.create_index("ix_evaluation_runs_plan_id", "evaluation_runs", ["plan_id"])
    op.create_index(
        "ix_evaluation_runs_ai_system_id", "evaluation_runs", ["ai_system_id"]
    )
    op.create_index(
        "ix_evaluation_runs_agent_version_id", "evaluation_runs", ["agent_version_id"]
    )
    op.create_index("ix_evaluation_runs_suite_id", "evaluation_runs", ["suite_id"])
    op.create_index(
        "ix_evaluation_runs_requirement_id", "evaluation_runs", ["requirement_id"]
    )
    op.create_index("ix_evaluation_runs_status", "evaluation_runs", ["status"])

    op.create_table(
        "evaluation_case_results",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("case_id", sa.UUID(), nullable=True),
        sa.Column("case_key", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("severity", sa.String(), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("actual_output", sa.JSON(), nullable=True),
        sa.Column("evidence_refs", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["run_id"], ["evaluation_runs.id"]),
        sa.ForeignKeyConstraint(["case_id"], ["evaluation_cases.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "case_key", name="uq_evaluation_case_result"),
    )
    op.create_index(
        "ix_evaluation_case_results_run_id", "evaluation_case_results", ["run_id"]
    )
    op.create_index(
        "ix_evaluation_case_results_case_key", "evaluation_case_results", ["case_key"]
    )

    op.create_table(
        "deployment_gates",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ai_system_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("environment", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("conditions", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "ai_system_id",
            "name",
            "environment",
            name="uq_deployment_gate_name_env",
        ),
    )
    op.create_index(
        "ix_deployment_gates_ai_system_id", "deployment_gates", ["ai_system_id"]
    )
    op.create_index(
        "ix_deployment_gates_environment", "deployment_gates", ["environment"]
    )
    op.create_index("ix_deployment_gates_enabled", "deployment_gates", ["enabled"])

    op.create_table(
        "deployment_gate_evaluations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("gate_id", sa.UUID(), nullable=True),
        sa.Column("ai_system_id", sa.UUID(), nullable=False),
        sa.Column("agent_version_id", sa.UUID(), nullable=False),
        sa.Column("evaluation_plan_id", sa.UUID(), nullable=True),
        sa.Column("environment", sa.String(), nullable=False),
        sa.Column("decision", sa.String(), nullable=False),
        sa.Column("condition_results", sa.JSON(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("evidence_refs", sa.JSON(), nullable=True),
        sa.Column("evaluated_by", sa.String(), nullable=False),
        sa.Column(
            "evaluated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["gate_id"], ["deployment_gates.id"]),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"]),
        sa.ForeignKeyConstraint(["agent_version_id"], ["agent_versions.id"]),
        sa.ForeignKeyConstraint(["evaluation_plan_id"], ["evaluation_plans.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_deployment_gate_evaluations_gate_id",
        "deployment_gate_evaluations",
        ["gate_id"],
    )
    op.create_index(
        "ix_deployment_gate_evaluations_ai_system_id",
        "deployment_gate_evaluations",
        ["ai_system_id"],
    )
    op.create_index(
        "ix_deployment_gate_evaluations_agent_version_id",
        "deployment_gate_evaluations",
        ["agent_version_id"],
    )
    op.create_index(
        "ix_deployment_gate_evaluations_environment",
        "deployment_gate_evaluations",
        ["environment"],
    )
    op.create_index(
        "ix_deployment_gate_evaluations_decision",
        "deployment_gate_evaluations",
        ["decision"],
    )

    op.create_table(
        "assurance_records",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ai_system_id", sa.UUID(), nullable=False),
        sa.Column("agent_version_id", sa.UUID(), nullable=False),
        sa.Column("environment", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("gate_evaluation_id", sa.UUID(), nullable=True),
        sa.Column("evaluation_plan_id", sa.UUID(), nullable=True),
        sa.Column("config_digest", sa.String(), nullable=True),
        sa.Column("evidence_refs", sa.JSON(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_by_id", sa.UUID(), nullable=True),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"]),
        sa.ForeignKeyConstraint(["agent_version_id"], ["agent_versions.id"]),
        sa.ForeignKeyConstraint(
            ["gate_evaluation_id"], ["deployment_gate_evaluations.id"]
        ),
        sa.ForeignKeyConstraint(["evaluation_plan_id"], ["evaluation_plans.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_assurance_records_ai_system_id", "assurance_records", ["ai_system_id"]
    )
    op.create_index(
        "ix_assurance_records_agent_version_id",
        "assurance_records",
        ["agent_version_id"],
    )
    op.create_index(
        "ix_assurance_records_environment", "assurance_records", ["environment"]
    )
    op.create_index("ix_assurance_records_status", "assurance_records", ["status"])
    op.create_index(
        "ix_assurance_records_valid_until", "assurance_records", ["valid_until"]
    )

    op.create_table(
        "evaluation_waivers",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ai_system_id", sa.UUID(), nullable=False),
        sa.Column("agent_version_id", sa.UUID(), nullable=False),
        sa.Column("gate_evaluation_id", sa.UUID(), nullable=True),
        sa.Column("environment", sa.String(), nullable=False),
        sa.Column("failed_condition", sa.JSON(), nullable=False),
        sa.Column("justification", sa.Text(), nullable=False),
        sa.Column("compensating_controls", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("requester", sa.String(), nullable=False),
        sa.Column("approver", sa.String(), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"]),
        sa.ForeignKeyConstraint(["agent_version_id"], ["agent_versions.id"]),
        sa.ForeignKeyConstraint(
            ["gate_evaluation_id"], ["deployment_gate_evaluations.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_evaluation_waivers_ai_system_id", "evaluation_waivers", ["ai_system_id"]
    )
    op.create_index(
        "ix_evaluation_waivers_agent_version_id",
        "evaluation_waivers",
        ["agent_version_id"],
    )
    op.create_index("ix_evaluation_waivers_status", "evaluation_waivers", ["status"])

    op.create_table(
        "reassessment_triggers",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ai_system_id", sa.UUID(), nullable=False),
        sa.Column("agent_version_id", sa.UUID(), nullable=False),
        sa.Column("trigger_type", sa.String(), nullable=False),
        sa.Column("change_category", sa.String(), nullable=True),
        sa.Column("impacted_categories", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("source_ref", sa.String(), nullable=True),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"]),
        sa.ForeignKeyConstraint(["agent_version_id"], ["agent_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_reassessment_triggers_ai_system_id",
        "reassessment_triggers",
        ["ai_system_id"],
    )
    op.create_index(
        "ix_reassessment_triggers_agent_version_id",
        "reassessment_triggers",
        ["agent_version_id"],
    )
    op.create_index(
        "ix_reassessment_triggers_trigger_type",
        "reassessment_triggers",
        ["trigger_type"],
    )
    op.create_index(
        "ix_reassessment_triggers_status", "reassessment_triggers", ["status"]
    )


def downgrade() -> None:
    op.drop_table("reassessment_triggers")
    op.drop_table("evaluation_waivers")
    op.drop_table("assurance_records")
    op.drop_table("deployment_gate_evaluations")
    op.drop_table("deployment_gates")
    op.drop_table("evaluation_case_results")
    op.drop_table("evaluation_runs")
    op.drop_table("evaluation_plans")
    op.drop_table("evaluation_requirements")
    op.drop_table("evaluation_cases")
    op.drop_table("evaluation_suites")
