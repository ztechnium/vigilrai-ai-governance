"""wp6_budgets_anomaly_oversight

Revision ID: l6m7n8o9p0qa
Revises: k5l6m7n8o9p0
Create Date: 2026-09-14 13:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "l6m7n8o9p0qa"
down_revision: Union[str, None] = "k5l6m7n8o9p0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "runtime_budgets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ai_system_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("scope_type", sa.String(), nullable=False),
        sa.Column("scope_id", sa.String(), nullable=True),
        sa.Column("metric", sa.String(), nullable=False),
        sa.Column("tool_name", sa.String(), nullable=True),
        sa.Column("tool_id", sa.UUID(), nullable=True),
        sa.Column("resource_filter", sa.JSON(), nullable=True),
        sa.Column("limit_value", sa.Float(), nullable=False),
        sa.Column("window_seconds", sa.Integer(), nullable=False),
        sa.Column("warning_threshold", sa.Float(), nullable=False),
        sa.Column("effect_on_exceed", sa.String(), nullable=False),
        sa.Column("amount_parameter_path", sa.String(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
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
        sa.ForeignKeyConstraint(["tool_id"], ["tool_resources.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_runtime_budgets_ai_system_id", "runtime_budgets", ["ai_system_id"]
    )
    op.create_index("ix_runtime_budgets_scope_type", "runtime_budgets", ["scope_type"])
    op.create_index("ix_runtime_budgets_scope_id", "runtime_budgets", ["scope_id"])
    op.create_index("ix_runtime_budgets_metric", "runtime_budgets", ["metric"])
    op.create_index("ix_runtime_budgets_tool_name", "runtime_budgets", ["tool_name"])
    op.create_index("ix_runtime_budgets_enabled", "runtime_budgets", ["enabled"])

    op.create_table(
        "runtime_budget_windows",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("budget_id", sa.UUID(), nullable=False),
        sa.Column("ai_system_id", sa.UUID(), nullable=False),
        sa.Column("scope_type", sa.String(), nullable=False),
        sa.Column("scope_id", sa.String(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("usage_value", sa.Float(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column(
            "updated_at",
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
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"]),
        sa.ForeignKeyConstraint(["budget_id"], ["runtime_budgets.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "budget_id",
            "scope_id",
            "window_start",
            name="uq_budget_window_scope_start",
        ),
    )
    op.create_index(
        "ix_runtime_budget_windows_budget_id", "runtime_budget_windows", ["budget_id"]
    )
    op.create_index(
        "ix_runtime_budget_windows_ai_system_id",
        "runtime_budget_windows",
        ["ai_system_id"],
    )
    op.create_index(
        "ix_runtime_budget_windows_scope_id", "runtime_budget_windows", ["scope_id"]
    )
    op.create_index(
        "ix_runtime_budget_windows_window_start",
        "runtime_budget_windows",
        ["window_start"],
    )
    op.create_index(
        "ix_runtime_budget_windows_status", "runtime_budget_windows", ["status"]
    )

    op.create_table(
        "runtime_budget_checks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("budget_id", sa.UUID(), nullable=False),
        sa.Column("ai_system_id", sa.UUID(), nullable=False),
        sa.Column("runtime_identity_id", sa.UUID(), nullable=True),
        sa.Column("trajectory_id", sa.UUID(), nullable=True),
        sa.Column("metric", sa.String(), nullable=False),
        sa.Column("window_seconds", sa.Integer(), nullable=False),
        sa.Column("usage_before", sa.Float(), nullable=False),
        sa.Column("attempted_increment", sa.Float(), nullable=False),
        sa.Column("projected_usage", sa.Float(), nullable=False),
        sa.Column("limit_value", sa.Float(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("decision", sa.String(), nullable=False),
        sa.Column("effect", sa.String(), nullable=True),
        sa.Column("evidence_refs", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"]),
        sa.ForeignKeyConstraint(["budget_id"], ["runtime_budgets.id"]),
        sa.ForeignKeyConstraint(
            ["runtime_identity_id"], ["agent_runtime_identities.id"]
        ),
        sa.ForeignKeyConstraint(["trajectory_id"], ["runtime_trajectories.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_runtime_budget_checks_budget_id", "runtime_budget_checks", ["budget_id"]
    )
    op.create_index(
        "ix_runtime_budget_checks_ai_system_id",
        "runtime_budget_checks",
        ["ai_system_id"],
    )
    op.create_index(
        "ix_runtime_budget_checks_runtime_identity_id",
        "runtime_budget_checks",
        ["runtime_identity_id"],
    )
    op.create_index(
        "ix_runtime_budget_checks_trajectory_id",
        "runtime_budget_checks",
        ["trajectory_id"],
    )

    op.create_table(
        "emerging_risk_candidates",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ai_system_id", sa.UUID(), nullable=False),
        sa.Column("pattern_key", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("evidence_refs", sa.JSON(), nullable=True),
        sa.Column("signal_ids", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
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
    )
    op.create_index(
        "ix_emerging_risk_candidates_ai_system_id",
        "emerging_risk_candidates",
        ["ai_system_id"],
    )
    op.create_index(
        "ix_emerging_risk_candidates_pattern_key",
        "emerging_risk_candidates",
        ["pattern_key"],
    )
    op.create_index(
        "ix_emerging_risk_candidates_status", "emerging_risk_candidates", ["status"]
    )


def downgrade() -> None:
    op.drop_table("emerging_risk_candidates")
    op.drop_table("runtime_budget_checks")
    op.drop_table("runtime_budget_windows")
    op.drop_table("runtime_budgets")
