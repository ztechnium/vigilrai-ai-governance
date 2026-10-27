"""approval_webhook_secret_ciphertext

Revision ID: c1d2e3f4a5b6
Revises: b0c1d2e3f4a5
Create Date: 2026-09-26 12:30:00.000000

Store encrypted webhook signing secrets so delivery can HMAC with the
customer-visible plaintext without keeping it in cleartext columns.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, None] = "b0c1d2e3f4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "webhook_endpoints",
        sa.Column("secret_ciphertext", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("webhook_endpoints", "secret_ciphertext")
