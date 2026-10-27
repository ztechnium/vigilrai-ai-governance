"""Admin IdP OIDC login / step-up — server-derived ACR/AMR assurance."""

from __future__ import annotations

import base64
import time
import uuid

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwt

from rai_gateway.approval.api import _server_approver_context
from rai_gateway.approval.authorization import (
    STEP_UP_VERIFIED,
    ApproverAuthorizationService,
)
from rai_gateway.approval.domain import ApprovalDenialCode
from rai_gateway.approval.errors import ApprovalDeniedError
from rai_gateway.core.admin_oidc import AdminOidcVerifier
from rai_gateway.core.auth import (
    create_admin_access_token,
    decode_admin_access_token,
    hash_password,
)
from rai_gateway.core.config import settings
from rai_gateway.core.errors import RaiException
from rai_gateway.models.database import AdminCredential, UserAccount, UserRole
from rai_gateway.sdk.jwks import JwksCache
from rai_gateway.services.admin_console import _issue_admin_session_from_oidc


def _rsa_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_numbers = private_key.public_key().public_numbers()

    def _b64int(val: int) -> str:
        raw = val.to_bytes((val.bit_length() + 7) // 8, "big")
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    jwk = {
        "kty": "RSA",
        "kid": "admin-idp-1",
        "use": "sig",
        "alg": "RS256",
        "n": _b64int(public_numbers.n),
        "e": _b64int(public_numbers.e),
    }
    return private_pem, {"keys": [jwk]}


def _configure_admin_oidc(monkeypatch, *, jwks: dict):
    monkeypatch.setattr(settings, "admin_oidc_issuer", "https://idp.example.com")
    monkeypatch.setattr(settings, "admin_oidc_audience", "rai-admin")
    monkeypatch.setattr(settings, "admin_oidc_jwks_url", "https://idp.example.com/jwks")
    monkeypatch.setattr(settings, "approval_minimum_acr", None)
    monkeypatch.setattr(settings, "approval_required_amr", None)
    monkeypatch.setattr(settings, "approval_max_auth_age_seconds", None)
    cache = JwksCache(fetcher=lambda _url: jwks)
    return cache


def _sign_id_token(private_pem: bytes, claims: dict) -> str:
    return jwt.encode(
        claims,
        private_pem,
        algorithm="RS256",
        headers={"kid": "admin-idp-1"},
    )


def _ensure_admin_user(db_session, email: str = "approver@example.com"):
    from rai_gateway.services.admin_console import _ensure_default_rbac_seed

    _ensure_default_rbac_seed(db_session)

    user_id = f"user-{uuid.uuid4().hex[:8]}"
    db_session.add(
        UserAccount(
            user_id=user_id,
            email=email,
            name="Approver",
            status="active",
        )
    )
    # Flush parent first — otherwise SQLAlchemy may insert AdminCredential
    # before UserAccount and trip admin_credentials_user_id_fkey.
    db_session.flush()
    db_session.add(
        AdminCredential(
            email=email,
            password_hash=hash_password("unused"),
            user_id=user_id,
            is_active=True,
        )
    )
    db_session.add(UserRole(user_id=user_id, role_id="admin"))
    db_session.commit()
    return email


def test_admin_oidc_embeds_mfa_assurance(db_session, monkeypatch):
    private_pem, jwks = _rsa_keypair()
    cache = _configure_admin_oidc(monkeypatch, jwks=jwks)
    email = _ensure_admin_user(db_session)

    now = int(time.time())
    token = _sign_id_token(
        private_pem,
        {
            "iss": "https://idp.example.com",
            "aud": "rai-admin",
            "sub": "idp-sub-1",
            "email": email,
            "acr": "urn:mfa",
            "amr": ["pwd", "otp"],
            "auth_time": now,
            "iat": now,
            "exp": now + 600,
        },
    )
    claims = AdminOidcVerifier(jwks_cache=cache).verify_id_token(token)
    assert claims.email == email
    assert claims.authentication_assurance == STEP_UP_VERIFIED
    assert claims.acr == "urn:mfa"
    assert "otp" in claims.amr

    import rai_gateway.core.admin_oidc as admin_oidc_mod

    class _Verifier(AdminOidcVerifier):
        def __init__(self) -> None:
            super().__init__(jwks_cache=cache)

    monkeypatch.setattr(admin_oidc_mod, "AdminOidcVerifier", _Verifier)
    session = _issue_admin_session_from_oidc(db_session, token)
    identity = decode_admin_access_token(session["access_token"])
    assert identity.authentication_assurance == STEP_UP_VERIFIED
    assert identity.acr == "urn:mfa"
    assert set(identity.amr) >= {"pwd", "otp"}
    assert identity.auth_time == now


def test_admin_oidc_rejects_disallowed_alg(monkeypatch):
    _private_pem, jwks = _rsa_keypair()
    cache = _configure_admin_oidc(monkeypatch, jwks=jwks)
    now = int(time.time())
    # Manually craft header with alg=none (jose may refuse to encode it)
    header = (
        base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}')
        .rstrip(b"=")
        .decode("ascii")
    )
    payload = (
        base64.urlsafe_b64encode(
            (
                '{"iss":"https://idp.example.com","aud":"rai-admin","sub":"x",'
                f'"email":"a@b.com","exp":{now + 60}}}'
            ).encode()
        )
        .rstrip(b"=")
        .decode("ascii")
    )
    token = f"{header}.{payload}."
    with pytest.raises(RaiException):
        AdminOidcVerifier(jwks_cache=cache).verify_id_token(token)


def test_admin_oidc_rejects_when_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "admin_oidc_issuer", None)
    monkeypatch.setattr(settings, "admin_oidc_audience", None)
    monkeypatch.setattr(settings, "admin_oidc_jwks_url", None)
    with pytest.raises(RaiException):
        AdminOidcVerifier().verify_id_token("not.a.token")


def test_shared_secret_step_up_disabled_by_default(monkeypatch):
    monkeypatch.setattr(settings, "allow_shared_secret_step_up", False)
    monkeypatch.setattr(settings, "step_up_token", "secret")
    ctx = _server_approver_context(
        actor="a@example.com",
        role="admin",
        x_step_up_token="secret",
    )
    assert ctx.authentication_assurance is None


def test_shared_secret_step_up_escape_hatch(monkeypatch):
    monkeypatch.setattr(settings, "allow_shared_secret_step_up", True)
    monkeypatch.setattr(settings, "step_up_token", "secret")
    ctx = _server_approver_context(
        actor="a@example.com",
        role="admin",
        x_step_up_token="secret",
    )
    assert ctx.authentication_assurance == STEP_UP_VERIFIED


def test_session_jwt_assurance_satisfies_critical(db_session, monkeypatch):
    monkeypatch.setattr(settings, "approval_minimum_acr", None)
    monkeypatch.setattr(settings, "approval_required_amr", None)
    monkeypatch.setattr(settings, "approval_max_auth_age_seconds", None)

    token = create_admin_access_token(
        email="approver@example.com",
        user_id="u1",
        roles=["admin"],
        authentication_assurance=STEP_UP_VERIFIED,
        acr="urn:mfa",
        amr=["otp", "pwd"],
        auth_time=int(time.time()),
    )
    identity = decode_admin_access_token(token)
    ctx = _server_approver_context(
        actor=identity.email,
        role="admin",
        principal=identity,
    )
    assert ctx.authentication_assurance == STEP_UP_VERIFIED

    request = type(
        "R",
        (),
        {"risk_tier": "CRITICAL", "initiating_principal": "other"},
    )()
    ApproverAuthorizationService(db_session).authorize_approve(request, ctx)


def test_password_session_without_assurance_denied_for_critical(
    db_session, monkeypatch
):
    monkeypatch.setattr(settings, "approval_minimum_acr", None)
    monkeypatch.setattr(settings, "approval_required_amr", None)
    monkeypatch.setattr(settings, "approval_max_auth_age_seconds", None)
    monkeypatch.setattr(settings, "allow_shared_secret_step_up", False)

    token = create_admin_access_token(
        email="approver@example.com",
        user_id="u1",
        roles=["admin"],
    )
    identity = decode_admin_access_token(token)
    ctx = _server_approver_context(
        actor=identity.email,
        role="admin",
        principal=identity,
        x_step_up_token="ignored-secret",
    )
    request = type(
        "R",
        (),
        {"risk_tier": "CRITICAL", "initiating_principal": "other"},
    )()
    with pytest.raises(ApprovalDeniedError) as exc:
        ApproverAuthorizationService(db_session).authorize_approve(request, ctx)
    assert exc.value.reason == ApprovalDenialCode.APPROVAL_STEP_UP_REQUIRED.value


def test_derive_assurance_from_amr():
    assert (
        AdminOidcVerifier.derive_assurance(acr=None, amr=("pwd", "otp"))
        == STEP_UP_VERIFIED
    )
    assert AdminOidcVerifier.derive_assurance(acr=None, amr=("pwd",)) is None
