"""
CSRF Protection for Cookie-Authenticated Requests

Phase 20: Browser Session Security
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Optional

from fastapi import Header, HTTPException, Request

from rai_gateway.core.config import settings


class CSRFProtection:
    """
    CSRF protection for cookie-authenticated mutations.

    Uses the double-submit cookie pattern:
    1. Set a CSRF token in a readable cookie
    2. Require the same token in a custom header for mutations
    3. Verify both match and are signed with server secret
    """

    COOKIE_NAME = "rai_csrf"
    HEADER_NAME = "x-csrf-token"

    @staticmethod
    def generate_token() -> str:
        """Generate a new CSRF token."""
        # Token format: <random>.<signature>
        random_part = secrets.token_urlsafe(32)
        signature = CSRFProtection._sign(random_part)
        return f"{random_part}.{signature}"

    @staticmethod
    def _sign(value: str) -> str:
        """Sign a value with the JWT secret."""
        key = settings.jwt_secret_key.encode("utf-8")
        data = value.encode("utf-8")
        h = hmac.new(key, data, hashlib.sha256)
        return h.hexdigest()[:16]

    @staticmethod
    def verify_token(token: str) -> bool:
        """Verify a CSRF token is valid."""
        if not token or "." not in token:
            return False

        parts = token.rsplit(".", 1)
        if len(parts) != 2:
            return False

        random_part, provided_sig = parts
        expected_sig = CSRFProtection._sign(random_part)

        # Constant-time comparison
        return hmac.compare_digest(provided_sig, expected_sig)


def require_csrf_token(
    request: Request,
    x_csrf_token: Optional[str] = Header(None, alias="x-csrf-token"),
) -> None:
    """
    FastAPI dependency to enforce CSRF protection.

    Required for mutations (POST, PUT, PATCH, DELETE) when using cookie auth.
    Safe methods (GET, HEAD, OPTIONS) are exempt.
    """
    # Skip CSRF for safe methods
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return

    # Skip CSRF if not using cookie auth
    if not settings.auth_set_cookies:
        return

    # Check for CSRF token in cookie
    cookie_token = request.cookies.get(CSRFProtection.COOKIE_NAME)
    if not cookie_token:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "CSRF_TOKEN_MISSING",
                "message": "CSRF token required in cookie",
            },
        )

    # Check for CSRF token in header
    if not x_csrf_token:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "CSRF_HEADER_MISSING",
                "message": "CSRF token required in X-CSRF-Token header",
            },
        )

    # Verify tokens match
    if cookie_token != x_csrf_token:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "CSRF_TOKEN_MISMATCH",
                "message": "CSRF tokens do not match",
            },
        )

    # Verify token is valid
    if not CSRFProtection.verify_token(cookie_token):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "CSRF_TOKEN_INVALID",
                "message": "CSRF token is invalid",
            },
        )


def set_csrf_cookie(response, csrf_token: Optional[str] = None) -> str:
    """
    Set CSRF token cookie. Returns the token value.

    Call this after login/refresh to set the CSRF token.
    """
    from fastapi import Response

    if csrf_token is None:
        csrf_token = CSRFProtection.generate_token()

    if isinstance(response, Response):
        response.set_cookie(
            key=CSRFProtection.COOKIE_NAME,
            value=csrf_token,
            httponly=False,  # Must be readable by JavaScript
            secure=settings.auth_cookie_secure,
            samesite=settings.auth_cookie_samesite,
            max_age=settings.auth_refresh_token_days * 86400,  # Same as refresh token
            path="/",
        )

    return csrf_token
