"""finops pricing catalog v2 dimensions

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-09-26 12:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d2e3f4a5b6c7"
down_revision: Union[str, None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "finops_pricing_catalog",
        sa.Column("cache_write_token_price", sa.Float(), nullable=True),
    )
    op.add_column(
        "finops_pricing_catalog",
        sa.Column("image_input_price", sa.Float(), nullable=True),
    )
    op.add_column(
        "finops_pricing_catalog",
        sa.Column("image_output_price", sa.Float(), nullable=True),
    )
    op.add_column(
        "finops_pricing_catalog",
        sa.Column("audio_input_price", sa.Float(), nullable=True),
    )
    op.add_column(
        "finops_pricing_catalog",
        sa.Column("audio_output_price", sa.Float(), nullable=True),
    )
    op.add_column(
        "finops_pricing_catalog",
        sa.Column("request_price", sa.Float(), nullable=True),
    )
    op.add_column(
        "finops_pricing_catalog",
        sa.Column("provider_tool_price", sa.Float(), nullable=True),
    )
    op.add_column(
        "finops_pricing_catalog",
        sa.Column("pricing_metadata", sa.JSON(), nullable=True),
    )
    op.add_column(
        "finops_pricing_catalog",
        sa.Column("source_url", sa.String(), nullable=True),
    )
    op.add_column(
        "finops_pricing_catalog",
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "finops_pricing_catalog",
        sa.Column("region", sa.String(), nullable=True),
    )
    op.add_column(
        "finops_pricing_catalog",
        sa.Column("service_tier", sa.String(), nullable=True),
    )


def downgrade() -> None:
    for col in (
        "service_tier",
        "region",
        "verified_at",
        "source_url",
        "pricing_metadata",
        "provider_tool_price",
        "request_price",
        "audio_output_price",
        "audio_input_price",
        "image_output_price",
        "image_input_price",
        "cache_write_token_price",
    ):
        op.drop_column("finops_pricing_catalog", col)
