"""
Security Configuration API

Phase 21: Production Configuration Validation

Provides endpoints for checking security configuration status.
"""

from typing import Any

from fastapi import APIRouter, Depends

from rai_gateway.core.authorization import require_platform_permission
from rai_gateway.core.principal import Principal
from rai_gateway.core.security_config import get_security_status

router = APIRouter(prefix="/v1/security", tags=["security"])


@router.get("/config-status")
def get_config_status(
    principal: Principal = Depends(require_platform_permission("platform:admin")),
) -> dict[str, Any]:
    """
    Get security configuration status.

    Platform admin only. Returns current security configuration
    with errors and warnings.

    **Errors** = Critical issues that should block production deployment
    **Warnings** = Suboptimal settings that should be reviewed
    """
    return get_security_status()


@router.get("/health")
def security_health() -> dict[str, Any]:
    """
    Public security health check.

    Returns minimal status without exposing configuration details.
    Useful for k8s/health monitoring.
    """
    from rai_gateway.core.config import settings
    from rai_gateway.core.security_config import validate_production_security

    errors, warnings = validate_production_security()

    # Only expose counts, not details
    return {
        "secure": len(errors) == 0,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "environment": settings.environment,
        "ready": len(errors) == 0 or settings.environment != "production",
    }
