"""wp2_identity_schema

Revision ID: b4e2d8f15a20
Revises: a3f1c2d94e10
Create Date: 2026-09-01 21:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b4e2d8f15a20"
down_revision: Union[str, None] = "a3f1c2d94e10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_runtime_identities",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("identity_key", sa.String(), nullable=False),
        sa.Column("agent_id", sa.UUID(), nullable=False),
        sa.Column("agent_version_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("identity_type", sa.String(), nullable=False),
        sa.Column("auth_provider", sa.String(), nullable=True),
        sa.Column("external_subject", sa.String(), nullable=True),
        sa.Column("environment", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_authenticated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
        sa.ForeignKeyConstraint(["agent_version_id"], ["agent_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("identity_key", name="uq_runtime_identity_key"),
    )
    op.create_index(
        op.f("ix_agent_runtime_identities_agent_id"),
        "agent_runtime_identities",
        ["agent_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_runtime_identities_agent_version_id"),
        "agent_runtime_identities",
        ["agent_version_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_runtime_identities_identity_key"),
        "agent_runtime_identities",
        ["identity_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_runtime_identities_status"),
        "agent_runtime_identities",
        ["status"],
        unique=False,
    )

    op.create_table(
        "runtime_credentials",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("runtime_identity_id", sa.UUID(), nullable=False),
        sa.Column("credential_key", sa.String(), nullable=False),
        sa.Column("credential_type", sa.String(), nullable=False),
        sa.Column("key_hash", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column(
            "issued_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_id", sa.UUID(), nullable=True),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["replaced_by_id"],
            ["runtime_credentials.id"],
        ),
        sa.ForeignKeyConstraint(
            ["runtime_identity_id"],
            ["agent_runtime_identities.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("credential_key", name="uq_runtime_credential_key"),
    )
    op.create_index(
        op.f("ix_runtime_credentials_credential_key"),
        "runtime_credentials",
        ["credential_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_runtime_credentials_key_hash"),
        "runtime_credentials",
        ["key_hash"],
        unique=False,
    )
    op.create_index(
        op.f("ix_runtime_credentials_runtime_identity_id"),
        "runtime_credentials",
        ["runtime_identity_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_runtime_credentials_status"),
        "runtime_credentials",
        ["status"],
        unique=False,
    )

    op.create_table(
        "delegation_grants",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("delegator_type", sa.String(), nullable=False),
        sa.Column("delegator_id", sa.String(), nullable=False),
        sa.Column("delegate_runtime_identity_id", sa.UUID(), nullable=False),
        sa.Column("parent_delegation_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("scope", sa.JSON(), nullable=False),
        sa.Column(
            "valid_from",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["delegate_runtime_identity_id"],
            ["agent_runtime_identities.id"],
        ),
        sa.ForeignKeyConstraint(
            ["parent_delegation_id"],
            ["delegation_grants.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_delegation_grants_delegate_runtime_identity_id"),
        "delegation_grants",
        ["delegate_runtime_identity_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_delegation_grants_delegator_id"),
        "delegation_grants",
        ["delegator_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_delegation_grants_parent_delegation_id"),
        "delegation_grants",
        ["parent_delegation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_delegation_grants_status"),
        "delegation_grants",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_delegation_grants_status"), table_name="delegation_grants")
    op.drop_index(
        op.f("ix_delegation_grants_parent_delegation_id"),
        table_name="delegation_grants",
    )
    op.drop_index(
        op.f("ix_delegation_grants_delegator_id"), table_name="delegation_grants"
    )
    op.drop_index(
        op.f("ix_delegation_grants_delegate_runtime_identity_id"),
        table_name="delegation_grants",
    )
    op.drop_table("delegation_grants")

    op.drop_index(
        op.f("ix_runtime_credentials_status"), table_name="runtime_credentials"
    )
    op.drop_index(
        op.f("ix_runtime_credentials_runtime_identity_id"),
        table_name="runtime_credentials",
    )
    op.drop_index(
        op.f("ix_runtime_credentials_key_hash"), table_name="runtime_credentials"
    )
    op.drop_index(
        op.f("ix_runtime_credentials_credential_key"), table_name="runtime_credentials"
    )
    op.drop_table("runtime_credentials")

    op.drop_index(
        op.f("ix_agent_runtime_identities_status"),
        table_name="agent_runtime_identities",
    )
    op.drop_index(
        op.f("ix_agent_runtime_identities_identity_key"),
        table_name="agent_runtime_identities",
    )
    op.drop_index(
        op.f("ix_agent_runtime_identities_agent_version_id"),
        table_name="agent_runtime_identities",
    )
    op.drop_index(
        op.f("ix_agent_runtime_identities_agent_id"),
        table_name="agent_runtime_identities",
    )
    op.drop_table("agent_runtime_identities")
