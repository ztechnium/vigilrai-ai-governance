"""Enterprise IdP verification for admin console sessions (human MFA / step-up).

Verifies IdP ID tokens with mandatory JWKS signature checks, then maps ACR/AMR/
auth_time into the RAI admin session JWT. Shared-secret step-up is not MFA.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from jose import JWTError, jwt

from rai_gateway.core.config import settings
from rai_gateway.core.errors import ErrorCode, RaiException
from rai_gateway.sdk.jwks import ALLOWED_OIDC_ALGORITHMS, JwksCache

# Keep in sync with approval.authorization.STEP_UP_VERIFIED
_STEP_UP_VERIFIED = "step_up_verified"

# OIDC AMR values commonly indicating multi-factor / step-up authentication.
_MFA_AMR_MARKERS = frozenset(
    {"mfa", "otp", "totp", "hwk", "swk", "sms", "phr", "pop", "sc", "face", "fpt"}
)


@dataclass(frozen=True)
class VerifiedHumanClaims:
    """Server-verified human IdP claims used for admin session / step-up."""

    email: str
    subject: str
    issuer: str
    acr: str | None
    amr: tuple[str, ...]
    auth_time: int | None
    authentication_assurance: str | None


class AdminOidcVerifier:
    """Fail-closed verification of enterprise IdP tokens for human admins."""

    def __init__(
        self,
        *,
        jwks_cache: JwksCache | None = None,
        clock_skew_seconds: int = 60,
    ) -> None:
        self._jwks = jwks_cache or JwksCache()
        self._clock_skew = clock_skew_seconds

    def verify_id_token(self, id_token: str) -> VerifiedHumanClaims:
        issuer = (settings.admin_oidc_issuer or "").strip()
        audience = (settings.admin_oidc_audience or "").strip()
        jwks_url = (
            settings.admin_oidc_jwks_url or settings.oidc_jwks_url or ""
        ).strip()

        if not issuer or not audience or not jwks_url:
            raise RaiException(
                error_code=ErrorCode.UNAUTHENTICATED,
                message="Admin OIDC is not configured (issuer/audience/JWKS required)",
            )

        try:
            header = jwt.get_unverified_header(id_token)
        except JWTError as exc:
            raise RaiException(
                error_code=ErrorCode.UNAUTHENTICATED,
                message=f"Invalid IdP token header: {exc}",
            ) from exc

        alg = header.get("alg")
        kid = header.get("kid")
        if not alg or alg == "none" or alg not in ALLOWED_OIDC_ALGORITHMS:
            raise RaiException(
                error_code=ErrorCode.UNAUTHENTICATED,
                message=f"IdP algorithm not allowed: {alg!r}",
            )

        claims = self._verify_signature(
            id_token,
            issuer=issuer,
            audience=audience,
            alg=alg,
            kid=kid,
            jwks_url=jwks_url,
        )
        self._validate_time_claims(claims)

        email = self._extract_email(claims)
        subject = str(claims.get("sub") or "").strip()
        if not email or not subject:
            raise RaiException(
                error_code=ErrorCode.UNAUTHENTICATED,
                message="IdP token missing email or subject",
            )

        acr = str(claims["acr"]) if claims.get("acr") is not None else None
        amr = self._normalize_amr(claims.get("amr"))
        auth_time = claims.get("auth_time")
        if auth_time is None and claims.get("iat") is not None:
            auth_time = int(claims["iat"])

        assurance = self.derive_assurance(acr=acr, amr=amr)
        return VerifiedHumanClaims(
            email=email.lower(),
            subject=subject,
            issuer=issuer,
            acr=acr,
            amr=amr,
            auth_time=int(auth_time) if auth_time is not None else None,
            authentication_assurance=assurance,
        )

    @staticmethod
    def derive_assurance(*, acr: str | None, amr: tuple[str, ...]) -> str | None:
        """Map verified IdP MFA signals to RAI step-up assurance."""
        amr_lower = {a.lower() for a in amr}
        if amr_lower & _MFA_AMR_MARKERS:
            return _STEP_UP_VERIFIED
        min_acr = (settings.approval_minimum_acr or "").strip()
        if min_acr and acr == min_acr:
            return _STEP_UP_VERIFIED
        if acr and "mfa" in acr.lower():
            return _STEP_UP_VERIFIED
        return None

    def _verify_signature(
        self,
        token: str,
        *,
        issuer: str,
        audience: str,
        alg: str,
        kid: str | None,
        jwks_url: str,
    ) -> dict[str, Any]:
        cache_key = f"admin-oidc:{issuer}"
        try:
            jwks = self._jwks.resolve(cache_key, jwks_url)
        except Exception as exc:
            raise RaiException(
                error_code=ErrorCode.UNAUTHENTICATED,
                message=f"IdP JWKS unavailable: {exc}",
            ) from exc

        key = self._jwks.find_key(jwks, kid=kid, alg=alg)
        if key is None and kid:
            self._jwks.invalidate(cache_key)
            try:
                jwks = self._jwks.resolve(cache_key, jwks_url, force_refresh=True)
            except Exception as exc:
                raise RaiException(
                    error_code=ErrorCode.UNAUTHENTICATED,
                    message=f"IdP JWKS refresh failed: {exc}",
                ) from exc
            key = self._jwks.find_key(jwks, kid=kid, alg=alg)

        if key is None:
            raise RaiException(
                error_code=ErrorCode.UNAUTHENTICATED,
                message="IdP signing key not found in JWKS",
            )

        try:
            return jwt.decode(
                token,
                key,
                algorithms=[alg],
                audience=audience,
                issuer=issuer,
                options={
                    "verify_at_hash": False,
                    "leeway": self._clock_skew,
                },
            )
        except JWTError as exc:
            raise RaiException(
                error_code=ErrorCode.UNAUTHENTICATED,
                message=f"IdP signature validation failed: {exc}",
            ) from exc

    def _validate_time_claims(self, claims: dict[str, Any]) -> None:
        now = int(time.time())
        exp = claims.get("exp")
        nbf = claims.get("nbf")
        if exp is not None and int(exp) + self._clock_skew < now:
            raise RaiException(
                error_code=ErrorCode.UNAUTHENTICATED,
                message="IdP token expired",
            )
        if nbf is not None and int(nbf) - self._clock_skew > now:
            raise RaiException(
                error_code=ErrorCode.UNAUTHENTICATED,
                message="IdP token not yet valid",
            )

    @staticmethod
    def _extract_email(claims: dict[str, Any]) -> str:
        claim_name = (settings.admin_oidc_email_claim or "email").strip() or "email"
        value = claims.get(claim_name)
        if value:
            return str(value).strip()
        for fallback in ("email", "preferred_username", "upn"):
            if claims.get(fallback):
                return str(claims[fallback]).strip()
        return ""

    @staticmethod
    def _normalize_amr(raw: Any) -> tuple[str, ...]:
        if raw is None:
            return ()
        if isinstance(raw, str):
            return (raw,) if raw else ()
        if isinstance(raw, list):
            return tuple(str(item) for item in raw if item)
        return ()
