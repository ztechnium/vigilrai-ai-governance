"""WP8 governance domain errors."""

from __future__ import annotations


class GovernanceError(Exception):
    error_code = "GOVERNANCE_ERROR"
    status_code = 400

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class GovernanceNotFoundError(GovernanceError):
    error_code = "GOVERNANCE_NOT_FOUND"
    status_code = 404


class GovernanceConflictError(GovernanceError):
    error_code = "GOVERNANCE_CONFLICT"
    status_code = 409


class GovernanceDeniedError(GovernanceError):
    error_code = "GOVERNANCE_DENIED"
    status_code = 403


class SeparationOfDutiesError(GovernanceDeniedError):
    error_code = "SEPARATION_OF_DUTIES"
    status_code = 403


class TenantIsolationError(GovernanceDeniedError):
    error_code = "TENANT_ISOLATION"
    status_code = 403
