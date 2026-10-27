"""public_registration_onboarding

Revision ID: p1q2r3s4t5u6
Revises: o0p1q2r3s4t5
Create Date: 2026-09-15 08:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p1q2r3s4t5u6"
down_revision: Union[str, None] = "o0p1q2r3s4t5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "organization_onboarding",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "singleton_key",
            sa.String(),
            nullable=False,
            server_default=sa.text("'default'"),
        ),
        sa.Column("current_step", sa.String(), nullable=False),
        sa.Column("completed_steps", sa.JSON(), nullable=False),
        sa.Column("first_ai_system_id", sa.UUID(), nullable=True),
        sa.Column("first_integration_id", sa.UUID(), nullable=True),
        sa.Column("first_trajectory_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
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
        sa.UniqueConstraint("singleton_key", name="uq_onboarding_singleton"),
    )
    op.create_index(
        "ix_organization_onboarding_status",
        "organization_onboarding",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_organization_onboarding_status", table_name="organization_onboarding"
    )
    op.drop_table("organization_onboarding")
