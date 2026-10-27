"""Runtime authenticator abstraction: API key, OIDC, mTLS seam."""

from __future__ import annotations

import hashlib
import hmac
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from jose import JWTError, jwt
from sqlalchemy.orm import Session

from rai_gateway.core.config import settings
from rai_gateway.identity.resolver import RuntimeAuthorityResolver
from rai_gateway.models.identity import AgentRuntimeIdentity, RuntimeCredential
from rai_gateway.models.productization import OidcRuntimeBinding, SdkIntegration
from rai_gateway.sdk.domain import AuthMethod, SdkErrorCode
from rai_gateway.sdk.errors import SdkError
from rai_gateway.sdk.jwks import ALLOWED_OIDC_ALGORITHMS, JwksCache


@dataclass
class AuthenticatedRuntime:
    """Authenticated runtime principal for the public SDK."""

    runtime_identity: AgentRuntimeIdentity
    credential: RuntimeCredential | None
    auth_method: str
    subject: str | None = None
    claims: dict[str, Any] | None = None
    integration: SdkIntegration | None = None


class RuntimeAuthenticator(ABC):
    @abstractmethod
    def authenticate(
        self, *, secret: str | None, token: str | None
    ) -> AuthenticatedRuntime:
        raise NotImplementedError


class ApiKeyAuthenticator(RuntimeAuthenticator):
    def __init__(self, db: Session) -> None:
        self._db = db
        self._resolver = RuntimeAuthorityResolver(db)

    def authenticate(
        self, *, secret: str | None, token: str | None
    ) -> AuthenticatedRuntime:
        plaintext = secret or token
        if not plaintext:
            raise SdkError(
                SdkErrorCode.AUTHENTICATION_FAILED,
                "Missing runtime credential",
            )
        credential = self._resolver.authenticate_credential(plaintext)
        if not credential:
            raise SdkError(
                SdkErrorCode.AUTHENTICATION_FAILED,
                "Invalid runtime credential",
            )
        identity = (
            self._db.query(AgentRuntimeIdentity)
            .filter(AgentRuntimeIdentity.id == credential.runtime_identity_id)
            .first()
        )
        if not identity:
            raise SdkError(
                SdkErrorCode.RUNTIME_IDENTITY_INACTIVE,
                "Runtime identity not found",
            )
        return AuthenticatedRuntime(
            runtime_identity=identity,
            credential=credential,
            auth_method=AuthMethod.API_KEY.value,
            subject=str(identity.id),
        )


class OIDCAuthenticator(RuntimeAuthenticator):
    """Validate OIDC JWT with mandatory signature verification, then map to WP2 identity.

    Production never accepts unsigned/unverified tokens. JWKS must be resolvable
    for the token issuer (global settings URL and/or injected cache).
    """

    def __init__(
        self,
        db: Session,
        *,
        jwks_cache: JwksCache | None = None,
        jwks_url: str | None = None,
        clock_skew_seconds: int = 60,
    ) -> None:
        self._db = db
        self._jwks = jwks_cache or JwksCache()
        self._jwks_url = jwks_url if jwks_url is not None else settings.oidc_jwks_url
        self._clock_skew = clock_skew_seconds

    def authenticate(
        self, *, secret: str | None, token: str | None
    ) -> AuthenticatedRuntime:
        if not token:
            raise SdkError(
                SdkErrorCode.AUTHENTICATION_FAILED,
                "Missing OIDC bearer token",
            )
        try:
            header = jwt.get_unverified_header(token)
            unverified = jwt.get_unverified_claims(token)
        except JWTError as exc:
            raise SdkError(
                SdkErrorCode.AUTHENTICATION_FAILED,
                f"Invalid OIDC token: {exc}",
            ) from exc

        alg = header.get("alg")
        kid = header.get("kid")
        if not alg or alg == "none" or alg not in ALLOWED_OIDC_ALGORITHMS:
            raise SdkError(
                SdkErrorCode.AUTHENTICATION_FAILED,
                f"OIDC algorithm not allowed: {alg!r}",
            )

        issuer = unverified.get("iss")
        subject = unverified.get("sub")
        audience = unverified.get("aud")
        if not issuer or not subject:
            raise SdkError(
                SdkErrorCode.AUTHENTICATION_FAILED,
                "OIDC token missing issuer or subject",
            )

        binding = (
            self._db.query(OidcRuntimeBinding)
            .filter(
                OidcRuntimeBinding.issuer == issuer,
                OidcRuntimeBinding.subject == subject,
                OidcRuntimeBinding.status == "ACTIVE",
            )
            .first()
        )
        if not binding:
            raise SdkError(
                SdkErrorCode.AUTHENTICATION_FAILED,
                "No OIDC runtime binding for issuer/subject",
            )

        aud_ok = False
        if isinstance(audience, list):
            aud_ok = binding.audience in audience
        else:
            aud_ok = audience == binding.audience
        if not aud_ok:
            raise SdkError(
                SdkErrorCode.AUTHENTICATION_FAILED,
                "OIDC audience mismatch",
            )

        jwks_url = self._jwks_url
        if not jwks_url:
            raise SdkError(
                SdkErrorCode.AUTHENTICATION_FAILED,
                "OIDC JWKS not configured — refusing unverified token",
            )

        claims = self._verify_signature(
            token,
            issuer=issuer,
            audience=binding.audience,
            alg=alg,
            kid=kid,
            jwks_url=jwks_url,
        )
        self._validate_time_claims(claims)

        identity = (
            self._db.query(AgentRuntimeIdentity)
            .filter(AgentRuntimeIdentity.id == binding.runtime_identity_id)
            .first()
        )
        if not identity:
            raise SdkError(
                SdkErrorCode.RUNTIME_IDENTITY_INACTIVE,
                "Bound runtime identity not found",
            )
        return AuthenticatedRuntime(
            runtime_identity=identity,
            credential=None,
            auth_method=AuthMethod.OIDC.value,
            subject=subject,
            claims={
                "iss": issuer,
                "sub": subject,
                "aud": audience,
                "acr": claims.get("acr"),
                "amr": claims.get("amr"),
                "auth_time": claims.get("auth_time"),
            },
        )

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
        cache_key = issuer
        try:
            jwks = self._jwks.resolve(cache_key, jwks_url)
        except Exception as exc:
            raise SdkError(
                SdkErrorCode.AUTHENTICATION_FAILED,
                f"OIDC JWKS unavailable: {exc}",
            ) from exc

        key = self._jwks.find_key(jwks, kid=kid, alg=alg)
        if key is None and kid:
            # Key rotation: refresh once, then fail
            self._jwks.invalidate(cache_key)
            try:
                jwks = self._jwks.resolve(cache_key, jwks_url, force_refresh=True)
            except Exception as exc:
                raise SdkError(
                    SdkErrorCode.AUTHENTICATION_FAILED,
                    f"OIDC JWKS refresh failed: {exc}",
                ) from exc
            key = self._jwks.find_key(jwks, kid=kid, alg=alg)

        if key is None:
            raise SdkError(
                SdkErrorCode.AUTHENTICATION_FAILED,
                "OIDC signing key not found in JWKS",
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
            raise SdkError(
                SdkErrorCode.AUTHENTICATION_FAILED,
                f"OIDC signature validation failed: {exc}",
            ) from exc

    def _validate_time_claims(self, claims: dict[str, Any]) -> None:
        now = int(time.time())
        exp = claims.get("exp")
        nbf = claims.get("nbf")
        iat = claims.get("iat")
        if exp is not None and int(exp) + self._clock_skew < now:
            raise SdkError(
                SdkErrorCode.AUTHENTICATION_FAILED,
                "OIDC token expired",
            )
        if nbf is not None and int(nbf) - self._clock_skew > now:
            raise SdkError(
                SdkErrorCode.AUTHENTICATION_FAILED,
                "OIDC token not yet valid",
            )
        if iat is not None and int(iat) - self._clock_skew > now:
            raise SdkError(
                SdkErrorCode.AUTHENTICATION_FAILED,
                "OIDC token issued in the future",
            )


class MTLSAuthenticator(RuntimeAuthenticator):
    """mTLS seam: map certificate fingerprint/subject to runtime identity.

    Identity headers are only accepted when a trusted ingress proves the
    request crossed a controlled TLS termination boundary. Spoofable public
    headers alone are never trusted.
    """

    def __init__(
        self,
        db: Session,
        *,
        trusted_proxy_mode: bool | None = None,
        trusted_proxy_secret: str | None = None,
        allow_insecure_identity_header: bool | None = None,
    ) -> None:
        self._db = db
        self._trusted_proxy_mode = (
            settings.mtls_trusted_proxy_mode
            if trusted_proxy_mode is None
            else trusted_proxy_mode
        )
        self._trusted_proxy_secret = (
            settings.mtls_trusted_proxy_secret
            if trusted_proxy_secret is None
            else trusted_proxy_secret
        )
        self._allow_insecure = (
            settings.mtls_allow_insecure_identity_header
            if allow_insecure_identity_header is None
            else allow_insecure_identity_header
        )

    def authenticate(
        self,
        *,
        secret: str | None,
        token: str | None,
        proxy_authorization: str | None = None,
    ) -> AuthenticatedRuntime:
        if not self._ingress_trusted(proxy_authorization):
            raise SdkError(
                SdkErrorCode.AUTHENTICATION_FAILED,
                "mTLS identity rejected: untrusted ingress / missing proxy proof",
            )

        cert_identity = token or secret
        if not cert_identity:
            raise SdkError(
                SdkErrorCode.AUTHENTICATION_FAILED,
                "Missing mTLS client identity",
            )
        # Reuse OIDC binding table with issuer="mtls" for certificate subjects
        binding = (
            self._db.query(OidcRuntimeBinding)
            .filter(
                OidcRuntimeBinding.issuer == "mtls",
                OidcRuntimeBinding.subject == cert_identity,
                OidcRuntimeBinding.status == "ACTIVE",
            )
            .first()
        )
        if not binding:
            raise SdkError(
                SdkErrorCode.AUTHENTICATION_FAILED,
                "No mTLS runtime binding for certificate identity",
            )
        identity = (
            self._db.query(AgentRuntimeIdentity)
            .filter(AgentRuntimeIdentity.id == binding.runtime_identity_id)
            .first()
        )
        if not identity:
            raise SdkError(
                SdkErrorCode.RUNTIME_IDENTITY_INACTIVE,
                "Bound runtime identity not found",
            )
        return AuthenticatedRuntime(
            runtime_identity=identity,
            credential=None,
            auth_method=AuthMethod.MTLS.value,
            subject=cert_identity,
        )

    def _ingress_trusted(self, proxy_authorization: str | None) -> bool:
        # Dev-only escape hatch (explicit); never default-on in production.
        if self._allow_insecure:
            return True
        if not self._trusted_proxy_mode:
            return False
        expected = self._trusted_proxy_secret
        if not expected or not proxy_authorization:
            return False
        return hmac.compare_digest(proxy_authorization, expected)


class CompositeRuntimeAuthenticator(RuntimeAuthenticator):
    """Select authenticator from integration auth_method or credential shape."""

    def __init__(
        self,
        db: Session,
        *,
        jwks_cache: JwksCache | None = None,
    ) -> None:
        self._db = db
        self._api_key = ApiKeyAuthenticator(db)
        self._oidc = OIDCAuthenticator(db, jwks_cache=jwks_cache)
        self._mtls = MTLSAuthenticator(db)

    def authenticate(
        self,
        *,
        secret: str | None,
        token: str | None,
        preferred_method: str | None = None,
        mtls_identity: str | None = None,
        mtls_proxy_authorization: str | None = None,
    ) -> AuthenticatedRuntime:
        method = (preferred_method or "").upper()
        if mtls_identity or method == AuthMethod.MTLS.value:
            return self._mtls.authenticate(
                secret=None,
                token=mtls_identity or token,
                proxy_authorization=mtls_proxy_authorization,
            )
        if method == AuthMethod.OIDC.value or (
            token and token.count(".") == 2 and not secret
        ):
            return self._oidc.authenticate(secret=None, token=token)
        return self._api_key.authenticate(secret=secret, token=token)

    def authenticate_for_integration(
        self,
        integration: SdkIntegration,
        *,
        secret: str | None,
        token: str | None,
        mtls_identity: str | None = None,
        mtls_proxy_authorization: str | None = None,
    ) -> AuthenticatedRuntime:
        auth = self.authenticate(
            secret=secret,
            token=token,
            preferred_method=integration.auth_method,
            mtls_identity=mtls_identity,
            mtls_proxy_authorization=mtls_proxy_authorization,
        )
        if auth.runtime_identity.id != integration.runtime_identity_id:
            raise SdkError(
                SdkErrorCode.AUTHENTICATION_FAILED,
                "Credential does not match integration runtime identity",
            )
        auth.integration = integration
        return auth


def hash_webhook_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()
