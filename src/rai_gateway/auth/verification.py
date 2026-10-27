"""Email verification token lifecycle."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

from sqlalchemy.orm import Session

from rai_gateway.auth.tokens import generate_opaque_token, hash_token
from rai_gateway.core.config import settings
from rai_gateway.core.errors import ErrorCode, RaiException
from rai_gateway.core.observability import generate_trace_id, log_siem_event
from rai_gateway.email.service import EmailService
from rai_gateway.models.auth import EmailVerificationToken
from rai_gateway.models.database import UserAccount
from rai_gateway.models.governance import OrganizationGovernanceProfile


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_verification_token(db: Session, *, user_id: str) -> str:
    """Create a hashed verification token; returns the raw token once."""
    now = _utcnow()
    # Revoke outstanding unused tokens (single active token policy).
    outstanding = (
        db.query(EmailVerificationToken)
        .filter(
            EmailVerificationToken.user_id == user_id,
            EmailVerificationToken.used_at.is_(None),
            EmailVerificationToken.revoked_at.is_(None),
        )
        .all()
    )
    for row in outstanding:
        row.revoked_at = now

    raw = generate_opaque_token()
    db.add(
        EmailVerificationToken(
            user_id=user_id,
            token_hash=hash_token(raw),
            expires_at=now + timedelta(minutes=settings.email_verification_ttl_minutes),
        )
    )
    db.commit()
    return raw


def verification_url(raw_token: str) -> str:
    base = settings.app_public_url.rstrip("/")
    return f"{base}/verify-email?{urlencode({'token': raw_token})}"


def _primary_organization_name(db: Session, user_id: str) -> str:
    del user_id
    profile = (
        db.query(OrganizationGovernanceProfile)
        .filter(OrganizationGovernanceProfile.singleton_key == "default")
        .first()
    )
    if profile is None or not profile.name:
        return "your organization"
    return profile.name


def issue_and_send_verification(
    db: Session,
    *,
    user: UserAccount,
    email_service: EmailService | None = None,
) -> dict[str, Any]:
    """Create token + send verification email. Never rolls back account state."""
    raw = create_verification_token(db, user_id=user.user_id)
    svc = email_service or EmailService(db)
    result = svc.send_email_verification(
        user_id=user.user_id,
        to_address=user.email,
        user_name=user.name,
        organization_name=_primary_organization_name(db, user.user_id),
        verification_url=verification_url(raw),
    )
    return {
        "email_sent": result.success,
        "email_error": None
        if result.success
        else (result.error_message or "send_failed"),
    }


def verify_email_token(db: Session, *, raw_token: str) -> dict[str, Any]:
    token_hash = hash_token(raw_token)
    row = (
        db.query(EmailVerificationToken)
        .filter(EmailVerificationToken.token_hash == token_hash)
        .first()
    )
    now = _utcnow()
    if row is None or row.used_at is not None or row.revoked_at is not None:
        raise RaiException(
            error_code=ErrorCode.NOT_ALLOWED,
            message="Invalid or already used verification token",
        )

    expires_at = row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= now:
        raise RaiException(
            error_code=ErrorCode.NOT_ALLOWED,
            message="Verification token has expired",
        )

    user = db.query(UserAccount).filter(UserAccount.user_id == row.user_id).first()
    if not user or user.status != "active":
        raise RaiException(
            error_code=ErrorCode.NOT_ALLOWED,
            message="Invalid or already used verification token",
        )

    already_verified = user.email_verified_at is not None
    row.used_at = now
    if not already_verified:
        user.email_verified_at = now

    # Revoke other outstanding tokens.
    others = (
        db.query(EmailVerificationToken)
        .filter(
            EmailVerificationToken.user_id == user.user_id,
            EmailVerificationToken.id != row.id,
            EmailVerificationToken.used_at.is_(None),
            EmailVerificationToken.revoked_at.is_(None),
        )
        .all()
    )
    for other in others:
        other.revoked_at = now
    db.commit()

    log_siem_event(
        trace_id=generate_trace_id(),
        event_type="auth.email_verified",
        decision="allow",
        metadata={"user_id": user.user_id, "email": user.email},
    )

    welcome_sent = False
    if user.welcome_email_sent_at is None:
        welcome_sent = _send_welcome_once(db, user)

    return {
        "status": "verified",
        "email": user.email,
        "already_verified": already_verified,
        "welcome_email_sent": welcome_sent,
    }


def _send_welcome_once(db: Session, user: UserAccount) -> bool:
    # Re-check under current session state.
    db.refresh(user)
    if user.welcome_email_sent_at is not None:
        return False
    svc = EmailService(db)
    result = svc.send_welcome_email(
        user_id=user.user_id,
        to_address=user.email,
        user_name=user.name,
        organization_name=_primary_organization_name(db, user.user_id),
    )
    if result.success:
        user.welcome_email_sent_at = _utcnow()
        db.commit()
        return True
    # Verification stays successful even if welcome send fails.
    return False


def resend_verification(
    db: Session,
    *,
    email: str,
    email_service: EmailService | None = None,
) -> dict[str, Any]:
    """Always return a generic response — do not leak account existence."""
    generic = {
        "status": "ok",
        "message": "If an account exists for this email, a verification message has been sent.",
    }
    normalized = email.strip().lower()
    user = db.query(UserAccount).filter(UserAccount.email == normalized).first()
    if not user or user.status != "active":
        return generic
    if user.email_verified_at is not None:
        return generic

    issue_and_send_verification(db, user=user, email_service=email_service)
    return generic
