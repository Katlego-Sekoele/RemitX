def test_health_returns_ok(anonymous_client):
    # Public: Container Apps probes this endpoint without credentials.
    response = anonymous_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
