"""wp4_closure_receipt_assurance

Revision ID: g1h2i3j4k5l6
Revises: a1b2c3d4e5f6
Create Date: 2026-09-04 22:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "g1h2i3j4k5l6"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "runtime_enforcement_receipts",
        sa.Column("deployment_control", sa.String(), nullable=True),
    )
    op.add_column(
        "runtime_enforcement_receipts",
        sa.Column("verification_status", sa.String(), nullable=True),
    )
    op.add_column(
        "runtime_enforcement_receipts",
        sa.Column("execution_source", sa.String(), nullable=True),
    )
    op.add_column(
        "runtime_enforcement_receipts",
        sa.Column("client_context", sa.JSON(), nullable=True),
    )
    op.add_column(
        "runtime_enforcement_receipts",
        sa.Column("execution_report", sa.JSON(), nullable=True),
    )
    op.add_column(
        "runtime_enforcement_receipts",
        sa.Column("idempotency_key", sa.String(), nullable=True),
    )
    op.add_column(
        "runtime_enforcement_receipts",
        sa.Column("duration_ms", sa.Integer(), nullable=True),
    )
    op.add_column(
        "runtime_enforcement_receipts",
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_runtime_enforcement_receipts_approval_request_id",
        "runtime_enforcement_receipts",
        ["approval_request_id"],
    )

    op.add_column(
        "runtime_client_integrations",
        sa.Column("deployment_control", sa.String(), nullable=True),
    )
    op.add_column(
        "runtime_client_integrations",
        sa.Column("verification_status", sa.String(), nullable=True),
    )

    # Normalize legacy proxy in-progress rows to STARTED.
    op.execute(
        "UPDATE runtime_enforcement_receipts "
        "SET execution_status = 'STARTED' "
        "WHERE execution_status = 'IN_PROGRESS'"
    )
    # Hook ALLOW receipts awaiting client report.
    op.execute(
        "UPDATE runtime_enforcement_receipts "
        "SET execution_status = 'PENDING_CLIENT_REPORT', "
        "    execution_source = 'CLIENT_REPORTED' "
        "WHERE enforcement_mode = 'HOOK_ENFORCED' "
        "  AND enforcement_decision IN ('ALLOW', 'MONITOR') "
        "  AND execution_status = 'NOT_ATTEMPTED' "
        "  AND execution_attempted = false"
    )
    op.execute(
        "UPDATE runtime_enforcement_receipts "
        "SET execution_source = 'RAI_EXECUTED', "
        "    deployment_control = 'PROXY_CONTROLLED', "
        "    verification_status = 'VERIFIED' "
        "WHERE enforcement_mode = 'PROXY_ENFORCED' "
        "  AND execution_source IS NULL"
    )
    op.execute(
        "UPDATE runtime_enforcement_receipts "
        "SET deployment_control = COALESCE(deployment_control, 'LOCAL_HOOK'), "
        "    verification_status = COALESCE(verification_status, 'DECLARED') "
        "WHERE enforcement_mode = 'HOOK_ENFORCED'"
    )
    op.execute(
        "UPDATE runtime_client_integrations "
        "SET deployment_control = COALESCE(deployment_control, 'LOCAL_HOOK'), "
        "    verification_status = COALESCE(verification_status, 'DECLARED')"
    )


def downgrade() -> None:
    op.drop_column("runtime_client_integrations", "verification_status")
    op.drop_column("runtime_client_integrations", "deployment_control")
    op.drop_index(
        "ix_runtime_enforcement_receipts_approval_request_id",
        table_name="runtime_enforcement_receipts",
    )
    op.drop_column("runtime_enforcement_receipts", "reported_at")
    op.drop_column("runtime_enforcement_receipts", "duration_ms")
    op.drop_column("runtime_enforcement_receipts", "idempotency_key")
    op.drop_column("runtime_enforcement_receipts", "execution_report")
    op.drop_column("runtime_enforcement_receipts", "client_context")
    op.drop_column("runtime_enforcement_receipts", "execution_source")
    op.drop_column("runtime_enforcement_receipts", "verification_status")
    op.drop_column("runtime_enforcement_receipts", "deployment_control")
