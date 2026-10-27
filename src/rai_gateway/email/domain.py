"""Email domain types and constants."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class EmailType(StrEnum):
    EMAIL_VERIFICATION = "EMAIL_VERIFICATION"
    WELCOME = "WELCOME"
    PASSWORD_RESET = "PASSWORD_RESET"
    SECURITY_NOTIFICATION = "SECURITY_NOTIFICATION"
    ORGANIZATION_INVITATION = "ORGANIZATION_INVITATION"


class DeliveryStatus(StrEnum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"


@dataclass(frozen=True)
class EmailMessage:
    to_address: str
    subject: str
    text_body: str
    html_body: str
    reply_to: str | None = None


@dataclass(frozen=True)
class SendResult:
    success: bool
    provider_message_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    retryable: bool = False
