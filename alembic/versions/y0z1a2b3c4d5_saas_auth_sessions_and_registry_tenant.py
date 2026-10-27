"""saas_auth_sessions_and_registry_tenant

Revision ID: y0z1a2b3c4d5
Revises: x9y0z1a2b3c4
Create Date: 2026-09-21 23:00:00.000000

SaaS auth session/email token tables and user email_verified_at.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "y0z1a2b3c4d5"
down_revision: Union[str, None] = "x9y0z1a2b3c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())
    user_columns = {c["name"] for c in inspector.get_columns("users")}

    if "email_verified_at" not in user_columns:
        op.add_column(
            "users",
            sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        )

    if "auth_sessions" not in existing_tables:
        op.create_table(
            "auth_sessions",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "user_id", sa.String(), sa.ForeignKey("users.user_id"), nullable=False
            ),
            sa.Column("refresh_token_hash", sa.String(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=True,
            ),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "rotated_from_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("auth_sessions.id"),
                nullable=True,
            ),
            sa.Column("ip_hash", sa.String(), nullable=True),
            sa.Column("user_agent", sa.Text(), nullable=True),
            sa.Column("authentication_assurance", sa.String(), nullable=True),
            sa.Column("acr", sa.String(), nullable=True),
            sa.Column("amr", sa.String(), nullable=True),
        )
        op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
        op.create_index(
            "ix_auth_sessions_refresh_token_hash",
            "auth_sessions",
            ["refresh_token_hash"],
            unique=True,
        )
        op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])
        op.create_index("ix_auth_sessions_revoked_at", "auth_sessions", ["revoked_at"])

    if "email_verification_tokens" not in existing_tables:
        op.create_table(
            "email_verification_tokens",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "user_id", sa.String(), sa.ForeignKey("users.user_id"), nullable=False
            ),
            sa.Column("token_hash", sa.String(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=True,
            ),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index(
            "ix_email_verification_tokens_user_id",
            "email_verification_tokens",
            ["user_id"],
        )
        op.create_index(
            "ix_email_verification_tokens_token_hash",
            "email_verification_tokens",
            ["token_hash"],
            unique=True,
        )
        op.create_index(
            "ix_email_verification_tokens_expires_at",
            "email_verification_tokens",
            ["expires_at"],
        )

    if "password_reset_tokens" not in existing_tables:
        op.create_table(
            "password_reset_tokens",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "user_id", sa.String(), sa.ForeignKey("users.user_id"), nullable=False
            ),
            sa.Column("token_hash", sa.String(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=True,
            ),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index(
            "ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"]
        )
        op.create_index(
            "ix_password_reset_tokens_token_hash",
            "password_reset_tokens",
            ["token_hash"],
            unique=True,
        )
        op.create_index(
            "ix_password_reset_tokens_expires_at",
            "password_reset_tokens",
            ["expires_at"],
        )

    if "email_delivery_attempts" not in existing_tables:
        op.create_table(
            "email_delivery_attempts",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "user_id", sa.String(), sa.ForeignKey("users.user_id"), nullable=True
            ),
            sa.Column("email", sa.String(), nullable=False),
            sa.Column("template_key", sa.String(), nullable=False),
            sa.Column("provider", sa.String(), nullable=True),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=True,
            ),
            sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index(
            "ix_email_delivery_attempts_user_id",
            "email_delivery_attempts",
            ["user_id"],
        )
        op.create_index(
            "ix_email_delivery_attempts_email", "email_delivery_attempts", ["email"]
        )
        op.create_index(
            "ix_email_delivery_attempts_template_key",
            "email_delivery_attempts",
            ["template_key"],
        )
        op.create_index(
            "ix_email_delivery_attempts_status",
            "email_delivery_attempts",
            ["status"],
        )


def downgrade() -> None:
    op.drop_table("email_delivery_attempts")
    op.drop_table("password_reset_tokens")
    op.drop_table("email_verification_tokens")
    op.drop_table("auth_sessions")
    op.drop_column("users", "email_verified_at")
