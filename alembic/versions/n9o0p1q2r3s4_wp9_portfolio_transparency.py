"""wp9_portfolio_transparency_executive_oversight

Revision ID: n9o0p1q2r3s4
Revises: m8n9o0p1q2r3
Create Date: 2026-09-15 01:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "n9o0p1q2r3s4"
down_revision: Union[str, None] = "m8n9o0p1q2r3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "portfolio_reports",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("scope_type", sa.String(), nullable=False),
        sa.Column("scope_id", sa.String(), nullable=True),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("generated_by", sa.String(), nullable=False),
        sa.Column("schema_version", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("data_snapshot", sa.JSON(), nullable=False),
        sa.Column("source_manifest", sa.JSON(), nullable=False),
        sa.Column("content_digest", sa.String(), nullable=False),
        sa.Column("report_html", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_portfolio_reports_scope_type", "portfolio_reports", ["scope_type"]
    )
    op.create_index("ix_portfolio_reports_scope_id", "portfolio_reports", ["scope_id"])
    op.create_index(
        "ix_portfolio_reports_generated_at", "portfolio_reports", ["generated_at"]
    )
    op.create_index(
        "ix_portfolio_reports_content_digest", "portfolio_reports", ["content_digest"]
    )

    op.create_table(
        "portfolio_report_schedules",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("cadence", sa.String(), nullable=False),
        sa.Column("scope_type", sa.String(), nullable=False),
        sa.Column("scope_id", sa.String(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_report_id", sa.UUID(), nullable=True),
        sa.Column("delivery", sa.JSON(), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "cadence",
            "scope_type",
            "scope_id",
            name="uq_portfolio_report_schedule_scope",
        ),
    )
    op.create_index(
        "ix_portfolio_report_schedules_cadence",
        "portfolio_report_schedules",
        ["cadence"],
    )

    op.create_table(
        "executive_governance_decisions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("scope_type", sa.String(), nullable=False),
        sa.Column("scope_id", sa.String(), nullable=False),
        sa.Column("decision", sa.String(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("actor_role", sa.String(), nullable=True),
        sa.Column("evidence_refs", sa.JSON(), nullable=True),
        sa.Column("recommended_domain_actions", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_executive_governance_decisions_scope_type",
        "executive_governance_decisions",
        ["scope_type"],
    )
    op.create_index(
        "ix_executive_governance_decisions_scope_id",
        "executive_governance_decisions",
        ["scope_id"],
    )
    op.create_index(
        "ix_executive_governance_decisions_decision",
        "executive_governance_decisions",
        ["decision"],
    )

    op.create_table(
        "portfolio_projection_state",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("projection_key", sa.String(), nullable=False),
        sa.Column("freshness", sa.String(), nullable=False),
        sa.Column("last_refreshed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("refresh_count", sa.Integer(), nullable=False),
        sa.Column("payload_digest", sa.String(), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "projection_key",
            name="uq_portfolio_projection_key",
        ),
    )
    op.create_index(
        "ix_portfolio_projection_state_projection_key",
        "portfolio_projection_state",
        ["projection_key"],
    )


def downgrade() -> None:
    op.drop_table("portfolio_projection_state")
    op.drop_table("executive_governance_decisions")
    op.drop_table("portfolio_report_schedules")
    op.drop_table("portfolio_reports")
