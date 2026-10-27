"""Policy engine exceptions."""

from __future__ import annotations


class PolicyError(Exception):
    error_code: str = "POLICY_ERROR"
    status_code: int = 400

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class PolicyNotFoundError(PolicyError):
    error_code = "NOT_FOUND"
    status_code = 404

    def __init__(self, resource: str, identifier: str) -> None:
        super().__init__(f"{resource} not found: {identifier}")


class PolicyValidationError(PolicyError):
    error_code = "POLICY_VALIDATION_ERROR"
    status_code = 422
