"""SaaS human authentication models."""

from __future__ import annotations

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from rai_gateway.models.database import Base


class AuthSession(Base):
    """Rotating refresh-session store for SaaS human authentication."""

    __tablename__ = "auth_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, ForeignKey("users.user_id"), nullable=False, index=True)
    refresh_token_hash = Column(String, nullable=False, unique=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True, index=True)
    rotated_from_id = Column(
        UUID(as_uuid=True), ForeignKey("auth_sessions.id"), nullable=True
    )
    ip_hash = Column(String, nullable=True)
    user_agent = Column(Text, nullable=True)
    authentication_assurance = Column(String, nullable=True)
    acr = Column(String, nullable=True)
    amr = Column(String, nullable=True)  # comma-separated


class EmailVerificationToken(Base):
    """Hashed, single-use email verification tokens."""

    __tablename__ = "email_verification_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, ForeignKey("users.user_id"), nullable=False, index=True)
    token_hash = Column(String, nullable=False, unique=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    used_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)


class PasswordResetToken(Base):
    """Hashed, single-use password reset tokens."""

    __tablename__ = "password_reset_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, ForeignKey("users.user_id"), nullable=False, index=True)
    token_hash = Column(String, nullable=False, unique=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    used_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    requested_ip_hash = Column(String, nullable=True)


class EmailDeliveryAttempt(Base):
    """Observability for transactional email sends (provider-agnostic)."""

    __tablename__ = "email_delivery_attempts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, ForeignKey("users.user_id"), nullable=True, index=True)
    email = Column(String, nullable=False, index=True)
    template_key = Column(String, nullable=False, index=True)
    provider = Column(String, nullable=True)
    status = Column(String, nullable=False, index=True)  # QUEUED|SENT|FAILED
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    sent_at = Column(DateTime(timezone=True), nullable=True)
