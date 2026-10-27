"""Registry-specific exceptions."""

from __future__ import annotations


class RegistryError(Exception):
    """Base registry error with HTTP mapping."""

    error_code: str = "REGISTRY_ERROR"
    status_code: int = 400

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class DuplicateKeyError(RegistryError):
    error_code = "DUPLICATE_KEY"
    status_code = 409

    def __init__(self, key_type: str, key_value: str) -> None:
        super().__init__(f"Duplicate {key_type}: {key_value}")


class NotFoundError(RegistryError):
    error_code = "NOT_FOUND"
    status_code = 404

    def __init__(self, resource: str, identifier: str) -> None:
        super().__init__(f"{resource} not found: {identifier}")


class InvalidTransitionError(RegistryError):
    error_code = "INVALID_LIFECYCLE_TRANSITION"
    status_code = 422


class ImmutableVersionError(RegistryError):
    error_code = "IMMUTABLE_VERSION"
    status_code = 422


class RelationshipError(RegistryError):
    error_code = "INVALID_RELATIONSHIP"
    status_code = 422


class CatalogPermissionError(RegistryError):
    error_code = "NOT_ALLOWED"
    status_code = 403


class EligibilityDeniedError(RegistryError):
    error_code = "NOT_ELIGIBLE"
    status_code = 403
