"""WP3 approval exceptions."""

from __future__ import annotations

from rai_gateway.approval.domain import ApprovalDenialCode


class ApprovalError(Exception):
    """Base approval error with HTTP mapping."""

    error_code: str = "APPROVAL_ERROR"
    status_code: int = 400

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class ApprovalNotFoundError(ApprovalError):
    error_code = ApprovalDenialCode.APPROVAL_NOT_FOUND.value
    status_code = 404

    def __init__(self, identifier: str) -> None:
        super().__init__(f"Approval request not found: {identifier}")


class ApprovalDeniedError(ApprovalError):
    error_code = "APPROVAL_DENIED"
    status_code = 403

    def __init__(self, reason: ApprovalDenialCode | str, message: str) -> None:
        self.reason = str(reason)
        super().__init__(message)


class InvalidApprovalTransitionError(ApprovalError):
    error_code = ApprovalDenialCode.INVALID_TRANSITION.value
    status_code = 409

    def __init__(self, current: str, target: str) -> None:
        super().__init__(f"Invalid approval transition: {current} -> {target}")


class ApprovalConflictError(ApprovalError):
    error_code = "APPROVAL_CONFLICT"
    status_code = 409
