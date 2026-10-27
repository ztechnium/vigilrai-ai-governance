"""End-to-end execute flow tests."""


def test_execute_happy_path(
    test_client, api_key_header, seed_prompt, mock_llm_provider
):
    request_data = {
        "prompt_id": seed_prompt["prompt_id"],
        "prompt_version": seed_prompt["version"],
        "system_id": "test_system",
        "module": "test_module",
        "variables": {"name": "John"},
    }

    response = test_client.post(
        "/v1/execute", json=request_data, headers=api_key_header
    )

    assert response.status_code == 200

    payload = response.json()
    assert payload["decision"] == "allow"
    assert payload["execution_id"]
    assert payload["trace_id"]
    assert payload["metadata"]["provider"] == "mock"
