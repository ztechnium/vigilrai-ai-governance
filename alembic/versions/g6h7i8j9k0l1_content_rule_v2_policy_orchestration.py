"""content_rule_v2_policy_orchestration

Revision ID: g6h7i8j9k0l1
Revises: f4a5b6c7d8e9
Create Date: 2026-09-26 14:40:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "g6h7i8j9k0l1"
down_revision: Union[str, None] = "f4a5b6c7d8e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "content_rules",
        sa.Column(
            "evaluation_type",
            sa.String(),
            nullable=False,
            server_default="LLM_JUDGE",
        ),
    )
    op.add_column(
        "content_rules",
        sa.Column("evaluator_profile_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "content_rules",
        sa.Column("intervention_points", sa.JSON(), nullable=True),
    )
    op.add_column(
        "content_rules",
        sa.Column("content_targets", sa.JSON(), nullable=True),
    )
    op.add_column(
        "content_rules",
        sa.Column("minimum_confidence", sa.Float(), nullable=True),
    )
    op.add_column(
        "content_rules",
        sa.Column(
            "failure_mode",
            sa.String(),
            nullable=False,
            server_default="INHERIT",
        ),
    )
    op.add_column(
        "content_rules",
        sa.Column(
            "remediation_type",
            sa.String(),
            nullable=False,
            server_default="NONE",
        ),
    )
    op.add_column(
        "content_rules",
        sa.Column("remediation_config", sa.JSON(), nullable=True),
    )
    op.add_column(
        "content_rules",
        sa.Column(
            "inline_enforcement_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "content_rules",
        sa.Column("evaluation_timeout_ms", sa.Integer(), nullable=True),
    )
    op.create_index(
        op.f("ix_content_rules_evaluator_profile_id"),
        "content_rules",
        ["evaluator_profile_id"],
        unique=False,
    )

    # Backfill intervention_points from legacy applies_to.
    op.execute(
        """
        UPDATE content_rules
        SET intervention_points = CASE
            WHEN upper(coalesce(applies_to, 'BOTH')) = 'INPUT' THEN '["INPUT"]'::json
            WHEN upper(coalesce(applies_to, 'BOTH')) = 'OUTPUT' THEN '["OUTPUT"]'::json
            ELSE '["INPUT", "OUTPUT"]'::json
        END
        WHERE intervention_points IS NULL
        """
    )
    op.execute(
        """
        UPDATE content_rules
        SET content_targets = '{"mode": "FULL_CONTENT"}'::json
        WHERE content_targets IS NULL
        """
    )

    op.alter_column(
        "content_rules",
        "intervention_points",
        existing_type=sa.JSON(),
        nullable=False,
    )
    op.alter_column(
        "content_rules",
        "content_targets",
        existing_type=sa.JSON(),
        nullable=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_content_rules_evaluator_profile_id"), table_name="content_rules"
    )
    op.drop_column("content_rules", "evaluation_timeout_ms")
    op.drop_column("content_rules", "inline_enforcement_required")
    op.drop_column("content_rules", "remediation_config")
    op.drop_column("content_rules", "remediation_type")
    op.drop_column("content_rules", "failure_mode")
    op.drop_column("content_rules", "minimum_confidence")
    op.drop_column("content_rules", "content_targets")
    op.drop_column("content_rules", "intervention_points")
    op.drop_column("content_rules", "evaluator_profile_id")
    op.drop_column("content_rules", "evaluation_type")
