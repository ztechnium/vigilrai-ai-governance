"""audit_p1_evaluation_accepted_runner_types

Revision ID: r3s4t5u6v7w8
Revises: q2r3s4t5u6v7
Create Date: 2026-09-15 13:50:00.000000

Recovers DBs that advanced past WP7 without applying its schema (common when
the WP6/WP7 revision IDs were corrected after a volume was already stamped).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "r3s4t5u6v7w8"
down_revision: Union[str, None] = "q2r3s4t5u6v7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _column_names(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _ensure_wp7_schema() -> None:
    """Apply WP7 DDL when tables are missing but alembic history already passed it."""
    tables = _table_names()
    if "evaluation_suites" in tables and "evaluation_requirements" in tables:
        return

    wp7_path = Path(__file__).with_name(
        "l6m7n8o9p0q1_wp7_evaluation_deployment_gates_schema.py"
    )
    spec = importlib.util.spec_from_file_location("wp7_schema_repair", wp7_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load WP7 migration for repair: {wp7_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # WP7 upgrade assumes none of its tables exist. Only run when suites missing.
    if "evaluation_suites" not in _table_names():
        module.upgrade()
        return

    # Partial WP7 (suites exist, requirements missing) — create requirements only.
    if "evaluation_requirements" not in _table_names():
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
            "ix_evaluation_requirements_category",
            "evaluation_requirements",
            ["category"],
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
            "ix_evaluation_requirements_enabled",
            "evaluation_requirements",
            ["enabled"],
        )


def upgrade() -> None:
    _ensure_wp7_schema()

    if "evaluation_requirements" not in _table_names():
        raise RuntimeError(
            "evaluation_requirements still missing after WP7 repair — "
            "reset the postgres volume or apply l6m7n8o9p0q1 manually"
        )

    if "accepted_runner_types" not in _column_names("evaluation_requirements"):
        op.add_column(
            "evaluation_requirements",
            sa.Column("accepted_runner_types", sa.JSON(), nullable=True),
        )


def downgrade() -> None:
    if "evaluation_requirements" in _table_names() and (
        "accepted_runner_types" in _column_names("evaluation_requirements")
    ):
        op.drop_column("evaluation_requirements", "accepted_runner_types")
