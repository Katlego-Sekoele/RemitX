import time
from types import SimpleNamespace

import jwt
import pytest
from clerk_backend_api.security import verifytoken
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from remitx_api.auth import clerk as clerk_module
from remitx_api.auth.clerk import (
    ClerkClaims,
    fetch_user_email,
    fetch_user_first_name,
    fetch_user_image_url,
    verify_request,
)
from remitx_api.config import TestConfig

JWT_ORIGIN = "http://loadtest.local"


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


def test_fetch_user_image_url_reads_clerk_image_url(monkeypatch):
    user = SimpleNamespace(image_url="https://img.clerk.com/eyJ0eXBlIjoidXNlciJ9")
    sdk = SimpleNamespace(users=SimpleNamespace(get=lambda user_id: user))
    monkeypatch.setattr(clerk_module, "_sdk", lambda secret_key: sdk)

    assert (
        fetch_user_image_url("user_abc", "sk_test_x")
        == "https://img.clerk.com/eyJ0eXBlIjoidXNlciJ9"
    )


def test_fetch_user_image_url_returns_none_when_lookup_fails(monkeypatch):
    def explode(user_id):
        raise RuntimeError("clerk is down")

    sdk = SimpleNamespace(users=SimpleNamespace(get=explode))
    monkeypatch.setattr(clerk_module, "_sdk", lambda secret_key: sdk)

    assert fetch_user_image_url("user_no_image", "sk_test_x") is None


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


def _signing_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _public_pem(key: rsa.RSAPrivateKey) -> str:
    return (
        key.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )


def _session_token(key: rsa.RSAPrivateKey, **claims) -> str:
    now = int(time.time())
    payload = {
        "sub": "seed_abc",
        "azp": JWT_ORIGIN,
        "iat": now,
        "nbf": now,
        "exp": now + 60,
        **claims,
    }
    return jwt.encode(payload, key, algorithm="RS256")


def _jwt_key_config(public_pem: str) -> TestConfig:
    class JwtKeyOnly(TestConfig):
        CLERK_SECRET_KEY = ""
        CLERK_JWT_KEY = public_pem
        CORS_ORIGINS = [JWT_ORIGIN]

    return JwtKeyOnly()


@pytest.fixture
def no_jwks(monkeypatch):
    """Fail the test if verification reaches for Clerk's JWKS endpoint."""

    def fetch(options):
        raise AssertionError("verification fetched Clerk's JWKS")

    monkeypatch.setattr(verifytoken, "_fetch_jwks", fetch)


def test_verifies_against_the_jwt_key_without_calling_clerk(no_jwks):
    """The load test's path: no secret key, tokens it signed itself."""
    key = _signing_key()
    token = _session_token(key, email="a@example.com", first_name="Ann")
    request = _FakeRequest({"Authorization": f"Bearer {token}"})

    claims = verify_request(request, _jwt_key_config(_public_pem(key)))

    assert claims == ClerkClaims(
        clerk_user_id="seed_abc", email="a@example.com", first_name="Ann"
    )


def test_accepts_a_jwt_key_whose_newlines_were_lost(no_jwks):
    """Env vars often arrive with a PEM's line breaks stripped."""
    key = _signing_key()
    request = _FakeRequest({"Authorization": f"Bearer {_session_token(key)}"})
    one_line = _public_pem(key).replace("\n", "")

    assert verify_request(request, _jwt_key_config(one_line)).clerk_user_id == (
        "seed_abc"
    )


def test_rejects_a_token_signed_with_another_key(no_jwks):
    token = _session_token(_signing_key())
    request = _FakeRequest({"Authorization": f"Bearer {token}"})

    with pytest.raises(HTTPException) as caught:
        verify_request(request, _jwt_key_config(_public_pem(_signing_key())))

    assert caught.value.status_code == 401


def test_rejects_a_jwt_key_token_from_another_origin(no_jwks):
    key = _signing_key()
    token = _session_token(key, azp="https://evil.example")
    request = _FakeRequest({"Authorization": f"Bearer {token}"})

    with pytest.raises(HTTPException) as caught:
        verify_request(request, _jwt_key_config(_public_pem(key)))

    assert caught.value.status_code == 401


def test_profile_lookups_are_skipped_without_a_secret_key(monkeypatch):
    """With only a JWT key there is no Backend API to call, so provisioning
    falls back to the token's claims (or nothing) instead of a failing call."""

    def no_sdk(secret_key):
        raise AssertionError("built a Clerk client with no secret key")

    monkeypatch.setattr(clerk_module, "_sdk", no_sdk)
    config = _jwt_key_config("unused")

    assert fetch_user_email("seed_abc", config) is None
    assert fetch_user_first_name("seed_abc", config) is None
