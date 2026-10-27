"""Main application factory for RAI Gateway."""

from fastapi import FastAPI

from rai_gateway.core.config import settings
from rai_gateway.core.database import init_db
from rai_gateway.core.observability import instrument_app, logger, setup_telemetry
from rai_gateway.services.llm_controller import app as llm_controller_app


def create_app() -> FastAPI:
    """Create and configure the RAI Gateway application."""

    # For now, we'll use the LLM Controller as the main app
    # In a full microservices deployment, this would be the API Gateway
    app = llm_controller_app

    @app.on_event("startup")
    async def startup_event():
        """Initialize application."""
        # Phase 21: Validate production security configuration
        from rai_gateway.core.security_config import enforce_production_security

        try:
            enforce_production_security(environment=settings.environment)
        except Exception as e:
            logger.error(
                "security_validation_failed",
                error=str(e),
                environment=settings.environment,
            )
            # Re-raise to prevent startup in production with insecure config
            raise

        setup_telemetry()
        instrument_app(app)
        try:
            init_db()
        except Exception:
            logger.warning("database_not_ready_at_startup")
        logger.info(
            "rai_gateway_started",
            version="0.1.0",
            environment=settings.environment,
        )

    return app


# Create app instance
app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "rai_gateway.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level=settings.log_level.lower(),
    )
