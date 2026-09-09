"""FastAPI dependencies exposing the authenticated caller.

Handlers receive a User, never a token or a raw claim dict, so no route has
to know that Clerk is the identity provider.
"""

from fastapi import Request

from remitx_api.auth.clerk import fetch_user_email, fetch_user_first_name, verify_request
from remitx_api.controllers.user_controller import UserController
from remitx_api.models.orm.user import User

_users = UserController()


def get_current_user(request: Request) -> User:
    """Verify the caller's Clerk session and return their local User row.

    Deliberately a plain `def`, not `async def`: `verify_request`'s cold
    path retries JWKS fetches aggressively, and FastAPI runs a sync
    dependency in a threadpool, so a slow/unreachable Clerk only stalls the
    request that hit it rather than blocking the whole event loop.
    """
    config = request.app.state.config
    claims = verify_request(request, config)

    # Passed as callables, not values: provisioning only invokes these when it
    # actually has to insert, so returning users cost no Clerk API call.
    def resolve_email():
        return claims.email or fetch_user_email(claims.clerk_user_id, config)

    def resolve_first_name():
        return claims.first_name or fetch_user_first_name(claims.clerk_user_id, config)

    return _users.ensure_provisioned(
        claims.clerk_user_id, resolve_email, resolve_first_name
    )
