"""finops cost states metered billed pricing snapshot

Revision ID: d3e4f5a6b7c8
Revises: d2e3f4a5b6c7
Create Date: 2026-09-26 12:05:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, None] = "d2e3f4a5b6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "finops_metering_spans",
        sa.Column("metered_cost", sa.Float(), nullable=True),
    )
    op.add_column(
        "finops_metering_spans",
        sa.Column("billed_cost", sa.Float(), nullable=True),
    )
    op.add_column(
        "finops_metering_spans",
        sa.Column("pricing_snapshot", sa.JSON(), nullable=True),
    )

    op.add_column(
        "finops_usage_settlements",
        sa.Column("estimated_cost", sa.Float(), nullable=True),
    )
    op.add_column(
        "finops_usage_settlements",
        sa.Column("metered_cost", sa.Float(), nullable=True),
    )
    op.add_column(
        "finops_usage_settlements",
        sa.Column("billed_cost", sa.Float(), nullable=True),
    )
    op.add_column(
        "finops_usage_settlements",
        sa.Column("pricing_snapshot", sa.JSON(), nullable=True),
    )

    # Backfill: catalog-derived ACTUAL/ESTIMATED with money → prefer metered.
    op.execute(
        """
        UPDATE finops_metering_spans
        SET metered_cost = COALESCE(actual_cost, estimated_cost),
            cost_state = 'METERED'
        WHERE metering_source = 'PRICING_CATALOG_DERIVED'
          AND (actual_cost IS NOT NULL OR estimated_cost IS NOT NULL)
        """
    )
    op.execute(
        """
        UPDATE finops_metering_spans
        SET billed_cost = actual_cost,
            cost_state = 'BILLED'
        WHERE cost_state = 'ACTUAL'
          AND metering_source IN (
              'PROVIDER_RESPONSE', 'GATEWAY_OBSERVED', 'SIGNED_SERVICE',
              'PROVIDER_BILLING_API', 'INVOICE_IMPORT'
          )
          AND actual_cost IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE finops_usage_settlements
        SET metered_cost = actual_cost,
            cost_state = 'METERED'
        WHERE metering_source = 'PRICING_CATALOG_DERIVED'
          AND actual_cost IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE finops_usage_settlements
        SET billed_cost = actual_cost,
            cost_state = 'BILLED'
        WHERE cost_state = 'ACTUAL'
          AND metering_source IN (
              'PROVIDER_RESPONSE', 'GATEWAY_OBSERVED', 'SIGNED_SERVICE',
              'PROVIDER_BILLING_API', 'INVOICE_IMPORT'
          )
          AND actual_cost IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_column("finops_usage_settlements", "pricing_snapshot")
    op.drop_column("finops_usage_settlements", "billed_cost")
    op.drop_column("finops_usage_settlements", "metered_cost")
    op.drop_column("finops_usage_settlements", "estimated_cost")
    op.drop_column("finops_metering_spans", "pricing_snapshot")
    op.drop_column("finops_metering_spans", "billed_cost")
    op.drop_column("finops_metering_spans", "metered_cost")
