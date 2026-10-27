"""audit_p1_finops_pricing_reservation_settlement

Revision ID: v7w8x9y0z1a2
Revises: u6v7w8x9y0z1
Create Date: 2026-09-19 10:40:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "v7w8x9y0z1a2"
down_revision: Union[str, None] = "u6v7w8x9y0z1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "finops_pricing_catalog",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("input_token_price", sa.Float(), nullable=False),
        sa.Column("output_token_price", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(), nullable=False, server_default="USD"),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
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
        sa.UniqueConstraint(
            "provider",
            "model",
            "currency",
            "effective_from",
            name="uq_finops_pricing_version",
        ),
    )
    op.create_index(
        "ix_finops_pricing_catalog_provider", "finops_pricing_catalog", ["provider"]
    )
    op.create_index(
        "ix_finops_pricing_catalog_model", "finops_pricing_catalog", ["model"]
    )
    op.create_index(
        "ix_finops_pricing_catalog_effective_from",
        "finops_pricing_catalog",
        ["effective_from"],
    )

    op.create_table(
        "finops_usage_reservations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "ai_system_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ai_systems.id"),
            nullable=True,
        ),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("agent_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("runtime_identity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "enforcement_receipt_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column("correlation_id", sa.String(), nullable=True),
        sa.Column("provider", sa.String(), nullable=True),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("estimated_input_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_output_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_cost", sa.Float(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(), nullable=False, server_default="USD"),
        sa.Column("pricing_entry_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="RESERVED"),
        sa.Column("allocation", sa.JSON(), nullable=True),
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
        "ix_finops_usage_reservations_status",
        "finops_usage_reservations",
        ["status"],
    )
    op.create_index(
        "ix_finops_usage_reservations_correlation_id",
        "finops_usage_reservations",
        ["correlation_id"],
    )
    op.create_index(
        "ix_finops_usage_reservations_enforcement_receipt_id",
        "finops_usage_reservations",
        ["enforcement_receipt_id"],
    )

    op.create_table(
        "finops_usage_settlements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "reservation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("finops_usage_reservations.id"),
            nullable=True,
        ),
        sa.Column(
            "enforcement_receipt_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column("correlation_id", sa.String(), nullable=True),
        sa.Column("provider", sa.String(), nullable=True),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("actual_cost", sa.Float(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(), nullable=False, server_default="USD"),
        sa.Column("metering_source", sa.String(), nullable=False),
        sa.Column("pricing_entry_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reserved_cost", sa.Float(), nullable=True),
        sa.Column("delta_cost", sa.Float(), nullable=True),
        sa.Column("allocation", sa.JSON(), nullable=True),
        sa.Column("raw_usage", sa.JSON(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_finops_usage_settlements_metering_source",
        "finops_usage_settlements",
        ["metering_source"],
    )
    op.create_index(
        "ix_finops_usage_settlements_reservation_id",
        "finops_usage_settlements",
        ["reservation_id"],
    )


def downgrade() -> None:
    op.drop_table("finops_usage_settlements")
    op.drop_table("finops_usage_reservations")
    op.drop_table("finops_pricing_catalog")
