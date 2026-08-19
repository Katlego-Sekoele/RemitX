"""Verify Clerk session tokens.

The SDK's `authenticate_request` only requires an object with a `.headers`
mapping (see `clerk_backend_api.security.types.Requestish`), but an
`httpx.Request` satisfies that structurally and is what the SDK's own
docs assume, so this module adapts a Starlette request into one and
converts Clerk's request state into a small domain object. Nothing
outside this module needs to know Clerk exists.
"""

from dataclasses import dataclass
from functools import lru_cache

import httpx
from clerk_backend_api import Clerk
from clerk_backend_api.security.types import AuthenticateRequestOptions
from fastapi import HTTPException, status


@dataclass(frozen=True)
class ClerkClaims:
    clerk_user_id: str
    email: str | None


def _unauthorized() -> HTTPException:
    # A fresh instance per call: FastAPI mutates nothing here, but a shared
    # module-level exception object is a trap waiting for the first handler
    # that attaches request-specific detail.
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


@lru_cache(maxsize=1)
def _sdk(secret_key: str) -> Clerk:
    """One SDK instance per secret key.

    Cached because the client holds a connection pool and Clerk's JWKS cache;
    building one per request would refetch signing keys constantly.
    """
    return Clerk(bearer_auth=secret_key)


def _to_httpx(request) -> httpx.Request:
    """Adapt a Starlette request to the httpx one the Clerk SDK expects.

    Deliberately bodyless: verification reads only the method, URL, and
    headers. Consuming the request stream here would leave the route handler
    with nothing to read.
    """
    return httpx.Request(
        method=request.method,
        url=str(request.url),
        headers=list(request.headers.items()),
    )


def verify_request(request, config) -> ClerkClaims:
    """Return the caller's claims, or raise 401.

    Raises RuntimeError — not 401 — when the secret key is missing: that is a
    deployment fault, and returning 401 would disguise it as a client error.
    """
    secret_key = config.CLERK_SECRET_KEY
    if not secret_key:
        raise RuntimeError("CLERK_SECRET_KEY is not configured")

    state = _sdk(secret_key).authenticate_request(
        _to_httpx(request),
        AuthenticateRequestOptions(
            # Reuses CORS_ORIGINS: both answer "which browser origins are
            # legitimate", so one list cannot drift from the other.
            authorized_parties=config.CORS_ORIGINS,
            accepts_token=["session_token"],
        ),
    )

    if not state.is_signed_in:
        raise _unauthorized()

    payload = state.payload or {}
    clerk_user_id = payload.get("sub")
    if not clerk_user_id:
        raise _unauthorized()

    return ClerkClaims(
        clerk_user_id=clerk_user_id,
        # Absent from Clerk's default session token. Present only if someone
        # adds a JWT template claim; fetch_user_email is the reliable path.
        email=payload.get("email"),
    )


def fetch_user_email(clerk_user_id: str, config) -> str | None:
    """Look up a user's primary email via Clerk's Backend API.

    Email is not a default session-token claim, so it cannot come from
    verification. Called only when provisioning a new local row — never on the
    hot path — so the network cost is once per user lifetime.

    Returns None rather than raising: a profile lookup failing is not a reason
    to reject an otherwise valid session, and the column is nullable.
    """
    try:
        user = _sdk(config.CLERK_SECRET_KEY).users.get(user_id=clerk_user_id)
        primary_id = getattr(user, "primary_email_address_id", None)
        addresses = getattr(user, "email_addresses", None) or []
        for address in addresses:
            if address.id == primary_id:
                return address.email_address
        return addresses[0].email_address if addresses else None
    except Exception:
        # Deliberately broad: any SDK or transport failure (network error,
        # auth failure, unexpected response shape, ...) degrades to "no email
        # on file" rather than blocking an otherwise-valid sign-in.
        return None
