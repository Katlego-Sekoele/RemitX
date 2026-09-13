"""The request-scoped SQLAlchemy session.

Per-request, not per-process. FastAPI runs sync (`def`) routes in an anyio
worker thread and serves requests concurrently, so a single shared session
attribute lets one request close the session another is still writing
through — losing writes and raising "session is not active" under load.
ContextVars are copied into anyio worker threads, so sync routes see the
session opened for their own request and nothing else.
"""

from contextvars import ContextVar

from sqlalchemy.orm import Session

_request_db_session: ContextVar[Session | None] = ContextVar(
    "remitx_request_db_session",
    default=None,
)


def current_request_db_session() -> Session | None:
    """The open session, or ``None`` when nothing has opened one."""
    return _request_db_session.get()


def require_request_db_session() -> Session:
    """The open session. Raises if called outside a request or script block."""
    session = _request_db_session.get()
    if session is None:
        raise RuntimeError("Database session is not active")
    return session


def set_request_db_session(session: Session):
    """Bind ``session`` to this context. Returns a reset token."""
    return _request_db_session.set(session)


def reset_request_db_session(token=None) -> None:
    """Drop the bound session. ``token`` is what ``set_request_db_session`` returned."""
    if token is None:
        _request_db_session.set(None)
    else:
        _request_db_session.reset(token)
