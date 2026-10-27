"""delegation scope v2 + revisions + lifecycle

Revision ID: i8j9k0l1m2n3
Revises: h7i8j9k0l1m2
Create Date: 2026-09-26 16:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "i8j9k0l1m2n3"
down_revision: Union[str, None] = "h7i8j9k0l1m2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "delegation_grants",
        sa.Column("scope_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "delegation_grants",
        sa.Column("revision_number", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "delegation_grants",
        sa.Column("scope_digest", sa.String(), nullable=True),
    )

    op.create_table(
        "delegation_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("delegation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("scope_version", sa.Integer(), nullable=False),
        sa.Column("scope_snapshot", sa.JSON(), nullable=False),
        sa.Column("scope_digest", sa.String(), nullable=True),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("change_type", sa.String(), nullable=False),
        sa.Column("change_reason", sa.Text(), nullable=True),
        sa.Column("changed_by", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["delegation_id"], ["delegation_grants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "delegation_id",
            "revision_number",
            name="uq_delegation_revision_number",
        ),
    )
    op.create_index(
        "ix_delegation_revisions_delegation_id",
        "delegation_revisions",
        ["delegation_id"],
        unique=False,
    )

    # Seed revision 1 for existing grants without rewriting historical V1 scope JSON.
    op.execute(
        """
        INSERT INTO delegation_revisions (
            id, delegation_id, revision_number, scope_version, scope_snapshot,
            scope_digest, valid_from, expires_at, change_type, change_reason, changed_by
        )
        SELECT
            gen_random_uuid(),
            dg.id,
            1,
            COALESCE(dg.scope_version, 1),
            COALESCE(dg.scope, '{}'::json),
            dg.scope_digest,
            dg.valid_from,
            dg.expires_at,
            'CREATED',
            'backfill',
            COALESCE(dg.created_by, 'system')
        FROM delegation_grants dg
        WHERE NOT EXISTS (
            SELECT 1 FROM delegation_revisions dr
            WHERE dr.delegation_id = dg.id AND dr.revision_number = 1
        )
        """
    )

    op.alter_column("delegation_grants", "scope_version", server_default=None)
    op.alter_column("delegation_grants", "revision_number", server_default=None)


def downgrade() -> None:
    op.drop_index(
        "ix_delegation_revisions_delegation_id", table_name="delegation_revisions"
    )
    op.drop_table("delegation_revisions")
    op.drop_column("delegation_grants", "scope_digest")
    op.drop_column("delegation_grants", "revision_number")
    op.drop_column("delegation_grants", "scope_version")
