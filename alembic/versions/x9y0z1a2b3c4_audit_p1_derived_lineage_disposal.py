"""audit_p1_derived_lineage_disposal

Revision ID: x9y0z1a2b3c4
Revises: w8x9y0z1a2b3
Create Date: 2026-09-19 15:40:00.000000

DataSourceVersion lineage root, derived assets, disposal requests and
per-store acknowledgements.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "x9y0z1a2b3c4"
down_revision: Union[str, None] = "w8x9y0z1a2b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "data_source_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "data_source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("data_sources.id"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("content_digest", sa.String(), nullable=True),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="ACTIVE"),
        sa.Column(
            "legal_hold", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "data_source_id",
            "version_number",
            name="uq_data_source_version_number",
        ),
    )
    op.create_index(
        "ix_data_source_versions_data_source_id",
        "data_source_versions",
        ["data_source_id"],
    )
    op.create_index(
        "ix_data_source_versions_content_digest",
        "data_source_versions",
        ["content_digest"],
    )
    op.create_index(
        "ix_data_source_versions_legal_hold",
        "data_source_versions",
        ["legal_hold"],
    )

    op.create_table(
        "derived_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("data_source_versions.id"),
            nullable=False,
        ),
        sa.Column(
            "parent_asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("derived_assets.id"),
            nullable=True,
        ),
        sa.Column("asset_type", sa.String(), nullable=False),
        sa.Column("store", sa.String(), nullable=False),
        sa.Column("locator", sa.String(), nullable=False),
        sa.Column("digest", sa.String(), nullable=True),
        sa.Column(
            "retention_class",
            sa.String(),
            nullable=False,
            server_default="STANDARD",
        ),
        sa.Column("status", sa.String(), nullable=False, server_default="ACTIVE"),
        sa.Column(
            "legal_hold", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("ai_system_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("agent_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("evidence_ref", sa.String(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
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
        sa.Column("disposed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_derived_assets_source_version_id",
        "derived_assets",
        ["source_version_id"],
    )
    op.create_index(
        "ix_derived_assets_parent_asset_id", "derived_assets", ["parent_asset_id"]
    )
    op.create_index("ix_derived_assets_asset_type", "derived_assets", ["asset_type"])
    op.create_index("ix_derived_assets_store", "derived_assets", ["store"])
    op.create_index("ix_derived_assets_digest", "derived_assets", ["digest"])
    op.create_index("ix_derived_assets_status", "derived_assets", ["status"])
    op.create_index("ix_derived_assets_legal_hold", "derived_assets", ["legal_hold"])
    op.create_index(
        "ix_derived_assets_ai_system_id", "derived_assets", ["ai_system_id"]
    )
    op.create_index(
        "ix_derived_assets_agent_version_id",
        "derived_assets",
        ["agent_version_id"],
    )

    op.create_table(
        "disposal_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("data_source_versions.id"),
            nullable=False,
        ),
        sa.Column("status", sa.String(), nullable=False, server_default="PENDING"),
        sa.Column("requested_by", sa.String(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("access_revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "backup_expiry_tracked_until",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("evidence", sa.JSON(), nullable=True),
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
    op.create_index(
        "ix_disposal_requests_source_version_id",
        "disposal_requests",
        ["source_version_id"],
    )
    op.create_index("ix_disposal_requests_status", "disposal_requests", ["status"])

    op.create_table(
        "disposal_acknowledgements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "disposal_request_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("disposal_requests.id"),
            nullable=False,
        ),
        sa.Column(
            "derived_asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("derived_assets.id"),
            nullable=False,
        ),
        sa.Column("store", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="RETRYING"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("adapter_response", sa.JSON(), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
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
    op.create_index(
        "ix_disposal_acknowledgements_disposal_request_id",
        "disposal_acknowledgements",
        ["disposal_request_id"],
    )
    op.create_index(
        "ix_disposal_acknowledgements_derived_asset_id",
        "disposal_acknowledgements",
        ["derived_asset_id"],
    )
    op.create_index(
        "ix_disposal_acknowledgements_store",
        "disposal_acknowledgements",
        ["store"],
    )
    op.create_index(
        "ix_disposal_acknowledgements_status",
        "disposal_acknowledgements",
        ["status"],
    )


def downgrade() -> None:
    op.drop_table("disposal_acknowledgements")
    op.drop_table("disposal_requests")
    op.drop_table("derived_assets")
    op.drop_table("data_source_versions")
