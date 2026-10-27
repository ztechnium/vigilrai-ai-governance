"""runtime_scale_indexes_and_semantics

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-09-23 16:00:00.000000

Add high-volume query indexes for trajectories, events, and receipts.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "d6e7f8a9b0c1"
down_revision: Union[str, None] = "c5d6e7f8a9b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_runtime_trajectories_delegation_id",
        "runtime_trajectories",
        ["delegation_id"],
    )
    op.create_index(
        "ix_runtime_trajectories_last_event_at",
        "runtime_trajectories",
        ["last_event_at"],
    )
    op.create_index(
        "ix_runtime_trajectories_status_started",
        "runtime_trajectories",
        ["status", "started_at"],
    )
    op.create_index(
        "ix_evidence_events_trajectory_sequence",
        "evidence_events",
        ["trajectory_id", "sequence_number"],
    )
    op.create_index(
        "ix_evidence_events_occurred_id",
        "evidence_events",
        ["occurred_at", "id"],
    )
    op.create_index(
        "ix_evidence_events_type_occurred",
        "evidence_events",
        ["event_type", "occurred_at"],
    )
    op.create_index(
        "ix_runtime_enforcement_receipts_started_id",
        "runtime_enforcement_receipts",
        ["started_at", "id"],
    )
    op.create_index(
        "ix_runtime_enforcement_receipts_delegation_id",
        "runtime_enforcement_receipts",
        ["delegation_id"],
    )
    op.create_index(
        "ix_runtime_enforcement_receipts_decision_status",
        "runtime_enforcement_receipts",
        ["enforcement_decision", "execution_status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_runtime_enforcement_receipts_decision_status",
        table_name="runtime_enforcement_receipts",
    )
    op.drop_index(
        "ix_runtime_enforcement_receipts_delegation_id",
        table_name="runtime_enforcement_receipts",
    )
    op.drop_index(
        "ix_runtime_enforcement_receipts_started_id",
        table_name="runtime_enforcement_receipts",
    )
    op.drop_index(
        "ix_evidence_events_type_occurred",
        table_name="evidence_events",
    )
    op.drop_index(
        "ix_evidence_events_occurred_id",
        table_name="evidence_events",
    )
    op.drop_index(
        "ix_evidence_events_trajectory_sequence",
        table_name="evidence_events",
    )
    op.drop_index(
        "ix_runtime_trajectories_status_started",
        table_name="runtime_trajectories",
    )
    op.drop_index(
        "ix_runtime_trajectories_last_event_at",
        table_name="runtime_trajectories",
    )
    op.drop_index(
        "ix_runtime_trajectories_delegation_id",
        table_name="runtime_trajectories",
    )
