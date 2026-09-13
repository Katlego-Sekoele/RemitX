"""Database transaction helper for multi-step use cases.

Repository writes flush only; a controller or repository method that
orchestrates several of them wraps the whole use case in ``@db_transaction``
so it commits once or rolls back entirely.
"""

from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar

from remitx_api.db.request_db_session import require_request_db_session

P = ParamSpec("P")
R = TypeVar("R")


def db_transaction(fn: Callable[P, R]) -> Callable[P, R]:
    @wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        session = require_request_db_session()
        try:
            result = fn(*args, **kwargs)
            session.commit()
            return result
        except Exception:
            session.rollback()
            raise

    return wrapper
