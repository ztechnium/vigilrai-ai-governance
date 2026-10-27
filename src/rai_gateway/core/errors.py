"""Error handling and taxonomy implementation."""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class ErrorCode(str, Enum):
    """Standardized error codes matching docs/specs/error_taxonomy.json."""

    INVALID_REQUEST = "INVALID_REQUEST"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    NOT_ALLOWED = "NOT_ALLOWED"
    PROMPT_NOT_FOUND = "PROMPT_NOT_FOUND"
    PROMPT_VERSION_NOT_APPROVED = "PROMPT_VERSION_NOT_APPROVED"
    INPUT_BLOCKED = "INPUT_BLOCKED"
    OUTPUT_BLOCKED = "OUTPUT_BLOCKED"
    CATALOG_UNAVAILABLE = "CATALOG_UNAVAILABLE"
    GUARD_UNAVAILABLE = "GUARD_UNAVAILABLE"
    LLM_TIMEOUT = "LLM_TIMEOUT"
    EXECUTION_FAILED = "EXECUTION_FAILED"


# HTTP status code mapping from error taxonomy
ERROR_HTTP_STATUS = {
    ErrorCode.INVALID_REQUEST: 400,
    ErrorCode.UNAUTHENTICATED: 401,
    ErrorCode.NOT_ALLOWED: 403,
    ErrorCode.PROMPT_NOT_FOUND: 404,
    ErrorCode.PROMPT_VERSION_NOT_APPROVED: 409,
    ErrorCode.INPUT_BLOCKED: 422,
    ErrorCode.OUTPUT_BLOCKED: 422,
    ErrorCode.CATALOG_UNAVAILABLE: 503,
    ErrorCode.GUARD_UNAVAILABLE: 503,
    ErrorCode.LLM_TIMEOUT: 504,
    ErrorCode.EXECUTION_FAILED: 500,
}


class RaiException(Exception):
    """Base exception for RAI Gateway with structured error response."""

    def __init__(
        self,
        error_code: ErrorCode,
        message: str,
        reason_codes: Optional[List[str]] = None,
        details: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None,
    ):
        self.error_code = error_code
        self.message = message
        self.reason_codes = reason_codes or []
        self.details = details or {}
        self.trace_id = trace_id
        super().__init__(message)

    @property
    def http_status(self) -> int:
        """Get HTTP status code for this error."""
        return ERROR_HTTP_STATUS[self.error_code]


class ErrorResponse(BaseModel):
    """Standardized error response format."""

    error: ErrorCode
    message: str
    reason_codes: List[str] = []
    trace_id: Optional[str] = None
    details: Dict[str, Any] = {}


# Specific exception classes for fail-closed behavior
class GuardUnavailableError(RaiException):
    """RAI Guard service unavailable - MUST fail closed."""

    def __init__(self, message: str = "RAI Guard service unavailable", **kwargs):
        super().__init__(ErrorCode.GUARD_UNAVAILABLE, message, **kwargs)


class CatalogUnavailableError(RaiException):
    """Prompt Catalog service unavailable - MUST fail closed."""

    def __init__(self, message: str = "Prompt Catalog service unavailable", **kwargs):
        super().__init__(ErrorCode.CATALOG_UNAVAILABLE, message, **kwargs)


class InputBlockedError(RaiException):
    """Input blocked by RAI policies."""

    def __init__(self, message: str = "Input blocked by policy", **kwargs):
        super().__init__(ErrorCode.INPUT_BLOCKED, message, **kwargs)


class OutputBlockedError(RaiException):
    """Output blocked by RAI policies."""

    def __init__(self, message: str = "Output blocked by policy", **kwargs):
        super().__init__(ErrorCode.OUTPUT_BLOCKED, message, **kwargs)


class NotAllowedError(RaiException):
    """Request not allowed by allowlist."""

    def __init__(self, message: str = "Request not allowed", **kwargs):
        super().__init__(ErrorCode.NOT_ALLOWED, message, **kwargs)


class PromptNotFoundError(RaiException):
    """Prompt not found."""

    def __init__(self, message: str = "Prompt not found", **kwargs):
        super().__init__(ErrorCode.PROMPT_NOT_FOUND, message, **kwargs)


class PromptVersionNotApprovedError(RaiException):
    """Prompt version not approved for use."""

    def __init__(self, message: str = "Prompt version not approved", **kwargs):
        super().__init__(ErrorCode.PROMPT_VERSION_NOT_APPROVED, message, **kwargs)
