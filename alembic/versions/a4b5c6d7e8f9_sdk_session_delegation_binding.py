"""sdk_session_delegation_binding

Revision ID: a4b5c6d7e8f9
Revises: b3c4d5e6f7a8
Create Date: 2026-09-23 00:00:00.000000

Bind optional tenant delegation to SdkSession for SaaS turn semantics.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a4b5c6d7e8f9"
down_revision: Union[str, None] = "b3c4d5e6f7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sdk_sessions",
        sa.Column("delegation_id", sa.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_sdk_sessions_delegation_id",
        "sdk_sessions",
        "delegation_grants",
        ["delegation_id"],
        ["id"],
    )
    op.create_index(
        "ix_sdk_sessions_integration_delegation",
        "sdk_sessions",
        ["integration_id", "delegation_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_sdk_sessions_integration_delegation",
        table_name="sdk_sessions",
    )
    op.drop_constraint(
        "fk_sdk_sessions_delegation_id",
        "sdk_sessions",
        type_="foreignkey",
    )
    op.drop_column("sdk_sessions", "delegation_id")
