"""Health check endpoint tests."""


def test_health_check(test_client):
    response = test_client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "healthy"
    assert payload["service"] == "rai-control-plane-api"
