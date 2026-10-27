"""audit_p2_multi_stage_approval_plans

Revision ID: s4t5u6v7w8x9
Revises: r3s4t5u6v7w8
Create Date: 2026-09-15 15:10:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "s4t5u6v7w8x9"
down_revision: Union[str, None] = "r3s4t5u6v7w8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "approval_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "approval_request_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("approval_requests.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("action_digest", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="IN_PROGRESS"),
        sa.Column(
            "current_stage_index", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_approval_plans_action_digest", "approval_plans", ["action_digest"]
    )
    op.create_index("ix_approval_plans_status", "approval_plans", ["status"])

    op.create_table(
        "approval_stages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("approval_plans.id"),
            nullable=False,
        ),
        sa.Column("stage_index", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("mode", sa.String(), nullable=False, server_default="QUORUM"),
        sa.Column("required_roles", sa.JSON(), nullable=False),
        sa.Column("quorum_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(), nullable=False, server_default="PENDING"),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("plan_id", "stage_index", name="uq_approval_stage_index"),
    )
    op.create_index("ix_approval_stages_plan_id", "approval_stages", ["plan_id"])
    op.create_index("ix_approval_stages_status", "approval_stages", ["status"])

    op.create_table(
        "approval_stage_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "stage_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("approval_stages.id"),
            nullable=False,
        ),
        sa.Column("decision", sa.String(), nullable=False),
        sa.Column("decided_by", sa.String(), nullable=False),
        sa.Column("approver_role", sa.String(), nullable=False),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("authentication_assurance", sa.String(), nullable=True),
        sa.Column("action_digest", sa.String(), nullable=False),
        sa.Column(
            "decided_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("correlation_id", sa.String(), nullable=True),
        sa.UniqueConstraint(
            "stage_id", "decided_by", name="uq_approval_stage_approver"
        ),
    )
    op.create_index(
        "ix_approval_stage_decisions_stage_id", "approval_stage_decisions", ["stage_id"]
    )


def downgrade() -> None:
    op.drop_table("approval_stage_decisions")
    op.drop_table("approval_stages")
    op.drop_table("approval_plans")
