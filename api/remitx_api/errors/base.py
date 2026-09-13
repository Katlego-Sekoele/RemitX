"""The shared error contract every domain error answers to.

A controller raises what went wrong in its own vocabulary; nothing in
``controllers/`` or ``repositories/`` imports FastAPI to say so. One handler
registered in ``app.py`` turns any ``DomainError`` into the HTTP response,
so routes carry no ``try``/``except`` mapping of their own — a route that
forgets one cannot turn a 404 into a 500.
"""

from __future__ import annotations

from fastapi import status


class DomainError(Exception):
    """A use case refusing, in the domain's terms rather than HTTP's.

    Subclasses set ``status_code`` and build ``detail`` — the message the
    caller reads, so it says what to do about it, not just what failed.
    """

    status_code: int = status.HTTP_400_BAD_REQUEST

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class NotFoundError(DomainError):
    """Something addressed by id or name is not there."""

    status_code = status.HTTP_404_NOT_FOUND


class ConflictError(DomainError):
    """The request is well formed but the domain's state refuses it."""

    status_code = status.HTTP_409_CONFLICT


class ForbiddenError(DomainError):
    """The caller is authenticated, but this particular record needs a
    permission they do not hold.

    Route dependencies (`RequirePermission`) answer 403 for anything decidable
    from the route alone. This is for the rest: refusals that depend on the
    data, which no route-level gate can see.
    """

    status_code = status.HTTP_403_FORBIDDEN
