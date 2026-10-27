"""Integration tests for the execute flow."""


def test_execute_success(test_client, api_key_header, seed_prompt, mock_llm_provider):
    request_data = {
        "prompt_id": seed_prompt["prompt_id"],
        "prompt_version": seed_prompt["version"],
        "system_id": "test_system",
        "module": "test_module",
        "variables": {"name": "World"},
    }

    response = test_client.post(
        "/v1/execute", json=request_data, headers=api_key_header
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["decision"] == "allow"
    assert payload["output"] == "mock-output"
    assert payload["trace_id"]


def test_execute_missing_api_key(test_client, seed_prompt, mock_llm_provider):
    request_data = {
        "prompt_id": seed_prompt["prompt_id"],
        "prompt_version": seed_prompt["version"],
        "system_id": "test_system",
        "module": "test_module",
        "variables": {"name": "World"},
    }

    response = test_client.post("/v1/execute", json=request_data)
    assert response.status_code == 401


def test_execute_not_allowed(
    test_client, api_key_header, seed_prompt, mock_llm_provider
):
    request_data = {
        "prompt_id": seed_prompt["prompt_id"],
        "prompt_version": seed_prompt["version"],
        "system_id": "test_system",
        "module": "other_module",
        "variables": {"name": "World"},
    }

    response = test_client.post(
        "/v1/execute", json=request_data, headers=api_key_header
    )
    assert response.status_code == 403


def test_execute_prompt_not_found(test_client, api_key_header, mock_llm_provider):
    request_data = {
        "prompt_id": "missing_prompt",
        "prompt_version": 1,
        "system_id": "test_system",
        "module": "test_module",
        "variables": {"name": "World"},
    }

    response = test_client.post(
        "/v1/execute", json=request_data, headers=api_key_header
    )
    assert response.status_code == 404
