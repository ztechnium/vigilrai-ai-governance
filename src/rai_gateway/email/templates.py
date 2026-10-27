"""HTML + plain-text transactional email templates."""

from __future__ import annotations

from rai_gateway.email.domain import EmailMessage


def _escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def render_verification_email(
    *,
    to_address: str,
    user_name: str,
    organization_name: str,
    verification_url: str,
    expires_in_minutes: int,
    support_email: str | None,
) -> EmailMessage:
    subject = "Confirm your RAI Control Plane email"
    text = (
        f"RAI Control Plane\n\n"
        f"Confirm your email\n\n"
        f"Hi {user_name},\n\n"
        f"Please confirm your email address to finish setting up "
        f"{organization_name} in RAI Control Plane.\n\n"
        f"Confirm Email: {verification_url}\n\n"
        f"This link expires in {expires_in_minutes} minutes.\n\n"
        f"If you did not create this account, you can ignore this email.\n"
    )
    if support_email:
        text += f"\nSupport: {support_email}\n"

    html = f"""<!DOCTYPE html>
<html><body style="font-family:Segoe UI,Helvetica,Arial,sans-serif;line-height:1.5;color:#111;">
  <h1 style="font-size:20px;">RAI Control Plane</h1>
  <h2 style="font-size:18px;">Confirm your email</h2>
  <p>Hi {_escape(user_name)},</p>
  <p>Please confirm your email address to finish setting up
     <strong>{_escape(organization_name)}</strong> in RAI Control Plane.</p>
  <p><a href="{_escape(verification_url)}"
        style="display:inline-block;padding:10px 16px;background:#0f766e;color:#fff;text-decoration:none;border-radius:4px;">
        Confirm Email</a></p>
  <p style="font-size:13px;color:#555;">This link expires in {expires_in_minutes} minutes.</p>
  <p style="font-size:13px;color:#555;">Or paste this URL into your browser:<br/>
     {_escape(verification_url)}</p>
  <p style="font-size:13px;color:#555;">If you did not create this account, you can ignore this email.</p>
</body></html>"""
    return EmailMessage(
        to_address=to_address,
        subject=subject,
        text_body=text,
        html_body=html,
        reply_to=support_email,
    )


def render_welcome_email(
    *,
    to_address: str,
    user_name: str,
    organization_name: str,
    app_url: str,
    onboarding_url: str,
    documentation_url: str,
    support_email: str | None,
) -> EmailMessage:
    subject = "Welcome to RAI Control Plane"
    text = (
        f"Welcome to RAI Control Plane\n\n"
        f"Hi {user_name},\n\n"
        f"{organization_name} is ready to continue setup.\n\n"
        f"Continue Setup: {onboarding_url}\n"
        f"Documentation: {documentation_url}\n"
        f"App: {app_url}\n\n"
        f"Next: register your first AI system and connect a runtime integration.\n"
    )
    if support_email:
        text += f"\nSupport: {support_email}\n"

    html = f"""<!DOCTYPE html>
<html><body style="font-family:Segoe UI,Helvetica,Arial,sans-serif;line-height:1.5;color:#111;">
  <h1 style="font-size:20px;">Welcome to RAI Control Plane</h1>
  <p>Hi {_escape(user_name)},</p>
  <p><strong>{_escape(organization_name)}</strong> is ready to continue setup.</p>
  <p><a href="{_escape(onboarding_url)}"
        style="display:inline-block;padding:10px 16px;background:#0f766e;color:#fff;text-decoration:none;border-radius:4px;">
        Continue Setup</a></p>
  <p>Next steps: register your first AI system and connect a runtime integration.</p>
  <p><a href="{_escape(documentation_url)}">Developer documentation</a></p>
</body></html>"""
    return EmailMessage(
        to_address=to_address,
        subject=subject,
        text_body=text,
        html_body=html,
        reply_to=support_email,
    )


def render_password_reset_email(
    *,
    to_address: str,
    user_name: str,
    reset_url: str,
    expires_in_minutes: int,
    support_email: str | None,
) -> EmailMessage:
    subject = "Reset your RAI Control Plane password"
    text = (
        f"Reset your password\n\n"
        f"Hi {user_name},\n\n"
        f"We received a request to reset your RAI Control Plane password.\n\n"
        f"Reset Password: {reset_url}\n\n"
        f"This link expires in {expires_in_minutes} minutes.\n\n"
        f"If you did not request a password reset, ignore this email.\n"
        f"Your password will remain unchanged.\n"
        f"Do not forward or share this link.\n"
    )
    if support_email:
        text += f"\nSupport: {support_email}\n"

    html = f"""<!DOCTYPE html>
<html><body style="font-family:Segoe UI,Helvetica,Arial,sans-serif;line-height:1.5;color:#111;">
  <h1 style="font-size:20px;">Reset your password</h1>
  <p>Hi {_escape(user_name)},</p>
  <p>We received a request to reset your RAI Control Plane password.</p>
  <p><a href="{_escape(reset_url)}"
        style="display:inline-block;padding:10px 16px;background:#0f766e;color:#fff;text-decoration:none;border-radius:4px;">
        Reset Password</a></p>
  <p style="font-size:13px;color:#555;">This link expires in {expires_in_minutes} minutes.</p>
  <p style="font-size:13px;color:#555;">Or paste this URL into your browser:<br/>
     {_escape(reset_url)}</p>
  <p style="font-size:13px;color:#555;">If you did not request a password reset, ignore this email.
     Your password will remain unchanged. Do not forward or share this link.</p>
</body></html>"""
    return EmailMessage(
        to_address=to_address,
        subject=subject,
        text_body=text,
        html_body=html,
        reply_to=support_email,
    )
