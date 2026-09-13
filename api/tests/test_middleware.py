"""What happens to a request before any handler sees it."""

import uuid

from remitx_api.extensions import db
from remitx_api.middleware import MAX_REQUEST_BODY_BYTES
from remitx_api.models.orm.audit_log import AuditAction, AuditLog, AuditSubject
from remitx_api.models.orm.kyc_document import MAX_SIZE_BYTES
from remitx_api.request_context import (
    current_request_id,
    reset_request_id,
    set_request_id,
)
from remitx_api.services.audit_service import record_audit
from sqlalchemy import select
from tests.kyc_helpers import make_user


def test_the_body_ceiling_is_above_the_document_limit():
    """An oversized *document* should be answered by the route, which can say
    what the document limit is; this is the backstop for everything else."""
    assert MAX_REQUEST_BODY_BYTES > MAX_SIZE_BYTES


def test_an_oversized_body_is_refused_on_a_route_that_does_not_exist(client):
    """The guard runs before routing: a request to a typo'd URL should not be
    able to cost us a gigabyte of buffering either."""
    response = client.post(
        "/no-such-endpoint",
        content=b"\x00" * (MAX_REQUEST_BODY_BYTES + 1),
    )

    assert response.status_code == 413
    assert "too large" in response.json()["detail"]


def test_an_oversized_body_is_refused_before_a_handler_runs(client):
    """`/integration-messages` parses JSON, and the framework reads the whole
    body to do it. Nothing should get that far."""
    response = client.post(
        "/integration-messages",
        content=b'{"body": "' + b"a" * (MAX_REQUEST_BODY_BYTES + 1) + b'"}',
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 413


def test_a_body_within_the_ceiling_reaches_the_handler(client, enqueued):
    """The guard has to be invisible to everything legitimate."""
    response = client.post("/integration-messages", json={"body": "hello"})

    assert response.status_code == 202


def test_every_response_carries_a_request_id(client):
    first = client.get("/health")
    second = client.get("/health")

    assert first.headers["x-request-id"]
    assert first.headers["x-request-id"] != second.headers["x-request-id"]


def test_a_caller_cannot_choose_their_own_request_id(client):
    """An inbound X-Request-Id would let a caller pick the value that
    correlates their entries in the audit log — including one that collides
    with somebody else's."""
    supplied = "deadbeef"

    response = client.get("/health", headers={"X-Request-Id": supplied})

    assert response.headers["x-request-id"] != supplied


def test_there_is_no_request_id_outside_a_request():
    """A Celery task or a script writing audit entries has nothing to
    correlate with, and should not invent something."""
    assert current_request_id() is None


def test_audit_entries_pick_up_the_request_id_without_being_handed_it(
    app_context,
):
    """The column exists so "what else happened in that request" is
    answerable; a helper nobody passes it to is a column that stays null."""
    actor = make_user("auditor")
    db.session.commit()

    request_id = uuid.uuid4().hex
    token = set_request_id(request_id)
    try:
        record_audit(
            actor_user_id=actor.id,
            action=AuditAction.KYC_DOCUMENT_VIEWED,
            subject_type=AuditSubject.KYC_DOCUMENT,
            subject_id=uuid.uuid4(),
        )
        db.session.commit()
    finally:
        reset_request_id(token)

    entry = db.session.scalars(select(AuditLog)).one()
    assert entry.request_id == request_id
