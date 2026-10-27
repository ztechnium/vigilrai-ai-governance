"""saas_email_welcome_and_reset_ip

Revision ID: z1a2b3c4d5e6
Revises: y0z1a2b3c4d5
Create Date: 2026-09-22 00:00:00.000000

welcome_email_sent_at on users; requested_ip_hash on password_reset_tokens.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "z1a2b3c4d5e6"
down_revision: Union[str, None] = "y0z1a2b3c4d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("welcome_email_sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "password_reset_tokens",
        sa.Column("requested_ip_hash", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("password_reset_tokens", "requested_ip_hash")
    op.drop_column("users", "welcome_email_sent_at")
