"""Execute endpoint error path tests."""


def test_execute_missing_prompt(test_client, api_key_header):
    request_data = {
        "prompt_id": "nonexistent",
        "prompt_version": 1,
        "system_id": "test_system",
        "module": "test_module",
        "variables": {"name": "John"},
    }

    response = test_client.post(
        "/v1/execute", json=request_data, headers=api_key_header
    )

    assert response.status_code == 404
    assert response.json()["error"] == "PROMPT_NOT_FOUND"


def test_execute_invalid_request(test_client, api_key_header):
    request_data = {
        "prompt_id": "",
        "prompt_version": 1,
        "system_id": "test_system",
        "module": "test_module",
        "variables": {},
    }

    response = test_client.post(
        "/v1/execute", json=request_data, headers=api_key_header
    )

    assert response.status_code == 422
