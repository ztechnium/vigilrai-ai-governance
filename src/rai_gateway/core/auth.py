"""Authentication helpers.

Release 1:
- External apps authenticate with X-API-Key
- Key is stored hashed in DB (plaintext shown only once at issuance)

Later phases:
- JWT/SSO + step-up verification
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, Header
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from rai_gateway.core.config import settings
from rai_gateway.core.database import get_db
from rai_gateway.core.errors import ErrorCode, RaiException
from rai_gateway.models.database import AdminCredential, ApiKey, UserRole


@dataclass(frozen=True)
class ApiKeyContext:
    api_key_id: str
    system_id: str
    scopes: list[str]


@dataclass(frozen=True)
class AdminIdentity:
    email: str
    user_id: str
    roles: list[str]
    # Server-derived IdP assurance (embedded in admin session JWT after MFA)
    authentication_assurance: str | None = None
    acr: str | None = None
    amr: tuple[str, ...] = ()
    auth_time: int | None = None


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_password(password: str, iterations: int = 390000) -> str:
    """Hash password using PBKDF2-HMAC-SHA256."""
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    salt_b64 = base64.b64encode(salt).decode("utf-8")
    digest_b64 = base64.b64encode(digest).decode("utf-8")
    return f"pbkdf2_sha256${iterations}${salt_b64}${digest_b64}"


def verify_password(password: str, encoded_hash: str) -> bool:
    """Verify password against PBKDF2 encoded format."""
    try:
        algorithm, iterations_s, salt_b64, digest_b64 = encoded_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_s)
        salt = base64.b64decode(salt_b64.encode("utf-8"))
        expected = base64.b64decode(digest_b64.encode("utf-8"))
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, iterations
        )
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def create_admin_access_token(
    email: str,
    user_id: str,
    roles: list[str],
    *,
    authentication_assurance: str | None = None,
    acr: str | None = None,
    amr: list[str] | None = None,
    auth_time: int | None = None,
) -> str:
    expires = datetime.now(timezone.utc) + timedelta(
        minutes=settings.admin_session_minutes
    )
    payload = {
        "sub": email,
        "uid": user_id,
        "roles": roles,
        "exp": expires,
        "type": "admin_session",
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


def decode_admin_access_token(token: str) -> AdminIdentity:
    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        if payload.get("type") != "admin_session":
            raise ValueError("Invalid token type")
        email = str(payload.get("sub", ""))
        user_id = str(payload.get("uid", ""))
        roles = [str(role) for role in payload.get("roles", []) if role]
        if not email or not user_id:
            raise ValueError("Missing identity claims")
        # Empty roles are valid for SaaS users whose authority comes from
        # OrganizationMembership, not global UserRole / JWT role claims.
        amr_raw = payload.get("amr") or []
        amr = tuple(str(a) for a in amr_raw) if isinstance(amr_raw, list) else ()
        auth_time = payload.get("auth_time")
        return AdminIdentity(
            email=email,
            user_id=user_id,
            roles=roles,
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
            message="Invalid admin session token",
        ) from err


def get_admin_identity_by_email(db: Session, email: str) -> Optional[AdminIdentity]:
    credential = (
        db.query(AdminCredential).filter(AdminCredential.email == email).first()
    )
    if not credential or not credential.is_active:
        return None
    role_rows = db.query(UserRole).filter(UserRole.user_id == credential.user_id).all()
    # Do not invent a platform "admin" role when the user has none. Tenant
    # authority is derived from OrganizationMembership instead.
    roles = sorted({row.role_id for row in role_rows})
    return AdminIdentity(
        email=credential.email, user_id=credential.user_id, roles=roles
    )


def get_api_key_context(
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    db: Session = Depends(get_db),
) -> Optional[ApiKeyContext]:
    """Validate X-API-Key and return identity context.

    If settings.require_api_key is False, returns None (auth bypass for dev/test).
    """

    if not settings.require_api_key:
        return None

    if not x_api_key:
        raise RaiException(
            error_code=ErrorCode.UNAUTHENTICATED,
            message="Missing API key",
        )

    key_hash = _sha256_hex(x_api_key)
    record = db.query(ApiKey).filter(ApiKey.key_hash == key_hash).first()

    if not record or record.status != "active":
        raise RaiException(
            error_code=ErrorCode.UNAUTHENTICATED,
            message="Invalid API key",
        )

    scopes = record.scopes or []
    if "execute" not in scopes and "*" not in scopes:
        raise RaiException(
            error_code=ErrorCode.NOT_ALLOWED,
            message="API key missing required scope",
            details={"required_scope": "execute"},
        )

    return ApiKeyContext(
        api_key_id=str(record.api_key_id),
        system_id=record.system_id,
        scopes=scopes,
    )
