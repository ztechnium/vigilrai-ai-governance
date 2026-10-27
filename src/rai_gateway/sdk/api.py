"""Public /sdk/v1 integration API + admin productization endpoints."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import rai_gateway.models.productization  # noqa: F401
from rai_gateway.core.authorization import require_permission
from rai_gateway.core.database import get_db
from rai_gateway.core.tenant_context import TenantContext
from rai_gateway.sdk.errors import SdkError
from rai_gateway.sdk.jobs import JobQueue
from rai_gateway.sdk.service import SdkService
from rai_gateway.sdk.webhooks import WebhookService

router = APIRouter(prefix="/sdk/v1", tags=["sdk-v1"])
admin_router = APIRouter(
    prefix="/v1/productization",
    tags=["productization"],
)


def _extract_runtime_secret(
    x_rai_agent_key: str | None,
    authorization: str | None,
) -> tuple[str | None, str | None]:
    """Return (api_key_secret, bearer_token)."""
    secret = x_rai_agent_key
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        if not secret:
            secret = token
    return secret, token


def _sdk_http(exc: SdkError) -> HTTPException:
    return HTTPException(status_code=exc.http_status, detail=exc.to_dict())


# Trusted ingress proof for mTLS identity forwarding (private network / authenticated proxy).
MTLS_PROXY_HEADER = "X-RAI-Trusted-Proxy"


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class StartSessionBody(BaseModel):
    integration_id: UUID
    external_session_id: str | None = None
    external_conversation_id: str | None = None
    principal: str | None = None
    channel: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    delegation_id: UUID | None = None
    allow_ended_session_reuse: bool = False


class ObserveInputBody(BaseModel):
    content: str | None = None
    content_type: str = "text"
    observed_model: str | None = None
    principal: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuthorizeActionBody(BaseModel):
    tool: str | None = None
    tool_id: UUID | None = None
    target: dict[str, Any] | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    amount: float | None = None
    currency: str | None = None
    idempotency_key: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    approval_request_id: UUID | None = None


class ReportExecutionBody(BaseModel):
    status: str
    external_execution_id: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    result_metadata: dict[str, Any] = Field(default_factory=dict)
    error_metadata: dict[str, Any] | None = None
    usage: dict[str, Any] | None = None
    cost: dict[str, Any] | None = None


class MeteringSpanBody(BaseModel):
    span_type: str = "MODEL_CALL"
    operation: str | None = None
    provider: str | None = None
    model: str | None = None
    usage: dict[str, Any] | None = None
    cost: dict[str, Any] | None = None
    started_at: str | None = None
    completed_at: str | None = None
    external_span_id: str | None = None
    parent_span_id: UUID | None = None
    trajectory_id: UUID | None = None
    metadata: dict[str, Any] | None = None
    tokens_are_estimated: bool = False


class ObserveOutputBody(BaseModel):
    content: str | None = None
    content_type: str = "text"
    observed_model: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuthorizeDataAccessBody(BaseModel):
    resource: str = Field(..., min_length=1)
    fields: list[str] = Field(default_factory=list)
    payload: dict[str, Any] | list[Any] | None = None
    purpose: str | None = None
    access_mode: str = "READ"
    data_source_id: UUID | None = None
    tool_id: UUID | None = None
    target: str | None = None
    row_filter: dict[str, Any] = Field(default_factory=dict)


class HeartbeatBody(BaseModel):
    integration_id: UUID
    sdk_version: str | None = None
    protocol_version: int | None = None
    capability_matrix: dict[str, bool] | None = None


class CreateIntegrationBody(BaseModel):
    integration_key: str
    name: str
    runtime_identity_id: UUID
    integration_type: str = "SDK"
    environment: str = "production"
    auth_method: str = "API_KEY"
    enforcement_mode: str = "HOOK_ENFORCED"
    fail_closed: bool = True
    capability_matrix: dict[str, bool] | None = None
    oidc_issuer: str | None = None
    oidc_audience: str | None = None
    metadata: dict[str, Any] | None = None


class BindOidcBody(BaseModel):
    runtime_identity_id: UUID
    issuer: str
    audience: str
    subject: str


class WebhookCreateBody(BaseModel):
    name: str
    url: str
    event_types: list[str]


class EnqueueJobBody(BaseModel):
    job_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = None


# ---------------------------------------------------------------------------
# Public SDK endpoints
# ---------------------------------------------------------------------------


@router.get("/health")
def sdk_health(db: Session = Depends(get_db)):
    return SdkService(db).health()


@router.post("/sessions")
def start_session(
    body: StartSessionBody,
    db: Session = Depends(get_db),
    x_rai_agent_key: str | None = Header(default=None, alias="X-RAI-Agent-Key"),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_rai_mtls_identity: str | None = Header(default=None, alias="X-RAI-MTLS-Identity"),
    x_rai_trusted_proxy: str | None = Header(default=None, alias="X-RAI-Trusted-Proxy"),
):
    secret, token = _extract_runtime_secret(x_rai_agent_key, authorization)
    svc = SdkService(db)
    try:
        auth = svc.authenticate(
            secret=secret,
            token=token,
            mtls_identity=x_rai_mtls_identity,
            mtls_proxy_authorization=x_rai_trusted_proxy,
            integration_id=body.integration_id,
        )
        return svc.start_session(
            auth,
            integration_id=body.integration_id,
            external_session_id=body.external_session_id,
            external_conversation_id=body.external_conversation_id,
            principal=body.principal,
            channel=body.channel,
            metadata=body.metadata,
            delegation_id=body.delegation_id,
            allow_ended_session_reuse=body.allow_ended_session_reuse,
        )
    except SdkError as exc:
        raise _sdk_http(exc) from exc


@router.post("/sessions/{session_id}/input")
def observe_input(
    session_id: UUID,
    body: ObserveInputBody,
    db: Session = Depends(get_db),
    x_rai_agent_key: str | None = Header(default=None, alias="X-RAI-Agent-Key"),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_rai_mtls_identity: str | None = Header(default=None, alias="X-RAI-MTLS-Identity"),
    x_rai_trusted_proxy: str | None = Header(default=None, alias="X-RAI-Trusted-Proxy"),
):
    secret, token = _extract_runtime_secret(x_rai_agent_key, authorization)
    svc = SdkService(db)
    try:
        auth = svc.authenticate(
            secret=secret,
            token=token,
            mtls_identity=x_rai_mtls_identity,
            mtls_proxy_authorization=x_rai_trusted_proxy,
        )
        return svc.observe_input(
            auth,
            session_id=session_id,
            content=body.content,
            content_type=body.content_type,
            observed_model=body.observed_model,
            principal=body.principal,
            metadata=body.metadata,
        )
    except SdkError as exc:
        raise _sdk_http(exc) from exc


@router.post("/sessions/{session_id}/actions/authorize")
def authorize_action(
    session_id: UUID,
    body: AuthorizeActionBody,
    db: Session = Depends(get_db),
    x_rai_agent_key: str | None = Header(default=None, alias="X-RAI-Agent-Key"),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_rai_mtls_identity: str | None = Header(default=None, alias="X-RAI-MTLS-Identity"),
    x_rai_trusted_proxy: str | None = Header(default=None, alias="X-RAI-Trusted-Proxy"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    secret, token = _extract_runtime_secret(x_rai_agent_key, authorization)
    svc = SdkService(db)
    try:
        auth = svc.authenticate(
            secret=secret,
            token=token,
            mtls_identity=x_rai_mtls_identity,
            mtls_proxy_authorization=x_rai_trusted_proxy,
        )
        return svc.authorize_action(
            auth,
            session_id=session_id,
            credential_secret=secret,
            tool=body.tool,
            tool_id=body.tool_id,
            target=body.target,
            parameters=body.parameters,
            amount=body.amount,
            currency=body.currency,
            idempotency_key=body.idempotency_key or idempotency_key,
            metadata=body.metadata,
            approval_request_id=body.approval_request_id,
        )
    except SdkError as exc:
        raise _sdk_http(exc) from exc


@router.post("/actions/{decision_id}/execution")
def report_execution(
    decision_id: UUID,
    body: ReportExecutionBody,
    db: Session = Depends(get_db),
    x_rai_agent_key: str | None = Header(default=None, alias="X-RAI-Agent-Key"),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_rai_mtls_identity: str | None = Header(default=None, alias="X-RAI-MTLS-Identity"),
    x_rai_trusted_proxy: str | None = Header(default=None, alias="X-RAI-Trusted-Proxy"),
):
    secret, token = _extract_runtime_secret(x_rai_agent_key, authorization)
    svc = SdkService(db)
    try:
        auth = svc.authenticate(
            secret=secret,
            token=token,
            mtls_identity=x_rai_mtls_identity,
            mtls_proxy_authorization=x_rai_trusted_proxy,
        )
        return svc.report_execution(
            auth,
            decision_id=decision_id,
            status=body.status,
            external_execution_id=body.external_execution_id,
            started_at=body.started_at,
            completed_at=body.completed_at,
            result_metadata=body.result_metadata,
            error_metadata=body.error_metadata,
            usage=body.usage,
            cost=body.cost,
        )
    except SdkError as exc:
        raise _sdk_http(exc) from exc


@router.post("/sessions/{session_id}/metering/spans")
def record_metering_span(
    session_id: UUID,
    body: MeteringSpanBody,
    db: Session = Depends(get_db),
    x_rai_agent_key: str | None = Header(default=None, alias="X-RAI-Agent-Key"),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_rai_mtls_identity: str | None = Header(default=None, alias="X-RAI-MTLS-Identity"),
    x_rai_trusted_proxy: str | None = Header(default=None, alias="X-RAI-Trusted-Proxy"),
):
    secret, token = _extract_runtime_secret(x_rai_agent_key, authorization)
    svc = SdkService(db)
    try:
        auth = svc.authenticate(
            secret=secret,
            token=token,
            mtls_identity=x_rai_mtls_identity,
            mtls_proxy_authorization=x_rai_trusted_proxy,
        )
        return svc.record_metering_span(
            auth, session_id=session_id, body=body.model_dump()
        )
    except SdkError as exc:
        raise _sdk_http(exc) from exc


@router.patch("/sessions/{session_id}/metering/spans/{span_id}")
def complete_metering_span(
    session_id: UUID,
    span_id: UUID,
    body: MeteringSpanBody,
    db: Session = Depends(get_db),
    x_rai_agent_key: str | None = Header(default=None, alias="X-RAI-Agent-Key"),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_rai_mtls_identity: str | None = Header(default=None, alias="X-RAI-MTLS-Identity"),
    x_rai_trusted_proxy: str | None = Header(default=None, alias="X-RAI-Trusted-Proxy"),
):
    secret, token = _extract_runtime_secret(x_rai_agent_key, authorization)
    svc = SdkService(db)
    try:
        auth = svc.authenticate(
            secret=secret,
            token=token,
            mtls_identity=x_rai_mtls_identity,
            mtls_proxy_authorization=x_rai_trusted_proxy,
        )
        return svc.complete_metering_span(
            auth, session_id=session_id, span_id=span_id, body=body.model_dump()
        )
    except SdkError as exc:
        raise _sdk_http(exc) from exc


@router.post("/sessions/{session_id}/data-access/authorize")
def authorize_data_access(
    session_id: UUID,
    body: AuthorizeDataAccessBody,
    db: Session = Depends(get_db),
    x_rai_agent_key: str | None = Header(default=None, alias="X-RAI-Agent-Key"),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_rai_mtls_identity: str | None = Header(default=None, alias="X-RAI-MTLS-Identity"),
    x_rai_trusted_proxy: str | None = Header(default=None, alias="X-RAI-Trusted-Proxy"),
):
    """Authorize and mask data before it reaches the model/agent."""
    secret, token = _extract_runtime_secret(x_rai_agent_key, authorization)
    svc = SdkService(db)
    try:
        auth = svc.authenticate(
            secret=secret,
            token=token,
            mtls_identity=x_rai_mtls_identity,
            mtls_proxy_authorization=x_rai_trusted_proxy,
        )
        return svc.authorize_data_access(
            auth,
            session_id=session_id,
            resource=body.resource,
            fields=body.fields,
            payload=body.payload,
            purpose=body.purpose,
            access_mode=body.access_mode,
            data_source_id=body.data_source_id,
            tool_id=body.tool_id,
            target=body.target,
            row_filter=body.row_filter,
        )
    except SdkError as exc:
        raise _sdk_http(exc) from exc


@router.post("/sessions/{session_id}/output")
def observe_output(
    session_id: UUID,
    body: ObserveOutputBody,
    db: Session = Depends(get_db),
    x_rai_agent_key: str | None = Header(default=None, alias="X-RAI-Agent-Key"),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_rai_mtls_identity: str | None = Header(default=None, alias="X-RAI-MTLS-Identity"),
    x_rai_trusted_proxy: str | None = Header(default=None, alias="X-RAI-Trusted-Proxy"),
):
    secret, token = _extract_runtime_secret(x_rai_agent_key, authorization)
    svc = SdkService(db)
    try:
        auth = svc.authenticate(
            secret=secret,
            token=token,
            mtls_identity=x_rai_mtls_identity,
            mtls_proxy_authorization=x_rai_trusted_proxy,
        )
        return svc.observe_output(
            auth,
            session_id=session_id,
            content=body.content,
            content_type=body.content_type,
            observed_model=body.observed_model,
            metadata=body.metadata,
        )
    except SdkError as exc:
        raise _sdk_http(exc) from exc


@router.post("/sessions/{session_id}/end")
def end_session(
    session_id: UUID,
    db: Session = Depends(get_db),
    x_rai_agent_key: str | None = Header(default=None, alias="X-RAI-Agent-Key"),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_rai_mtls_identity: str | None = Header(default=None, alias="X-RAI-MTLS-Identity"),
    x_rai_trusted_proxy: str | None = Header(default=None, alias="X-RAI-Trusted-Proxy"),
):
    secret, token = _extract_runtime_secret(x_rai_agent_key, authorization)
    svc = SdkService(db)
    try:
        auth = svc.authenticate(
            secret=secret,
            token=token,
            mtls_identity=x_rai_mtls_identity,
            mtls_proxy_authorization=x_rai_trusted_proxy,
        )
        return svc.end_session(auth, session_id=session_id)
    except SdkError as exc:
        raise _sdk_http(exc) from exc


@router.get("/decisions/{decision_id}")
def get_decision(
    decision_id: UUID,
    db: Session = Depends(get_db),
    x_rai_agent_key: str | None = Header(default=None, alias="X-RAI-Agent-Key"),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_rai_mtls_identity: str | None = Header(default=None, alias="X-RAI-MTLS-Identity"),
    x_rai_trusted_proxy: str | None = Header(default=None, alias="X-RAI-Trusted-Proxy"),
):
    secret, token = _extract_runtime_secret(x_rai_agent_key, authorization)
    svc = SdkService(db)
    try:
        auth = svc.authenticate(
            secret=secret,
            token=token,
            mtls_identity=x_rai_mtls_identity,
            mtls_proxy_authorization=x_rai_trusted_proxy,
        )
        return svc.get_decision(auth, decision_id=decision_id)
    except SdkError as exc:
        raise _sdk_http(exc) from exc


@router.get("/approvals/{approval_request_id}")
def get_approval_status(
    approval_request_id: UUID,
    db: Session = Depends(get_db),
    x_rai_agent_key: str | None = Header(default=None, alias="X-RAI-Agent-Key"),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_rai_mtls_identity: str | None = Header(default=None, alias="X-RAI-MTLS-Identity"),
    x_rai_trusted_proxy: str | None = Header(default=None, alias="X-RAI-Trusted-Proxy"),
):
    secret, token = _extract_runtime_secret(x_rai_agent_key, authorization)
    svc = SdkService(db)
    try:
        auth = svc.authenticate(
            secret=secret,
            token=token,
            mtls_identity=x_rai_mtls_identity,
            mtls_proxy_authorization=x_rai_trusted_proxy,
        )
        return svc.get_approval_status(auth, approval_request_id=approval_request_id)
    except SdkError as exc:
        raise _sdk_http(exc) from exc


@router.post("/heartbeat")
def heartbeat(
    body: HeartbeatBody,
    db: Session = Depends(get_db),
    x_rai_agent_key: str | None = Header(default=None, alias="X-RAI-Agent-Key"),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_rai_mtls_identity: str | None = Header(default=None, alias="X-RAI-MTLS-Identity"),
    x_rai_trusted_proxy: str | None = Header(default=None, alias="X-RAI-Trusted-Proxy"),
):
    secret, token = _extract_runtime_secret(x_rai_agent_key, authorization)
    svc = SdkService(db)
    try:
        auth = svc.authenticate(
            secret=secret,
            token=token,
            mtls_identity=x_rai_mtls_identity,
            mtls_proxy_authorization=x_rai_trusted_proxy,
            integration_id=body.integration_id,
        )
        return svc.heartbeat(
            auth,
            integration_id=body.integration_id,
            sdk_version=body.sdk_version,
            protocol_version=body.protocol_version,
            capability_matrix=body.capability_matrix,
        )
    except SdkError as exc:
        raise _sdk_http(exc) from exc


# ---------------------------------------------------------------------------
# Admin productization endpoints
# ---------------------------------------------------------------------------


@admin_router.post("/integrations")
def create_integration(
    body: CreateIntegrationBody,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("sdk:manage")),
):
    svc = SdkService(db)
    try:
        return svc.create_integration(
            integration_key=body.integration_key,
            name=body.name,
            runtime_identity_id=body.runtime_identity_id,
            created_by=tenant.user_id,
            integration_type=body.integration_type,
            environment=body.environment,
            auth_method=body.auth_method,
            enforcement_mode=body.enforcement_mode,
            fail_closed=body.fail_closed,
            capability_matrix=body.capability_matrix,
            oidc_issuer=body.oidc_issuer,
            oidc_audience=body.oidc_audience,
            metadata=body.metadata,
        )
    except SdkError as exc:
        raise _sdk_http(exc) from exc


@admin_router.get("/integrations")
def list_integrations(
    db: Session = Depends(get_db),
    _tenant: TenantContext = Depends(require_permission("sdk:read")),
):
    return {"items": SdkService(db).list_integrations()}


@admin_router.get("/integrations/{integration_id}")
def get_integration(
    integration_id: UUID,
    db: Session = Depends(get_db),
    _tenant: TenantContext = Depends(require_permission("sdk:read")),
):
    try:
        return SdkService(db).get_integration(integration_id)
    except SdkError as exc:
        raise _sdk_http(exc) from exc


@admin_router.post("/oidc-bindings")
def bind_oidc(
    body: BindOidcBody,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("sdk:manage")),
):
    try:
        return SdkService(db).bind_oidc(
            runtime_identity_id=body.runtime_identity_id,
            issuer=body.issuer,
            audience=body.audience,
            subject=body.subject,
            created_by=tenant.user_id,
        )
    except SdkError as exc:
        raise _sdk_http(exc) from exc


@admin_router.get("/onboarding")
def onboarding_checklist(
    db: Session = Depends(get_db),
    _tenant: TenantContext = Depends(require_permission("sdk:read")),
):
    try:
        return SdkService(db).onboarding_checklist()
    except SdkError as exc:
        raise _sdk_http(exc) from exc


class OnboardingPatchBody(BaseModel):
    current_step: str | None = None
    complete_step: str | None = None
    completed_steps: list[str] | None = None
    first_ai_system_id: UUID | None = None
    first_integration_id: UUID | None = None
    first_trajectory_id: UUID | None = None
    status: str | None = None


@admin_router.patch("/onboarding")
def patch_onboarding_checklist(
    body: OnboardingPatchBody,
    db: Session = Depends(get_db),
    _tenant: TenantContext = Depends(require_permission("sdk:manage")),
):
    from rai_gateway.public_product.onboarding import OnboardingError, OnboardingService

    try:
        return OnboardingService(db).update(
            current_step=body.current_step,
            complete_step=body.complete_step,
            completed_steps=body.completed_steps,
            first_ai_system_id=body.first_ai_system_id,
            first_integration_id=body.first_integration_id,
            first_trajectory_id=body.first_trajectory_id,
            status=body.status,
        )
    except OnboardingError as exc:
        raise HTTPException(
            status_code=exc.http_status,
            detail={"error": "INVALID_REQUEST", "message": exc.message},
        ) from exc


@admin_router.post("/webhooks")
def create_webhook(
    body: WebhookCreateBody,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("sdk:manage")),
):
    endpoint, secret = WebhookService(db).create_endpoint(
        name=body.name,
        url=body.url,
        event_types=body.event_types,
        created_by=tenant.user_id,
    )
    return {"endpoint": endpoint, "secret": secret}


@admin_router.get("/webhooks")
def list_webhooks(
    db: Session = Depends(get_db),
    _tenant: TenantContext = Depends(require_permission("sdk:read")),
):
    return {"items": WebhookService(db).list_endpoints()}


@admin_router.get("/webhooks/deliveries")
def list_webhook_deliveries(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _tenant: TenantContext = Depends(require_permission("sdk:read")),
):
    return {"items": WebhookService(db).list_deliveries(limit=limit)}


@admin_router.post("/webhooks/{endpoint_id}/rotate")
def rotate_webhook_secret(
    endpoint_id: UUID,
    db: Session = Depends(get_db),
    _tenant: TenantContext = Depends(require_permission("sdk:manage")),
):
    try:
        endpoint, secret = WebhookService(db).rotate_secret(endpoint_id)
        db.commit()
        return {"endpoint": endpoint, "secret": secret}
    except SdkError as exc:
        raise _sdk_http(exc) from exc


@admin_router.post("/jobs")
def enqueue_job(
    body: EnqueueJobBody,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("sdk:manage")),
):
    return JobQueue(db).enqueue(
        job_type=body.job_type,
        payload=body.payload,
        idempotency_key=body.idempotency_key,
        created_by=tenant.user_id,
    )


@admin_router.get("/jobs")
def list_jobs(
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _tenant: TenantContext = Depends(require_permission("sdk:read")),
):
    return {"items": JobQueue(db).list_jobs(status=status, limit=limit)}
