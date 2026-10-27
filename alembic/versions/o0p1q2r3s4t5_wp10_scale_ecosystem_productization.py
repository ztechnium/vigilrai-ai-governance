"""wp10_scale_ecosystem_enterprise_productization

Revision ID: o0p1q2r3s4t5
Revises: n9o0p1q2r3s4
Create Date: 2026-09-15 02:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "o0p1q2r3s4t5"
down_revision: Union[str, None] = "n9o0p1q2r3s4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sdk_integrations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("integration_key", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("integration_type", sa.String(), nullable=False),
        sa.Column("runtime_identity_id", sa.UUID(), nullable=False),
        sa.Column("client_integration_id", sa.UUID(), nullable=True),
        sa.Column("environment", sa.String(), nullable=False),
        sa.Column("auth_method", sa.String(), nullable=False),
        sa.Column("protocol_version", sa.Integer(), nullable=False),
        sa.Column("sdk_version", sa.String(), nullable=True),
        sa.Column("enforcement_mode", sa.String(), nullable=False),
        sa.Column("deployment_control", sa.String(), nullable=True),
        sa.Column("verification_status", sa.String(), nullable=True),
        sa.Column("certification_status", sa.String(), nullable=False),
        sa.Column("capability_matrix", sa.JSON(), nullable=True),
        sa.Column("fail_closed", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("oidc_issuer", sa.String(), nullable=True),
        sa.Column("oidc_audience", sa.String(), nullable=True),
        sa.Column("oidc_subject_claim", sa.String(), nullable=True),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sdk_version", sa.String(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["runtime_identity_id"], ["agent_runtime_identities.id"]
        ),
        sa.ForeignKeyConstraint(
            ["client_integration_id"], ["runtime_client_integrations.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "integration_key",
            name="uq_sdk_integration_key",
        ),
    )
    op.create_index(
        "ix_sdk_integrations_integration_key", "sdk_integrations", ["integration_key"]
    )
    op.create_index(
        "ix_sdk_integrations_runtime_identity_id",
        "sdk_integrations",
        ["runtime_identity_id"],
    )
    op.create_index("ix_sdk_integrations_status", "sdk_integrations", ["status"])

    op.create_table(
        "sdk_sessions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("integration_id", sa.UUID(), nullable=False),
        sa.Column("runtime_identity_id", sa.UUID(), nullable=False),
        sa.Column("trajectory_id", sa.UUID(), nullable=True),
        sa.Column("correlation_id", sa.String(), nullable=False),
        sa.Column("external_session_id", sa.String(), nullable=True),
        sa.Column("external_conversation_id", sa.String(), nullable=True),
        sa.Column("principal", sa.String(), nullable=True),
        sa.Column("channel", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["integration_id"], ["sdk_integrations.id"]),
        sa.ForeignKeyConstraint(
            ["runtime_identity_id"], ["agent_runtime_identities.id"]
        ),
        sa.ForeignKeyConstraint(["trajectory_id"], ["runtime_trajectories.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "integration_id",
            "external_session_id",
            name="uq_sdk_session_external",
        ),
    )
    op.create_index(
        "ix_sdk_sessions_integration_id", "sdk_sessions", ["integration_id"]
    )
    op.create_index(
        "ix_sdk_sessions_runtime_identity_id",
        "sdk_sessions",
        ["runtime_identity_id"],
    )
    op.create_index(
        "ix_sdk_sessions_correlation_id", "sdk_sessions", ["correlation_id"]
    )
    op.create_index("ix_sdk_sessions_status", "sdk_sessions", ["status"])

    op.create_table(
        "sdk_decision_records",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("integration_id", sa.UUID(), nullable=False),
        sa.Column("enforcement_receipt_id", sa.UUID(), nullable=True),
        sa.Column("decision", sa.String(), nullable=False),
        sa.Column("reason_code", sa.String(), nullable=True),
        sa.Column("tool_key", sa.String(), nullable=True),
        sa.Column("idempotency_key", sa.String(), nullable=True),
        sa.Column("approval_request_id", sa.UUID(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["session_id"], ["sdk_sessions.id"]),
        sa.ForeignKeyConstraint(["integration_id"], ["sdk_integrations.id"]),
        sa.ForeignKeyConstraint(
            ["enforcement_receipt_id"], ["runtime_enforcement_receipts.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_sdk_decision_idempotency"),
    )
    op.create_index(
        "ix_sdk_decision_records_session_id", "sdk_decision_records", ["session_id"]
    )
    op.create_index(
        "ix_sdk_decision_records_idempotency_key",
        "sdk_decision_records",
        ["idempotency_key"],
    )

    op.create_table(
        "webhook_endpoints",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("secret_hash", sa.String(), nullable=False),
        sa.Column("secret_prefix", sa.String(), nullable=False),
        sa.Column("event_types", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
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
        sa.Column("last_rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("endpoint_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("event_id", sa.String(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["endpoint_id"], ["webhook_endpoints.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_webhook_deliveries_status", "webhook_deliveries", ["status"])

    op.create_table(
        "background_jobs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("job_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("idempotency_key", sa.String(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(), nullable=True),
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
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index("ix_background_jobs_job_type", "background_jobs", ["job_type"])
    op.create_index("ix_background_jobs_status", "background_jobs", ["status"])

    op.create_table(
        "oidc_runtime_bindings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("runtime_identity_id", sa.UUID(), nullable=False),
        sa.Column("issuer", sa.String(), nullable=False),
        sa.Column("audience", sa.String(), nullable=False),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["runtime_identity_id"], ["agent_runtime_identities.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("issuer", "subject", name="uq_oidc_runtime_issuer_subject"),
    )
    op.create_index(
        "ix_oidc_runtime_bindings_issuer", "oidc_runtime_bindings", ["issuer"]
    )
    op.create_index(
        "ix_oidc_runtime_bindings_subject", "oidc_runtime_bindings", ["subject"]
    )


def downgrade() -> None:
    op.drop_table("oidc_runtime_bindings")
    op.drop_table("background_jobs")
    op.drop_table("webhook_deliveries")
    op.drop_table("webhook_endpoints")
    op.drop_table("sdk_decision_records")
    op.drop_table("sdk_sessions")
    op.drop_table("sdk_integrations")
