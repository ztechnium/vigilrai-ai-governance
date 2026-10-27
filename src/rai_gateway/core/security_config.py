"""
Production Security Configuration Validation

Phase 20-21: Validates that production deployments use secure configuration.
Fails fast on startup if insecure settings are detected.
"""

from __future__ import annotations

import sys
from typing import Any

from rai_gateway.core.config import settings


class SecurityConfigError(Exception):
    """Raised when insecure configuration is detected in production."""

    pass


def validate_production_security() -> tuple[list[str], list[str]]:
    """
    Validate security configuration for production deployment.

    Returns tuple of (errors, warnings).
    Errors are critical and should block startup in production.
    Warnings are suboptimal but allowed.
    """
    errors: list[str] = []
    warnings: list[str] = []

    # 1. JWT Secret Validation (CRITICAL)
    default_jwt_secrets = {
        "your-secret-key-change-in-production",
        "change-this-jwt-secret-in-production",
        "dev-secret",
        "test-secret",
        "secret",
        "changeme",
    }
    jwt_secret = settings.jwt_secret_key
    if jwt_secret.lower() in default_jwt_secrets or len(jwt_secret) < 32:
        errors.append(
            "Insecure JWT secret detected. "
            "Set RAI_JWT_SECRET_KEY to a strong random value (32+ chars). "
            f"Current length: {len(jwt_secret)} chars."
        )

    # 2. Evidence Encryption Key Validation (CRITICAL)
    default_encryption_keys = {
        "change-this-encryption-key",
        "change-this-key",
        "dev-key",
        "test-key",
        "changeme",
    }
    if settings.evidence_encryption_key in default_encryption_keys:
        errors.append(
            "Default evidence encryption key detected. "
            "Set RAI_EVIDENCE_ENCRYPTION_KEY to a strong random value (32+ chars)."
        )
    elif len(settings.evidence_encryption_key) < 32:
        warnings.append(
            f"Evidence encryption key is short ({len(settings.evidence_encryption_key)} chars). "
            "Recommended: 32+ characters."
        )

    # 3. Bootstrap Admin Password Validation (CRITICAL)
    default_passwords = {
        "ChangeMe123!",
        "changeme",
        "admin",
        "password",
        "Password123!",
    }
    if settings.admin_bootstrap_password in default_passwords:
        errors.append(
            "Default bootstrap admin password detected. "
            "Set RAI_ADMIN_BOOTSTRAP_PASSWORD to a strong unique password "
            "or disable bootstrap (RAI_ADMIN_BOOTSTRAP_ENABLED=false)."
        )

    # 4. Admin Token Validation (should be disabled in production)
    if settings.admin_token:
        warnings.append(
            "Shared admin token (X-Admin-Token) is enabled. "
            "This bypasses proper authentication and should be disabled in production. "
            "Unset RAI_ADMIN_TOKEN."
        )

    # 5. Bootstrap Admin Validation
    if settings.admin_bootstrap_enabled:
        warnings.append(
            "Bootstrap admin auto-creation is enabled. "
            "In production, set RAI_ADMIN_BOOTSTRAP_ENABLED=false "
            "and provision admin users explicitly through proper channels."
        )

    # 6. Shared-Secret Step-Up Validation (CRITICAL)
    if settings.allow_shared_secret_step_up:
        errors.append(
            "Shared-secret step-up authentication is enabled (RAI_ALLOW_SHARED_SECRET_STEP_UP=true). "
            "This is a development-only feature and MUST be disabled in production."
        )

    # 7. Cookie Security Validation (CRITICAL when cookies enabled)
    if settings.auth_set_cookies:
        if not settings.auth_cookie_secure:
            errors.append(
                "Cookie auth enabled but Secure flag is disabled. "
                "Cookies will be sent over HTTP, exposing tokens. "
                "Set RAI_AUTH_COOKIE_SECURE=true for HTTPS-only cookies."
            )

        if settings.auth_cookie_samesite.lower() not in ("lax", "strict"):
            warnings.append(
                f"Cookie SameSite={settings.auth_cookie_samesite} may allow CSRF attacks. "
                "Recommended: 'lax' or 'strict'."
            )

        if settings.auth_access_token_minutes > 60:
            warnings.append(
                f"Access token lifetime is {settings.auth_access_token_minutes} minutes. "
                "For cookie auth, consider 15-30 minutes for better security."
            )

    # 8. Email Security Validation (CRITICAL if enabled)
    if settings.email_enabled:
        if not settings.smtp_password:
            errors.append(
                "Email is enabled but SMTP password is not set. "
                "Set RAI_SMTP_PASSWORD or disable email (RAI_EMAIL_ENABLED=false)."
            )
        if not settings.email_from_address:
            warnings.append(
                "Email enabled but no from address set. "
                "Set RAI_EMAIL_FROM_ADDRESS for proper email delivery."
            )

    # 9. mTLS Security Validation (CRITICAL)
    if settings.mtls_allow_insecure_identity_header:
        errors.append(
            "Insecure mTLS identity header forwarding is enabled (RAI_MTLS_ALLOW_INSECURE_IDENTITY_HEADER=true). "
            "This allows client certificate spoofing and MUST be disabled in production."
        )

    if settings.mtls_trusted_proxy_mode and not settings.mtls_trusted_proxy_secret:
        errors.append(
            "mTLS trusted proxy mode is enabled but no proxy secret is set. "
            "Set RAI_MTLS_TRUSTED_PROXY_SECRET to authenticate proxy forwarding, "
            "or disable RAI_MTLS_TRUSTED_PROXY_MODE."
        )

    # 10. MCP Security Validation (CRITICAL)
    if settings.mcp_adapter_mode == "DEMO_SIMULATED":
        errors.append(
            "MCP adapter is in DEMO_SIMULATED mode (RAI_MCP_ADAPTER_MODE=DEMO_SIMULATED). "
            "This bypasses actual MCP server calls and MUST NOT be used in production. "
            "Set RAI_MCP_ADAPTER_MODE=PRODUCTION."
        )

    if settings.mcp_allow_private_hosts:
        warnings.append(
            "MCP is configured to allow private/internal hosts (RAI_MCP_ALLOW_PRIVATE_HOSTS=true). "
            "This may allow SSRF attacks. Consider disabling in production unless required."
        )

    if settings.mcp_allow_http:
        warnings.append(
            "MCP is configured to allow HTTP endpoints (RAI_MCP_ALLOW_HTTP_ENDPOINTS=true). "
            "Production should use HTTPS for security. Consider setting to false."
        )

    # 11. CORS Validation (Phase 23)
    if settings.cors_allowed_origins == "*" and settings.cors_allow_credentials:
        errors.append(
            "Wildcard CORS origin (*) is enabled with credentials (RAI_CORS_ALLOW_CREDENTIALS=true). "
            "This allows any website to make authenticated requests to your API and is a critical security vulnerability. "
            "Set RAI_CORS_ALLOWED_ORIGINS to a comma-separated list of allowed origins "
            "(e.g., https://app.example.com,https://admin.example.com) "
            "or disable credentials (RAI_CORS_ALLOW_CREDENTIALS=false)."
        )

    if settings.cors_allowed_origins == "*":
        warnings.append(
            "Wildcard CORS origin (*) is enabled. "
            "Any website can make requests to your API. "
            "For production, set RAI_CORS_ALLOWED_ORIGINS to specific allowed origins."
        )

    # Check for common misconfigurations
    if settings.cors_allowed_origins != "*":
        origins = [o.strip() for o in settings.cors_allowed_origins.split(",")]
        for origin in origins:
            if origin == "*":
                if settings.cors_allow_credentials:
                    errors.append(
                        "Wildcard (*) found in CORS allowed origins list with credentials enabled. "
                        "Remove the wildcard or disable credentials."
                    )
                else:
                    warnings.append(
                        "Wildcard (*) found in CORS allowed origins list. "
                        "Consider using specific origins only."
                    )
            elif not origin.startswith(("http://", "https://")):
                warnings.append(
                    f"CORS origin '{origin}' does not start with http:// or https://. "
                    "Ensure this is intentional."
                )
            elif (
                origin.startswith("http://")
                and origin != "http://localhost"
                and not origin.startswith("http://127.0.0.1")
            ):
                warnings.append(
                    f"CORS origin '{origin}' uses HTTP (not HTTPS). "
                    "Production origins should use HTTPS for security."
                )

    # 12. Step-Up Verification
    if not settings.require_step_up:
        warnings.append(
            "Step-up verification is disabled (RAI_REQUIRE_STEP_UP=false). "
            "Sensitive operations will not require additional verification."
        )

    # 13. Evidence Demo Content Defaults
    if settings.evidence_use_demo_content_defaults:
        warnings.append(
            "Evidence demo content defaults are enabled (RAI_EVIDENCE_USE_DEMO_CONTENT_DEFAULTS=true). "
            "Tool parameters and tool results are retained. Disable the flag in production "
            "to keep those as metadata only. Prompt and output text stay stored with secrets redacted."
        )

    # 14. Fail-Closed Policy
    if not settings.fail_closed_on_rai_unavailable:
        warnings.append(
            "RAI fail-closed mode is disabled (RAI_FAIL_CLOSED_ON_RAI_UNAVAILABLE=false). "
            "If RAI gateway is unavailable, requests will be allowed through without policy checks."
        )

    return errors, warnings


def enforce_production_security(environment: str = None) -> None:
    """
    Enforce production security requirements.

    Args:
        environment: Deployment environment (production, staging, development)

    Raises:
        SecurityConfigError: If critical security issues are found
    """
    if environment is None:
        environment = getattr(settings, "environment", "development").lower()

    # Only enforce for production
    if environment not in ("production", "prod"):
        return

    errors, warnings = validate_production_security()

    # Print warnings
    if warnings:
        print("⚠️  Security Configuration Warnings:", file=sys.stderr)
        for warning in warnings:
            print(f"   - {warning}", file=sys.stderr)
        print(file=sys.stderr)

    # Fail on errors
    if errors:
        print("❌ Security Configuration Errors:", file=sys.stderr)
        for error in errors:
            print(f"   - {error}", file=sys.stderr)
        print(file=sys.stderr)
        raise SecurityConfigError(
            f"Production deployment blocked: {len(errors)} security issue(s) detected. "
            "Fix configuration and restart."
        )

    if not errors and not warnings:
        print("✅ Security configuration validated", file=sys.stderr)


def get_security_status() -> dict[str, Any]:
    """
    Get current security configuration status.

    Returns dict with security settings and recommendations.
    """
    errors, warnings = validate_production_security()

    return {
        "secure": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "environment": settings.environment,
        "config": {
            "environment": settings.environment,
            "auth_set_cookies": settings.auth_set_cookies,
            "auth_cookie_secure": settings.auth_cookie_secure,
            "auth_cookie_samesite": settings.auth_cookie_samesite,
            "auth_access_token_minutes": settings.auth_access_token_minutes,
            "auth_refresh_token_days": settings.auth_refresh_token_days,
            "admin_token_enabled": bool(settings.admin_token),
            "bootstrap_admin_enabled": settings.admin_bootstrap_enabled,
            "email_enabled": settings.email_enabled,
            "jwt_secret_length": len(settings.jwt_secret_key),
            "evidence_encryption_key_length": len(settings.evidence_encryption_key),
            "mcp_adapter_mode": settings.mcp_adapter_mode,
            "mcp_allow_private_hosts": settings.mcp_allow_private_hosts,
            "mcp_allow_http": settings.mcp_allow_http,
            "mtls_allow_insecure_identity_header": settings.mtls_allow_insecure_identity_header,
            "allow_shared_secret_step_up": settings.allow_shared_secret_step_up,
            "fail_closed_on_rai_unavailable": settings.fail_closed_on_rai_unavailable,
            "cors_allowed_origins": settings.cors_allowed_origins,
            "cors_allow_credentials": settings.cors_allow_credentials,
            "cors_wildcard_with_credentials": settings.cors_allowed_origins == "*"
            and settings.cors_allow_credentials,
        },
    }
