def test_list_requires_authentication(anonymous_client):
    response = anonymous_client.get("/integration-messages")

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_create_requires_authentication(anonymous_client):
    response = anonymous_client.post(
        "/integration-messages",
        json={"body": "hello"},
    )

    assert response.status_code == 401


def test_health_stays_public(anonymous_client):
    # Container Apps probes this endpoint without credentials.
    assert anonymous_client.get("/health").status_code == 200


def test_authenticated_client_can_list(client):
    assert client.get("/integration-messages").status_code == 200
