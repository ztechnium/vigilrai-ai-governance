"""tool_mcp_server_fk

Revision ID: a3f1c2d94e10
Revises: e8ab47ba64ca
Create Date: 2026-09-01 18:50:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a3f1c2d94e10"
down_revision: Union[str, None] = "e8ab47ba64ca"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tool_resources",
        sa.Column("mcp_server_id", sa.UUID(), nullable=True),
    )
    op.create_index(
        op.f("ix_tool_resources_mcp_server_id"),
        "tool_resources",
        ["mcp_server_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_tool_resources_mcp_server_id",
        "tool_resources",
        "mcp_servers",
        ["mcp_server_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_tool_resources_mcp_server_id", "tool_resources", type_="foreignkey"
    )
    op.drop_index(op.f("ix_tool_resources_mcp_server_id"), table_name="tool_resources")
    op.drop_column("tool_resources", "mcp_server_id")
