"""wp4_client_hook_integrations

Revision ID: a1b2c3d4e5f6
Revises: f9a6b3c45d72
Create Date: 2026-09-02 22:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "f9a6b3c45d72"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "runtime_client_integrations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("runtime_identity_id", sa.UUID(), nullable=False),
        sa.Column("client_type", sa.String(), nullable=False),
        sa.Column("enforcement_mode", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("client_version", sa.String(), nullable=True),
        sa.Column("bridge_version", sa.String(), nullable=True),
        sa.Column("protocol_version", sa.String(), nullable=True),
        sa.Column("configuration_status", sa.String(), nullable=True),
        sa.Column("coverage", sa.JSON(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_decision_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_decision_effect", sa.String(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["runtime_identity_id"], ["agent_runtime_identities.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "runtime_identity_id",
            "client_type",
            name="uq_runtime_client_integration",
        ),
    )
    op.create_index(
        op.f("ix_runtime_client_integrations_runtime_identity_id"),
        "runtime_client_integrations",
        ["runtime_identity_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_runtime_client_integrations_runtime_identity_id"),
        table_name="runtime_client_integrations",
    )
    op.drop_table("runtime_client_integrations")
