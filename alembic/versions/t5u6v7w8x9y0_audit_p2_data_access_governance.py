"""audit_p2_data_access_governance

Revision ID: t5u6v7w8x9y0
Revises: s4t5u6v7w8x9
Create Date: 2026-09-15 15:40:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "t5u6v7w8x9y0"
down_revision: Union[str, None] = "s4t5u6v7w8x9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "data_access_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "ai_system_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ai_systems.id"),
            nullable=True,
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("enabled", sa.String(), nullable=False, server_default="true"),
        sa.Column("data_source_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resource", sa.String(), nullable=True),
        sa.Column("field_name", sa.String(), nullable=True),
        sa.Column("classification", sa.String(), nullable=True),
        sa.Column("purpose", sa.String(), nullable=True),
        sa.Column("access_mode", sa.String(), nullable=True),
        sa.Column("effect", sa.String(), nullable=False, server_default="DENY"),
        sa.Column("mask_style", sa.String(), nullable=True),
        sa.Column("row_predicate", sa.JSON(), nullable=True),
        sa.Column("priority", sa.String(), nullable=False, server_default="100"),
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
    )
    op.create_index(
        "ix_data_access_policies_ai_system_id", "data_access_policies", ["ai_system_id"]
    )
    op.create_index(
        "ix_data_access_policies_field_name", "data_access_policies", ["field_name"]
    )

    op.create_table(
        "data_access_receipts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ai_system_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("agent_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("runtime_identity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("data_source_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("tool_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("principal", sa.String(), nullable=True),
        sa.Column("resource", sa.String(), nullable=False),
        sa.Column("purpose", sa.String(), nullable=True),
        sa.Column("access_mode", sa.String(), nullable=False),
        sa.Column("requested_fields", sa.JSON(), nullable=False),
        sa.Column("allowed_fields", sa.JSON(), nullable=False),
        sa.Column("denied_fields", sa.JSON(), nullable=False),
        sa.Column("masked_fields", sa.JSON(), nullable=False),
        sa.Column("decision", sa.String(), nullable=False),
        sa.Column("reason_code", sa.String(), nullable=False),
        sa.Column("human_explanation", sa.Text(), nullable=True),
        sa.Column("transforms", sa.JSON(), nullable=True),
        sa.Column("row_filter", sa.JSON(), nullable=True),
        sa.Column("policy_rule_ids", sa.JSON(), nullable=True),
        sa.Column("correlation_id", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_data_access_receipts_runtime_identity_id",
        "data_access_receipts",
        ["runtime_identity_id"],
    )
    op.create_index(
        "ix_data_access_receipts_created_at", "data_access_receipts", ["created_at"]
    )


def downgrade() -> None:
    op.drop_table("data_access_receipts")
    op.drop_table("data_access_policies")
