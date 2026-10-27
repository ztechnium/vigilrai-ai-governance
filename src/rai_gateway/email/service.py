"""Provider-agnostic transactional email service."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from rai_gateway.core.config import settings
from rai_gateway.core.observability import logger
from rai_gateway.email.domain import DeliveryStatus, EmailMessage, EmailType, SendResult
from rai_gateway.email.errors import EmailConfigurationError, EmailError
from rai_gateway.email.smtp import EmailTransport, get_email_transport
from rai_gateway.email.templates import (
    render_password_reset_email,
    render_verification_email,
    render_welcome_email,
)
from rai_gateway.models.auth import EmailDeliveryAttempt


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EmailService:
    """High-level send APIs used by auth/registration — never SMTP details."""

    def __init__(
        self,
        db: Session,
        *,
        transport: EmailTransport | None = None,
    ) -> None:
        self._db = db
        self._transport = transport

    def _transport_or_default(self) -> EmailTransport:
        return self._transport or get_email_transport()

    def send_email_verification(
        self,
        *,
        user_id: str,
        to_address: str,
        user_name: str,
        organization_name: str,
        verification_url: str,
    ) -> SendResult:
        message = render_verification_email(
            to_address=to_address,
            user_name=user_name,
            organization_name=organization_name,
            verification_url=verification_url,
            expires_in_minutes=settings.email_verification_ttl_minutes,
            support_email=settings.email_reply_to,
        )
        return self._deliver(
            user_id=user_id,
            email_type=EmailType.EMAIL_VERIFICATION,
            message=message,
        )

    def send_welcome_email(
        self,
        *,
        user_id: str,
        to_address: str,
        user_name: str,
        organization_name: str,
    ) -> SendResult:
        app_url = settings.app_public_url.rstrip("/")
        message = render_welcome_email(
            to_address=to_address,
            user_name=user_name,
            organization_name=organization_name,
            app_url=app_url,
            onboarding_url=f"{app_url}/onboarding",
            documentation_url=settings.email_docs_url,
            support_email=settings.email_reply_to,
        )
        return self._deliver(
            user_id=user_id,
            email_type=EmailType.WELCOME,
            message=message,
        )

    def send_password_reset(
        self,
        *,
        user_id: str,
        to_address: str,
        user_name: str,
        reset_url: str,
    ) -> SendResult:
        message = render_password_reset_email(
            to_address=to_address,
            user_name=user_name,
            reset_url=reset_url,
            expires_in_minutes=settings.password_reset_ttl_minutes,
            support_email=settings.email_reply_to,
        )
        return self._deliver(
            user_id=user_id,
            email_type=EmailType.PASSWORD_RESET,
            message=message,
        )

    def _deliver(
        self,
        *,
        user_id: str | None,
        email_type: EmailType,
        message: EmailMessage,
    ) -> SendResult:
        attempt = EmailDeliveryAttempt(
            user_id=user_id,
            email=message.to_address,
            template_key=email_type.value,
            provider=settings.email_provider if settings.email_enabled else "null",
            status=DeliveryStatus.PENDING.value,
        )
        self._db.add(attempt)
        self._db.commit()
        self._db.refresh(attempt)

        try:
            transport = self._transport_or_default()
            result = transport.send(message)
        except EmailConfigurationError as exc:
            attempt.status = DeliveryStatus.FAILED.value
            attempt.error_message = exc.message[:500]
            self._db.commit()
            logger.warning(
                "email.config_failed",
                email_type=email_type.value,
                error=exc.message,
            )
            return SendResult(
                success=False,
                error_code=exc.code,
                error_message=exc.message,
                retryable=False,
            )
        except EmailError as exc:
            attempt.status = DeliveryStatus.FAILED.value
            attempt.error_message = exc.message[:500]
            self._db.commit()
            return SendResult(
                success=False,
                error_code=exc.code,
                error_message=exc.message,
                retryable=exc.retryable,
            )
        except Exception as exc:  # pragma: no cover - unexpected transport failures
            attempt.status = DeliveryStatus.FAILED.value
            attempt.error_message = str(exc)[:500]
            self._db.commit()
            logger.warning(
                "email.unexpected_failure",
                email_type=email_type.value,
                error_type=type(exc).__name__,
            )
            return SendResult(
                success=False,
                error_code="EMAIL_UNEXPECTED",
                error_message=str(exc)[:500],
                retryable=True,
            )

        if result.success:
            attempt.status = DeliveryStatus.SENT.value
            attempt.sent_at = _utcnow()
            attempt.error_message = None
        else:
            attempt.status = DeliveryStatus.FAILED.value
            attempt.error_message = (result.error_message or "send failed")[:500]
        self._db.commit()
        return result
