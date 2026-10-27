"""audit_p0_budget_enforcement_mode

Revision ID: q2r3s4t5u6v7
Revises: p1q2r3s4t5u6
Create Date: 2026-09-15 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "q2r3s4t5u6v7"
down_revision: Union[str, None] = "p1q2r3s4t5u6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "runtime_budgets",
        sa.Column(
            "enforcement_mode",
            sa.String(),
            nullable=False,
            server_default="BEST_EFFORT",
        ),
    )


def downgrade() -> None:
    op.drop_column("runtime_budgets", "enforcement_mode")
