from types import SimpleNamespace

from remitx_api.auth import dependencies as dependencies_module
from remitx_api.auth.clerk import ClerkClaims
from remitx_api.auth.dependencies import get_current_user
from remitx_api.config import TestConfig
from remitx_api.repositories.user_repository import UserRepository


class _FakeRequest:
    """get_current_user only reads `request.app.state.config` on this path —
    verify_request is patched out below, so nothing else needs to be real."""

    def __init__(self, config):
        self.app = SimpleNamespace(state=SimpleNamespace(config=config))


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


def test_first_call_provisions_a_local_user_row(app_context, monkeypatch):
    """Exercises the seam itself: verify_request's claims must actually flow
    through get_current_user into UserController.ensure_provisioned and land
    in the database — not just satisfy each half's own tests in isolation.
    """
    claims = ClerkClaims(
        clerk_user_id="user_new_dep", email="new@example.com", first_name="Sian"
    )
    monkeypatch.setattr(
        dependencies_module, "verify_request", lambda request, config: claims
    )

    user = get_current_user(_FakeRequest(TestConfig()))

    assert user.clerk_user_id == "user_new_dep"
    assert user.email == "new@example.com"
    assert user.first_name == "Sian"
    assert user.reference == "sian1"
    stored = UserRepository().get_by_clerk_id("user_new_dep")
    assert stored is not None
    assert stored.id == user.id


def test_repeat_call_is_idempotent_and_resolver_runs_once(app_context, monkeypatch):
    """Pins the laziness contract at the composition point: a second call
    for the same identity must return the same row and must NOT re-invoke
    fetch_user_email. If get_current_user ever passed resolve_email() —
    called — instead of resolve_email — the callable — this count would
    read 2, and the email claim would be re-fetched from Clerk on every
    single request instead of once per user lifetime.
    """
    claims = ClerkClaims(
        clerk_user_id="user_repeat_dep", email=None, first_name="Repeat"
    )
    monkeypatch.setattr(
        dependencies_module, "verify_request", lambda request, config: claims
    )

    calls = []

    def fake_fetch_user_email(clerk_user_id, config):
        calls.append(clerk_user_id)
        return "fetched@example.com"

    monkeypatch.setattr(dependencies_module, "fetch_user_email", fake_fetch_user_email)

    first = get_current_user(_FakeRequest(TestConfig()))
    second = get_current_user(_FakeRequest(TestConfig()))

    assert first.id == second.id
    # The resolver's return value must be threaded through, not dropped.
    assert first.email == "fetched@example.com"
    assert calls == ["user_repeat_dep"]
