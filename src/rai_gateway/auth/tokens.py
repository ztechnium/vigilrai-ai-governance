"""Access/refresh token helpers for SaaS user sessions."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from jose import JWTError, jwt

from rai_gateway.core.config import settings
from rai_gateway.core.errors import ErrorCode, RaiException
from rai_gateway.core.principal import Principal

USER_SESSION_TYPE = "user_session"


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def generate_opaque_token() -> str:
    return secrets.token_urlsafe(32)


def create_user_access_token(
    *,
    email: str,
    user_id: str,
    session_id: UUID,
    platform_roles: list[str] | tuple[str, ...] = (),
    authentication_assurance: str | None = None,
    acr: str | None = None,
    amr: list[str] | tuple[str, ...] | None = None,
    auth_time: int | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=settings.auth_access_token_minutes)
    payload: dict[str, Any] = {
        "sub": email,
        "uid": user_id,
        "sid": str(session_id),
        "roles": list(platform_roles),
        "iat": now,
        "exp": expires,
        "type": USER_SESSION_TYPE,
    }
    if authentication_assurance:
        payload["authentication_assurance"] = authentication_assurance
    if acr:
        payload["acr"] = acr
    if amr:
        payload["amr"] = list(amr)
    if auth_time is not None:
        payload["auth_time"] = int(auth_time)
    return jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )


def decode_user_access_token(token: str) -> Principal:
    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        if payload.get("type") != USER_SESSION_TYPE:
            raise ValueError("Invalid token type")
        email = str(payload.get("sub", ""))
        user_id = str(payload.get("uid", ""))
        session_id = str(payload.get("sid", "")) or None
        roles = tuple(str(role) for role in payload.get("roles", []) if role)
        if not email or not user_id:
            raise ValueError("Missing identity claims")
        amr_raw = payload.get("amr") or []
        amr = tuple(str(a) for a in amr_raw) if isinstance(amr_raw, list) else ()
        auth_time = payload.get("auth_time")
        return Principal(
            user_id=user_id,
            email=email,
            session_id=session_id,
            platform_roles=roles,
            authentication_assurance=(
                str(payload["authentication_assurance"])
                if payload.get("authentication_assurance")
                else None
            ),
            acr=str(payload["acr"]) if payload.get("acr") else None,
            amr=amr,
            auth_time=int(auth_time) if auth_time is not None else None,
        )
    except (JWTError, ValueError) as err:
        raise RaiException(
            error_code=ErrorCode.UNAUTHENTICATED,
            message="Invalid session token",
        ) from err
