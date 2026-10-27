"""SMTP transport for transactional email (Resend-compatible by default)."""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage as MimeEmailMessage
from typing import Protocol

from rai_gateway.core.config import settings
from rai_gateway.core.observability import logger
from rai_gateway.email.domain import EmailMessage, SendResult
from rai_gateway.email.errors import EmailConfigurationError


class EmailTransport(Protocol):
    def send(self, message: EmailMessage) -> SendResult: ...


class NullEmailTransport:
    """No-op transport used when EMAIL_ENABLED=false."""

    def send(self, message: EmailMessage) -> SendResult:
        logger.info(
            "email.disabled_skip",
            to=message.to_address,
            subject=message.subject,
        )
        return SendResult(success=True, provider_message_id="disabled")


class MemoryEmailTransport:
    """In-memory transport for tests — never touches the network."""

    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []
        self.fail_next: bool = False
        self.fail_message: str = "simulated SMTP failure"

    def send(self, message: EmailMessage) -> SendResult:
        if self.fail_next:
            self.fail_next = False
            return SendResult(
                success=False,
                error_code="EMAIL_TRANSPORT",
                error_message=self.fail_message,
                retryable=True,
            )
        self.sent.append(message)
        return SendResult(
            success=True,
            provider_message_id=f"mem-{len(self.sent)}",
        )


class SmtpEmailTransport:
    """SMTP transport suitable for Resend and other SMTP providers."""

    def __init__(
        self,
        *,
        host: str | None = None,
        port: int | None = None,
        username: str | None = None,
        password: str | None = None,
        use_ssl: bool | None = None,
        use_starttls: bool | None = None,
        timeout: float | None = None,
        from_name: str | None = None,
        from_address: str | None = None,
    ) -> None:
        self.host = host if host is not None else settings.smtp_host
        self.port = port if port is not None else settings.smtp_port
        self.username = username if username is not None else settings.smtp_username
        self.password = password if password is not None else settings.smtp_password
        self.use_ssl = settings.smtp_use_ssl if use_ssl is None else use_ssl
        self.use_starttls = (
            settings.smtp_use_starttls if use_starttls is None else use_starttls
        )
        self.timeout = settings.smtp_timeout_seconds if timeout is None else timeout
        self.from_name = (
            from_name if from_name is not None else settings.email_from_name
        )
        self.from_address = (
            from_address if from_address is not None else settings.email_from_address
        )

    def send(self, message: EmailMessage) -> SendResult:
        if not self.from_address:
            raise EmailConfigurationError("EMAIL_FROM_ADDRESS is required")
        if not self.password:
            raise EmailConfigurationError("SMTP_PASSWORD is required")

        mime = MimeEmailMessage()
        mime["Subject"] = message.subject
        mime["From"] = f"{self.from_name} <{self.from_address}>"
        mime["To"] = message.to_address
        reply_to = message.reply_to or settings.email_reply_to
        if reply_to:
            mime["Reply-To"] = reply_to
        mime.set_content(message.text_body)
        mime.add_alternative(message.html_body, subtype="html")

        try:
            if self.use_ssl:
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(
                    self.host, self.port, timeout=self.timeout, context=context
                ) as server:
                    server.login(self.username, self.password)
                    response = server.send_message(mime)
            else:
                with smtplib.SMTP(self.host, self.port, timeout=self.timeout) as server:
                    server.ehlo()
                    if self.use_starttls:
                        context = ssl.create_default_context()
                        server.starttls(context=context)
                        server.ehlo()
                    server.login(self.username, self.password)
                    response = server.send_message(mime)
            # send_message returns {} on full success
            logger.info(
                "email.smtp_sent",
                to=message.to_address,
                subject=message.subject,
                rejected=len(response or {}),
            )
            return SendResult(success=True, provider_message_id=None)
        except EmailConfigurationError:
            raise
        except (smtplib.SMTPException, OSError, TimeoutError) as exc:
            logger.warning(
                "email.smtp_failed",
                to=message.to_address,
                error_type=type(exc).__name__,
            )
            return SendResult(
                success=False,
                error_code="EMAIL_TRANSPORT",
                error_message=str(exc)[:500],
                retryable=True,
            )


_test_transport: EmailTransport | None = None


def set_test_email_transport(transport: EmailTransport | None) -> None:
    """Override transport for tests (None restores default)."""
    global _test_transport
    _test_transport = transport


def get_email_transport() -> EmailTransport:
    if _test_transport is not None:
        return _test_transport
    if not settings.email_enabled:
        return NullEmailTransport()
    if not settings.smtp_password or not settings.email_from_address:
        raise EmailConfigurationError(
            "EMAIL_ENABLED requires SMTP_PASSWORD and EMAIL_FROM_ADDRESS"
        )
    if not (settings.app_public_url or "").strip():
        raise EmailConfigurationError("EMAIL_ENABLED requires APP_PUBLIC_URL")
    return SmtpEmailTransport()
