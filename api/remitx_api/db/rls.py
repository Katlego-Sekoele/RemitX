"""Request identity for Postgres row-level security.

Authenticated routes stamp ``current_user_id`` and ``is_admin_route`` on the
session. ``is_admin_route`` is true when the route requires a permission
(admin), false for a customer route. Each cursor then copies those onto the
connection as ``SET LOCAL`` settings, and clears them again after the
statement; FORCE ROW LEVEL SECURITY on ``kyc_applications``, ``quotes``,
``remittances``, and ``transactions`` does the filtering. Unbound sessions
(workers, migrations, tests) leave the settings empty and see every row.
None of it applies unless the transaction runs as a role that RLS binds —
see ``adopt_row_security_role``.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from psycopg2 import sql as pg_sql
from sqlalchemy import event
from sqlalchemy.engine import Engine

from remitx_api.db.request_db_session import (
    current_request_db_session,
    require_request_db_session,
)

# Created by the V20260913_1530 migration.
APP_DATABASE_ROLE = "remitx_app"
_CURRENT_USER_ID_SETTING = "app.current_user_id"
_IS_ADMIN_ROUTE_SETTING = "app.is_admin_route"
_ROW_SECURITY_CURRENT_USER_ID_KEY = "row_security_current_user_id"
_ROW_SECURITY_IS_ADMIN_ROUTE_KEY = "row_security_is_admin_route"
_ROW_SECURITY_LISTENERS_REGISTERED = False
_SET_CONFIG_SQL = "SELECT set_config(%s, %s, true), set_config(%s, %s, true)"


def bind_row_security_context(user_id: UUID, *, is_admin_route: bool) -> None:
    """Record who is asking, and whether this is an admin (permission-gated) route."""
    session = require_request_db_session()
    session.info[_ROW_SECURITY_CURRENT_USER_ID_KEY] = str(user_id)
    session.info[_ROW_SECURITY_IS_ADMIN_ROUTE_KEY] = is_admin_route


def clear_row_security_context() -> None:
    """Drop the request stamp so a later caller cannot inherit it."""
    session = current_request_db_session()
    if session is None:
        return
    session.info.pop(_ROW_SECURITY_CURRENT_USER_ID_KEY, None)
    session.info.pop(_ROW_SECURITY_IS_ADMIN_ROUTE_KEY, None)


@contextmanager
def bound_row_security_context(
    user_id: UUID, *, is_admin_route: bool
) -> Iterator[None]:
    """Bind for the duration of the request, then clear even if the handler fails."""
    bind_row_security_context(user_id, is_admin_route=is_admin_route)
    try:
        yield
    finally:
        clear_row_security_context()


def register_row_security_listeners() -> None:
    """Install the cursor hooks once per process so every query carries the request."""
    global _ROW_SECURITY_LISTENERS_REGISTERED
    if _ROW_SECURITY_LISTENERS_REGISTERED:
        return
    event.listen(
        Engine, "before_cursor_execute", _copy_row_security_context_to_connection
    )
    event.listen(
        Engine, "after_cursor_execute", _clear_row_security_context_from_connection
    )
    _ROW_SECURITY_LISTENERS_REGISTERED = True


def adopt_row_security_role(engine: Engine) -> None:
    """Run every transaction on ``engine`` as ``remitx_app``.

    Postgres skips RLS for superusers and BYPASSRLS roles, which is what the
    connection URL logs in as (Docker's ``POSTGRES_USER``, Neon's owner).
    ``SET LOCAL ROLE`` drops those attributes until the transaction ends.

    It must be per transaction, not per session. Neon's ``-pooler`` host is
    PgBouncer in transaction mode: a client's next transaction can land on a
    different server connection, so a session ``SET ROLE`` would silently run
    some requests as the owner and bypass RLS, and leak ``remitx_app`` into
    whichever client (e.g. a migration) picked that server connection up.
    Migrations build their own engine and keep the owner.
    """

    @event.listens_for(engine, "begin")
    def _set_local_role(conn) -> None:
        if conn.dialect.name != "postgresql":
            return
        # The raw DBAPI cursor opens the transaction SQLAlchemy is beginning,
        # so the role holds for every statement in it and ends with it.
        cursor = conn.connection.dbapi_connection.cursor()
        try:
            # Utility statements take no bind parameters; quote as an identifier.
            cursor.execute(
                pg_sql.SQL("SET LOCAL ROLE {}").format(
                    pg_sql.Identifier(APP_DATABASE_ROLE)
                )
            )
        finally:
            cursor.close()


def _copy_row_security_context_to_connection(
    conn,
    cursor,
    statement,
    _parameters,
    _context,
    _executemany,
) -> None:
    """Copy the bound user onto the connection before the statement runs.

    ``set_config(..., is_local := true)`` only lasts for the current
    transaction, so this must run on the same cursor SQLAlchemy is about to
    use. A second cursor can autocommit, in which case ``SET LOCAL`` is a
    no-op and the policy sees an empty user — every KYC row, including the
    caller's. ``fetchall`` drains this result so the real statement can
    reuse the cursor. SQLite has no row-level security, so this is a no-op
    there. The ``set_config`` guard stops the hook from recursing into itself.
    """
    if conn.dialect.name != "postgresql" or _is_set_config_statement(statement):
        return
    cursor.execute(_SET_CONFIG_SQL, _row_security_set_config_arguments())
    cursor.fetchall()


def _clear_row_security_context_from_connection(
    conn,
    _cursor,
    statement,
    _parameters,
    _context,
    _executemany,
) -> None:
    """Clear the connection settings after the statement, even if the next
    caller would overwrite them.

    Must not use ``cursor``: that is the statement's result cursor, and
    executing on it would replace the query result (so ``users.id`` becomes
    a ``set_config`` column and the request 500s).
    """
    if conn.dialect.name != "postgresql" or _is_set_config_statement(statement):
        return
    _execute_set_config_on_connection(
        conn, _cleared_row_security_set_config_arguments()
    )


def _execute_set_config_on_connection(
    conn, arguments: tuple[str, str, str, str]
) -> None:
    """Run ``set_config`` on a fresh DBAPI cursor on this connection."""
    extra = conn.connection.cursor()
    try:
        extra.execute(_SET_CONFIG_SQL, arguments)
        extra.fetchall()
    finally:
        extra.close()


def _is_set_config_statement(statement) -> bool:
    return "set_config(" in "".join(str(statement).split()).lower()


def _row_security_set_config_arguments() -> tuple[str, str, str, str]:
    """Names and values for ``app.current_user_id`` and ``app.is_admin_route``.

    Empty strings (no session, or a session nobody bound) are the worker and
    migration path: Postgres treats them as unbound and shows every row.
    """
    session = current_request_db_session()
    user_id = ""
    is_admin_route = False
    if session is not None:
        user_id = session.info.get(_ROW_SECURITY_CURRENT_USER_ID_KEY) or ""
        is_admin_route = bool(session.info.get(_ROW_SECURITY_IS_ADMIN_ROUTE_KEY))
    return (
        _CURRENT_USER_ID_SETTING,
        user_id,
        _IS_ADMIN_ROUTE_SETTING,
        "true" if is_admin_route else "false",
    )


def _cleared_row_security_set_config_arguments() -> tuple[str, str, str, str]:
    return (
        _CURRENT_USER_ID_SETTING,
        "",
        _IS_ADMIN_ROUTE_SETTING,
        "false",
    )
