"""API key authentication tests."""


def test_execute_invalid_api_key(test_client):
    request_data = {
        "prompt_id": "nonexistent",
        "prompt_version": 1,
        "system_id": "test_system",
        "module": "test_module",
        "variables": {"name": "John"},
    }

    response = test_client.post(
        "/v1/execute",
        json=request_data,
        headers={"X-API-Key": "bad"},
    )

    assert response.status_code == 401
    assert response.json()["error"] == "UNAUTHENTICATED"


def test_execute_system_id_mismatch(test_client, api_key_header):
    request_data = {
        "prompt_id": "nonexistent",
        "prompt_version": 1,
        "system_id": "other_system",
        "module": "test_module",
        "variables": {"name": "John"},
    }

    response = test_client.post(
        "/v1/execute", json=request_data, headers=api_key_header
    )

    assert response.status_code == 403
    assert response.json()["error"] == "NOT_ALLOWED"
