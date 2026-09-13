"""The request stamps who is asking, and whether the route is admin.

Postgres RLS reads those session settings. Tests run on SQLite, so this only
checks the session stamp the cursor hook will send.
"""

from remitx_api.db.rls import bind_row_security_context, clear_row_security_context
from remitx_api.extensions import db
from tests.kyc_helpers import make_user


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


def test_setting_row_security_uses_the_statement_cursor_and_clearing_does_not():
    """SET LOCAL must share SQLAlchemy's transaction or it is a no-op.

    That is why the admin queue still showed the caller's own application:
    a second cursor can autocommit, the policy sees an empty user, and every
    row is visible. Clearing after the statement must not reuse that cursor
    or it replaces the query result (the 500 on GET /me/permissions).
    """
    from unittest.mock import Mock

    from remitx_api.db.rls import (
        _clear_row_security_context_from_connection,
        _copy_row_security_context_to_connection,
    )

    statement_cursor = Mock()
    extra_cursor = Mock()
    conn = Mock()
    conn.dialect.name = "postgresql"
    conn.connection.cursor.return_value = extra_cursor

    _copy_row_security_context_to_connection(
        conn, statement_cursor, "SELECT users.id FROM users", None, None, False
    )
    _clear_row_security_context_from_connection(
        conn, statement_cursor, "SELECT users.id FROM users", None, None, False
    )

    statement_cursor.execute.assert_called_once()
    statement_cursor.fetchall.assert_called_once()
    extra_cursor.execute.assert_called_once()
    extra_cursor.close.assert_called()
