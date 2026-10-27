"""Email verification and welcome flow tests."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from rai_gateway.auth.rate_limit import email_auth_rate_limiter
from rai_gateway.auth.tokens import hash_token
from rai_gateway.auth.verification import (
    create_verification_token,
    verify_email_token,
)
from rai_gateway.core.database import get_db
from rai_gateway.email.smtp import MemoryEmailTransport, set_test_email_transport
from rai_gateway.main import app
from rai_gateway.models.auth import EmailVerificationToken
from rai_gateway.models.database import UserAccount
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


def _user(db_session) -> UserAccount:
    suffix = uuid.uuid4().hex[:8]
    user = UserAccount(
        user_id=f"u-{suffix}",
        email=f"ada-{suffix}@example.com",
        name="Ada Lovelace",
        status="active",
    )
    db_session.add(user)
    db_session.commit()
    return user


def test_public_registration_is_not_available(client):
    response = client.post(
        "/v1/public/register",
        json={
            "full_name": "Ada Lovelace",
            "work_email": "ada@example.com",
            "password": "SecurePass123!",
            "company_name": "Acme",
            "country": "GB",
            "terms_accepted": True,
        },
    )
    assert response.status_code == 404


def test_verification_token_is_stored_as_a_hash(db_session):
    user = _user(db_session)
    raw = create_verification_token(db_session, user_id=user.user_id)
    tokens = (
        db_session.query(EmailVerificationToken)
        .filter(EmailVerificationToken.user_id == user.user_id)
        .all()
    )
    assert len(tokens) == 1
    assert tokens[0].token_hash == hash_token(raw)
    assert raw not in (tokens[0].token_hash or "")


def test_verify_email_marks_verified_and_sends_welcome(client, db_session, memory_mail):
    user = _user(db_session)
    user_id = user.user_id
    memory_mail.sent.clear()

    raw = create_verification_token(db_session, user_id=user_id)
    # create_verification_token revokes prior and does not send — send separately unused
    result = client.post("/v1/auth/verify-email", json={"token": raw})
    assert result.status_code == 200, result.text
    payload = result.json()
    assert payload["status"] == "verified"

    user = db_session.query(UserAccount).filter(UserAccount.user_id == user_id).one()
    db_session.refresh(user)
    assert user.email_verified_at is not None
    assert user.welcome_email_sent_at is not None

    subjects = [m.subject for m in memory_mail.sent]
    assert "Welcome to RAI Control Plane" in subjects

    # Idempotent second verify with used token fails
    again = client.post("/v1/auth/verify-email", json={"token": raw})
    assert again.status_code == 403


def test_expired_verification_token_rejected(db_session, memory_mail):
    user = UserAccount(
        user_id=f"u-{uuid.uuid4().hex[:8]}",
        email=f"exp-{uuid.uuid4().hex[:6]}@example.com",
        name="Exp",
        status="active",
    )
    db_session.add(user)
    db_session.commit()
    raw = create_verification_token(db_session, user_id=user.user_id)
    row = (
        db_session.query(EmailVerificationToken)
        .filter(EmailVerificationToken.token_hash == hash_token(raw))
        .one()
    )
    row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.commit()

    with pytest.raises(Exception):
        verify_email_token(db_session, raw_token=raw)


def test_welcome_email_not_duplicated(db_session, memory_mail):
    user = UserAccount(
        user_id=f"u-{uuid.uuid4().hex[:8]}",
        email=f"wel-{uuid.uuid4().hex[:6]}@example.com",
        name="Wel",
        status="active",
    )
    db_session.add(user)
    db_session.commit()
    raw = create_verification_token(db_session, user_id=user.user_id)
    first = verify_email_token(db_session, raw_token=raw)
    assert first["welcome_email_sent"] is True
    welcome_count = sum(1 for m in memory_mail.sent if m.subject.startswith("Welcome"))
    assert welcome_count == 1

    # Already verified user creating another token and verifying shouldn't re-welcome
    # (used token path). Mark welcome already sent and call private path via second verify
    # of a fresh token when already verified:
    raw2 = create_verification_token(db_session, user_id=user.user_id)
    second = verify_email_token(db_session, raw_token=raw2)
    assert second["already_verified"] is True
    assert second["welcome_email_sent"] is False
    welcome_count2 = sum(1 for m in memory_mail.sent if m.subject.startswith("Welcome"))
    assert welcome_count2 == 1


def test_resend_verification_generic_and_rate_limited(client, db_session, memory_mail):
    user = _user(db_session)
    email = user.email
    memory_mail.sent.clear()

    for _ in range(5):
        resp = client.post("/v1/auth/resend-verification", json={"email": email})
        assert resp.status_code == 200
        assert "If an account exists" in resp.json()["message"]

    limited = client.post("/v1/auth/resend-verification", json={"email": email})
    assert limited.status_code == 429

    # Unknown email still generic 200 (until rate limited by email key)
    email_auth_rate_limiter._hits.clear()
    unknown = client.post(
        "/v1/auth/resend-verification",
        json={"email": f"nobody-{uuid.uuid4().hex[:6]}@example.com"},
    )
    assert unknown.status_code == 200
