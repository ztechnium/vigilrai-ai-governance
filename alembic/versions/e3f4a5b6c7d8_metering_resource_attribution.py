"""metering resource attribution columns

Revision ID: e3f4a5b6c7d8
Revises: d3e4f5a6b7c8
Create Date: 2026-09-26 13:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e3f4a5b6c7d8"
down_revision: Union[str, None] = "d3e4f5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for col in (
        "model_resource_id",
        "tool_id",
        "mcp_server_id",
        "external_service_id",
    ):
        op.add_column(
            "finops_metering_spans",
            sa.Column(col, postgresql.UUID(as_uuid=True), nullable=True),
        )
        op.create_index(
            f"ix_finops_metering_spans_{col}",
            "finops_metering_spans",
            [col],
        )
    op.add_column(
        "finops_metering_spans",
        sa.Column("cache_write_tokens", sa.Integer(), nullable=True),
    )
    # Allow unavailable settlements without fabricating $0.
    op.alter_column(
        "finops_usage_settlements",
        "actual_cost",
        existing_type=sa.Float(),
        nullable=True,
        server_default=None,
    )


def downgrade() -> None:
    op.alter_column(
        "finops_usage_settlements",
        "actual_cost",
        existing_type=sa.Float(),
        nullable=False,
        server_default="0",
    )
    op.drop_column("finops_metering_spans", "cache_write_tokens")
    for col in (
        "external_service_id",
        "mcp_server_id",
        "tool_id",
        "model_resource_id",
    ):
        op.drop_index(
            f"ix_finops_metering_spans_{col}", table_name="finops_metering_spans"
        )
        op.drop_column("finops_metering_spans", col)
