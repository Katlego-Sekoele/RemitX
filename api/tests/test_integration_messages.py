import uuid

import pytest

ENDPOINT = "/integration-messages"


def test_create_returns_202_with_pending_message(client, enqueued):
    response = client.post(ENDPOINT, json={"body": "hello"})

    assert response.status_code == 202
    payload = response.json()
    assert payload["body"] == "hello"
    assert payload["status"] == "PENDING"
    assert payload["processed_at"] is None
    uuid.UUID(payload["id"])  # raises if not a UUID


def test_create_enqueues_the_new_message_id_once(client, enqueued):
    response = client.post(ENDPOINT, json={"body": "hello"})

    assert enqueued == [response.json()["id"]]


def test_create_strips_surrounding_whitespace(client, enqueued):
    response = client.post(ENDPOINT, json={"body": "  padded  "})

    assert response.json()["body"] == "padded"


def test_create_accepts_a_body_at_the_limit(client, enqueued):
    response = client.post(ENDPOINT, json={"body": "x" * 280})

    assert response.status_code == 202


@pytest.mark.parametrize(
    "body",
    ["", "   ", "x" * 281],
    ids=["empty", "whitespace_only", "over_limit"],
)
def test_create_rejects_invalid_bodies(client, enqueued, body):
    response = client.post(ENDPOINT, json={"body": body})

    assert response.status_code == 422
    assert enqueued == []


def test_create_requires_a_body_field(client, enqueued):
    assert client.post(ENDPOINT, json={}).status_code == 422


def test_list_is_empty_before_anything_is_sent(client):
    response = client.get(ENDPOINT)

    assert response.status_code == 200
    assert response.json() == []


def test_list_returns_newest_first(client, enqueued):
    for body in ("first", "second", "third"):
        client.post(ENDPOINT, json={"body": body})

    bodies = [m["body"] for m in client.get(ENDPOINT).json()]

    assert bodies == ["third", "second", "first"]


def test_list_honours_limit(client, enqueued):
    for body in ("first", "second", "third"):
        client.post(ENDPOINT, json={"body": body})

    bodies = [m["body"] for m in client.get(ENDPOINT, params={"limit": 2}).json()]

    assert bodies == ["third", "second"]


@pytest.mark.parametrize("limit", [0, -1, 201])
def test_list_rejects_out_of_range_limits(client, limit):
    response = client.get(ENDPOINT, params={"limit": limit})

    assert response.status_code == 422
