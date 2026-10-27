"""hierarchical runtime budgets and reservations

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-09-26 14:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f4a5b6c7d8e9"
down_revision: Union[str, None] = "e3f4a5b6c7d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "runtime_budgets",
        "ai_system_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )

    op.add_column(
        "runtime_budget_windows",
        sa.Column("reserved_value", sa.Float(), nullable=False, server_default="0"),
    )
    op.alter_column(
        "runtime_budget_windows",
        "ai_system_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )

    for col in (
        "agent_id",
        "agent_version_id",
        "delegation_id",
        "model_resource_id",
        "tool_id",
        "enforcement_receipt_id",
        "metering_span_id",
        "reservation_id",
    ):
        op.add_column(
            "runtime_budget_checks",
            sa.Column(col, postgresql.UUID(as_uuid=True), nullable=True),
        )
        op.create_index(
            f"ix_runtime_budget_checks_{col}", "runtime_budget_checks", [col]
        )
    op.add_column(
        "runtime_budget_checks",
        sa.Column("reconciliation_status", sa.String(), nullable=True),
    )
    op.alter_column(
        "runtime_budget_checks",
        "ai_system_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )

    op.create_table(
        "runtime_budget_reservations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "budget_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("runtime_budgets.id"),
            nullable=False,
        ),
        sa.Column(
            "budget_window_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("runtime_budget_windows.id"),
            nullable=True,
        ),
        sa.Column("runtime_identity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("delegation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("trajectory_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "enforcement_receipt_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column(
            "finops_usage_reservation_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("metric", sa.String(), nullable=False),
        sa.Column("reserved_value", sa.Float(), nullable=False, server_default="0"),
        sa.Column("settled_value", sa.Float(), nullable=True),
        sa.Column("delta_value", sa.Float(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="RESERVED"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "budget_id", "idempotency_key", name="uq_budget_reservation_idempotency"
        ),
    )
    op.create_index(
        "ix_runtime_budget_reservations_budget_id",
        "runtime_budget_reservations",
        ["budget_id"],
    )
    op.create_index(
        "ix_runtime_budget_reservations_status",
        "runtime_budget_reservations",
        ["status"],
    )
    op.create_index(
        "ix_runtime_budget_reservations_idempotency_key",
        "runtime_budget_reservations",
        ["idempotency_key"],
    )


def downgrade() -> None:
    op.drop_table("runtime_budget_reservations")
    op.drop_column("runtime_budget_checks", "reconciliation_status")
    for col in (
        "reservation_id",
        "metering_span_id",
        "enforcement_receipt_id",
        "tool_id",
        "model_resource_id",
        "delegation_id",
        "agent_version_id",
        "agent_id",
    ):
        op.drop_index(
            f"ix_runtime_budget_checks_{col}", table_name="runtime_budget_checks"
        )
        op.drop_column("runtime_budget_checks", col)
    op.alter_column(
        "runtime_budget_checks",
        "ai_system_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.drop_column("runtime_budget_windows", "reserved_value")
    op.alter_column(
        "runtime_budget_windows",
        "ai_system_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.alter_column(
        "runtime_budgets",
        "ai_system_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
