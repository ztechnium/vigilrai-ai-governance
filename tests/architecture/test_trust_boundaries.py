"""Architecture tests protecting trust boundaries before WP1+."""

from __future__ import annotations


def test_auth_failure_denies_execute(test_client):
    """Authentication failure must deny protected /v1/execute operations."""
    response = test_client.post(
        "/v1/execute",
        json={
            "prompt_id": "any",
            "prompt_version": 1,
            "system_id": "test_system",
            "module": "test_module",
            "variables": {},
        },
        headers={"X-API-Key": "invalid-key"},
    )
    assert response.status_code == 401
    assert response.json()["error"] == "UNAUTHENTICATED"


def test_guard_unavailable_blocks_execution(
    test_client, api_key_header, seed_prompt, monkeypatch
):
    """RAI Guard critical dependency failure must block governed execution."""

    async def _fail_precheck(*_args, **_kwargs):
        raise RuntimeError("guard service down")

    monkeypatch.setattr(
        "rai_gateway.services.llm_controller.RaiGuardService.precheck",
        _fail_precheck,
    )

    response = test_client.post(
        "/v1/execute",
        json={
            "prompt_id": seed_prompt["prompt_id"],
            "prompt_version": seed_prompt["version"],
            "system_id": "test_system",
            "module": "test_module",
            "variables": {"name": "Jane"},
        },
        headers=api_key_header,
    )

    assert response.status_code == 503
    assert response.json()["error"] == "GUARD_UNAVAILABLE"


def test_catalog_resolution_failure_blocks_execution(test_client, api_key_header):
    """Prompt catalog resolution failure must block governed execution."""
    response = test_client.post(
        "/v1/execute",
        json={
            "prompt_id": "missing_prompt",
            "prompt_version": 99,
            "system_id": "test_system",
            "module": "test_module",
            "variables": {"name": "Jane"},
        },
        headers=api_key_header,
    )

    assert response.status_code == 404
    assert response.json()["error"] == "PROMPT_NOT_FOUND"


def test_api_key_cannot_broaden_system_authority(test_client, api_key_header):
    """API caller cannot impersonate another system via request metadata."""
    response = test_client.post(
        "/v1/execute",
        json={
            "prompt_id": "any",
            "prompt_version": 1,
            "system_id": "other_system",
            "module": "test_module",
            "variables": {},
        },
        headers=api_key_header,
    )

    assert response.status_code == 403
    assert response.json()["error"] == "NOT_ALLOWED"


def test_execute_is_llm_governance_path(
    test_client, api_key_header, seed_prompt, mock_llm_provider
):
    """/v1/execute remains an LLM-governance path, not arbitrary tool authorization."""
    response = test_client.post(
        "/v1/execute",
        json={
            "prompt_id": seed_prompt["prompt_id"],
            "prompt_version": seed_prompt["version"],
            "system_id": "test_system",
            "module": "test_module",
            "variables": {"name": "Test"},
        },
        headers=api_key_header,
    )

    assert response.status_code == 200
    payload = response.json()
    assert "execution_id" in payload
    assert "decision" in payload
    assert "trace_id" in payload
    assert "output" in payload
    # Must not expose tool/MCP authorization semantics
    assert "tool_grants" not in payload
    assert "agent_identity" not in payload
