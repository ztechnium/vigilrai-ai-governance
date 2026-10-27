"""Stable public SDK error contract."""

from __future__ import annotations

from typing import Any

from rai_gateway.sdk.domain import SdkErrorCode

_HTTP_STATUS: dict[SdkErrorCode, int] = {
    SdkErrorCode.AUTHENTICATION_FAILED: 401,
    SdkErrorCode.TENANT_SUSPENDED: 403,
    SdkErrorCode.RUNTIME_IDENTITY_INACTIVE: 403,
    SdkErrorCode.AGENT_VERSION_INELIGIBLE: 403,
    SdkErrorCode.RESOURCE_OUT_OF_SCOPE: 403,
    SdkErrorCode.POLICY_DENIED: 403,
    SdkErrorCode.APPROVAL_REQUIRED: 403,
    SdkErrorCode.BUDGET_EXCEEDED: 403,
    SdkErrorCode.RUNTIME_SUSPENDED: 403,
    SdkErrorCode.CONTENT_DENIED: 422,
    SdkErrorCode.ASSURANCE_INVALID: 403,
    SdkErrorCode.RATE_LIMITED: 429,
    SdkErrorCode.RAI_UNAVAILABLE: 503,
    SdkErrorCode.INVALID_REQUEST: 400,
    SdkErrorCode.SESSION_NOT_FOUND: 404,
    SdkErrorCode.INTEGRATION_NOT_FOUND: 404,
    SdkErrorCode.DECISION_NOT_FOUND: 404,
}


class SdkError(Exception):
    """Structured public SDK exception."""

    def __init__(
        self,
        code: SdkErrorCode | str,
        message: str,
        *,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> None:
        if isinstance(code, str):
            try:
                code = SdkErrorCode(code)
            except ValueError:
                code = SdkErrorCode.INVALID_REQUEST
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details or {}
        self.correlation_id = correlation_id
        super().__init__(message)

    @property
    def http_status(self) -> int:
        return _HTTP_STATUS.get(self.code, 400)

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": self.code.value,
            "message": self.message,
            "retryable": self.retryable,
            "correlation_id": self.correlation_id,
            "details": self.details,
        }
