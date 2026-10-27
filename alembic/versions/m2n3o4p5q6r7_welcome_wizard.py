"""Profile logo and first-run welcome completion.

Revision ID: m2n3o4p5q6r7
Revises: l1m2n3o4p5q6
Create Date: 2026-10-26 01:10:00.000000

Existing onboarding rows are treated as already welcomed so they are not
sent through the first-run wizard. New registrations leave the timestamp null.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "m2n3o4p5q6r7"
down_revision: Union[str, None] = "l1m2n3o4p5q6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "organization_governance_profiles",
        sa.Column("logo", sa.Text(), nullable=True),
    )
    op.add_column(
        "organization_onboarding",
        sa.Column("welcome_completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE organization_onboarding "
            "SET welcome_completed_at = CURRENT_TIMESTAMP "
            "WHERE welcome_completed_at IS NULL"
        )
    )


def downgrade() -> None:
    op.drop_column("organization_onboarding", "welcome_completed_at")
    op.drop_column("organization_governance_profiles", "logo")
