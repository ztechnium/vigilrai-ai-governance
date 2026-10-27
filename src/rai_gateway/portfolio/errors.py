"""WP9 portfolio domain errors."""

from __future__ import annotations


class PortfolioError(Exception):
    error_code = "PORTFOLIO_ERROR"
    status_code = 400

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class PortfolioNotFoundError(PortfolioError):
    error_code = "PORTFOLIO_NOT_FOUND"
    status_code = 404


class PortfolioConflictError(PortfolioError):
    error_code = "PORTFOLIO_CONFLICT"
    status_code = 409


class PortfolioDeniedError(PortfolioError):
    error_code = "PORTFOLIO_DENIED"
    status_code = 403


class TenantIsolationError(PortfolioDeniedError):
    error_code = "TENANT_ISOLATION"
    status_code = 403
