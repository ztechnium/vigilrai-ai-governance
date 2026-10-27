"""Email-specific errors."""

from __future__ import annotations


class EmailError(Exception):
    """Base email error."""

    def __init__(
        self, message: str, *, retryable: bool = False, code: str = "EMAIL_ERROR"
    ):
        super().__init__(message)
        self.message = message
        self.retryable = retryable
        self.code = code


class EmailConfigurationError(EmailError):
    def __init__(self, message: str):
        super().__init__(message, retryable=False, code="EMAIL_CONFIG")


class EmailTransportError(EmailError):
    def __init__(self, message: str, *, retryable: bool = True):
        super().__init__(message, retryable=retryable, code="EMAIL_TRANSPORT")
