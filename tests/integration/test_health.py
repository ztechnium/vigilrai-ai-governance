"""Integration tests for health, readiness, and version endpoints."""


def test_health_check(test_client):
    response = test_client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "healthy"
    assert payload["service"] == "rai-control-plane-api"


def test_readiness_check(test_client):
    response = test_client.get("/ready")
    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == "rai-control-plane-api"
    assert payload["status"] == "ready"
    assert payload["checks"]["postgresql"] == "ok"


def test_version_endpoint(test_client):
    response = test_client.get("/version")
    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == "rai-control-plane-api"
    assert "version" in payload
    assert "commit" in payload
    assert "build_time" in payload
    assert "schema_revision" in payload
