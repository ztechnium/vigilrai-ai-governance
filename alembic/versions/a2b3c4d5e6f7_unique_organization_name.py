"""Unique organization display names (case-insensitive).

Revision ID: a2b3c4d5e6f7
Revises: z1a2b3c4d5e6
Create Date: 2026-09-22 02:00:00.000000

No-op: the singleton profile is one row, so name uniqueness is not required.
"""

from __future__ import annotations

revision = "a2b3c4d5e6f7"
down_revision = "z1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
