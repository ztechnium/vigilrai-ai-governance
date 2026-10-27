"""wp4_runtime_enforcement_schema

Revision ID: f9a6b3c45d72
Revises: e8f5a2b34c61
Create Date: 2026-09-02 20:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f9a6b3c45d72"
down_revision: Union[str, None] = "e8f5a2b34c61"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "runtime_enforcement_receipts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("runtime_identity_id", sa.UUID(), nullable=False),
        sa.Column("ai_system_id", sa.UUID(), nullable=False),
        sa.Column("agent_id", sa.UUID(), nullable=False),
        sa.Column("agent_version_id", sa.UUID(), nullable=False),
        sa.Column("delegation_id", sa.UUID(), nullable=True),
        sa.Column("enforcement_mode", sa.String(), nullable=False),
        sa.Column("integration_type", sa.String(), nullable=False),
        sa.Column("integration_id", sa.UUID(), nullable=True),
        sa.Column("tool_id", sa.UUID(), nullable=True),
        sa.Column("action_digest", sa.String(), nullable=False),
        sa.Column("policy_effect", sa.String(), nullable=True),
        sa.Column("matched_rule_ids", sa.JSON(), nullable=True),
        sa.Column("approval_request_id", sa.UUID(), nullable=True),
        sa.Column("approval_consumed", sa.Boolean(), nullable=False),
        sa.Column("enforcement_decision", sa.String(), nullable=False),
        sa.Column("reason_code", sa.String(), nullable=True),
        sa.Column("human_explanation", sa.Text(), nullable=True),
        sa.Column("execution_attempted", sa.Boolean(), nullable=False),
        sa.Column("execution_status", sa.String(), nullable=False),
        sa.Column("downstream_reference", sa.String(), nullable=True),
        sa.Column("policy_decision", sa.JSON(), nullable=True),
        sa.Column("action_summary", sa.JSON(), nullable=True),
        sa.Column("monitor", sa.Boolean(), nullable=False),
        sa.Column("monitoring_instruction", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.String(), nullable=True),
        sa.Column("trace_id", sa.String(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
        sa.ForeignKeyConstraint(["agent_version_id"], ["agent_versions.id"]),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"]),
        sa.ForeignKeyConstraint(["delegation_id"], ["delegation_grants.id"]),
        sa.ForeignKeyConstraint(
            ["runtime_identity_id"], ["agent_runtime_identities.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_runtime_enforcement_receipts_action_digest"),
        "runtime_enforcement_receipts",
        ["action_digest"],
        unique=False,
    )
    op.create_index(
        op.f("ix_runtime_enforcement_receipts_agent_id"),
        "runtime_enforcement_receipts",
        ["agent_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_runtime_enforcement_receipts_ai_system_id"),
        "runtime_enforcement_receipts",
        ["ai_system_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_runtime_enforcement_receipts_correlation_id"),
        "runtime_enforcement_receipts",
        ["correlation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_runtime_enforcement_receipts_runtime_identity_id"),
        "runtime_enforcement_receipts",
        ["runtime_identity_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_runtime_enforcement_receipts_tool_id"),
        "runtime_enforcement_receipts",
        ["tool_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_runtime_enforcement_receipts_trace_id"),
        "runtime_enforcement_receipts",
        ["trace_id"],
        unique=False,
    )

    op.create_table(
        "runtime_idempotency_records",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("runtime_identity_id", sa.UUID(), nullable=False),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("action_digest", sa.String(), nullable=False),
        sa.Column("receipt_id", sa.UUID(), nullable=False),
        sa.Column("execution_status", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["receipt_id"], ["runtime_enforcement_receipts.id"]),
        sa.ForeignKeyConstraint(
            ["runtime_identity_id"], ["agent_runtime_identities.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "runtime_identity_id",
            "idempotency_key",
            name="uq_runtime_idempotency_key",
        ),
    )
    op.create_index(
        op.f("ix_runtime_idempotency_records_runtime_identity_id"),
        "runtime_idempotency_records",
        ["runtime_identity_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_runtime_idempotency_records_runtime_identity_id"),
        table_name="runtime_idempotency_records",
    )
    op.drop_table("runtime_idempotency_records")
    op.drop_index(
        op.f("ix_runtime_enforcement_receipts_trace_id"),
        table_name="runtime_enforcement_receipts",
    )
    op.drop_index(
        op.f("ix_runtime_enforcement_receipts_tool_id"),
        table_name="runtime_enforcement_receipts",
    )
    op.drop_index(
        op.f("ix_runtime_enforcement_receipts_runtime_identity_id"),
        table_name="runtime_enforcement_receipts",
    )
    op.drop_index(
        op.f("ix_runtime_enforcement_receipts_correlation_id"),
        table_name="runtime_enforcement_receipts",
    )
    op.drop_index(
        op.f("ix_runtime_enforcement_receipts_ai_system_id"),
        table_name="runtime_enforcement_receipts",
    )
    op.drop_index(
        op.f("ix_runtime_enforcement_receipts_agent_id"),
        table_name="runtime_enforcement_receipts",
    )
    op.drop_index(
        op.f("ix_runtime_enforcement_receipts_action_digest"),
        table_name="runtime_enforcement_receipts",
    )
    op.drop_table("runtime_enforcement_receipts")
