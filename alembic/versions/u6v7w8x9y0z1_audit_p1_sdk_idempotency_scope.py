"""audit_p1_sdk_idempotency_scope

Revision ID: u6v7w8x9y0z1
Revises: t5u6v7w8x9y0
Create Date: 2026-09-19 10:30:00.000000

Scope SDK decision idempotency to (integration_id, key)
and store action_digest for mismatch detection.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "u6v7w8x9y0z1"
down_revision: Union[str, None] = "t5u6v7w8x9y0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sdk_decision_records",
        sa.Column("action_digest", sa.String(), nullable=True),
    )
    op.create_index(
        "ix_sdk_decision_records_action_digest",
        "sdk_decision_records",
        ["action_digest"],
    )
    op.drop_constraint(
        "uq_sdk_decision_idempotency", "sdk_decision_records", type_="unique"
    )
    op.create_unique_constraint(
        "uq_sdk_decision_integration_idempotency",
        "sdk_decision_records",
        ["integration_id", "idempotency_key"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_sdk_decision_integration_idempotency",
        "sdk_decision_records",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_sdk_decision_idempotency",
        "sdk_decision_records",
        ["idempotency_key"],
    )
    op.drop_index(
        "ix_sdk_decision_records_action_digest", table_name="sdk_decision_records"
    )
    op.drop_column("sdk_decision_records", "action_digest")
