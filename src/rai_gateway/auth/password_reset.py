"""Forgot / reset password flows."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

from sqlalchemy.orm import Session

from rai_gateway.auth.passwords import hash_password
from rai_gateway.auth.service import logout_all_sessions
from rai_gateway.auth.tokens import generate_opaque_token, hash_token
from rai_gateway.core.config import settings
from rai_gateway.core.errors import ErrorCode, RaiException
from rai_gateway.core.observability import generate_trace_id, log_siem_event
from rai_gateway.email.service import EmailService
from rai_gateway.models.auth import PasswordResetToken
from rai_gateway.models.database import AdminCredential, UserAccount


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


_GENERIC_FORGOT = {
    "status": "ok",
    "message": (
        "If an account exists for this email, password reset instructions have been sent."
    ),
}


def reset_url(raw_token: str) -> str:
    base = settings.app_public_url.rstrip("/")
    return f"{base}/reset-password?{urlencode({'token': raw_token})}"


def validate_new_password(password: str) -> None:
    if len(password) < 8:
        raise RaiException(
            error_code=ErrorCode.INVALID_REQUEST,
            message="Password must be at least 8 characters",
        )


def forgot_password(
    db: Session,
    *,
    email: str,
    ip_address: str | None = None,
    email_service: EmailService | None = None,
) -> dict[str, Any]:
    normalized = email.strip().lower()
    credential = (
        db.query(AdminCredential).filter(AdminCredential.email == normalized).first()
    )
    if not credential or not credential.is_active:
        return dict(_GENERIC_FORGOT)

    user = (
        db.query(UserAccount).filter(UserAccount.user_id == credential.user_id).first()
    )
    if not user or user.status != "active":
        return dict(_GENERIC_FORGOT)

    now = _utcnow()
    outstanding = (
        db.query(PasswordResetToken)
        .filter(
            PasswordResetToken.user_id == user.user_id,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.revoked_at.is_(None),
        )
        .all()
    )
    for row in outstanding:
        row.revoked_at = now

    raw = generate_opaque_token()
    db.add(
        PasswordResetToken(
            user_id=user.user_id,
            token_hash=hash_token(raw),
            expires_at=now + timedelta(minutes=settings.password_reset_ttl_minutes),
            requested_ip_hash=hash_token(ip_address) if ip_address else None,
        )
    )
    db.commit()

    svc = email_service or EmailService(db)
    result = svc.send_password_reset(
        user_id=user.user_id,
        to_address=user.email,
        user_name=user.name,
        reset_url=reset_url(raw),
    )
    log_siem_event(
        trace_id=generate_trace_id(),
        event_type="auth.password_reset_requested",
        decision="allow",
        metadata={
            "user_id": user.user_id,
            "email_sent": result.success,
        },
    )
    return dict(_GENERIC_FORGOT)


def reset_password(
    db: Session,
    *,
    raw_token: str,
    new_password: str,
) -> dict[str, Any]:
    validate_new_password(new_password)
    token_hash = hash_token(raw_token)
    row = (
        db.query(PasswordResetToken)
        .filter(PasswordResetToken.token_hash == token_hash)
        .first()
    )
    now = _utcnow()
    if row is None or row.used_at is not None or row.revoked_at is not None:
        raise RaiException(
            error_code=ErrorCode.NOT_ALLOWED,
            message="Invalid or already used reset token",
        )

    expires_at = row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= now:
        raise RaiException(
            error_code=ErrorCode.NOT_ALLOWED,
            message="Reset token has expired",
        )

    user = db.query(UserAccount).filter(UserAccount.user_id == row.user_id).first()
    credential = (
        db.query(AdminCredential).filter(AdminCredential.user_id == row.user_id).first()
    )
    if not user or not credential or user.status != "active":
        raise RaiException(
            error_code=ErrorCode.NOT_ALLOWED,
            message="Invalid or already used reset token",
        )

    credential.password_hash = hash_password(new_password)
    row.used_at = now

    others = (
        db.query(PasswordResetToken)
        .filter(
            PasswordResetToken.user_id == user.user_id,
            PasswordResetToken.id != row.id,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.revoked_at.is_(None),
        )
        .all()
    )
    for other in others:
        other.revoked_at = now
    db.commit()

    logout_all_sessions(db, user_id=user.user_id)
    log_siem_event(
        trace_id=generate_trace_id(),
        event_type="auth.password_reset_completed",
        decision="allow",
        metadata={"user_id": user.user_id},
    )
    return {"status": "ok"}
