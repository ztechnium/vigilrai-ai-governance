"""Password reset flow tests."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from rai_gateway.auth.passwords import hash_password, verify_password
from rai_gateway.auth.rate_limit import email_auth_rate_limiter
from rai_gateway.auth.tokens import hash_token
from rai_gateway.core.database import get_db
from rai_gateway.email.smtp import MemoryEmailTransport, set_test_email_transport
from rai_gateway.main import app
from rai_gateway.models.auth import AuthSession, PasswordResetToken
from rai_gateway.models.database import AdminCredential, UserAccount
from rai_gateway.public_product.rate_limit import registration_rate_limiter


@pytest.fixture()
def memory_mail():
    transport = MemoryEmailTransport()
    set_test_email_transport(transport)
    try:
        yield transport
    finally:
        set_test_email_transport(None)


@pytest.fixture()
def client(db_session, db_engine, memory_mail):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    registration_rate_limiter._hits.clear()
    email_auth_rate_limiter._hits.clear()
    c = TestClient(app)
    try:
        yield c
    finally:
        app.dependency_overrides.pop(get_db, None)


def _register(client: TestClient, db_session) -> dict:
    """Create a signed-in account without public company registration."""
    suffix = uuid.uuid4().hex[:8]
    email = f"ada-{suffix}@example.com"
    user_id = f"u-{suffix}"
    password = "SecurePass123!"
    db_session.add(
        UserAccount(
            user_id=user_id,
            email=email,
            name="Ada Lovelace",
            status="active",
            email_verified_at=datetime.now(timezone.utc),
        )
    )
    db_session.add(
        AdminCredential(
            email=email,
            user_id=user_id,
            password_hash=hash_password(password),
            is_active=True,
        )
    )
    db_session.commit()
    login = client.post("/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    return {
        "user": {"email": email, "user_id": user_id},
        "access_token": login.json()["access_token"],
    }


def test_forgot_password_same_response_known_and_unknown(
    client, db_session, memory_mail
):
    body = _register(client, db_session)
    memory_mail.sent.clear()

    known = client.post(
        "/v1/auth/forgot-password", json={"email": body["user"]["email"]}
    )
    unknown = client.post(
        "/v1/auth/forgot-password",
        json={"email": f"missing-{uuid.uuid4().hex[:6]}@example.com"},
    )
    assert known.status_code == 200
    assert unknown.status_code == 200
    assert known.json()["message"] == unknown.json()["message"]
    assert len(memory_mail.sent) == 1
    assert "Reset your RAI Control Plane password" in memory_mail.sent[0].subject
    assert "reset-password?token=" in memory_mail.sent[0].text_body


def test_password_reset_changes_password_and_revokes_sessions(
    client, db_session, memory_mail
):
    body = _register(client, db_session)
    email = body["user"]["email"]
    user_id = body["user"]["user_id"]
    old_access = body["access_token"]

    # Ensure a session exists
    sessions_before = (
        db_session.query(AuthSession)
        .filter(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .count()
    )
    assert sessions_before >= 1

    memory_mail.sent.clear()
    forgot = client.post("/v1/auth/forgot-password", json={"email": email})
    assert forgot.status_code == 200

    row = (
        db_session.query(PasswordResetToken)
        .filter(PasswordResetToken.user_id == user_id)
        .order_by(PasswordResetToken.created_at.desc())
        .first()
    )
    assert row is not None
    # Recover raw token from the outbound email URL
    text = memory_mail.sent[0].text_body
    raw = text.split("token=")[1].split()[0].strip()
    assert row.token_hash == hash_token(raw)

    reset = client.post(
        "/v1/auth/reset-password",
        json={"token": raw, "new_password": "BrandNewPass456!"},
    )
    assert reset.status_code == 200, reset.text

    cred = (
        db_session.query(AdminCredential).filter(AdminCredential.email == email).one()
    )
    db_session.refresh(cred)
    assert verify_password("BrandNewPass456!", cred.password_hash)
    assert not verify_password("SecurePass123!", cred.password_hash)

    active = (
        db_session.query(AuthSession)
        .filter(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .count()
    )
    assert active == 0

    # Old access token rejected
    me = client.get("/v1/auth/me", headers={"Authorization": f"Bearer {old_access}"})
    assert me.status_code == 401

    # New password works
    login = client.post(
        "/v1/auth/login",
        json={"email": email, "password": "BrandNewPass456!"},
    )
    assert login.status_code == 200


def test_expired_and_reused_reset_token_rejected(client, db_session, memory_mail):
    body = _register(client, db_session)
    email = body["user"]["email"]
    memory_mail.sent.clear()
    client.post("/v1/auth/forgot-password", json={"email": email})
    raw = memory_mail.sent[0].text_body.split("token=")[1].split()[0].strip()

    row = (
        db_session.query(PasswordResetToken)
        .filter(PasswordResetToken.token_hash == hash_token(raw))
        .one()
    )
    row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.commit()

    expired = client.post(
        "/v1/auth/reset-password",
        json={"token": raw, "new_password": "BrandNewPass456!"},
    )
    assert expired.status_code == 403

    # Fresh token then reuse
    memory_mail.sent.clear()
    client.post("/v1/auth/forgot-password", json={"email": email})
    raw2 = memory_mail.sent[0].text_body.split("token=")[1].split()[0].strip()
    ok = client.post(
        "/v1/auth/reset-password",
        json={"token": raw2, "new_password": "BrandNewPass456!"},
    )
    assert ok.status_code == 200
    reuse = client.post(
        "/v1/auth/reset-password",
        json={"token": raw2, "new_password": "AnotherPass789!"},
    )
    assert reuse.status_code == 403
