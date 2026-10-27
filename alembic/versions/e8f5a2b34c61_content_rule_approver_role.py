"""content_rule_approver_role

Revision ID: e8f5a2b34c61
Revises: d7e4f1a23b50
Create Date: 2026-09-02 18:40:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e8f5a2b34c61"
down_revision: Union[str, None] = "d7e4f1a23b50"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "content_rules",
        sa.Column("required_approver_role", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("content_rules", "required_approver_role")
