"""Catalog resource scope (PLATFORM | ORGANIZATION).

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-09-22 08:20:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b3c4d5e6f7a8"
down_revision = "a2b3c4d5e6f7"
branch_labels = None
depends_on = None

CATALOG_TABLES = (
    "model_resources",
    "tool_resources",
    "mcp_servers",
    "external_services",
    "data_sources",
)

KEYED_TABLES = (
    ("tool_resources", "tool_key", "ix_tool_resources_tool_key"),
    ("mcp_servers", "server_key", "ix_mcp_servers_server_key"),
    ("external_services", "service_key", "ix_external_services_service_key"),
    ("data_sources", "data_source_key", "ix_data_sources_data_source_key"),
)


def upgrade() -> None:
    for table in CATALOG_TABLES:
        op.add_column(
            table,
            sa.Column(
                "scope",
                sa.String(),
                nullable=False,
                server_default="PLATFORM",
            ),
        )
        op.create_index(f"ix_{table}_scope", table, ["scope"])

    # Existing rows are platform-global curated/seeded catalog entries.
    for table in CATALOG_TABLES:
        op.execute(sa.text(f"UPDATE {table} SET scope = 'PLATFORM'"))

    for table, key_col, old_index in KEYED_TABLES:
        op.drop_index(old_index, table_name=table)
        op.create_index(f"ix_{table}_{key_col}", table, [key_col])
        op.create_index(
            f"uq_{table}_platform_{key_col}",
            table,
            [key_col],
            unique=True,
            postgresql_where=sa.text("scope = 'PLATFORM'"),
        )
        op.create_index(
            f"uq_{table}_instance_{key_col}",
            table,
            [key_col],
            unique=True,
            postgresql_where=sa.text("scope = 'ORGANIZATION'"),
        )


def downgrade() -> None:
    for table, key_col, old_index in KEYED_TABLES:
        op.drop_index(f"uq_{table}_instance_{key_col}", table_name=table)
        op.drop_index(f"uq_{table}_platform_{key_col}", table_name=table)
        op.drop_index(f"ix_{table}_{key_col}", table_name=table)
        op.create_index(old_index, table, [key_col], unique=True)

    for table in CATALOG_TABLES:
        op.drop_index(f"ix_{table}_scope", table_name=table)
        op.drop_column(table, "scope")
