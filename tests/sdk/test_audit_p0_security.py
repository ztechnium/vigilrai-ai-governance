"""P0 audit gap tests — OIDC fail-closed, mTLS trust, MCP prod, budgets, emergency stop."""

from __future__ import annotations

import base64
import json
import time
import uuid
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwt

from rai_gateway.approval.authorization import (
    STEP_UP_VERIFIED,
    ApproverAuthorizationService,
    ApproverContext,
)
from rai_gateway.approval.domain import (
    ActionTarget,
    ApprovalDenialCode,
    IntegrationType,
    ProposedAction,
)
from rai_gateway.approval.errors import ApprovalDeniedError
from rai_gateway.core.config import settings
from rai_gateway.models.productization import OidcRuntimeBinding
from rai_gateway.models.registry import MCPServer, ToolResource
from rai_gateway.registry.domain import AISystemStatus
from rai_gateway.risk_intelligence.budgets import BudgetService
from rai_gateway.risk_intelligence.domain import (
    BudgetEffect,
    BudgetEnforcementMode,
    BudgetMetric,
    BudgetStatus,
    InterventionAuthorizationMode,
    InterventionEffect,
    RiskScopeType,
    RiskSeverity,
)
from rai_gateway.risk_intelligence.intervention import InterventionService
from rai_gateway.risk_intelligence.risk_engine import RiskEngine
from rai_gateway.runtime_enforcement.adapters.mcp import MCPToolExecutionAdapter
from rai_gateway.sdk.auth import MTLSAuthenticator, OIDCAuthenticator
from rai_gateway.sdk.errors import SdkError
from rai_gateway.sdk.jwks import JwksCache


def _rsa_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_numbers = private_key.public_key().public_numbers()

    def _b64int(val: int) -> str:
        raw = val.to_bytes((val.bit_length() + 7) // 8, "big")
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    jwk = {
        "kty": "RSA",
        "kid": "test-key-1",
        "use": "sig",
        "alg": "RS256",
        "n": _b64int(public_numbers.n),
        "e": _b64int(public_numbers.e),
    }
    return private_pem, {"keys": [jwk]}


def _make_oidc_binding(
    db_session, runtime_stack, *, issuer: str, subject: str, audience: str
):
    binding = OidcRuntimeBinding(
        runtime_identity_id=runtime_stack["identity"].id,
        issuer=issuer,
        audience=audience,
        subject=subject,
        status="ACTIVE",
        created_by="test",
    )
    db_session.add(binding)
    db_session.commit()
    return binding


def test_oidc_rejects_when_jwks_not_configured(db_session, runtime_stack, monkeypatch):
    monkeypatch.setattr(settings, "oidc_jwks_url", None)
    private_pem, _jwks = _rsa_keypair()
    issuer = "https://idp.example.com"
    subject = "runtime-sub-1"
    audience = "rai-runtime"
    _make_oidc_binding(
        db_session, runtime_stack, issuer=issuer, subject=subject, audience=audience
    )
    token = jwt.encode(
        {
            "iss": issuer,
            "sub": subject,
            "aud": audience,
            "exp": int(time.time()) + 600,
        },
        private_pem,
        algorithm="RS256",
        headers={"kid": "test-key-1"},
    )
    auth = OIDCAuthenticator(db_session, jwks_url=None)
    with pytest.raises(SdkError) as exc:
        auth.authenticate(secret=None, token=token)
    assert "JWKS" in exc.value.message


def test_oidc_rejects_alg_none(db_session, runtime_stack):
    _private_pem, jwks = _rsa_keypair()
    issuer = "https://idp.example.com"
    subject = "runtime-sub-2"
    audience = "rai-runtime"
    _make_oidc_binding(
        db_session, runtime_stack, issuer=issuer, subject=subject, audience=audience
    )
    header = (
        base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode())
        .rstrip(b"=")
        .decode()
    )
    payload = (
        base64.urlsafe_b64encode(
            json.dumps(
                {
                    "iss": issuer,
                    "sub": subject,
                    "aud": audience,
                    "exp": int(time.time()) + 600,
                }
            ).encode()
        )
        .rstrip(b"=")
        .decode()
    )
    token = f"{header}.{payload}."
    cache = JwksCache(fetcher=lambda _url: jwks)
    auth = OIDCAuthenticator(
        db_session, jwks_cache=cache, jwks_url="https://idp.example.com/jwks"
    )
    with pytest.raises(SdkError) as exc:
        auth.authenticate(secret=None, token=token)
    assert "algorithm" in exc.value.message.lower()


def test_oidc_accepts_verified_signature(db_session, runtime_stack):
    private_pem, jwks = _rsa_keypair()
    issuer = "https://idp.example.com"
    subject = "runtime-sub-3"
    audience = "rai-runtime"
    _make_oidc_binding(
        db_session, runtime_stack, issuer=issuer, subject=subject, audience=audience
    )
    token = jwt.encode(
        {
            "iss": issuer,
            "sub": subject,
            "aud": audience,
            "exp": int(time.time()) + 600,
            "iat": int(time.time()),
        },
        private_pem,
        algorithm="RS256",
        headers={"kid": "test-key-1"},
    )
    cache = JwksCache(fetcher=lambda _url: jwks)
    auth = OIDCAuthenticator(
        db_session, jwks_cache=cache, jwks_url="https://idp.example.com/jwks"
    )
    result = auth.authenticate(secret=None, token=token)
    assert result.runtime_identity.id == runtime_stack["identity"].id
    assert result.auth_method == "OIDC"


def test_oidc_rejects_wrong_audience(db_session, runtime_stack):
    private_pem, jwks = _rsa_keypair()
    issuer = "https://idp.example.com"
    subject = "runtime-sub-4"
    audience = "rai-runtime"
    _make_oidc_binding(
        db_session, runtime_stack, issuer=issuer, subject=subject, audience=audience
    )
    token = jwt.encode(
        {
            "iss": issuer,
            "sub": subject,
            "aud": "wrong-aud",
            "exp": int(time.time()) + 600,
        },
        private_pem,
        algorithm="RS256",
        headers={"kid": "test-key-1"},
    )
    cache = JwksCache(fetcher=lambda _url: jwks)
    auth = OIDCAuthenticator(
        db_session, jwks_cache=cache, jwks_url="https://idp.example.com/jwks"
    )
    with pytest.raises(SdkError) as exc:
        auth.authenticate(secret=None, token=token)
    assert "audience" in exc.value.message.lower()


def test_oidc_rejects_expired(db_session, runtime_stack):
    private_pem, jwks = _rsa_keypair()
    issuer = "https://idp.example.com"
    subject = "runtime-sub-5"
    audience = "rai-runtime"
    _make_oidc_binding(
        db_session, runtime_stack, issuer=issuer, subject=subject, audience=audience
    )
    token = jwt.encode(
        {
            "iss": issuer,
            "sub": subject,
            "aud": audience,
            "exp": int(time.time()) - 120,
        },
        private_pem,
        algorithm="RS256",
        headers={"kid": "test-key-1"},
    )
    cache = JwksCache(fetcher=lambda _url: jwks)
    auth = OIDCAuthenticator(
        db_session, jwks_cache=cache, jwks_url="https://idp.example.com/jwks"
    )
    with pytest.raises(SdkError):
        auth.authenticate(secret=None, token=token)


def test_oidc_unknown_kid_refreshes_then_fails(db_session, runtime_stack):
    private_pem, jwks = _rsa_keypair()
    issuer = "https://idp.example.com"
    subject = "runtime-sub-6"
    audience = "rai-runtime"
    _make_oidc_binding(
        db_session, runtime_stack, issuer=issuer, subject=subject, audience=audience
    )
    token = jwt.encode(
        {
            "iss": issuer,
            "sub": subject,
            "aud": audience,
            "exp": int(time.time()) + 600,
        },
        private_pem,
        algorithm="RS256",
        headers={"kid": "rotated-away"},
    )
    fetches = {"n": 0}

    def fetcher(_url: str):
        fetches["n"] += 1
        return jwks

    cache = JwksCache(fetcher=fetcher)
    auth = OIDCAuthenticator(
        db_session, jwks_cache=cache, jwks_url="https://idp.example.com/jwks"
    )
    with pytest.raises(SdkError) as exc:
        auth.authenticate(secret=None, token=token)
    assert "signing key" in exc.value.message.lower()
    assert fetches["n"] >= 2


def test_mtls_rejects_spoofed_header_without_proxy_proof(db_session, runtime_stack):
    cert_id = "CN=agent.example.com"
    db_session.add(
        OidcRuntimeBinding(
            runtime_identity_id=runtime_stack["identity"].id,
            issuer="mtls",
            audience="mtls",
            subject=cert_id,
            status="ACTIVE",
            created_by="test",
        )
    )
    db_session.commit()

    auth = MTLSAuthenticator(
        db_session,
        trusted_proxy_mode=True,
        trusted_proxy_secret="proxy-secret",
        allow_insecure_identity_header=False,
    )
    with pytest.raises(SdkError) as exc:
        auth.authenticate(secret=None, token=cert_id, proxy_authorization=None)
    assert "untrusted ingress" in exc.value.message.lower()


def test_mtls_accepts_with_trusted_proxy_proof(db_session, runtime_stack):
    cert_id = "CN=trusted.example.com"
    db_session.add(
        OidcRuntimeBinding(
            runtime_identity_id=runtime_stack["identity"].id,
            issuer="mtls",
            audience="mtls",
            subject=cert_id,
            status="ACTIVE",
            created_by="test",
        )
    )
    db_session.commit()

    auth = MTLSAuthenticator(
        db_session,
        trusted_proxy_mode=True,
        trusted_proxy_secret="proxy-secret",
        allow_insecure_identity_header=False,
    )
    result = auth.authenticate(
        secret=None, token=cert_id, proxy_authorization="proxy-secret"
    )
    assert result.runtime_identity.id == runtime_stack["identity"].id


def _mcp_action(db_session, runtime_stack):
    system = runtime_stack["system"]
    identity = runtime_stack["identity"]
    agent = runtime_stack["agent"]
    version = runtime_stack["version"]
    mcp = MCPServer(
        server_key=f"mcp-{uuid.uuid4().hex[:6]}",
        name="Test MCP",
        status="ACTIVE",
        endpoint_reference=None,
    )
    db_session.add(mcp)
    db_session.flush()
    tool = ToolResource(
        tool_key=f"tool-{uuid.uuid4().hex[:6]}",
        name="create_order",
        status="ACTIVE",
        mcp_server_id=mcp.id,
    )
    db_session.add(tool)
    db_session.commit()
    action = ProposedAction(
        ai_system_id=system.id,
        agent_id=agent.id,
        agent_version_id=version.id,
        runtime_identity_id=identity.id,
        delegation_id=None,
        integration_type=IntegrationType.MCP.value,
        integration_id=mcp.id,
        tool_id=tool.id,
        target=ActionTarget(type="order", id="1"),
        parameters={},
        environment="PRODUCTION",
    )
    return action


def test_mcp_production_denies_missing_endpoint(db_session, runtime_stack):
    action = _mcp_action(db_session, runtime_stack)

    class _Auth:
        pass

    adapter = MCPToolExecutionAdapter(db_session, adapter_mode="PRODUCTION")
    result = adapter.execute(action, _Auth())  # type: ignore[arg-type]
    assert result.success is False
    assert "CONFIGURATION_ERROR" in (result.error_message or "")


def test_mcp_demo_allows_simulation(db_session, runtime_stack):
    action = _mcp_action(db_session, runtime_stack)

    class _Auth:
        pass

    adapter = MCPToolExecutionAdapter(db_session, adapter_mode="DEMO_SIMULATED")
    result = adapter.execute(action, _Auth())  # type: ignore[arg-type]
    assert result.success is True
    assert result.result_payload and result.result_payload.get("mode") == "simulated"


def test_mandatory_budget_unavailable_denies(db_session, runtime_stack):
    system = runtime_stack["system"]
    identity = runtime_stack["identity"]
    svc = BudgetService(db_session)
    svc.create_budget(
        ai_system_id=system.id,
        name="mandatory tokens",
        scope_type="RUNTIME_IDENTITY",
        metric=BudgetMetric.TOKEN_USAGE.value,
        limit_value=10000,
        window_seconds=86400,
        warning_threshold=0.8,
        effect_on_exceed=BudgetEffect.DENY.value,
        enforcement_mode=BudgetEnforcementMode.MANDATORY.value,
        enabled=True,
    )
    db_session.commit()

    result = svc.check_and_consume(
        ai_system_id=system.id,
        runtime_identity_id=identity.id,
    )
    assert result["deny"] is True
    assert any(
        c["reason"] == "BUDGET_MEASUREMENT_UNAVAILABLE" for c in result["checks"]
    )


def test_best_effort_budget_unavailable_skips(db_session, runtime_stack):
    system = runtime_stack["system"]
    identity = runtime_stack["identity"]
    svc = BudgetService(db_session)
    svc.create_budget(
        ai_system_id=system.id,
        name="best effort tokens",
        scope_type="RUNTIME_IDENTITY",
        metric=BudgetMetric.TOKEN_USAGE.value,
        limit_value=10000,
        window_seconds=86400,
        warning_threshold=0.8,
        effect_on_exceed=BudgetEffect.MONITOR.value,
        enforcement_mode=BudgetEnforcementMode.BEST_EFFORT.value,
        enabled=True,
    )
    db_session.commit()

    result = svc.check_and_consume(
        ai_system_id=system.id,
        runtime_identity_id=identity.id,
    )
    assert result["deny"] is False
    assert result["checks"][0]["status"] == BudgetStatus.UNAVAILABLE.value
    assert result["checks"][0]["decision"] == "SKIP"


def test_emergency_stop_sets_system_stopped_and_overlay_denies(
    db_session, runtime_stack
):
    system = runtime_stack["system"]
    identity = runtime_stack["identity"]
    svc = InterventionService(db_session)
    intervention = svc._repo.create_intervention(
        trajectory_id=None,
        ai_system_id=system.id,
        scope_type=RiskScopeType.AI_SYSTEM.value,
        scope_id=str(system.id),
        effect=InterventionEffect.EMERGENCY_STOP.value,
        reason="Kill switch test",
        risk_level=RiskSeverity.CRITICAL.value,
        confidence=1.0,
        triggering_signal_ids=[],
        policy_rule_ids=[],
        finding_id=None,
        status="PENDING_CONFIRMATION",
        authorization_mode=InterventionAuthorizationMode.HUMAN_CONFIRM_HIGH_CRITICAL.value,
        automatic=False,
        explanation={"why": "test"},
    )
    db_session.commit()

    executed = svc.confirm_intervention(intervention.id, executed_by="security-officer")
    assert executed.status == "EXECUTED"
    db_session.refresh(system)
    assert system.status == AISystemStatus.STOPPED.value

    overlay = RiskEngine(db_session).get_authorization_overlay(
        ai_system_id=system.id,
        runtime_identity_id=identity.id,
    )
    assert overlay["deny"] is True
    reason = (overlay["deny_reason"] or "").lower()
    assert "kill switch" in reason or "stopped" in reason or "emergency" in reason


def test_critical_approval_rejects_missing_server_assurance(db_session, monkeypatch):
    monkeypatch.setattr(settings, "approval_minimum_acr", None)
    monkeypatch.setattr(settings, "approval_required_amr", None)
    monkeypatch.setattr(settings, "approval_max_auth_age_seconds", None)

    request = SimpleNamespace(
        risk_tier="CRITICAL",
        initiating_principal="someone-else",
    )
    authz = ApproverAuthorizationService(db_session)
    with pytest.raises(ApprovalDeniedError) as exc:
        authz.authorize_approve(
            request,  # type: ignore[arg-type]
            ApproverContext(
                actor="approver@example.com",
                role="admin",
                authentication_assurance=None,
            ),
        )
    assert exc.value.reason == ApprovalDenialCode.APPROVAL_STEP_UP_REQUIRED.value


def test_critical_approval_accepts_server_derived_step_up(db_session, monkeypatch):
    monkeypatch.setattr(settings, "approval_minimum_acr", None)
    monkeypatch.setattr(settings, "approval_required_amr", None)
    monkeypatch.setattr(settings, "approval_max_auth_age_seconds", None)

    request = SimpleNamespace(
        risk_tier="CRITICAL",
        initiating_principal="someone-else",
    )
    authz = ApproverAuthorizationService(db_session)
    authz.authorize_approve(
        request,  # type: ignore[arg-type]
        ApproverContext(
            actor="approver@example.com",
            role="admin",
            authentication_assurance=STEP_UP_VERIFIED,
        ),
    )


def test_critical_approval_requires_configured_acr(db_session, monkeypatch):
    monkeypatch.setattr(settings, "approval_minimum_acr", "urn:mfa")
    monkeypatch.setattr(settings, "approval_required_amr", "otp,pwd")
    monkeypatch.setattr(settings, "approval_max_auth_age_seconds", 300)

    request = SimpleNamespace(
        risk_tier="CRITICAL",
        initiating_principal="someone-else",
    )
    authz = ApproverAuthorizationService(db_session)
    with pytest.raises(ApprovalDeniedError):
        authz.authorize_approve(
            request,  # type: ignore[arg-type]
            ApproverContext(
                actor="approver@example.com",
                role="admin",
                authentication_assurance=STEP_UP_VERIFIED,
                acr="urn:pwd",
                amr=["pwd"],
                auth_time=int(time.time()),
            ),
        )

    authz.authorize_approve(
        request,  # type: ignore[arg-type]
        ApproverContext(
            actor="approver@example.com",
            role="admin",
            authentication_assurance=STEP_UP_VERIFIED,
            acr="urn:mfa",
            amr=["otp", "pwd"],
            auth_time=int(time.time()),
        ),
    )
