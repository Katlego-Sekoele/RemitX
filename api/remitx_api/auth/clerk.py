"""Verify Clerk session tokens.

The SDK's `authenticate_request` only requires an object with a `.headers`
mapping (see `clerk_backend_api.security.types.Requestish`), but an
`httpx.Request` satisfies that structurally and is what the SDK's own
docs assume, so this module adapts a Starlette request into one and
converts Clerk's request state into a small domain object. Nothing
outside this module needs to know Clerk exists.
"""

import logging
from dataclasses import dataclass
from functools import lru_cache

import httpx
from clerk_backend_api import Clerk
from clerk_backend_api.security.types import AuthenticateRequestOptions
from fastapi import HTTPException, Request, status

from remitx_api.config import Config

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClerkClaims:
    clerk_user_id: str
    email: str | None
    first_name: str | None = None


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
    """Build (and memoize) the process-wide Clerk SDK client.

    `maxsize=1` means only the most recently seen secret key gets a live
    client — fine in practice since a process runs against a single Clerk
    instance, and a key rotation simply evicts and rebuilds on next call.
    Cached at all because the client holds a connection pool and Clerk's
    JWKS cache; building one per request would refetch signing keys
    constantly.
    """
    return Clerk(bearer_auth=secret_key)


def _to_httpx(request: Request) -> httpx.Request:
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


def verify_request(request: Request, config: Config) -> ClerkClaims:
    """Return the caller's claims, or raise 401.

    Raises RuntimeError — not 401 — when neither key is configured: that is a
    deployment fault, and returning 401 would disguise it as a client error.
    """
    secret_key = config.CLERK_SECRET_KEY
    jwt_key = config.CLERK_JWT_KEY
    if not (secret_key or jwt_key):
        raise RuntimeError("Neither CLERK_SECRET_KEY nor CLERK_JWT_KEY is configured")

    state = _sdk(secret_key).authenticate_request(
        _to_httpx(request),
        AuthenticateRequestOptions(
            # With a JWT key the SDK verifies against it alone, never fetching
            # Clerk's JWKS; without one, it fetches them with the secret key.
            jwt_key=jwt_key or None,
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
        # Same story as email: not a default claim, so fetch_user_first_name
        # is the reliable path when this comes back None.
        first_name=payload.get("first_name"),
    )


def fetch_user_email(clerk_user_id: str, config: Config) -> str | None:
    """Look up a user's primary email via Clerk's Backend API.

    Email is not a default session-token claim, so it cannot come from
    verification. Called only when provisioning a new local row — never on the
    hot path — so the network cost is once per user lifetime.

    Returns None rather than raising: a profile lookup failing is not a reason
    to reject an otherwise valid session, and the column is nullable.
    """
    if not config.CLERK_SECRET_KEY:
        # Verifying with CLERK_JWT_KEY alone: there is no Backend API to ask.
        return None
    sdk = _sdk(config.CLERK_SECRET_KEY)
    try:
        user = sdk.users.get(user_id=clerk_user_id)
        primary_id = getattr(user, "primary_email_address_id", None)
        addresses = getattr(user, "email_addresses", None) or []
        for address in addresses:
            if address.id == primary_id:
                return address.email_address
        return addresses[0].email_address if addresses else None
    except Exception as exc:
        # Deliberately broad: any SDK or transport failure (network error,
        # auth failure, unexpected response shape, ...) degrades to "no email
        # on file" rather than blocking an otherwise-valid sign-in. Log only
        # the user id and exception type — never the secret key, the token,
        # or the full exception, which could carry response bodies/headers.
        logger.warning(
            "fetch_user_email failed for clerk_user_id=%s: %s",
            clerk_user_id,
            type(exc).__name__,
        )
        return None


@lru_cache(maxsize=512)
def fetch_user_image_url(clerk_user_id: str, secret_key: str) -> str | None:
    """Return a Clerk-hosted profile image URL for a user.

    Includes Clerk's generated avatar when the person has not uploaded a
    photo. Cached in-process so beneficiary lists do not hammer Clerk for
    the same people on every poll.

    Returns None rather than raising: a missing image must not break the
    beneficiaries list.
    """
    if not secret_key:
        return None
    try:
        user = _sdk(secret_key).users.get(user_id=clerk_user_id)
        image_url = getattr(user, "image_url", None)
        return image_url or None
    except Exception as exc:
        logger.warning(
            "fetch_user_image_url failed for clerk_user_id=%s: %s",
            clerk_user_id,
            type(exc).__name__,
        )
        return None


def fetch_user_first_name(clerk_user_id: str, config: Config) -> str | None:
    """Look up a user's first name via Clerk's Backend API.

    Called only when provisioning a new local row (to build the user's
    permanent base reference — Transaction_Flow_Context.md §1/§2 Phase A),
    never on the hot path.

    Returns None rather than raising: a profile lookup failing is not a
    reason to reject an otherwise valid session — `UserRepository.next_base_reference`
    falls back to a generic base when no name is available.
    """
    if not config.CLERK_SECRET_KEY:
        # Same as fetch_user_email: no secret key, no Backend API.
        return None
    sdk = _sdk(config.CLERK_SECRET_KEY)
    try:
        user = sdk.users.get(user_id=clerk_user_id)
        return getattr(user, "first_name", None)
    except Exception as exc:
        # Deliberately broad — see fetch_user_email's identical rationale.
        logger.warning(
            "fetch_user_first_name failed for clerk_user_id=%s: %s",
            clerk_user_id,
            type(exc).__name__,
        )
        return None
