"""SaaS authentication API — /v1/auth/*."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from rai_gateway.auth import password_reset as password_reset_service
from rai_gateway.auth import service as auth_service
from rai_gateway.auth import verification as verification_service
from rai_gateway.auth.passwords import hash_password, verify_password
from rai_gateway.auth.rate_limit import (
    FORGOT_PASSWORD_LIMIT,
    FORGOT_PASSWORD_WINDOW_SECONDS,
    RESEND_VERIFICATION_LIMIT,
    RESEND_VERIFICATION_WINDOW_SECONDS,
    RESET_PASSWORD_LIMIT,
    RESET_PASSWORD_WINDOW_SECONDS,
    email_auth_rate_limiter,
)
from rai_gateway.core.authorization import require_tenant, require_user
from rai_gateway.core.database import get_db
from rai_gateway.core.errors import ErrorCode, RaiException
from rai_gateway.core.principal import Principal
from rai_gateway.core.tenant_context import TenantContext
from rai_gateway.models.database import AdminCredential, UserAccount

router = APIRouter(prefix="/v1/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3)
    password: str = Field(..., min_length=1)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=10)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8)


class VerifyEmailRequest(BaseModel):
    token: str = Field(..., min_length=10)


class ResendVerificationRequest(BaseModel):
    email: str = Field(..., min_length=3)


class ForgotPasswordRequest(BaseModel):
    email: str = Field(..., min_length=3)


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=10)
    new_password: str = Field(..., min_length=8)


def _client_meta(request: Request) -> tuple[str | None, str | None]:
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    return ip, ua


def _rate_limit_or_429(key: str, *, limit: int, window_seconds: float) -> None:
    result = email_auth_rate_limiter.check(
        key, limit=limit, window_seconds=window_seconds
    )
    if not result.allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "RATE_LIMITED",
                "message": "Too many requests; try again later",
                "retry_after_seconds": max(0, int(result.reset_at - time.time())),
            },
        )


def _set_auth_cookies(response: Response, body: dict[str, Any]) -> None:
    """
    Optionally mirror tokens into HttpOnly cookies for browser clients.

    Phase 20: Browser Session Security
    - Sets HttpOnly cookies for access and refresh tokens
    - Sets readable CSRF token cookie for double-submit pattern
    """
    from rai_gateway.core.config import settings
    from rai_gateway.core.csrf import set_csrf_cookie

    if not settings.auth_set_cookies:
        return

    secure = settings.auth_cookie_secure
    samesite = settings.auth_cookie_samesite

    # Access token (HttpOnly, short-lived)
    response.set_cookie(
        key=settings.auth_access_cookie_name,
        value=body["access_token"],
        httponly=True,
        secure=secure,
        samesite=samesite,
        max_age=settings.auth_access_token_minutes * 60,
        path="/",
    )

    # Refresh token (HttpOnly, longer-lived, restricted path)
    response.set_cookie(
        key=settings.auth_refresh_cookie_name,
        value=body["refresh_token"],
        httponly=True,
        secure=secure,
        samesite=samesite,
        max_age=settings.auth_refresh_token_days * 86400,
        path="/v1/auth",
    )

    # CSRF token (readable by JavaScript for double-submit pattern)
    csrf_token = set_csrf_cookie(response)
    body["csrf_token"] = csrf_token  # Return in response for client to store


def _clear_auth_cookies(response: Response) -> None:
    """Clear auth cookies on logout."""
    from rai_gateway.core.config import settings
    from rai_gateway.core.csrf import CSRFProtection

    response.delete_cookie(settings.auth_access_cookie_name, path="/")
    response.delete_cookie(settings.auth_refresh_cookie_name, path="/v1/auth")
    response.delete_cookie(CSRFProtection.COOKIE_NAME, path="/")


@router.post("/login")
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    ip, ua = _client_meta(request)
    body = auth_service.login_with_password(
        db,
        email=payload.email,
        password=payload.password,
        ip_address=ip,
        user_agent=ua,
    )
    _set_auth_cookies(response, body)
    return body


@router.post("/refresh")
def refresh(
    payload: RefreshRequest | None = None,
    request: Request = None,
    response: Response = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Refresh access token using refresh token.

    Phase 20: Accepts refresh token from:
    1. Cookie (rai_refresh) when auth_set_cookies=true
    2. Request body (refresh_token) for API clients
    """
    from rai_gateway.core.config import settings

    ip, ua = _client_meta(request)

    # Phase 20: Extract refresh token from cookie or body
    refresh_token = None
    if settings.auth_set_cookies and request:
        cookie_refresh = request.cookies.get(settings.auth_refresh_cookie_name)
        if cookie_refresh:
            refresh_token = cookie_refresh

    # Fallback to body if no cookie or cookie auth disabled
    if not refresh_token:
        if not payload or not payload.refresh_token:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "REFRESH_TOKEN_REQUIRED",
                    "message": "Refresh token required in cookie or request body",
                },
            )
        refresh_token = payload.refresh_token

    body = auth_service.refresh_session(
        db,
        refresh_token=refresh_token,
        ip_address=ip,
        user_agent=ua,
    )
    _set_auth_cookies(response, body)
    return body


@router.post("/logout")
def logout(
    response: Response,
    principal: Principal = Depends(require_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    auth_service.logout_session(db, session_id=principal.session_id)
    _clear_auth_cookies(response)
    return {"status": "ok"}


@router.post("/logout-all")
def logout_all(
    response: Response,
    principal: Principal = Depends(require_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    count = auth_service.logout_all_sessions(db, user_id=principal.user_id)
    _clear_auth_cookies(response)
    return {"status": "ok", "revoked": count}


@router.get("/me")
def me(
    principal: Principal = Depends(require_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    user = (
        db.query(UserAccount).filter(UserAccount.user_id == principal.user_id).first()
    )
    if not user:
        raise RaiException(
            error_code=ErrorCode.UNAUTHENTICATED,
            message="User not found",
        )
    result = auth_service.build_me_response(db, user)
    result["session"] = {
        "authentication_assurance": principal.authentication_assurance,
        "acr": principal.acr,
        "amr": list(principal.amr),
        "session_id": principal.session_id,
    }
    return result


@router.get("/context")
def auth_context(
    tenant: TenantContext = Depends(require_tenant),
) -> dict[str, Any]:
    return {
        "roles": list(tenant.roles),
        "permissions": sorted(tenant.permissions),
        "memberships": [str(membership_id) for membership_id in tenant.membership_ids],
    }


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    principal: Principal = Depends(require_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    credential = (
        db.query(AdminCredential)
        .filter(AdminCredential.email == principal.email)
        .first()
    )
    if not credential or not verify_password(
        payload.current_password, credential.password_hash
    ):
        raise RaiException(
            error_code=ErrorCode.NOT_ALLOWED,
            message="Current password is incorrect",
        )
    password_reset_service.validate_new_password(payload.new_password)
    credential.password_hash = hash_password(payload.new_password)
    db.commit()
    auth_service.logout_all_sessions(db, user_id=principal.user_id)
    return {"status": "ok"}


@router.post("/verify-email")
def verify_email(
    payload: VerifyEmailRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return verification_service.verify_email_token(db, raw_token=payload.token)


@router.post("/resend-verification")
def resend_verification(
    payload: ResendVerificationRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    ip, _ = _client_meta(request)
    email = payload.email.strip().lower()
    _rate_limit_or_429(
        f"resend-verify:{email}",
        limit=RESEND_VERIFICATION_LIMIT,
        window_seconds=RESEND_VERIFICATION_WINDOW_SECONDS,
    )
    if ip:
        _rate_limit_or_429(
            f"resend-verify-ip:{ip}",
            limit=RESEND_VERIFICATION_LIMIT,
            window_seconds=RESEND_VERIFICATION_WINDOW_SECONDS,
        )
    return verification_service.resend_verification(db, email=email)


@router.post("/forgot-password")
def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    ip, _ = _client_meta(request)
    email = payload.email.strip().lower()
    _rate_limit_or_429(
        f"forgot-password:{email}",
        limit=FORGOT_PASSWORD_LIMIT,
        window_seconds=FORGOT_PASSWORD_WINDOW_SECONDS,
    )
    if ip:
        _rate_limit_or_429(
            f"forgot-password-ip:{ip}",
            limit=FORGOT_PASSWORD_LIMIT,
            window_seconds=FORGOT_PASSWORD_WINDOW_SECONDS,
        )
    return password_reset_service.forgot_password(db, email=email, ip_address=ip)


@router.post("/reset-password")
def reset_password(
    payload: ResetPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    ip, _ = _client_meta(request)
    if ip:
        _rate_limit_or_429(
            f"reset-password-ip:{ip}",
            limit=RESET_PASSWORD_LIMIT,
            window_seconds=RESET_PASSWORD_WINDOW_SECONDS,
        )
    return password_reset_service.reset_password(
        db, raw_token=payload.token, new_password=payload.new_password
    )
