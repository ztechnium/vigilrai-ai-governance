"""SaaS authentication service — sessions, login, logout, /me."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from rai_gateway.auth.domain import SessionTokens
from rai_gateway.auth.passwords import verify_and_upgrade
from rai_gateway.auth.tokens import (
    create_user_access_token,
    generate_refresh_token,
    hash_token,
)
from rai_gateway.core.config import settings
from rai_gateway.core.errors import ErrorCode, RaiException
from rai_gateway.core.observability import generate_trace_id, log_siem_event
from rai_gateway.governance.domain import MembershipStatus
from rai_gateway.models.auth import AuthSession
from rai_gateway.models.database import AdminCredential, UserAccount, UserRole
from rai_gateway.models.governance import OrganizationMembership
from rai_gateway.models.productization import OrganizationOnboarding


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _platform_roles(db: Session, user_id: str) -> tuple[str, ...]:
    rows = db.query(UserRole).filter(UserRole.user_id == user_id).all()
    return tuple(sorted({row.role_id for row in rows}))


def create_session(
    db: Session,
    *,
    user: UserAccount,
    authentication_assurance: str | None = "password",
    acr: str | None = None,
    amr: tuple[str, ...] = ("pwd",),
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> SessionTokens:
    now = _utcnow()
    refresh_raw = generate_refresh_token()
    session = AuthSession(
        user_id=user.user_id,
        refresh_token_hash=hash_token(refresh_raw),
        expires_at=now + timedelta(days=settings.auth_refresh_token_days),
        last_used_at=now,
        authentication_assurance=authentication_assurance,
        acr=acr,
        amr=",".join(amr) if amr else None,
        ip_hash=hash_token(ip_address) if ip_address else None,
        user_agent=(user_agent or "")[:512] or None,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    platform_roles = _platform_roles(db, user.user_id)
    access = create_user_access_token(
        email=user.email,
        user_id=user.user_id,
        session_id=session.id,
        platform_roles=platform_roles,
        authentication_assurance=authentication_assurance,
        acr=acr,
        amr=list(amr),
        auth_time=int(now.timestamp()),
    )
    return SessionTokens(
        access_token=access,
        refresh_token=refresh_raw,
        session_id=session.id,
        expires_at=session.expires_at,
    )


def login_with_password(
    db: Session,
    *,
    email: str,
    password: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict[str, Any]:
    normalized = email.strip().lower()
    credential = (
        db.query(AdminCredential).filter(AdminCredential.email == normalized).first()
    )
    if not credential or not credential.is_active:
        raise RaiException(
            error_code=ErrorCode.UNAUTHENTICATED,
            message="Invalid email or password",
        )

    user = (
        db.query(UserAccount).filter(UserAccount.user_id == credential.user_id).first()
    )
    if not user or user.status != "active":
        raise RaiException(
            error_code=ErrorCode.UNAUTHENTICATED,
            message="Invalid email or password",
        )

    ok, upgraded = verify_and_upgrade(password, credential.password_hash)
    if not ok:
        raise RaiException(
            error_code=ErrorCode.UNAUTHENTICATED,
            message="Invalid email or password",
        )
    if upgraded:
        credential.password_hash = upgraded
        db.commit()

    tokens = create_session(
        db,
        user=user,
        authentication_assurance="password",
        amr=("pwd",),
        ip_address=ip_address,
        user_agent=user_agent,
    )
    log_siem_event(
        trace_id=generate_trace_id(),
        event_type="auth.login",
        decision="allow",
        metadata={"user_id": user.user_id, "email": user.email},
    )
    return _session_response(db, user, tokens)


def refresh_session(
    db: Session,
    *,
    refresh_token: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict[str, Any]:
    token_hash = hash_token(refresh_token)
    session = (
        db.query(AuthSession)
        .filter(AuthSession.refresh_token_hash == token_hash)
        .first()
    )
    now = _utcnow()
    if session is None:
        raise RaiException(
            error_code=ErrorCode.UNAUTHENTICATED,
            message="Invalid refresh token",
        )

    if session.revoked_at is not None:
        # Refresh-token reuse after rotation/revocation — revoke the family.
        _revoke_user_sessions(db, session.user_id)
        raise RaiException(
            error_code=ErrorCode.UNAUTHENTICATED,
            message="Refresh token reuse detected",
        )

    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= now:
        session.revoked_at = now
        db.commit()
        raise RaiException(
            error_code=ErrorCode.UNAUTHENTICATED,
            message="Refresh token expired",
        )

    user = db.query(UserAccount).filter(UserAccount.user_id == session.user_id).first()
    if not user or user.status != "active":
        session.revoked_at = now
        db.commit()
        raise RaiException(
            error_code=ErrorCode.UNAUTHENTICATED,
            message="User is not active",
        )

    # Rotate: revoke current, issue new session linked to previous.
    session.revoked_at = now
    amr = tuple(p for p in (session.amr or "").split(",") if p)
    tokens = create_session(
        db,
        user=user,
        authentication_assurance=session.authentication_assurance,
        acr=session.acr,
        amr=amr or ("pwd",),
        ip_address=ip_address,
        user_agent=user_agent,
    )
    # Link rotation chain
    new_session = (
        db.query(AuthSession).filter(AuthSession.id == tokens.session_id).one()
    )
    new_session.rotated_from_id = session.id
    db.commit()

    return _session_response(db, user, tokens)


def logout_session(db: Session, *, session_id: UUID | str | None) -> None:
    if not session_id:
        return
    sid = UUID(str(session_id))
    session = db.query(AuthSession).filter(AuthSession.id == sid).first()
    if session and session.revoked_at is None:
        session.revoked_at = _utcnow()
        db.commit()
        log_siem_event(
            trace_id=generate_trace_id(),
            event_type="auth.logout",
            decision="allow",
            metadata={"user_id": session.user_id, "session_id": str(session.id)},
        )


def logout_all_sessions(db: Session, *, user_id: str) -> int:
    count = _revoke_user_sessions(db, user_id)
    log_siem_event(
        trace_id=generate_trace_id(),
        event_type="auth.logout_all",
        decision="allow",
        metadata={"user_id": user_id, "revoked": count},
    )
    return count


def _revoke_user_sessions(db: Session, user_id: str) -> int:
    now = _utcnow()
    sessions = (
        db.query(AuthSession)
        .filter(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .all()
    )
    for session in sessions:
        session.revoked_at = now
    db.commit()
    return len(sessions)


def require_active_session(db: Session, session_id: str | None, user_id: str) -> None:
    """Reject revoked/expired sessions even if the access JWT is still valid."""
    if not session_id:
        raise RaiException(
            error_code=ErrorCode.UNAUTHENTICATED,
            message="Session required",
        )
    session = (
        db.query(AuthSession).filter(AuthSession.id == UUID(str(session_id))).first()
    )
    if session is None or session.user_id != user_id or session.revoked_at is not None:
        raise RaiException(
            error_code=ErrorCode.UNAUTHENTICATED,
            message="Session is not active",
        )
    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= _utcnow():
        raise RaiException(
            error_code=ErrorCode.UNAUTHENTICATED,
            message="Session expired",
        )
    session.last_used_at = _utcnow()
    db.commit()


def build_me_response(db: Session, user: UserAccount) -> dict[str, Any]:
    platform_roles = list(_platform_roles(db, user.user_id))
    memberships = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.user_id == user.user_id,
            OrganizationMembership.status == MembershipStatus.ACTIVE.value,
        )
        .all()
    )
    welcome = (
        db.query(OrganizationOnboarding)
        .filter(OrganizationOnboarding.singleton_key == "default")
        .first()
    )
    roles = sorted({m.role for m in memberships})
    return {
        "user": {
            "id": user.user_id,
            "email": user.email,
            "name": user.name,
            "email_verified": user.email_verified_at is not None,
        },
        "session": {
            "authentication_assurance": None,
            "acr": None,
            "amr": [],
        },
        "roles": roles,
        "memberships": [{"id": str(m.id), "role": m.role} for m in memberships],
        "welcome_completed": (
            welcome.welcome_completed_at is not None if welcome is not None else False
        ),
        "platform_roles": platform_roles,
    }


def _session_response(
    db: Session, user: UserAccount, tokens: SessionTokens
) -> dict[str, Any]:
    me = build_me_response(db, user)
    return {
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "token_type": tokens.token_type,
        "session_id": str(tokens.session_id),
        "expires_at": tokens.expires_at.isoformat(),
        **me,
    }
