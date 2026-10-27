"""stokvel cover photo

A current member may set one cover photo for a stokvel. The bytes live in
object storage; this table stores the key and the sniffed content type.

``stokvels`` itself may be updated only by the Organiser (``V20261009_1801``),
so the cover is its own table. Current members may read, insert and update
it. A former member may not: ``stokvel_is_current_member`` requires
``left_at`` null, unlike ``stokvel_is_member``. There is no ``DELETE``
policy. Replacing a photo updates the row and overwrites the object.

The trigger ``stokvel_cover_key_fixed`` refuses any key other than
``stokvel-covers/<stokvel id>``, for every role, so a member cannot point
the row at some other object (a KYC document, for one) and have the API
sign it. SQLSTATE 23514. The API also refuses to sign a key that does not
match, which is what SQLite tests see: they have no trigger.

Revision ID: d4c8e2a91b17
Revises: b6d1e4a7c302
Create Date: 2026-10-27 21:34:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4c8e2a91b17"
down_revision: str | None = "b6d1e4a7c302"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None

_ME = "current_setting('app.current_user_id', true)"
_APP_ROLE = "remitx_app"
_TABLE = "stokvel_covers"
_FUNCTION = "stokvel_is_current_member"
_TRIGGER_FUNCTION = "stokvel_cover_key_fixed"


def _customer(expression: str) -> str:
    """Workers, migrations and admin routes see every row; customers see
    ``expression``."""
    return f"""CASE
      WHEN COALESCE({_ME}, '') = ''
        OR current_setting('app.is_admin_route', true) = 'true' THEN true
      ELSE ({expression})
    END"""


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("stokvel_id", sa.Uuid(), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "content_type IN ('image/jpeg', 'image/png', 'image/webp')",
            name="stokvel_covers_content_type_valid",
        ),
        sa.ForeignKeyConstraint(
            ["stokvel_id"],
            ["stokvels.id"],
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("stokvel_id"),
    )
    op.create_index(
        op.f("ix_stokvel_covers_updated_by_user_id"),
        _TABLE,
        ["updated_by_user_id"],
        unique=False,
    )

    op.execute(
        f"""
        CREATE FUNCTION {_FUNCTION}(p_stokvel_id uuid, p_user_id text)
          RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
          SET search_path = pg_catalog, public, pg_temp
          AS $$ SELECT EXISTS (
            SELECT 1 FROM stokvel_members
            WHERE stokvel_id = p_stokvel_id
              AND user_id::text = p_user_id
              AND left_at IS NULL
          ) $$
        """
    )
    op.execute(f"REVOKE ALL ON FUNCTION {_FUNCTION}(uuid, text) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {_FUNCTION}(uuid, text) TO {_APP_ROLE}")

    member = f"{_FUNCTION}(stokvel_id, {_ME})"
    op.execute(f"ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY {_TABLE}_select ON {_TABLE} FOR SELECT
          USING ({_customer(member)})
        """
    )
    op.execute(
        f"""
        CREATE POLICY {_TABLE}_insert ON {_TABLE} FOR INSERT
          WITH CHECK ({_customer(member)})
        """
    )
    op.execute(
        f"""
        CREATE POLICY {_TABLE}_update ON {_TABLE} FOR UPDATE
          USING ({_customer(member)})
          WITH CHECK ({_customer(member)})
        """
    )

    op.execute(
        f"""
        CREATE FUNCTION {_TRIGGER_FUNCTION}()
          RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
          SET search_path = pg_catalog, public, pg_temp
          AS $$
        BEGIN
          IF NEW.object_key IS DISTINCT FROM
             'stokvel-covers/' || NEW.stokvel_id::text
          THEN
            RAISE EXCEPTION 'cover object key must name this stokvel'
              USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END;
        $$
        """
    )
    op.execute(f"REVOKE ALL ON FUNCTION {_TRIGGER_FUNCTION}() FROM PUBLIC")
    op.execute(
        f"""
        CREATE TRIGGER {_TRIGGER_FUNCTION}
          BEFORE INSERT OR UPDATE OF object_key, stokvel_id
          ON {_TABLE}
          FOR EACH ROW EXECUTE FUNCTION {_TRIGGER_FUNCTION}()
        """
    )


def downgrade() -> None:
    op.execute(f"DROP TRIGGER IF EXISTS {_TRIGGER_FUNCTION} ON {_TABLE}")
    op.execute(f"DROP FUNCTION IF EXISTS {_TRIGGER_FUNCTION}()")
    for operation in ("select", "insert", "update"):
        op.execute(f"DROP POLICY IF EXISTS {_TABLE}_{operation} ON {_TABLE}")
    op.execute(f"DROP FUNCTION IF EXISTS {_FUNCTION}(uuid, text)")
    op.drop_index(op.f("ix_stokvel_covers_updated_by_user_id"), table_name=_TABLE)
    op.drop_table(_TABLE)
