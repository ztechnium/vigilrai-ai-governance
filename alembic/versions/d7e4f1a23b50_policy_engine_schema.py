"""policy_engine_schema

Revision ID: d7e4f1a23b50
Revises: c5f3a9b12e40
Create Date: 2026-09-02 15:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d7e4f1a23b50"
down_revision: Union[str, None] = "c5f3a9b12e40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "policy_collections",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ai_system_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
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
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ai_system_id", name="uq_policy_collection_ai_system"),
    )
    op.create_index(
        op.f("ix_policy_collections_ai_system_id"),
        "policy_collections",
        ["ai_system_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_policy_collections_status"),
        "policy_collections",
        ["status"],
        unique=False,
    )

    op.create_table(
        "content_rules",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("policy_collection_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("effect", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["policy_collection_id"], ["policy_collections.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_content_rules_effect"),
        "content_rules",
        ["effect"],
        unique=False,
    )
    op.create_index(
        op.f("ix_content_rules_enabled"),
        "content_rules",
        ["enabled"],
        unique=False,
    )
    op.create_index(
        op.f("ix_content_rules_policy_collection_id"),
        "content_rules",
        ["policy_collection_id"],
        unique=False,
    )

    op.create_table(
        "tool_rules",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("policy_collection_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("mcp_server_id", sa.UUID(), nullable=True),
        sa.Column("tool_id", sa.UUID(), nullable=False),
        sa.Column("match_mode", sa.String(), nullable=False),
        sa.Column("effect", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("required_approver_role", sa.String(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["policy_collection_id"], ["policy_collections.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["mcp_server_id"], ["mcp_servers.id"]),
        sa.ForeignKeyConstraint(["tool_id"], ["tool_resources.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_tool_rules_effect"),
        "tool_rules",
        ["effect"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tool_rules_enabled"),
        "tool_rules",
        ["enabled"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tool_rules_mcp_server_id"),
        "tool_rules",
        ["mcp_server_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tool_rules_policy_collection_id"),
        "tool_rules",
        ["policy_collection_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tool_rules_tool_id"),
        "tool_rules",
        ["tool_id"],
        unique=False,
    )

    op.create_table(
        "tool_rule_conditions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tool_rule_id", sa.UUID(), nullable=False),
        sa.Column("parameter_path", sa.String(), nullable=False),
        sa.Column("operator", sa.String(), nullable=False),
        sa.Column("value_type", sa.String(), nullable=False),
        sa.Column("value_json", sa.JSON(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tool_rule_id"], ["tool_rules.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_tool_rule_conditions_tool_rule_id"),
        "tool_rule_conditions",
        ["tool_rule_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_tool_rule_conditions_tool_rule_id"), table_name="tool_rule_conditions"
    )
    op.drop_table("tool_rule_conditions")
    op.drop_index(op.f("ix_tool_rules_tool_id"), table_name="tool_rules")
    op.drop_index(op.f("ix_tool_rules_policy_collection_id"), table_name="tool_rules")
    op.drop_index(op.f("ix_tool_rules_mcp_server_id"), table_name="tool_rules")
    op.drop_index(op.f("ix_tool_rules_enabled"), table_name="tool_rules")
    op.drop_index(op.f("ix_tool_rules_effect"), table_name="tool_rules")
    op.drop_table("tool_rules")
    op.drop_index(
        op.f("ix_content_rules_policy_collection_id"), table_name="content_rules"
    )
    op.drop_index(op.f("ix_content_rules_enabled"), table_name="content_rules")
    op.drop_index(op.f("ix_content_rules_effect"), table_name="content_rules")
    op.drop_table("content_rules")
    op.drop_index(op.f("ix_policy_collections_status"), table_name="policy_collections")
    op.drop_index(
        op.f("ix_policy_collections_ai_system_id"), table_name="policy_collections"
    )
    op.drop_table("policy_collections")
