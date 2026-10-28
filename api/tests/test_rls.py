"""The request stamps who is asking, and whether the route is admin.

Postgres RLS reads those session settings. Tests run on SQLite, so this only
checks the session stamp the cursor hook will send.
"""

from unittest.mock import Mock

from remitx_api.db.rls import (
    _copy_row_security_context_to_connection,
    _forget_applied_row_security_on_savepoint_rollback,
    adopt_row_security_role,
    bind_row_security_context,
    clear_row_security_context,
)
from remitx_api.extensions import db
from sqlalchemy import create_engine
from tests.kyc_helpers import make_user


def _postgres_connection():
    conn = Mock()
    conn.dialect.name = "postgresql"
    conn.info = {}
    conn.connection.dbapi_connection.cursor.return_value = Mock()
    return conn, Mock()


def _copy(conn, cursor, statement="SELECT 1"):
    _copy_row_security_context_to_connection(conn, cursor, statement, None, None, False)


def _begin(conn):
    engine = create_engine("postgresql+psycopg2://u:p@localhost/db")
    adopt_row_security_role(engine)
    for listener in engine.dispatch.begin:
        listener(conn)


def test_a_customer_route_stamps_the_user_as_not_admin(app_context):
    user = make_user("rls-customer")

    bind_row_security_context(user.id, is_admin_route=False)

    assert db.session.info["row_security_current_user_id"] == str(user.id)
    assert db.session.info["row_security_is_admin_route"] is False


def test_an_admin_route_stamps_the_user_as_admin(app_context):
    user = make_user("rls-officer")

    bind_row_security_context(user.id, is_admin_route=True)

    assert db.session.info["row_security_current_user_id"] == str(user.id)
    assert db.session.info["row_security_is_admin_route"] is True


def test_clearing_row_security_context_drops_the_stamp(app_context):
    user = make_user("rls-clear")
    bind_row_security_context(user.id, is_admin_route=True)

    clear_row_security_context()

    assert "row_security_current_user_id" not in db.session.info
    assert "row_security_is_admin_route" not in db.session.info


def test_row_security_is_copied_once_per_transaction_on_the_statement_cursor(
    app_context,
):
    """SET LOCAL must share this cursor's transaction, and only once.

    A second cursor can autocommit, so the policy sees an empty user and
    every row. Further statements in the transaction reuse the copy. The
    next transaction drops SET LOCAL, so it copies again.
    """
    user = make_user("rls-once")
    bind_row_security_context(user.id, is_admin_route=False)
    conn, cursor = _postgres_connection()

    _copy(conn, cursor)
    _copy(conn, cursor, "SELECT 2")

    assert cursor.execute.call_count == 1
    cursor.fetchall.assert_called_once()
    assert cursor.execute.call_args.args[1] == (
        "app.current_user_id",
        str(user.id),
        "app.is_admin_route",
        "false",
    )

    _begin(conn)
    _copy(conn, cursor, "SELECT 3")
    assert cursor.execute.call_count == 2


def test_an_unbound_session_does_not_copy_row_security(app_context):
    conn, cursor = _postgres_connection()

    _begin(conn)
    _copy(conn, cursor)
    _copy(conn, cursor, "SELECT 2")

    cursor.execute.assert_not_called()


def test_changing_the_stamp_copies_row_security_again(app_context):
    user = make_user("rls-change")
    conn, cursor = _postgres_connection()
    bind_row_security_context(user.id, is_admin_route=False)
    _copy(conn, cursor)

    clear_row_security_context()
    bind_row_security_context(user.id, is_admin_route=True)
    _copy(conn, cursor, "SELECT 2")
    _copy(conn, cursor, "SELECT 3")

    assert cursor.execute.call_count == 2
    assert cursor.execute.call_args.args[1][3] == "true"


def test_clearing_the_stamp_copies_unbound_settings_once(app_context):
    user = make_user("rls-unbind")
    conn, cursor = _postgres_connection()
    bind_row_security_context(user.id, is_admin_route=False)
    _copy(conn, cursor)

    clear_row_security_context()
    _copy(conn, cursor, "SELECT 2")
    _copy(conn, cursor, "SELECT 3")

    assert cursor.execute.call_count == 2
    assert cursor.execute.call_args.args[1][1] == ""
    assert cursor.execute.call_args.args[1][3] == "false"


def test_a_rolled_back_savepoint_copies_row_security_again(app_context):
    user = make_user("rls-savepoint")
    bind_row_security_context(user.id, is_admin_route=False)
    conn, cursor = _postgres_connection()
    _copy(conn, cursor)

    _forget_applied_row_security_on_savepoint_rollback(conn, "sa_savepoint_1", None)
    _copy(conn, cursor, "ROLLBACK TO SAVEPOINT sa_savepoint_1")
    _copy(conn, cursor, "SELECT 2")
    _copy(conn, cursor, "SELECT 3")

    assert cursor.execute.call_count == 2


def test_set_config_does_not_copy_row_security_again(app_context):
    user = make_user("rls-recurse")
    bind_row_security_context(user.id, is_admin_route=True)
    conn, cursor = _postgres_connection()

    _copy(conn, cursor, "SELECT set_config(%s, %s, true)")

    cursor.execute.assert_not_called()


def test_the_app_role_is_set_per_transaction_not_per_session():
    """A session-level SET ROLE does not survive Neon's transaction pooler.

    The next transaction can land on another server connection and run as the
    BYPASSRLS owner, while the role leaks to whoever gets this one — the QA
    migration that failed with "must be owner of table users".
    """
    engine = create_engine("postgresql+psycopg2://u:p@localhost/db")
    adopt_row_security_role(engine)

    begin_listeners = list(engine.dispatch.begin)
    assert len(begin_listeners) == 1

    cursor = Mock()
    conn = Mock()
    conn.dialect.name = "postgresql"
    conn.connection.dbapi_connection.cursor.return_value = cursor

    begin_listeners[0](conn)

    (statement,), _ = cursor.execute.call_args
    assert repr(statement).startswith("Composed([SQL('SET LOCAL ROLE ')")
    cursor.close.assert_called_once()
