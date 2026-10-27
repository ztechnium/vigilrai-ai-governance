"""canonical enforcement receipt v2 + control decisions

Revision ID: j9k0l1m2n3o4
Revises: i8j9k0l1m2n3
Create Date: 2026-09-26 16:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "j9k0l1m2n3o4"
down_revision: Union[str, None] = "i8j9k0l1m2n3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "runtime_enforcement_receipts",
        sa.Column(
            "receipt_schema_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )
    op.add_column(
        "runtime_enforcement_receipts",
        sa.Column("decision_phase", sa.String(), nullable=True),
    )
    op.add_column(
        "runtime_enforcement_receipts",
        sa.Column("decision_finalized_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "runtime_enforcement_receipts",
        sa.Column("decision_digest", sa.String(), nullable=True),
    )
    op.add_column(
        "runtime_enforcement_receipts",
        sa.Column("authority_digest", sa.String(), nullable=True),
    )
    op.add_column(
        "runtime_enforcement_receipts",
        sa.Column("authority_snapshot", sa.JSON(), nullable=True),
    )
    op.add_column(
        "runtime_enforcement_receipts",
        sa.Column("effective_scope_digest", sa.String(), nullable=True),
    )
    op.add_column(
        "runtime_enforcement_receipts",
        sa.Column("policy_bundle_digest", sa.String(), nullable=True),
    )
    op.add_column(
        "runtime_enforcement_receipts",
        sa.Column("control_summary", sa.JSON(), nullable=True),
    )
    op.add_column(
        "runtime_enforcement_receipts",
        sa.Column("resume_of_receipt_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "runtime_enforcement_receipts",
        sa.Column("decision_chain_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "runtime_enforcement_receipts",
        sa.Column("revalidated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "runtime_enforcement_receipts",
        sa.Column(
            "revalidation_count", sa.Integer(), nullable=False, server_default="0"
        ),
    )

    op.create_foreign_key(
        "fk_runtime_enforcement_receipts_resume_of",
        "runtime_enforcement_receipts",
        "runtime_enforcement_receipts",
        ["resume_of_receipt_id"],
        ["id"],
    )
    op.create_index(
        "ix_runtime_enforcement_receipts_resume_of_receipt_id",
        "runtime_enforcement_receipts",
        ["resume_of_receipt_id"],
    )
    op.create_index(
        "ix_runtime_enforcement_receipts_decision_chain_id",
        "runtime_enforcement_receipts",
        ["decision_chain_id"],
    )

    op.create_table(
        "runtime_control_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("receipt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("phase", sa.String(), nullable=True),
        sa.Column("control_type", sa.String(), nullable=False),
        sa.Column("policy_domain", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("effect", sa.String(), nullable=True),
        sa.Column("reason_code", sa.String(), nullable=True),
        sa.Column("human_explanation", sa.Text(), nullable=True),
        sa.Column("source_type", sa.String(), nullable=True),
        sa.Column("source_id", sa.String(), nullable=True),
        sa.Column("source_version", sa.String(), nullable=True),
        sa.Column("matched_rule_ids", sa.JSON(), nullable=True),
        sa.Column("control_snapshot", sa.JSON(), nullable=True),
        sa.Column("evidence_refs", sa.JSON(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["receipt_id"], ["runtime_enforcement_receipts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "receipt_id",
            "sequence",
            name="uq_runtime_control_decision_sequence",
        ),
    )
    op.create_index(
        "ix_runtime_control_decisions_receipt_id",
        "runtime_control_decisions",
        ["receipt_id"],
    )

    op.alter_column(
        "runtime_enforcement_receipts", "receipt_schema_version", server_default=None
    )
    op.alter_column(
        "runtime_enforcement_receipts", "revalidation_count", server_default=None
    )


def downgrade() -> None:
    op.drop_index(
        "ix_runtime_control_decisions_receipt_id",
        table_name="runtime_control_decisions",
    )
    op.drop_table("runtime_control_decisions")

    op.drop_index(
        "ix_runtime_enforcement_receipts_decision_chain_id",
        table_name="runtime_enforcement_receipts",
    )
    op.drop_index(
        "ix_runtime_enforcement_receipts_resume_of_receipt_id",
        table_name="runtime_enforcement_receipts",
    )
    op.drop_constraint(
        "fk_runtime_enforcement_receipts_resume_of",
        "runtime_enforcement_receipts",
        type_="foreignkey",
    )
    for col in (
        "revalidation_count",
        "revalidated_at",
        "decision_chain_id",
        "resume_of_receipt_id",
        "control_summary",
        "policy_bundle_digest",
        "effective_scope_digest",
        "authority_snapshot",
        "authority_digest",
        "decision_digest",
        "decision_finalized_at",
        "decision_phase",
        "receipt_schema_version",
    ):
        op.drop_column("runtime_enforcement_receipts", col)
