"""WP2 identity and delegation exceptions."""

from __future__ import annotations


class IdentityError(Exception):
    """Base identity error with HTTP mapping."""

    error_code: str = "IDENTITY_ERROR"
    status_code: int = 400

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class NotFoundError(IdentityError):
    error_code = "NOT_FOUND"
    status_code = 404

    def __init__(self, resource: str, identifier: str) -> None:
        super().__init__(f"{resource} not found: {identifier}")


class InvalidTransitionError(IdentityError):
    error_code = "INVALID_LIFECYCLE_TRANSITION"
    status_code = 422


class AuthorityDeniedError(IdentityError):
    error_code = "AUTHORITY_DENIED"
    status_code = 403

    def __init__(self, reason: str, message: str) -> None:
        self.reason = reason
        super().__init__(message)


class ScopeExceededError(IdentityError):
    error_code = "AUTHORITY_SCOPE_EXCEEDED"
    status_code = 403


class RelationshipError(IdentityError):
    error_code = "INVALID_RELATIONSHIP"
    status_code = 422
