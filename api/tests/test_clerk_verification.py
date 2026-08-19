from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from remitx_api.auth import clerk as clerk_module
from remitx_api.auth.clerk import ClerkClaims, fetch_user_email, verify_request
from remitx_api.config import TestConfig


class _FakeRequest:
    """Minimal stand-in for a Starlette Request."""

    def __init__(self, headers=None):
        self.method = "GET"
        self.url = "http://testserver/integration-messages"
        self.headers = headers or {}


def _stub_sdk(monkeypatch, state, captured=None):
    """Replace the Clerk SDK with one returning a fixed request state.

    When `captured` is a list, the `AuthenticateRequestOptions` passed to
    `authenticate_request` is appended to it so a test can assert on what
    was actually sent to the SDK.
    """

    def _authenticate(request, options):
        if captured is not None:
            captured.append(options)
        return state

    sdk = SimpleNamespace(authenticate_request=_authenticate)
    monkeypatch.setattr(clerk_module, "_sdk", lambda secret_key: sdk)


def test_returns_claims_for_a_signed_in_request(monkeypatch):
    _stub_sdk(
        monkeypatch,
        SimpleNamespace(
            is_signed_in=True,
            payload={"sub": "user_abc", "email": "a@example.com"},
        ),
    )

    claims = verify_request(_FakeRequest(), TestConfig())

    assert claims == ClerkClaims(clerk_user_id="user_abc", email="a@example.com")


def test_passes_authorized_parties_and_restricts_token_type(monkeypatch):
    """Both SDK defaults fail OPEN, so these options must actually be sent.

    Omitting `authorized_parties` makes the SDK skip the azp check entirely
    (any origin on the same Clerk instance would validate); omitting
    `accepts_token` defaults to `["any"]`, which would accept API keys,
    OAuth tokens, and M2M tokens as if they were user sessions. Neither is
    exercised by the other tests, since the stub there ignores `options`.
    """
    captured = []
    _stub_sdk(
        monkeypatch,
        SimpleNamespace(is_signed_in=True, payload={"sub": "user_abc"}),
        captured=captured,
    )

    verify_request(_FakeRequest(), TestConfig())

    assert len(captured) == 1
    assert captured[0].authorized_parties == TestConfig().CORS_ORIGINS
    assert captured[0].accepts_token == ["session_token"]


def test_email_is_optional(monkeypatch):
    _stub_sdk(
        monkeypatch,
        SimpleNamespace(is_signed_in=True, payload={"sub": "user_abc"}),
    )

    assert verify_request(_FakeRequest(), TestConfig()).email is None


def test_rejects_a_signed_out_request(monkeypatch):
    _stub_sdk(monkeypatch, SimpleNamespace(is_signed_in=False, payload=None))

    with pytest.raises(HTTPException) as caught:
        verify_request(_FakeRequest(), TestConfig())

    assert caught.value.status_code == 401
    assert caught.value.headers["WWW-Authenticate"] == "Bearer"


def test_rejects_a_token_without_a_subject(monkeypatch):
    _stub_sdk(
        monkeypatch,
        SimpleNamespace(is_signed_in=True, payload={"email": "a@example.com"}),
    )

    with pytest.raises(HTTPException) as caught:
        verify_request(_FakeRequest(), TestConfig())

    assert caught.value.status_code == 401


def test_fetch_user_email_reads_the_primary_address(monkeypatch):
    """Email is not a session-token claim, so it comes from the Backend API."""
    user = SimpleNamespace(
        primary_email_address_id="idn_1",
        email_addresses=[
            SimpleNamespace(id="idn_0", email_address="old@example.com"),
            SimpleNamespace(id="idn_1", email_address="primary@example.com"),
        ],
    )
    sdk = SimpleNamespace(users=SimpleNamespace(get=lambda user_id: user))
    monkeypatch.setattr(clerk_module, "_sdk", lambda secret_key: sdk)

    assert fetch_user_email("user_abc", TestConfig()) == "primary@example.com"


def test_fetch_user_email_returns_none_when_lookup_fails(monkeypatch):
    """A profile lookup failure must not block sign-in — email is optional."""

    def explode(user_id):
        raise RuntimeError("clerk is down")

    sdk = SimpleNamespace(users=SimpleNamespace(get=explode))
    monkeypatch.setattr(clerk_module, "_sdk", lambda secret_key: sdk)

    assert fetch_user_email("user_abc", TestConfig()) is None


def test_raises_when_the_secret_key_is_not_configured():
    class Unconfigured(TestConfig):
        CLERK_SECRET_KEY = ""

    with pytest.raises(RuntimeError, match="CLERK_SECRET_KEY"):
        verify_request(_FakeRequest(), Unconfigured())
