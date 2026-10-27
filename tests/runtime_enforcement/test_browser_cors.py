"""Browser preflight for runtime action calls from the control-plane UI."""

from rai_gateway.core.config import settings


def _allowed_origin() -> str:
    configured = settings.cors_allowed_origins.strip()
    if configured == "*":
        return "https://rai.ztechnium.com"
    return configured.split(",")[0].strip()


def test_runtime_action_preflight_allows_agent_key(test_client):
    response = test_client.options(
        "/v1/runtime/actions/execute",
        headers={
            "Origin": _allowed_origin(),
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-rai-agent-key",
        },
    )
    assert response.status_code == 200, response.text
    allowed = response.headers.get("access-control-allow-headers", "").lower()
    assert "x-rai-agent-key" in allowed

    authorize = test_client.options(
        "/v1/runtime/actions/authorize",
        headers={
            "Origin": _allowed_origin(),
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-rai-agent-key",
        },
    )
    assert authorize.status_code == 200, authorize.text
