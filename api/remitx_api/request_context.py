"""The id that ties everything written while serving one request together.

`audit_log.request_id` exists so a compliance officer can ask "what else
happened in the request that wrote this entry" — a KYC approval and the tier
grant beside it are one action to a person and two rows to the database.
Passing that id down through every controller signature would put a plumbing
parameter in every use case, so it lives in a ContextVar for the same reason
the database session does (see ``remitx_api.db.request_db_session``): FastAPI
copies the context into the worker thread a sync route runs in, so a handler
sees the id belonging to its own request and nothing else.
"""

from contextvars import ContextVar

_request_id: ContextVar[str | None] = ContextVar("remitx_request_id", default=None)


def set_request_id(request_id: str):
    """Returns a reset token, like any other ContextVar set."""
    return _request_id.set(request_id)


def reset_request_id(token) -> None:
    _request_id.reset(token)


def current_request_id() -> str | None:
    """``None`` outside a request — a Celery task or a script writing audit
    entries has no request to correlate with, and should not invent one."""
    return _request_id.get()
