"""audit_p1_managed_hooks_eval_endpoint

Revision ID: w8x9y0z1a2b3
Revises: v7w8x9y0z1a2
Create Date: 2026-09-19 10:50:00.000000

Managed-hook attestation columns on runtime_client_integrations and
Agent Version evaluation_endpoint_url for live runner binding.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "w8x9y0z1a2b3"
down_revision: Union[str, None] = "v7w8x9y0z1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "runtime_client_integrations",
        sa.Column("expected_bridge_hash", sa.String(), nullable=True),
    )
    op.add_column(
        "runtime_client_integrations",
        sa.Column("expected_bridge_version", sa.String(), nullable=True),
    )
    op.add_column(
        "runtime_client_integrations",
        sa.Column("observed_bridge_hash", sa.String(), nullable=True),
    )
    op.add_column(
        "runtime_client_integrations",
        sa.Column("managed_profile_key", sa.String(), nullable=True),
    )
    op.add_column(
        "runtime_client_integrations",
        sa.Column("last_attested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "agent_versions",
        sa.Column("evaluation_endpoint_url", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agent_versions", "evaluation_endpoint_url")
    op.drop_column("runtime_client_integrations", "last_attested_at")
    op.drop_column("runtime_client_integrations", "managed_profile_key")
    op.drop_column("runtime_client_integrations", "observed_bridge_hash")
    op.drop_column("runtime_client_integrations", "expected_bridge_version")
    op.drop_column("runtime_client_integrations", "expected_bridge_hash")
