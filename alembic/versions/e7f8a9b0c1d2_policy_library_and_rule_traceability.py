"""policy_library_and_rule_traceability

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
Create Date: 2026-09-23 17:00:00.000000

Add Policy Library sources, obligation/rule linkage, and ToolRule severity/category.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e7f8a9b0c1d2"
down_revision: Union[str, None] = "d6e7f8a9b0c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "policy_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("authority", sa.String(), nullable=True),
        sa.Column("owner", sa.String(), nullable=True),
        sa.Column("jurisdiction", sa.String(), nullable=True),
        sa.Column("policy_type", sa.String(), nullable=True),
        sa.Column("version", sa.String(), nullable=True),
        sa.Column("effective_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="ACTIVE"),
        sa.Column("source_uri", sa.String(), nullable=True),
        sa.Column("content_digest", sa.String(), nullable=True),
        sa.Column("content_text", sa.Text(), nullable=True),
        sa.Column(
            "ingestion_status", sa.String(), nullable=False, server_default="READY"
        ),
        sa.Column("crawl_metadata", sa.JSON(), nullable=True),
        sa.Column(
            "legacy_doc_id",
            sa.String(),
            sa.ForeignKey("policy_documents.doc_id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
    )
    op.create_index("ix_policy_sources_source_type", "policy_sources", ["source_type"])
    op.create_index(
        "ix_policy_sources_jurisdiction", "policy_sources", ["jurisdiction"]
    )
    op.create_index("ix_policy_sources_policy_type", "policy_sources", ["policy_type"])
    op.create_index("ix_policy_sources_status", "policy_sources", ["status"])
    op.create_index(
        "ix_policy_sources_ingestion_status", "policy_sources", ["ingestion_status"]
    )

    op.create_table(
        "policy_source_obligations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "policy_source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("policy_sources.id"),
            nullable=False,
        ),
        sa.Column("section_ref", sa.String(), nullable=True),
        sa.Column("topic", sa.String(), nullable=True),
        sa.Column("scope", sa.String(), nullable=True),
        sa.Column("constraint_action", sa.String(), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="draft"),
        sa.Column("structured", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_policy_source_obligations_policy_source_id",
        "policy_source_obligations",
        ["policy_source_id"],
    )
    op.create_index(
        "ix_policy_source_obligations_status",
        "policy_source_obligations",
        ["status"],
    )

    op.create_table(
        "policy_rule_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "policy_source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("policy_sources.id"),
            nullable=False,
        ),
        sa.Column(
            "obligation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("policy_source_obligations.id"),
            nullable=True,
        ),
        sa.Column("rule_type", sa.String(), nullable=False),
        sa.Column("rule_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "relationship_type",
            sa.String(),
            nullable=False,
            server_default="DERIVED_FROM",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.UniqueConstraint(
            "policy_source_id",
            "rule_type",
            "rule_id",
            name="uq_policy_rule_link_source_rule",
        ),
    )
    op.create_index(
        "ix_policy_rule_links_policy_source_id",
        "policy_rule_links",
        ["policy_source_id"],
    )
    op.create_index(
        "ix_policy_rule_links_obligation_id", "policy_rule_links", ["obligation_id"]
    )
    op.create_index("ix_policy_rule_links_rule_id", "policy_rule_links", ["rule_id"])

    op.add_column("tool_rules", sa.Column("severity", sa.String(), nullable=True))
    op.add_column("tool_rules", sa.Column("category", sa.String(), nullable=True))

    # Helpful catalog filter indexes (idempotent-ish: skip if already present via IF NOT EXISTS)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_model_resources_status ON model_resources (status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_mcp_servers_status ON mcp_servers (status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_mcp_servers_environment ON mcp_servers (environment)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_data_sources_status ON data_sources (status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_external_services_status ON external_services (status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_agent_version_dependencies_resource "
        "ON agent_version_dependencies (resource_type, resource_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_agent_version_dependencies_resource")
    op.execute("DROP INDEX IF EXISTS ix_external_services_status")
    op.execute("DROP INDEX IF EXISTS ix_data_sources_status")
    op.execute("DROP INDEX IF EXISTS ix_mcp_servers_environment")
    op.execute("DROP INDEX IF EXISTS ix_mcp_servers_status")
    op.execute("DROP INDEX IF EXISTS ix_model_resources_status")

    op.drop_column("tool_rules", "category")
    op.drop_column("tool_rules", "severity")

    op.drop_index("ix_policy_rule_links_rule_id", table_name="policy_rule_links")
    op.drop_index("ix_policy_rule_links_obligation_id", table_name="policy_rule_links")
    op.drop_index(
        "ix_policy_rule_links_policy_source_id", table_name="policy_rule_links"
    )
    op.drop_table("policy_rule_links")

    op.drop_index(
        "ix_policy_source_obligations_status", table_name="policy_source_obligations"
    )
    op.drop_index(
        "ix_policy_source_obligations_policy_source_id",
        table_name="policy_source_obligations",
    )
    op.drop_table("policy_source_obligations")

    op.drop_index("ix_policy_sources_ingestion_status", table_name="policy_sources")
    op.drop_index("ix_policy_sources_status", table_name="policy_sources")
    op.drop_index("ix_policy_sources_policy_type", table_name="policy_sources")
    op.drop_index("ix_policy_sources_jurisdiction", table_name="policy_sources")
    op.drop_index("ix_policy_sources_source_type", table_name="policy_sources")
    op.drop_table("policy_sources")
