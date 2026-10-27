"""wp5_evidence_retention_eligible_for_purge

Revision ID: i3j4k5l6m7n8
Revises: h2i3j4k5l6m7
Create Date: 2026-09-07 22:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "i3j4k5l6m7n8"
down_revision: Union[str, None] = "h2i3j4k5l6m7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_RETENTION_DAYS = 90


def upgrade() -> None:
    op.add_column(
        "runtime_trajectories",
        sa.Column("eligible_for_purge_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f("ix_runtime_trajectories_eligible_for_purge_at"),
        "runtime_trajectories",
        ["eligible_for_purge_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_runtime_trajectories_legal_hold"),
        "runtime_trajectories",
        ["legal_hold"],
        unique=False,
    )
    # Backfill defaults for existing rows.
    op.execute(
        f"""
        UPDATE runtime_trajectories
        SET retention_days = COALESCE(retention_days, {DEFAULT_RETENTION_DAYS}),
            eligible_for_purge_at = COALESCE(
                eligible_for_purge_at,
                (COALESCE(ended_at, last_event_at, started_at, now())
                    + make_interval(days => COALESCE(retention_days, {DEFAULT_RETENTION_DAYS})))
            )
        """
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_runtime_trajectories_legal_hold"), table_name="runtime_trajectories"
    )
    op.drop_index(
        op.f("ix_runtime_trajectories_eligible_for_purge_at"),
        table_name="runtime_trajectories",
    )
    op.drop_column("runtime_trajectories", "eligible_for_purge_at")
