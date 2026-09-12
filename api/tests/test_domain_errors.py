"""The shared DomainError contract: one handler, one response shape."""

import uuid

import pytest
from fastapi.testclient import TestClient
from remitx_api.app import create_app
from remitx_api.config import TestConfig
from remitx_api.errors.base import ConflictError, DomainError, NotFoundError
from remitx_api.errors.users import UnknownUserError
from remitx_api.repositories.user_repository import UserRepository


class _ExampleConflict(ConflictError):
    pass


def test_domain_error_is_answered_with_its_status_and_http_exception_shape():
    """A single handler in app.py turns any DomainError into HTTP.

    Routes carry no try/except mapping — a forgotten mapping would be a 500
    the caller cannot act on. The body matches HTTPException so clients
    see one error shape.
    """
    app = create_app(TestConfig)

    @app.get("/_test/domain-error")
    def raise_conflict():
        raise _ExampleConflict("reload and try again")

    with TestClient(app) as client:
        response = client.get("/_test/domain-error")

    assert response.status_code == 409
    assert response.json() == {"detail": "reload and try again"}


def test_not_found_error_is_answered_with_404():
    app = create_app(TestConfig)

    @app.get("/_test/missing")
    def raise_missing():
        raise NotFoundError("User not found")

    with TestClient(app) as client:
        response = client.get("/_test/missing")

    assert response.status_code == 404
    assert response.json() == {"detail": "User not found"}


def test_require_by_id_raises_unknown_user(app_context):
    """Whether a user id exists is the user domain's question.

    Callers that only need the row get it answered here rather than each
    writing their own ``if is None: raise``.
    """
    missing = uuid.uuid4()
    with pytest.raises(UnknownUserError) as caught:
        UserRepository().require_by_id(missing)

    assert caught.value.status_code == 404
    assert caught.value.detail == "User not found"
    assert caught.value.user_id == str(missing)
    assert isinstance(caught.value, DomainError)
