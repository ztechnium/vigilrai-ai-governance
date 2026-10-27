"""wp5_runtime_trajectory_evidence_schema

Revision ID: h2i3j4k5l6m7
Revises: g1h2i3j4k5l6
Create Date: 2026-09-06 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "h2i3j4k5l6m7"
down_revision: Union[str, None] = "g1h2i3j4k5l6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "runtime_trajectories",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ai_system_id", sa.UUID(), nullable=False),
        sa.Column("agent_id", sa.UUID(), nullable=False),
        sa.Column("agent_version_id", sa.UUID(), nullable=False),
        sa.Column("runtime_identity_id", sa.UUID(), nullable=False),
        sa.Column("client_integration_id", sa.UUID(), nullable=True),
        sa.Column("delegation_id", sa.UUID(), nullable=True),
        sa.Column("session_key", sa.String(), nullable=False),
        sa.Column("conversation_id", sa.String(), nullable=True),
        sa.Column("client_session_id", sa.String(), nullable=True),
        sa.Column("correlation_id", sa.String(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column(
            "last_event_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("enforcement_mode", sa.String(), nullable=True),
        sa.Column("deployment_control", sa.String(), nullable=True),
        sa.Column("assurance_summary", sa.JSON(), nullable=True),
        sa.Column("coverage_summary", sa.JSON(), nullable=True),
        sa.Column("event_count", sa.Integer(), nullable=False),
        sa.Column("finding_count", sa.Integer(), nullable=False),
        sa.Column("completeness_pct", sa.Integer(), nullable=True),
        sa.Column("retention_days", sa.Integer(), nullable=True),
        sa.Column("legal_hold", sa.Boolean(), nullable=False),
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
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
        sa.ForeignKeyConstraint(["agent_version_id"], ["agent_versions.id"]),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"]),
        sa.ForeignKeyConstraint(
            ["client_integration_id"], ["runtime_client_integrations.id"]
        ),
        sa.ForeignKeyConstraint(["delegation_id"], ["delegation_grants.id"]),
        sa.ForeignKeyConstraint(
            ["runtime_identity_id"], ["agent_runtime_identities.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "runtime_identity_id",
            "session_key",
            name="uq_runtime_trajectory_session",
        ),
    )
    op.create_index(
        op.f("ix_runtime_trajectories_ai_system_id"),
        "runtime_trajectories",
        ["ai_system_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_runtime_trajectories_agent_id"),
        "runtime_trajectories",
        ["agent_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_runtime_trajectories_agent_version_id"),
        "runtime_trajectories",
        ["agent_version_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_runtime_trajectories_runtime_identity_id"),
        "runtime_trajectories",
        ["runtime_identity_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_runtime_trajectories_client_integration_id"),
        "runtime_trajectories",
        ["client_integration_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_runtime_trajectories_session_key"),
        "runtime_trajectories",
        ["session_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_runtime_trajectories_conversation_id"),
        "runtime_trajectories",
        ["conversation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_runtime_trajectories_client_session_id"),
        "runtime_trajectories",
        ["client_session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_runtime_trajectories_correlation_id"),
        "runtime_trajectories",
        ["correlation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_runtime_trajectories_started_at"),
        "runtime_trajectories",
        ["started_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_runtime_trajectories_status"),
        "runtime_trajectories",
        ["status"],
        unique=False,
    )

    op.create_table(
        "evidence_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("trajectory_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("source_reference", sa.String(), nullable=False),
        sa.Column("assurance_level", sa.String(), nullable=False),
        sa.Column("correlation_id", sa.String(), nullable=True),
        sa.Column("trace_id", sa.String(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("payload_digest", sa.String(), nullable=True),
        sa.Column("content_handling_mode", sa.String(), nullable=False),
        sa.Column("redaction_status", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["trajectory_id"], ["runtime_trajectories.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "trajectory_id",
            "source_type",
            "source_reference",
            "event_type",
            name="uq_evidence_event_idempotency",
        ),
    )
    op.create_index(
        op.f("ix_evidence_events_trajectory_id"),
        "evidence_events",
        ["trajectory_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_evidence_events_event_type"),
        "evidence_events",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_evidence_events_occurred_at"),
        "evidence_events",
        ["occurred_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_evidence_events_source_reference"),
        "evidence_events",
        ["source_reference"],
        unique=False,
    )
    op.create_index(
        op.f("ix_evidence_events_correlation_id"),
        "evidence_events",
        ["correlation_id"],
        unique=False,
    )

    op.create_table(
        "evidence_artifacts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("trajectory_id", sa.UUID(), nullable=False),
        sa.Column("event_id", sa.UUID(), nullable=True),
        sa.Column("artifact_type", sa.String(), nullable=False),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("content_location", sa.String(), nullable=True),
        sa.Column("inline_content", sa.Text(), nullable=True),
        sa.Column("content_digest", sa.String(), nullable=True),
        sa.Column("mime_type", sa.String(), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("content_handling_mode", sa.String(), nullable=False),
        sa.Column("sensitivity_classification", sa.String(), nullable=True),
        sa.Column("encrypted", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["event_id"], ["evidence_events.id"]),
        sa.ForeignKeyConstraint(["trajectory_id"], ["runtime_trajectories.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_evidence_artifacts_trajectory_id"),
        "evidence_artifacts",
        ["trajectory_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_evidence_artifacts_event_id"),
        "evidence_artifacts",
        ["event_id"],
        unique=False,
    )

    op.create_table(
        "evidence_relations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("trajectory_id", sa.UUID(), nullable=False),
        sa.Column("source_entity_type", sa.String(), nullable=False),
        sa.Column("source_entity_id", sa.String(), nullable=False),
        sa.Column("relation_type", sa.String(), nullable=False),
        sa.Column("target_entity_type", sa.String(), nullable=False),
        sa.Column("target_entity_id", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["trajectory_id"], ["runtime_trajectories.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "trajectory_id",
            "source_entity_type",
            "source_entity_id",
            "relation_type",
            "target_entity_type",
            "target_entity_id",
            name="uq_evidence_relation",
        ),
    )
    op.create_index(
        op.f("ix_evidence_relations_trajectory_id"),
        "evidence_relations",
        ["trajectory_id"],
        unique=False,
    )

    op.create_table(
        "evidence_findings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("trajectory_id", sa.UUID(), nullable=False),
        sa.Column("finding_type", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_event_ids", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
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
        sa.ForeignKeyConstraint(["trajectory_id"], ["runtime_trajectories.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_evidence_findings_trajectory_id"),
        "evidence_findings",
        ["trajectory_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_evidence_findings_finding_type"),
        "evidence_findings",
        ["finding_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_evidence_findings_severity"),
        "evidence_findings",
        ["severity"],
        unique=False,
    )
    op.create_index(
        op.f("ix_evidence_findings_status"),
        "evidence_findings",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_evidence_findings_status"), table_name="evidence_findings")
    op.drop_index(op.f("ix_evidence_findings_severity"), table_name="evidence_findings")
    op.drop_index(
        op.f("ix_evidence_findings_finding_type"), table_name="evidence_findings"
    )
    op.drop_index(
        op.f("ix_evidence_findings_trajectory_id"), table_name="evidence_findings"
    )
    op.drop_table("evidence_findings")

    op.drop_index(
        op.f("ix_evidence_relations_trajectory_id"), table_name="evidence_relations"
    )
    op.drop_table("evidence_relations")

    op.drop_index(
        op.f("ix_evidence_artifacts_event_id"), table_name="evidence_artifacts"
    )
    op.drop_index(
        op.f("ix_evidence_artifacts_trajectory_id"), table_name="evidence_artifacts"
    )
    op.drop_table("evidence_artifacts")

    op.drop_index(
        op.f("ix_evidence_events_correlation_id"), table_name="evidence_events"
    )
    op.drop_index(
        op.f("ix_evidence_events_source_reference"), table_name="evidence_events"
    )
    op.drop_index(op.f("ix_evidence_events_occurred_at"), table_name="evidence_events")
    op.drop_index(op.f("ix_evidence_events_event_type"), table_name="evidence_events")
    op.drop_index(
        op.f("ix_evidence_events_trajectory_id"), table_name="evidence_events"
    )
    op.drop_table("evidence_events")

    op.drop_index(
        op.f("ix_runtime_trajectories_status"), table_name="runtime_trajectories"
    )
    op.drop_index(
        op.f("ix_runtime_trajectories_started_at"), table_name="runtime_trajectories"
    )
    op.drop_index(
        op.f("ix_runtime_trajectories_correlation_id"),
        table_name="runtime_trajectories",
    )
    op.drop_index(
        op.f("ix_runtime_trajectories_client_session_id"),
        table_name="runtime_trajectories",
    )
    op.drop_index(
        op.f("ix_runtime_trajectories_conversation_id"),
        table_name="runtime_trajectories",
    )
    op.drop_index(
        op.f("ix_runtime_trajectories_session_key"), table_name="runtime_trajectories"
    )
    op.drop_index(
        op.f("ix_runtime_trajectories_client_integration_id"),
        table_name="runtime_trajectories",
    )
    op.drop_index(
        op.f("ix_runtime_trajectories_runtime_identity_id"),
        table_name="runtime_trajectories",
    )
    op.drop_index(
        op.f("ix_runtime_trajectories_agent_version_id"),
        table_name="runtime_trajectories",
    )
    op.drop_index(
        op.f("ix_runtime_trajectories_agent_id"), table_name="runtime_trajectories"
    )
    op.drop_index(
        op.f("ix_runtime_trajectories_ai_system_id"), table_name="runtime_trajectories"
    )
    op.drop_table("runtime_trajectories")
