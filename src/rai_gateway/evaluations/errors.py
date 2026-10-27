"""WP7 evaluation / assurance domain errors."""

from __future__ import annotations


class EvaluationError(Exception):
    """Base evaluation domain error."""

    error_code = "EVALUATION_ERROR"
    status_code = 400

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class EvaluationNotFoundError(EvaluationError):
    error_code = "EVALUATION_NOT_FOUND"
    status_code = 404


class EvaluationConflictError(EvaluationError):
    error_code = "EVALUATION_CONFLICT"
    status_code = 409


class EvaluationDeniedError(EvaluationError):
    error_code = "EVALUATION_DENIED"
    status_code = 403


class SuiteImmutableError(EvaluationError):
    error_code = "SUITE_IMMUTABLE"
    status_code = 409


class WaiverDeniedError(EvaluationError):
    error_code = "WAIVER_DENIED"
    status_code = 403
