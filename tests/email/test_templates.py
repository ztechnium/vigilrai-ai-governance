"""Unit tests for email templates and memory transport."""

from __future__ import annotations

from rai_gateway.email.smtp import MemoryEmailTransport
from rai_gateway.email.templates import (
    render_password_reset_email,
    render_verification_email,
    render_welcome_email,
)


def test_templates_contain_required_content():
    verify = render_verification_email(
        to_address="a@example.com",
        user_name="Ada",
        organization_name="Acme",
        verification_url="https://app.example.com/verify-email?token=abc",
        expires_in_minutes=60,
        support_email="support@example.com",
    )
    assert "Confirm your RAI Control Plane email" == verify.subject
    assert "Acme" in verify.text_body
    assert "verify-email?token=abc" in verify.html_body

    welcome = render_welcome_email(
        to_address="a@example.com",
        user_name="Ada",
        organization_name="Acme",
        app_url="https://app.example.com",
        onboarding_url="https://app.example.com/onboarding",
        documentation_url="https://docs.example.com",
        support_email=None,
    )
    assert "Welcome to RAI Control Plane" == welcome.subject
    assert "Continue Setup" in welcome.html_body

    reset = render_password_reset_email(
        to_address="a@example.com",
        user_name="Ada",
        reset_url="https://app.example.com/reset-password?token=xyz",
        expires_in_minutes=30,
        support_email=None,
    )
    assert "Reset your RAI Control Plane password" == reset.subject
    assert "Do not forward" in reset.text_body or "share" in reset.text_body.lower()


def test_memory_transport_failure_mode():
    transport = MemoryEmailTransport()
    transport.fail_next = True
    msg = render_verification_email(
        to_address="a@example.com",
        user_name="Ada",
        organization_name="Acme",
        verification_url="https://x/verify-email?token=t",
        expires_in_minutes=60,
        support_email=None,
    )
    result = transport.send(msg)
    assert result.success is False
    assert transport.sent == []
    ok = transport.send(msg)
    assert ok.success is True
    assert len(transport.sent) == 1
