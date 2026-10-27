"""reporting_snapshots_and_schedules

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
Create Date: 2026-09-24 14:30:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "f8a9b0c1d2e3"
down_revision = "e7f8a9b0c1d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create report_snapshots table
    op.create_table(
        "report_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("report_type", sa.String(), nullable=False),
        sa.Column("scope_type", sa.String(), nullable=False),
        sa.Column("scope_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "filters_json", postgresql.JSON(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("generated_by", sa.String(), nullable=False),
        sa.Column("schema_version", sa.String(), nullable=False),
        sa.Column(
            "data_snapshot", postgresql.JSON(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "source_manifest", postgresql.JSON(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("content_digest", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # Create indexes for report_snapshots
    op.create_index(
        "ix_report_snapshots_report_type", "report_snapshots", ["report_type"]
    )
    op.create_index("ix_report_snapshots_scope_id", "report_snapshots", ["scope_id"])
    op.create_index(
        "ix_report_snapshots_period_start", "report_snapshots", ["period_start"]
    )
    op.create_index(
        "ix_report_snapshots_period_end", "report_snapshots", ["period_end"]
    )
    op.create_index(
        "ix_report_snapshots_generated_at", "report_snapshots", ["generated_at"]
    )

    # Create report_schedules table
    op.create_table(
        "report_schedules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("report_type", sa.String(), nullable=False),
        sa.Column("scope_type", sa.String(), nullable=False),
        sa.Column("scope_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("cadence", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "filters_json", postgresql.JSON(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "delivery_config", postgresql.JSON(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["last_snapshot_id"], ["report_snapshots.id"], ondelete="SET NULL"
        ),
    )

    # Create indexes for report_schedules
    op.create_index("ix_report_schedules_enabled", "report_schedules", ["enabled"])
    op.create_index(
        "ix_report_schedules_next_run_at", "report_schedules", ["next_run_at"]
    )


def downgrade() -> None:
    op.drop_table("report_schedules")
    op.drop_table("report_snapshots")
