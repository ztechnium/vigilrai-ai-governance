"""Configuration management for RAI Gateway."""

from typing import Any, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    # Environment Configuration
    environment: str = "development"  # development | staging | production

    # Database Configuration
    database_url: str = "postgresql://localhost:5432/rai_gateway"
    database_pool_size: int = 20
    database_max_overflow: int = 30

    # Feature Flags (Global)
    enable_cache: bool = True
    enable_cases: bool = True
    enable_rag: bool = False
    enable_judge: bool = False
    enable_xai: bool = True
    enable_ethics_eval: bool = True

    # Security Configuration
    jwt_secret_key: str = "your-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30

    # External Services - LLM Providers (Multi-Provider Support)
    # OpenAI
    llm_provider: str = "openai"
    llm_provider_url: str = "https://api.openai.com/v1"
    llm_provider_model: str = "gpt-3.5-turbo"
    llm_provider_api_key: Optional[str] = None

    # Azure OpenAI
    azure_openai_api_key: Optional[str] = None
    azure_openai_endpoint: Optional[str] = None
    azure_openai_deployment: Optional[str] = None
    azure_openai_api_version: str = "2024-02-15-preview"

    # Anthropic (Claude)
    anthropic_api_key: Optional[str] = None

    # AWS Bedrock
    aws_region: str = "us-east-1"  # boto3 credentials from environment/IAM

    # Google Vertex AI
    gcp_project_id: Optional[str] = None
    gcp_location: str = "us-central1"

    # Ollama (local/on-prem)
    ollama_endpoint: str = "http://localhost:11434"

    # Data Classification Service
    data_classification_url: Optional[str] = None

    # Runtime Auth
    # If true, /v1/execute requires a valid X-API-Key.
    require_api_key: bool = False

    # Cache Configuration
    redis_url: str = "redis://localhost:6379"
    cache_ttl_seconds: int = 3600

    # Observability
    otel_endpoint: Optional[str] = None
    log_level: str = "INFO"

    # Security & Compliance
    evidence_encryption_key: str = "change-this-encryption-key"
    siem_endpoint: Optional[str] = None

    # Internal Admin Console (Release 1 Option A)
    # Simple token gate for internal admin pages/APIs. Prefer JWT/SSO later.
    admin_token: Optional[str] = None
    admin_session_minutes: int = 480
    admin_bootstrap_enabled: bool = True  # Set false in production
    admin_bootstrap_email: str = "admin@raigateway.local"
    admin_bootstrap_password: str = "ChangeMe123!"
    admin_bootstrap_name: str = "General Admin"
    admin_bootstrap_role: str = "admin"
    # Sample ACME / public-agency pilots. Off so a fresh install stays empty.
    enable_reference_pilot_seed: bool = False

    # Step-up verification for sensitive admin actions.
    # Shared-secret header is a non-prod escape hatch only — enable explicitly.
    require_step_up: bool = True
    step_up_token: Optional[str] = None
    allow_shared_secret_step_up: bool = False

    # Enterprise IdP for admin login / CRITICAL approval MFA (ACR/AMR/auth_time)
    admin_oidc_issuer: Optional[str] = None
    admin_oidc_audience: Optional[str] = None
    admin_oidc_jwks_url: Optional[str] = None
    admin_oidc_email_claim: str = "email"

    # WP5 evidence content handling (org defaults).
    # Prompt, model request/response, and agent output stay REDACTED (text kept,
    # secrets scrubbed) even when demo defaults are off. Tool parameters and
    # tool results fall back to METADATA_ONLY unless demo defaults are on.
    evidence_use_demo_content_defaults: bool = True
    evidence_prompt_handling_mode: Optional[str] = None
    evidence_model_request_handling_mode: Optional[str] = None
    evidence_model_response_handling_mode: Optional[str] = None
    evidence_agent_output_handling_mode: Optional[str] = None
    evidence_tool_parameters_handling_mode: Optional[str] = None
    evidence_tool_result_handling_mode: Optional[str] = None

    # WP10 productization
    sdk_rate_limit_per_minute: int = 600
    sdk_auth_failure_limit_per_minute: int = 30
    object_storage_backend: str = "postgres"  # postgres | s3 | minio
    object_storage_bucket: Optional[str] = None
    object_storage_endpoint: Optional[str] = None
    oidc_jwks_url: Optional[str] = None
    fail_closed_on_rai_unavailable: bool = True
    approval_webhooks_enabled: bool = True
    webhook_allow_private_hosts: bool = False
    webhook_allow_http: bool = False

    # mTLS trust boundary — never trust public cert headers alone
    mtls_trusted_proxy_mode: bool = False
    mtls_trusted_proxy_secret: Optional[str] = None
    # Dev/demo only. Production must keep this false.
    mtls_allow_insecure_identity_header: bool = False

    # MCP adapter: PRODUCTION denies missing endpoints; DEMO_SIMULATED allows sim.
    mcp_adapter_mode: str = "PRODUCTION"  # PRODUCTION | DEMO_SIMULATED
    # Comma-separated hostnames (exact or *.suffix). Empty = no hostname allowlist.
    mcp_allowed_hosts: Optional[str] = None
    # Allow RFC1918 / loopback / link-local targets (dev only; keep false in prod).
    mcp_allow_private_hosts: bool = False
    # Allow http:// endpoints (dev only; production should use https).
    mcp_allow_http: bool = False

    # Human approval step-up (server-derived; never trust caller body alone)
    approval_minimum_acr: Optional[str] = None
    approval_required_amr: Optional[str] = None  # comma-separated
    approval_max_auth_age_seconds: Optional[int] = None

    @field_validator("approval_max_auth_age_seconds", mode="before")
    @classmethod
    def _empty_optional_int(cls, value: Any) -> Any:
        """Compose often passes APPROVAL_MAX_AUTH_AGE_SECONDS=; treat as unset."""
        if value is None or value == "":
            return None
        return value

    # SaaS human session authentication
    auth_access_token_minutes: int = 480  # 8h access JWT; refresh token extends further
    auth_refresh_token_days: int = 30
    auth_set_cookies: bool = False
    auth_cookie_secure: bool = True
    auth_cookie_samesite: str = "lax"
    auth_access_cookie_name: str = "rai_access"
    auth_refresh_cookie_name: str = "rai_refresh"
    app_public_url: str = "http://localhost:3000"

    # CORS Configuration (Phase 23)
    # Comma-separated list of allowed origins (exact match)
    # Example: https://app.example.com,https://admin.example.com
    # Use "*" for development only. NEVER use "*" with credentials in production.
    cors_allowed_origins: str = "*"
    cors_allow_credentials: bool = True
    cors_allow_methods: str = "*"
    # Include X-Admin-Token — control-plane-ui sends it on every fetch when
    # NEXT_PUBLIC_ADMIN_TOKEN is set; omitting it fails browser preflight (400).
    # Include X-RAI-Agent-Key — the enforcement test console sends the runtime
    # credential from the browser; omitting it fails that preflight (400).
    cors_allow_headers: str = (
        "Content-Type,Authorization,X-CSRF-Token,X-Admin-Token,X-RAI-Agent-Key"
    )
    cors_max_age: int = 600

    # Transactional email (Resend SMTP by default; provider-agnostic transport)
    email_enabled: bool = False
    email_provider: str = "resend"
    email_from_name: str = "RAI Control Plane"
    email_from_address: Optional[str] = None
    email_reply_to: Optional[str] = None
    smtp_host: str = "smtp.resend.com"
    smtp_port: int = 465
    smtp_username: str = "resend"
    smtp_password: Optional[str] = None
    smtp_use_ssl: bool = True
    smtp_use_starttls: bool = False
    smtp_timeout_seconds: float = 15.0
    email_verification_ttl_minutes: int = 60
    password_reset_ttl_minutes: int = 30
    email_docs_url: str = "https://docs.rai.example.com"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # Ignore extra environment variables


# Global settings instance
settings = Settings()
