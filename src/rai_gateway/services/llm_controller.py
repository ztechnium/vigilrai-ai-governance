"""LLM Controller API - Central orchestration service."""

import hashlib
import uuid
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from rai_gateway.approval.api import router as approval_router
from rai_gateway.auth.api import router as auth_router
from rai_gateway.client_hooks.api import router as client_hooks_router
from rai_gateway.core.auth import ApiKeyContext, get_api_key_context
from rai_gateway.core.config import settings
from rai_gateway.core.database import SessionLocal, get_db, init_db
from rai_gateway.core.errors import (
    ErrorResponse,
    GuardUnavailableError,
    InputBlockedError,
    NotAllowedError,
    OutputBlockedError,
    PromptNotFoundError,
    RaiException,
)
from rai_gateway.core.health import router as health_router
from rai_gateway.core.observability import (
    generate_trace_id,
    get_current_trace_id,
    instrument_app,
    log_siem_event,
    logger,
    setup_telemetry,
)
from rai_gateway.core.security_api import router as security_router
from rai_gateway.data_access.api import router as data_access_router
from rai_gateway.evaluations.api import router as evaluations_router
from rai_gateway.evidence.api import router as evidence_router
from rai_gateway.finops.api import router as finops_router
from rai_gateway.governance.api import router as governance_router
from rai_gateway.identity.api import router as identity_router
from rai_gateway.lineage.api import router as lineage_router
from rai_gateway.models.database import Case, ExecutionAudit
from rai_gateway.policy.api import router as policy_router
from rai_gateway.portfolio.api import router as portfolio_router
from rai_gateway.public_product.welcome_api import router as welcome_router
from rai_gateway.registry.api import router as registry_router
from rai_gateway.reporting.api import router as reporting_router
from rai_gateway.risk_intelligence.api import router as risk_intelligence_router
from rai_gateway.runtime_enforcement.api import router as runtime_enforcement_router
from rai_gateway.sdk.api import admin_router as productization_admin_router
from rai_gateway.sdk.api import router as sdk_router
from rai_gateway.services.admin_console import router as admin_router
from rai_gateway.services.llm_providers import get_llm_provider
from rai_gateway.services.prompt_catalog import PromptCatalogService
from rai_gateway.services.provider_settings_store import (
    load_provider_settings_into_runtime,
)
from rai_gateway.services.rai_guard import RaiGuardService

app = FastAPI(
    title="RAI Gateway - LLM Controller",
    description="Central orchestration service for responsible AI governance",
    version="0.1.0",
)

# Release 1 Option A: built-in admin console (token-gated)
app.include_router(admin_router)
app.include_router(auth_router)
app.include_router(registry_router)
app.include_router(identity_router)
app.include_router(approval_router)
app.include_router(policy_router)
app.include_router(runtime_enforcement_router)
app.include_router(client_hooks_router)
app.include_router(evidence_router)
app.include_router(risk_intelligence_router)
app.include_router(evaluations_router)
app.include_router(governance_router)
app.include_router(portfolio_router)
app.include_router(reporting_router)
app.include_router(sdk_router)
app.include_router(productization_admin_router)
app.include_router(data_access_router)
app.include_router(finops_router)
app.include_router(lineage_router)
app.include_router(welcome_router)
app.include_router(health_router)
app.include_router(security_router)


# Setup CORS (Phase 23: Environment-driven configuration)
def _split_cors_list(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


# The control-plane UI sends these on browser fetches. Omitting any of them
# makes Starlette reject the preflight with 400 ("Disallowed CORS headers").
_BROWSER_CORS_HEADERS = (
    "Content-Type",
    "Authorization",
    "X-CSRF-Token",
    "X-Admin-Token",
    # Enforcement test console posts the runtime credential from the browser.
    "X-RAI-Agent-Key",
)


def _cors_header_list(value: str) -> list[str]:
    if value.strip() == "*":
        return ["*"]
    configured = _split_cors_list(value)
    seen = {header.lower() for header in configured}
    for header in _BROWSER_CORS_HEADERS:
        if header.lower() not in seen:
            configured.append(header)
            seen.add(header.lower())
    return configured


_cors_origins = (
    _split_cors_list(settings.cors_allowed_origins)
    if settings.cors_allowed_origins != "*"
    else ["*"]
)
_cors_methods = (
    _split_cors_list(settings.cors_allow_methods)
    if settings.cors_allow_methods != "*"
    else ["*"]
)
_cors_headers = _cors_header_list(settings.cors_allow_headers)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=_cors_methods,
    allow_headers=_cors_headers,
    max_age=settings.cors_max_age,
)


@app.middleware("http")
async def bind_request_context(request: Request, call_next):
    """Expose the current Request to imperative auth helpers.

    FastAPI Depends() runs in a copied ContextVar context, so identity stored
    only in a ContextVar inside require_admin is invisible to route bodies.
    Middleware-bound request.state is visible to both.
    """
    from rai_gateway.services.admin_console import (
        bind_current_request,
        reset_current_request,
    )

    token = bind_current_request(request)
    try:
        return await call_next(request)
    finally:
        reset_current_request(token)


def _provider_candidates(prompt_config: Dict[str, Any]) -> List[Dict[str, str]]:
    """Resolve provider/model candidate chain from prompt model policy.

    Priority:
    1. prompt_version.model_policy.provider + default_model
    2. runtime defaults from settings
    3. hard fallback to openai + configured default model
    """
    model_policy = prompt_config.get("model_policy") or {}
    configured_provider = model_policy.get("provider") or getattr(
        settings, "llm_provider", "openai"
    )
    configured_model = model_policy.get("default_model") or settings.llm_provider_model

    candidates: List[Dict[str, str]] = []

    if configured_provider == "auto":
        auto_chain: List[Dict[str, str]] = []
        if settings.llm_provider_api_key:
            auto_chain.append(
                {"provider": "openai", "model": settings.llm_provider_model}
            )
        if settings.anthropic_api_key:
            auto_chain.append(
                {"provider": "anthropic", "model": "claude-3-5-sonnet-20241022"}
            )
        if (
            settings.azure_openai_api_key
            and settings.azure_openai_endpoint
            and settings.azure_openai_deployment
        ):
            auto_chain.append(
                {"provider": "azure_openai", "model": settings.azure_openai_deployment}
            )
        if settings.gcp_project_id:
            auto_chain.append({"provider": "vertex", "model": "gemini-1.5-pro-001"})
        if settings.aws_region:
            auto_chain.append(
                {
                    "provider": "bedrock",
                    "model": "anthropic.claude-3-sonnet-20240229-v1:0",
                }
            )
        if settings.ollama_endpoint:
            auto_chain.append({"provider": "ollama", "model": "llama3"})
        candidates.extend(auto_chain)
    else:
        candidates.append({"provider": configured_provider, "model": configured_model})

    for item in model_policy.get("fallback_providers", []):
        provider_name = item.get("provider")
        model_name = item.get("model") or settings.llm_provider_model
        if provider_name:
            candidates.append({"provider": provider_name, "model": model_name})

    # Guarantee at least one terminal fallback.
    if not any(c["provider"] == "openai" for c in candidates):
        candidates.append({"provider": "openai", "model": settings.llm_provider_model})

    return candidates


class ExecuteRequest(BaseModel):
    """Request model for /v1/execute endpoint."""

    prompt_id: str = Field(..., min_length=1)
    prompt_version: int = Field(..., ge=1)
    system_id: str = Field(..., min_length=1)
    module: str = Field(..., min_length=1)
    variables: Dict[str, Any]
    system_user_id: Optional[str] = None
    objective: Optional[str] = None
    trace_id: Optional[str] = None


class ExecuteResponse(BaseModel):
    """Response model for /v1/execute endpoint."""

    execution_id: str
    output: str
    decision: str
    reason_codes: List[str] = []
    trace_id: str
    citations_refs: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = {}


def _is_sensitive(reason_codes: list[str]) -> bool:
    return any(code.startswith("pii_") for code in reason_codes)


def _create_case(db: Session, execution_id: str, reason_codes: list[str]):
    case = Case(
        execution_id=execution_id,
        reason_codes=reason_codes,
        status="open",
    )
    db.add(case)
    db.commit()
    return case.case_id


@app.exception_handler(RaiException)
async def rai_exception_handler(request: Request, exc: RaiException):
    """Handle RAI Gateway exceptions with standardized responses."""
    error_response = ErrorResponse(
        error=exc.error_code,
        message=exc.message,
        reason_codes=exc.reason_codes,
        trace_id=exc.trace_id or get_current_trace_id(),
        details=exc.details,
    )

    # Log error for monitoring
    logger.error(
        "rai_exception",
        error_code=exc.error_code,
        message=exc.message,
        trace_id=error_response.trace_id,
        reason_codes=exc.reason_codes,
    )

    return JSONResponse(status_code=exc.http_status, content=error_response.dict())


@app.middleware("http")
async def trace_id_middleware(request: Request, call_next):
    """Ensure every request has a trace_id."""
    trace_id = request.headers.get("X-Trace-Id") or generate_trace_id()
    request.state.trace_id = trace_id

    # Add trace_id to response headers
    response = await call_next(request)
    response.headers["X-Trace-Id"] = trace_id
    return response


@app.on_event("startup")
async def startup_event():
    """Initialize application on startup."""
    setup_telemetry()
    instrument_app(app)
    init_db()
    db = SessionLocal()
    try:
        loaded = load_provider_settings_into_runtime(db, bootstrap_from_runtime=True)
        if loaded:
            logger.info("provider_settings_loaded", keys=sorted(list(loaded.keys())))
    finally:
        db.close()
    logger.info("LLM Controller started", version="0.1.0")


@app.post("/v1/execute", response_model=ExecuteResponse)
async def execute_prompt(
    request: ExecuteRequest,
    http_request: Request,
    api_key_ctx: ApiKeyContext | None = Depends(get_api_key_context),
    db: Session = Depends(get_db),
):
    """
    Execute a prompt with full RAI governance pipeline.

    This is the main execution flow that implements the deterministic
    orchestration documented in the architecture diagrams.
    """
    trace_id = http_request.state.trace_id
    execution_id = str(uuid.uuid4())
    classification_tags: list[str] = []
    classification_level: Optional[str] = None
    citations_refs: Optional[Dict[str, Any]] = None
    llm_result: Dict[str, Any] = {}
    provider_name = "openai"

    try:
        # Auth binding: if API key auth is enabled, the key's system_id must match
        # the request system_id. This prevents a key from impersonating another tenant.
        if api_key_ctx and api_key_ctx.system_id != request.system_id:
            raise NotAllowedError(
                "API key not allowed for requested system_id",
                trace_id=trace_id,
            )

        # Step 1: Resolve prompt and validate allowlist
        prompt_catalog = PromptCatalogService(db)
        prompt_config = await prompt_catalog.resolve_prompt(
            request.prompt_id, request.prompt_version, trace_id
        )

        if not prompt_config:
            raise PromptNotFoundError(
                f"Prompt {request.prompt_id}:{request.prompt_version} not found",
                trace_id=trace_id,
            )

        # Step 2: Allowlist enforcement (fail-closed)
        is_allowed = await prompt_catalog.check_allowlist(
            request.prompt_id,
            request.prompt_version,
            request.system_id,
            request.module,
            trace_id,
        )

        if not is_allowed:
            raise NotAllowedError(
                f"System {request.system_id}:{request.module} not allowed for prompt",
                trace_id=trace_id,
            )

        # Step 3: Input classification and hashing
        input_hash = hashlib.sha256(str(request.variables).encode("utf-8")).hexdigest()

        # Step 4: RAI Guard Precheck
        rai_guard = RaiGuardService()
        try:
            precheck_result = await rai_guard.precheck(
                prompt_config=prompt_config,
                input_vars=request.variables,
                trace_id=trace_id,
            )
        except Exception as exc:
            logger.error("guard_unavailable", trace_id=trace_id, error=str(exc))
            audit_record = ExecutionAudit(
                execution_id=execution_id,
                trace_id=trace_id,
                prompt_id=request.prompt_id,
                prompt_version=request.prompt_version,
                system_id=request.system_id,
                system_user_id=request.system_user_id,
                module=request.module,
                objective=request.objective,
                input_hash=input_hash,
                output_hash=None,
                decision="block",
                reason_codes=["guard_unavailable"],
                rule_ids=["guard_unavailable"],
                policy_version="v1.0",
                guard_version="v1.0",
                llm_model=settings.llm_provider_model,
                cache_hit=False,
            )
            db.add(audit_record)
            db.commit()
            raise GuardUnavailableError(trace_id=trace_id)

        if precheck_result.decision == "uncertain":
            audit_record = ExecutionAudit(
                execution_id=execution_id,
                trace_id=trace_id,
                prompt_id=request.prompt_id,
                prompt_version=request.prompt_version,
                system_id=request.system_id,
                system_user_id=request.system_user_id,
                module=request.module,
                objective=request.objective,
                input_hash=input_hash,
                output_hash=None,
                decision="block",
                reason_codes=precheck_result.reason_codes or ["guard_unavailable"],
                rule_ids=precheck_result.rule_ids or ["guard_unavailable"],
                policy_version="v1.0",
                guard_version="v1.0",
                llm_model=settings.llm_provider_model,
                cache_hit=False,
            )
            db.add(audit_record)
            db.commit()
            raise GuardUnavailableError(
                trace_id=trace_id,
                reason_codes=precheck_result.reason_codes,
            )

        classification_tags = precheck_result.reason_codes or []
        if _is_sensitive(classification_tags):
            classification_level = "sensitive"

        if precheck_result.decision == "block":
            # Create case if enabled
            audit_record = ExecutionAudit(
                execution_id=execution_id,
                trace_id=trace_id,
                prompt_id=request.prompt_id,
                prompt_version=request.prompt_version,
                system_id=request.system_id,
                system_user_id=request.system_user_id,
                module=request.module,
                objective=request.objective,
                input_hash=input_hash,
                output_hash=None,
                decision="block",
                reason_codes=precheck_result.reason_codes,
                rule_ids=precheck_result.rule_ids,
                policy_version="v1.0",
                guard_version="v1.0",
                llm_model=settings.llm_provider_model,
                cache_hit=False,
                classification_level=classification_level,
                classification_tags=classification_tags,
            )
            db.add(audit_record)
            db.commit()

            if settings.enable_cases:
                case_id = _create_case(db, execution_id, precheck_result.reason_codes)
                audit_record.case_id = case_id
                db.commit()

            raise InputBlockedError(
                "Input blocked by policy",
                reason_codes=precheck_result.reason_codes,
                trace_id=trace_id,
            )

        # Step 5: Check cache (if enabled and eligible)
        cache_hit = False
        output = None

        cache_allowed = not _is_sensitive(classification_tags)
        if (
            settings.enable_cache
            and cache_allowed
            and prompt_config.get("cache_policy", {}).get("enabled", False)
        ):
            # TODO: Implement cache lookup
            pass

        # Step 6: LLM Generation (if not cached)
        if not cache_hit:
            rag_policy = prompt_config.get("rag_policy", {})
            rag_required = bool(rag_policy.get("enabled", False))
            if rag_required and not settings.enable_rag:
                audit_record = ExecutionAudit(
                    execution_id=execution_id,
                    trace_id=trace_id,
                    prompt_id=request.prompt_id,
                    prompt_version=request.prompt_version,
                    system_id=request.system_id,
                    system_user_id=request.system_user_id,
                    module=request.module,
                    objective=request.objective,
                    input_hash=input_hash,
                    output_hash=None,
                    decision="block",
                    reason_codes=["rag_required_disabled"],
                    rule_ids=["rag_required_disabled"],
                    policy_version="v1.0",
                    guard_version="v1.0",
                    llm_model=settings.llm_provider_model,
                    cache_hit=False,
                    classification_level=classification_level,
                    classification_tags=classification_tags,
                )
                db.add(audit_record)
                db.commit()
                raise NotAllowedError(
                    "RAG required but disabled",
                    trace_id=trace_id,
                )

            resolved_provider = "openai"
            llm_model = settings.llm_provider_model
            last_provider_error: Optional[Exception] = None
            for candidate in _provider_candidates(prompt_config):
                resolved_provider = candidate["provider"]
                llm_model = candidate["model"]
                try:
                    provider = get_llm_provider(resolved_provider)
                    llm_result = await provider.generate(
                        prompt=prompt_config["template"],
                        variables=request.variables,
                        model=llm_model,
                    )
                    output = llm_result["output"]
                    citations_refs = llm_result.get("citations_refs") or llm_result.get(
                        "citations"
                    )
                    break
                except Exception as provider_exc:  # noqa: PERF203
                    last_provider_error = provider_exc
                    logger.warning(
                        "provider_generation_failed",
                        trace_id=trace_id,
                        provider=resolved_provider,
                        model=llm_model,
                        error=str(provider_exc),
                    )

            if output is None:
                raise RuntimeError(
                    f"All LLM providers failed; last error: {last_provider_error}"
                )
            provider_name = resolved_provider

            if rag_policy.get("enabled", False) and rag_policy.get(
                "require_citations", True
            ):
                if not citations_refs:
                    audit_record = ExecutionAudit(
                        execution_id=execution_id,
                        trace_id=trace_id,
                        prompt_id=request.prompt_id,
                        prompt_version=request.prompt_version,
                        system_id=request.system_id,
                        system_user_id=request.system_user_id,
                        module=request.module,
                        objective=request.objective,
                        input_hash=input_hash,
                        output_hash=hashlib.sha256(output.encode("utf-8")).hexdigest(),
                        decision="block",
                        reason_codes=["rag_citations_missing"],
                        rule_ids=["rag_citations_missing"],
                        policy_version="v1.0",
                        guard_version="v1.0",
                        llm_model=llm_result.get("model", llm_model),
                        cache_hit=False,
                        citations_refs=None,
                        classification_level=classification_level,
                        classification_tags=classification_tags,
                    )
                    db.add(audit_record)
                    db.commit()
                    if settings.enable_cases:
                        case_id = _create_case(
                            db, execution_id, ["rag_citations_missing"]
                        )
                        audit_record.case_id = case_id
                        db.commit()
                    raise OutputBlockedError(
                        "Citations required for RAG responses",
                        reason_codes=["rag_citations_missing"],
                        trace_id=trace_id,
                    )

        # Step 7: Output classification and RAI Guard Postcheck
        output_hash = hashlib.sha256(output.encode("utf-8")).hexdigest()

        try:
            postcheck_result = await rai_guard.postcheck(
                output=output,
                prompt_config=prompt_config,
                trace_id=trace_id,
            )
        except Exception as exc:
            logger.error("guard_unavailable", trace_id=trace_id, error=str(exc))
            audit_record = ExecutionAudit(
                execution_id=execution_id,
                trace_id=trace_id,
                prompt_id=request.prompt_id,
                prompt_version=request.prompt_version,
                system_id=request.system_id,
                system_user_id=request.system_user_id,
                module=request.module,
                objective=request.objective,
                input_hash=input_hash,
                output_hash=hashlib.sha256(output.encode("utf-8")).hexdigest(),
                decision="block",
                reason_codes=["guard_unavailable"],
                rule_ids=["guard_unavailable"],
                policy_version="v1.0",
                guard_version="v1.0",
                llm_model=llm_result.get("model")
                if llm_result
                else settings.llm_provider_model,
                cache_hit=cache_hit,
                citations_refs=citations_refs,
                classification_level=classification_level,
                classification_tags=classification_tags,
            )
            db.add(audit_record)
            db.commit()
            raise GuardUnavailableError(trace_id=trace_id)

        if postcheck_result.decision == "uncertain":
            audit_record = ExecutionAudit(
                execution_id=execution_id,
                trace_id=trace_id,
                prompt_id=request.prompt_id,
                prompt_version=request.prompt_version,
                system_id=request.system_id,
                system_user_id=request.system_user_id,
                module=request.module,
                objective=request.objective,
                input_hash=input_hash,
                output_hash=hashlib.sha256(output.encode("utf-8")).hexdigest(),
                decision="block",
                reason_codes=postcheck_result.reason_codes or ["guard_unavailable"],
                rule_ids=postcheck_result.rule_ids or ["guard_unavailable"],
                policy_version="v1.0",
                guard_version="v1.0",
                llm_model=llm_result.get("model")
                if llm_result
                else settings.llm_provider_model,
                cache_hit=cache_hit,
                citations_refs=citations_refs,
                classification_level=classification_level,
                classification_tags=classification_tags,
            )
            db.add(audit_record)
            db.commit()
            raise GuardUnavailableError(
                trace_id=trace_id,
                reason_codes=postcheck_result.reason_codes,
            )

        if postcheck_result.decision in {"block", "flag", "redact"}:
            output_hash = hashlib.sha256(output.encode("utf-8")).hexdigest()
            audit_record = ExecutionAudit(
                execution_id=execution_id,
                trace_id=trace_id,
                prompt_id=request.prompt_id,
                prompt_version=request.prompt_version,
                system_id=request.system_id,
                system_user_id=request.system_user_id,
                module=request.module,
                objective=request.objective,
                input_hash=input_hash,
                output_hash=output_hash,
                decision=postcheck_result.decision,
                reason_codes=postcheck_result.reason_codes,
                rule_ids=postcheck_result.rule_ids,
                policy_version="v1.0",
                guard_version="v1.0",
                llm_model=llm_result.get("model")
                if llm_result
                else settings.llm_provider_model,
                cache_hit=cache_hit,
                citations_refs=citations_refs,
                classification_level=classification_level,
                classification_tags=classification_tags,
            )
            db.add(audit_record)
            db.commit()

            if settings.enable_cases:
                case_id = _create_case(db, execution_id, postcheck_result.reason_codes)
                audit_record.case_id = case_id
                db.commit()

            if postcheck_result.decision == "redact":
                output = "[REDACTED]"
                return ExecuteResponse(
                    execution_id=execution_id,
                    output=output,
                    decision="redact",
                    trace_id=trace_id,
                    citations_refs=citations_refs,
                    metadata={
                        "llm_model": llm_result.get(
                            "model", settings.llm_provider_model
                        ),
                        "cache_hit": cache_hit,
                        "provider": llm_result.get("provider", provider_name),
                        "usage": llm_result.get("usage", {}),
                    },
                )

            raise OutputBlockedError(
                "Output blocked by policy",
                reason_codes=postcheck_result.reason_codes,
                trace_id=trace_id,
            )

        # Step 8: Store execution audit (metadata only)
        audit_record = ExecutionAudit(
            execution_id=execution_id,
            trace_id=trace_id,
            prompt_id=request.prompt_id,
            prompt_version=request.prompt_version,
            system_id=request.system_id,
            system_user_id=request.system_user_id,
            module=request.module,
            objective=request.objective,
            input_hash=input_hash,
            output_hash=output_hash,
            decision="allow",
            reason_codes=precheck_result.reason_codes + postcheck_result.reason_codes,
            rule_ids=precheck_result.rule_ids + postcheck_result.rule_ids,
            policy_version="v1.0",
            guard_version="v1.0",
            llm_model=llm_result.get("model")
            if llm_result
            else settings.llm_provider_model,
            cache_hit=cache_hit,
            citations_refs=citations_refs,
            classification_level=classification_level,
            classification_tags=classification_tags,
        )

        db.add(audit_record)
        db.commit()

        # Step 9: Log to SIEM (metadata only)
        log_siem_event(
            trace_id=trace_id,
            event_type="execution_complete",
            decision="allow",
            metadata={
                "execution_id": execution_id,
                "prompt_id": request.prompt_id,
                "system_id": request.system_id,
                "cache_hit": cache_hit,
            },
        )

        return ExecuteResponse(
            execution_id=execution_id,
            output=output,
            decision="allow",
            trace_id=trace_id,
            citations_refs=citations_refs,
            metadata={
                "llm_model": llm_result.get("model", settings.llm_provider_model),
                "cache_hit": cache_hit,
                "provider": llm_result.get("provider", provider_name),
                "usage": llm_result.get("usage", {}),
            },
        )

    except RaiException:
        # Re-raise RAI exceptions to be handled by exception handler
        raise
    except Exception as e:
        # Log unexpected errors and convert to execution failed
        logger.error(
            "execution_failed",
            trace_id=trace_id,
            execution_id=execution_id,
            error=str(e),
        )

        raise RaiException(
            error_code="EXECUTION_FAILED",
            message="Internal execution error",
            trace_id=trace_id,
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
