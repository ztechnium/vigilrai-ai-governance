"""finops runtime metering spans and attribution columns

Revision ID: b7c8d9e0f1a2
Revises: z1a2b3c4d5e6
Create Date: 2026-09-25 00:30:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, tuple[str, str], None] = ("z1a2b3c4d5e6", "f8a9b0c1d2e3")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "finops_pricing_catalog",
        sa.Column("cached_input_token_price", sa.Float(), nullable=True),
    )
    op.add_column(
        "finops_pricing_catalog",
        sa.Column("reasoning_token_price", sa.Float(), nullable=True),
    )
    op.add_column(
        "finops_pricing_catalog",
        sa.Column("minimum_request_cost", sa.Float(), nullable=True),
    )
    op.add_column(
        "finops_pricing_catalog",
        sa.Column("pricing_unit", sa.Integer(), nullable=False, server_default="1000"),
    )

    op.add_column(
        "finops_usage_reservations",
        sa.Column("delegation_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "finops_usage_reservations",
        sa.Column(
            "runtime_conversation_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
    )
    op.add_column(
        "finops_usage_reservations",
        sa.Column("trajectory_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    for name in (
        "ai_system_id",
        "agent_id",
        "agent_version_id",
        "runtime_identity_id",
        "delegation_id",
        "runtime_conversation_id",
        "trajectory_id",
        "metering_span_id",
    ):
        op.add_column(
            "finops_usage_settlements",
            sa.Column(name, postgresql.UUID(as_uuid=True), nullable=True),
        )
    op.add_column(
        "finops_usage_settlements",
        sa.Column("cost_state", sa.String(), nullable=True),
    )

    op.execute(
        """
        UPDATE finops_usage_settlements AS s
        SET ai_system_id = r.ai_system_id,
            agent_id = r.agent_id,
            agent_version_id = r.agent_version_id,
            runtime_identity_id = r.runtime_identity_id,
            delegation_id = r.delegation_id,
            runtime_conversation_id = r.runtime_conversation_id,
            trajectory_id = r.trajectory_id
        FROM finops_usage_reservations AS r
        WHERE s.reservation_id = r.id
        """
    )
    op.execute(
        """
        UPDATE finops_usage_reservations AS r
        SET trajectory_id = t.id,
            runtime_conversation_id = COALESCE(r.runtime_conversation_id, t.runtime_conversation_id),
            delegation_id = COALESCE(r.delegation_id, t.delegation_id)
        FROM runtime_trajectories AS t
        WHERE r.trajectory_id IS NULL
          AND r.correlation_id IS NOT NULL
          AND r.correlation_id = t.correlation_id
          AND (
            SELECT COUNT(*) FROM runtime_trajectories AS t2
            WHERE t2.correlation_id = r.correlation_id
          ) = 1
        """
    )
    op.execute(
        """
        UPDATE finops_usage_settlements AS s
        SET trajectory_id = t.id,
            runtime_conversation_id = COALESCE(s.runtime_conversation_id, t.runtime_conversation_id),
            delegation_id = COALESCE(s.delegation_id, t.delegation_id),
            ai_system_id = COALESCE(s.ai_system_id, t.ai_system_id),
            agent_id = COALESCE(s.agent_id, t.agent_id),
            agent_version_id = COALESCE(s.agent_version_id, t.agent_version_id),
            runtime_identity_id = COALESCE(s.runtime_identity_id, t.runtime_identity_id)
        FROM runtime_trajectories AS t
        WHERE s.trajectory_id IS NULL
          AND s.correlation_id IS NOT NULL
          AND s.correlation_id = t.correlation_id
          AND (
            SELECT COUNT(*) FROM runtime_trajectories AS t2
            WHERE t2.correlation_id = s.correlation_id
          ) = 1
        """
    )
    op.execute(
        """
        UPDATE finops_usage_settlements
        SET cost_state = CASE
            WHEN metering_source IN ('ESTIMATED', 'AGENT_SUPPLIED') THEN 'ESTIMATED'
            WHEN COALESCE(actual_cost, 0) = 0
                 AND input_tokens IS NULL
                 AND output_tokens IS NULL THEN 'UNAVAILABLE'
            ELSE 'ACTUAL'
        END
        WHERE cost_state IS NULL
        """
    )

    op.create_index(
        "ix_finops_usage_reservations_delegation_id",
        "finops_usage_reservations",
        ["delegation_id"],
    )
    op.create_index(
        "ix_finops_usage_reservations_trajectory_id",
        "finops_usage_reservations",
        ["trajectory_id"],
    )
    op.create_index(
        "ix_finops_usage_settlements_trajectory_id",
        "finops_usage_settlements",
        ["trajectory_id"],
    )
    op.create_index(
        "ix_finops_usage_settlements_cost_state",
        "finops_usage_settlements",
        ["cost_state"],
    )
    op.create_index(
        "uq_finops_settlement_metering_span",
        "finops_usage_settlements",
        ["metering_span_id"],
        unique=True,
        postgresql_where=sa.text("metering_span_id IS NOT NULL"),
    )

    op.create_table(
        "finops_metering_spans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ai_system_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("agent_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("runtime_identity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("delegation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "runtime_conversation_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column("trajectory_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "enforcement_receipt_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column("external_span_id", sa.String(), nullable=True),
        sa.Column("parent_span_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("correlation_id", sa.String(), nullable=True),
        sa.Column(
            "span_type", sa.String(), nullable=False, server_default="MODEL_CALL"
        ),
        sa.Column("operation", sa.String(), nullable=True),
        sa.Column("provider", sa.String(), nullable=True),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("environment", sa.String(), nullable=True),
        sa.Column("integration_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("cached_input_tokens", sa.Integer(), nullable=True),
        sa.Column("reasoning_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_cost", sa.Float(), nullable=True),
        sa.Column("actual_cost", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(), nullable=False, server_default="USD"),
        sa.Column(
            "cost_state", sa.String(), nullable=False, server_default="UNAVAILABLE"
        ),
        sa.Column("pricing_entry_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "metering_source", sa.String(), nullable=False, server_default="UNKNOWN"
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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
        "ix_finops_span_started",
        "finops_metering_spans",
        ["started_at"],
    )
    op.create_index(
        "ix_finops_span_system_started",
        "finops_metering_spans",
        ["ai_system_id", "started_at"],
    )
    op.create_index(
        "ix_finops_span_agent_started",
        "finops_metering_spans",
        ["agent_id", "started_at"],
    )
    op.create_index(
        "ix_finops_span_trajectory_started",
        "finops_metering_spans",
        ["trajectory_id", "started_at"],
    )
    op.create_index(
        "ix_finops_span_provider_model_started",
        "finops_metering_spans",
        ["provider", "model", "started_at"],
    )
    op.create_index(
        "ix_finops_metering_spans_correlation_id",
        "finops_metering_spans",
        ["correlation_id"],
    )
    op.create_index(
        "ix_finops_metering_spans_enforcement_receipt_id",
        "finops_metering_spans",
        ["enforcement_receipt_id"],
    )
    op.create_index(
        "uq_finops_metering_external_span",
        "finops_metering_spans",
        ["external_span_id"],
        unique=True,
        postgresql_where=sa.text("external_span_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_table("finops_metering_spans")
    op.drop_index(
        "uq_finops_settlement_metering_span", table_name="finops_usage_settlements"
    )
    op.drop_index(
        "ix_finops_usage_settlements_cost_state", table_name="finops_usage_settlements"
    )
    op.drop_index(
        "ix_finops_usage_settlements_trajectory_id",
        table_name="finops_usage_settlements",
    )
    op.drop_index(
        "ix_finops_usage_reservations_trajectory_id",
        table_name="finops_usage_reservations",
    )
    op.drop_index(
        "ix_finops_usage_reservations_delegation_id",
        table_name="finops_usage_reservations",
    )
    for name in (
        "cost_state",
        "metering_span_id",
        "trajectory_id",
        "runtime_conversation_id",
        "delegation_id",
        "runtime_identity_id",
        "agent_version_id",
        "agent_id",
        "ai_system_id",
    ):
        op.drop_column("finops_usage_settlements", name)
    for name in ("trajectory_id", "runtime_conversation_id", "delegation_id"):
        op.drop_column("finops_usage_reservations", name)
    for name in (
        "pricing_unit",
        "minimum_request_cost",
        "reasoning_token_price",
        "cached_input_token_price",
    ):
        op.drop_column("finops_pricing_catalog", name)
