"""runtime_conversation_projection

Revision ID: c5d6e7f8a9b0
Revises: a4b5c6d7e8f9
Create Date: 2026-09-23 12:00:00.000000

Durable RuntimeConversation read projection + trajectory FK.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c5d6e7f8a9b0"
down_revision: Union[str, None] = "a4b5c6d7e8f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "runtime_conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("conversation_key", sa.String(), nullable=False),
        sa.Column("external_conversation_id", sa.String(), nullable=False),
        sa.Column(
            "client_integration_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("runtime_client_integrations.id"),
            nullable=True,
        ),
        sa.Column(
            "runtime_identity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_runtime_identities.id"),
            nullable=True,
        ),
        sa.Column(
            "ai_system_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ai_systems.id"),
            nullable=True,
        ),
        sa.Column(
            "primary_agent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agents.id"),
            nullable=True,
        ),
        sa.Column("principal_reference", sa.String(), nullable=True),
        sa.Column("channel", sa.String(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="ACTIVE"),
        sa.Column("trajectory_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("event_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("action_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("finding_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("highest_risk_level", sa.String(), nullable=True),
        sa.Column("highest_assurance_level", sa.String(), nullable=True),
        sa.Column("last_trajectory_id", postgresql.UUID(as_uuid=True), nullable=True),
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
            "conversation_key",
            name="uq_runtime_conversation_key",
        ),
    )
    op.create_index(
        "ix_runtime_conversations_last_activity_at",
        "runtime_conversations",
        ["last_activity_at"],
    )
    op.create_index(
        "ix_runtime_conversations_ai_system_id",
        "runtime_conversations",
        ["ai_system_id"],
    )
    op.create_index(
        "ix_runtime_conversations_runtime_identity_id",
        "runtime_conversations",
        ["runtime_identity_id"],
    )
    op.create_index(
        "ix_runtime_conversations_highest_risk_level",
        "runtime_conversations",
        ["highest_risk_level"],
    )
    op.create_index(
        "ix_runtime_conversations_external_id",
        "runtime_conversations",
        ["external_conversation_id"],
    )
    op.create_index(
        "ix_runtime_conversations_status",
        "runtime_conversations",
        ["status"],
    )

    op.add_column(
        "runtime_trajectories",
        sa.Column(
            "runtime_conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("runtime_conversations.id"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_runtime_trajectories_runtime_conversation_id",
        "runtime_trajectories",
        ["runtime_conversation_id"],
    )
    op.add_column(
        "runtime_trajectories",
        sa.Column(
            "trajectory_semantics",
            sa.String(),
            nullable=True,
            server_default="TURN",
        ),
    )


def downgrade() -> None:
    op.drop_column("runtime_trajectories", "trajectory_semantics")
    op.drop_index(
        "ix_runtime_trajectories_runtime_conversation_id",
        table_name="runtime_trajectories",
    )
    op.drop_column("runtime_trajectories", "runtime_conversation_id")
    op.drop_index("ix_runtime_conversations_status", table_name="runtime_conversations")
    op.drop_index(
        "ix_runtime_conversations_external_id", table_name="runtime_conversations"
    )
    op.drop_index(
        "ix_runtime_conversations_highest_risk_level",
        table_name="runtime_conversations",
    )
    op.drop_index(
        "ix_runtime_conversations_runtime_identity_id",
        table_name="runtime_conversations",
    )
    op.drop_index(
        "ix_runtime_conversations_ai_system_id",
        table_name="runtime_conversations",
    )
    op.drop_index(
        "ix_runtime_conversations_last_activity_at",
        table_name="runtime_conversations",
    )
    op.drop_table("runtime_conversations")
