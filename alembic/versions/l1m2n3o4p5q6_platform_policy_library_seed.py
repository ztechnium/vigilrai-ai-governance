"""platform policy library seed scope

Revision ID: l1m2n3o4p5q6
Revises: k0l1m2n3o4p5
Create Date: 2026-10-26 00:20:00.000000

Allow shared PLATFORM policy sources alongside instance sources.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "l1m2n3o4p5q6"
down_revision: Union[str, None] = "k0l1m2n3o4p5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "policy_sources",
        sa.Column(
            "scope",
            sa.String(),
            nullable=False,
            server_default="ORGANIZATION",
        ),
    )
    op.add_column("policy_sources", sa.Column("source_key", sa.String(), nullable=True))
    op.create_index("ix_policy_sources_scope", "policy_sources", ["scope"])
    op.create_index("ix_policy_sources_source_key", "policy_sources", ["source_key"])
    op.create_index(
        "uq_policy_sources_platform_source_key",
        "policy_sources",
        ["source_key"],
        unique=True,
        postgresql_where=sa.text("scope = 'PLATFORM'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_policy_sources_platform_source_key",
        table_name="policy_sources",
    )
    op.drop_index("ix_policy_sources_source_key", table_name="policy_sources")
    op.drop_index("ix_policy_sources_scope", table_name="policy_sources")
    op.execute(sa.text("DELETE FROM policy_sources WHERE scope = 'PLATFORM'"))
    op.drop_column("policy_sources", "source_key")
    op.drop_column("policy_sources", "scope")
