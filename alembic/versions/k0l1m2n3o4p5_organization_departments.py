"""organization departments

Revision ID: k0l1m2n3o4p5
Revises: j9k0l1m2n3o4
Create Date: 2026-10-22 15:10:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "k0l1m2n3o4p5"
down_revision: Union[str, None] = "j9k0l1m2n3o4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "departments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", sa.String(), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_department_name"),
    )
    op.add_column(
        "organization_memberships",
        sa.Column("department_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_organization_memberships_department_id",
        "organization_memberships",
        "departments",
        ["department_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_organization_memberships_department_id",
        "organization_memberships",
        ["department_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_organization_memberships_department_id",
        table_name="organization_memberships",
    )
    op.drop_constraint(
        "fk_organization_memberships_department_id",
        "organization_memberships",
        type_="foreignkey",
    )
    op.drop_column("organization_memberships", "department_id")
    op.drop_table("departments")
