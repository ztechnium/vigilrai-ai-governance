"""approval_runtime_idempotency_key

Revision ID: a9b0c1d2e3f4
Revises: b7c8d9e0f1a2
Create Date: 2026-09-26 12:00:00.000000

Bind optional runtime idempotency keys to approval requests so retries
while PENDING/APPROVED reuse the same request instead of creating duplicates.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a9b0c1d2e3f4"
down_revision: Union[str, None] = "b7c8d9e0f1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "approval_requests",
        sa.Column("runtime_idempotency_key", sa.String(), nullable=True),
    )
    op.create_index(
        "ix_approval_requests_runtime_idempotency_key",
        "approval_requests",
        ["runtime_idempotency_key"],
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_approval_runtime_idempotency
        ON approval_requests (runtime_identity_id, runtime_idempotency_key)
        WHERE runtime_idempotency_key IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_approval_runtime_idempotency")
    op.drop_index(
        "ix_approval_requests_runtime_idempotency_key",
        table_name="approval_requests",
    )
    op.drop_column("approval_requests", "runtime_idempotency_key")
