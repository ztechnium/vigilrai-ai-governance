"""wp3_approval_schema

Revision ID: c5f3a9b12e40
Revises: b4e2d8f15a20
Create Date: 2026-09-02 06:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c5f3a9b12e40"
down_revision: Union[str, None] = "b4e2d8f15a20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "approval_requests",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ai_system_id", sa.UUID(), nullable=False),
        sa.Column("agent_id", sa.UUID(), nullable=False),
        sa.Column("agent_version_id", sa.UUID(), nullable=False),
        sa.Column("runtime_identity_id", sa.UUID(), nullable=False),
        sa.Column("delegation_id", sa.UUID(), nullable=True),
        sa.Column("initiating_principal", sa.String(), nullable=True),
        sa.Column("action_type", sa.String(), nullable=False),
        sa.Column("integration_type", sa.String(), nullable=False),
        sa.Column("integration_id", sa.UUID(), nullable=True),
        sa.Column("tool_id", sa.UUID(), nullable=True),
        sa.Column("model_id", sa.UUID(), nullable=True),
        sa.Column("data_source_id", sa.UUID(), nullable=True),
        sa.Column("target_type", sa.String(), nullable=True),
        sa.Column("target_identifier", sa.String(), nullable=True),
        sa.Column("canonical_action_payload", sa.JSON(), nullable=False),
        sa.Column("action_digest", sa.String(), nullable=False),
        sa.Column("business_reason", sa.Text(), nullable=True),
        sa.Column("risk_tier", sa.String(), nullable=True),
        sa.Column("risk_score", sa.Float(), nullable=True),
        sa.Column("approval_policy_reference", sa.String(), nullable=True),
        sa.Column("requirement_reason", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("correlation_id", sa.String(), nullable=True),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
        sa.ForeignKeyConstraint(["agent_version_id"], ["agent_versions.id"]),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"]),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_sources.id"]),
        sa.ForeignKeyConstraint(["delegation_id"], ["delegation_grants.id"]),
        sa.ForeignKeyConstraint(
            ["runtime_identity_id"], ["agent_runtime_identities.id"]
        ),
        sa.ForeignKeyConstraint(["tool_id"], ["tool_resources.id"]),
        sa.ForeignKeyConstraint(["model_id"], ["model_resources.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_approval_requests_action_digest"),
        "approval_requests",
        ["action_digest"],
        unique=False,
    )
    op.create_index(
        op.f("ix_approval_requests_agent_id"),
        "approval_requests",
        ["agent_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_approval_requests_agent_version_id"),
        "approval_requests",
        ["agent_version_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_approval_requests_ai_system_id"),
        "approval_requests",
        ["ai_system_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_approval_requests_correlation_id"),
        "approval_requests",
        ["correlation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_approval_requests_created_at"),
        "approval_requests",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_approval_requests_expires_at"),
        "approval_requests",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_approval_requests_initiating_principal"),
        "approval_requests",
        ["initiating_principal"],
        unique=False,
    )
    op.create_index(
        op.f("ix_approval_requests_risk_tier"),
        "approval_requests",
        ["risk_tier"],
        unique=False,
    )
    op.create_index(
        op.f("ix_approval_requests_runtime_identity_id"),
        "approval_requests",
        ["runtime_identity_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_approval_requests_status"),
        "approval_requests",
        ["status"],
        unique=False,
    )

    op.create_table(
        "approval_decisions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("approval_request_id", sa.UUID(), nullable=False),
        sa.Column("decision", sa.String(), nullable=False),
        sa.Column("decided_by", sa.String(), nullable=False),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("authentication_assurance", sa.String(), nullable=True),
        sa.Column(
            "decided_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("correlation_id", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ["approval_request_id"], ["approval_requests.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_approval_decisions_approval_request_id"),
        "approval_decisions",
        ["approval_request_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_approval_decisions_approval_request_id"),
        table_name="approval_decisions",
    )
    op.drop_table("approval_decisions")
    op.drop_index(op.f("ix_approval_requests_status"), table_name="approval_requests")
    op.drop_index(
        op.f("ix_approval_requests_runtime_identity_id"), table_name="approval_requests"
    )
    op.drop_index(
        op.f("ix_approval_requests_risk_tier"), table_name="approval_requests"
    )
    op.drop_index(
        op.f("ix_approval_requests_initiating_principal"),
        table_name="approval_requests",
    )
    op.drop_index(
        op.f("ix_approval_requests_expires_at"), table_name="approval_requests"
    )
    op.drop_index(
        op.f("ix_approval_requests_created_at"), table_name="approval_requests"
    )
    op.drop_index(
        op.f("ix_approval_requests_correlation_id"), table_name="approval_requests"
    )
    op.drop_index(
        op.f("ix_approval_requests_ai_system_id"), table_name="approval_requests"
    )
    op.drop_index(
        op.f("ix_approval_requests_agent_version_id"), table_name="approval_requests"
    )
    op.drop_index(op.f("ix_approval_requests_agent_id"), table_name="approval_requests")
    op.drop_index(
        op.f("ix_approval_requests_action_digest"), table_name="approval_requests"
    )
    op.drop_table("approval_requests")
