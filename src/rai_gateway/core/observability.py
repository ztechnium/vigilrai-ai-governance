"""Observability setup with OpenTelemetry and structured logging."""

import uuid
from typing import Any, Dict, Optional

import structlog
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from rai_gateway.core.config import settings

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Field names whose values must never appear in structured logs
_SENSITIVE_LOG_KEYS = frozenset(
    {
        "api_key",
        "password",
        "secret",
        "token",
        "authorization",
        "authorization_header",
        "key_hash",
        "evidence_encryption_key",
        "jwt_secret_key",
        "llm_provider_api_key",
        "anthropic_api_key",
        "azure_openai_api_key",
        "admin_bootstrap_password",
        "step_up_token",
        "admin_token",
    }
)


def _redact_sensitive_fields(**kwargs: Any) -> dict[str, Any]:
    """Replace sensitive field values with a redaction marker."""
    redacted: dict[str, Any] = {}
    for key, value in kwargs.items():
        if key.lower() in _SENSITIVE_LOG_KEYS or any(
            s in key.lower() for s in ("secret", "password", "token", "api_key")
        ):
            redacted[key] = "[REDACTED]"
        else:
            redacted[key] = value
    return redacted


def setup_telemetry() -> None:
    """Setup OpenTelemetry tracing."""
    if settings.otel_endpoint:
        # Configure tracer provider
        trace.set_tracer_provider(TracerProvider())

        # Configure OTLP exporter
        otlp_exporter = OTLPSpanExporter(endpoint=settings.otel_endpoint)
        span_processor = BatchSpanProcessor(otlp_exporter)

        trace.get_tracer_provider().add_span_processor(span_processor)


def instrument_app(app) -> None:
    """Instrument FastAPI app with OpenTelemetry."""
    if settings.otel_endpoint:
        FastAPIInstrumentor.instrument_app(app)
        SQLAlchemyInstrumentor().instrument()


def generate_trace_id() -> str:
    """Generate a new trace ID."""
    return str(uuid.uuid4())


def get_current_trace_id() -> Optional[str]:
    """Get current trace ID from OpenTelemetry context."""
    span = trace.get_current_span()
    if span and span.is_recording():
        return format(span.get_span_context().trace_id, "032x")
    return None


def log_execution_audit(
    trace_id: str,
    execution_id: str,
    prompt_id: str,
    prompt_version: int,
    system_id: str,
    decision: str,
    reason_codes: list = None,
    **kwargs,
) -> None:
    """Log execution audit metadata (compliance-safe, no sensitive data)."""
    safe_kwargs = _redact_sensitive_fields(**kwargs)
    logger.info(
        "execution_audit",
        trace_id=trace_id,
        execution_id=execution_id,
        prompt_id=prompt_id,
        prompt_version=prompt_version,
        system_id=system_id,
        decision=decision,
        reason_codes=reason_codes or [],
        **safe_kwargs,
    )


def log_admin_audit(
    trace_id: str,
    actor_user_id: str,
    actor_role: str,
    action: str,
    target: Optional[Dict[str, Any]] = None,
    auth_strength: Optional[str] = None,
    reason: Optional[str] = None,
) -> None:
    """Log admin action audit (metadata only)."""
    logger.info(
        "admin_audit",
        trace_id=trace_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        action=action,
        target=target or {},
        auth_strength=auth_strength,
        reason=reason,
    )


def log_guard_decision(
    trace_id: str,
    guard_type: str,  # precheck|postcheck
    decision: str,  # allow|block|redact|flag
    rule_ids: list = None,
    reason_codes: list = None,
    **metadata,
) -> None:
    """Log RAI Guard decision (metadata only)."""
    logger.info(
        "guard_decision",
        trace_id=trace_id,
        guard_type=guard_type,
        decision=decision,
        rule_ids=rule_ids or [],
        reason_codes=reason_codes or [],
        **metadata,
    )


def log_siem_event(
    trace_id: str, event_type: str, decision: str, metadata: Dict[str, Any]
) -> None:
    """Forward metadata-only event to SIEM."""
    if settings.siem_endpoint:
        # In production, this would forward to actual SIEM
        # For now, log with siem_event marker
        logger.info(
            "siem_event",
            trace_id=trace_id,
            event_type=event_type,
            decision=decision,
            metadata=metadata,
        )
