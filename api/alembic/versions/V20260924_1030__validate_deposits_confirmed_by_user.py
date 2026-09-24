"""validate deposits confirmed_by references users

Postgres cannot express a foreign key on ``confirmed_by`` while also allowing
the literal ``system``. A trigger enforces that admin ids exist in ``users``.

Revision ID: d9e1a4c2b807
Revises: c4b8e2f1a903
Create Date: 2026-09-24 10:30:00.000000+00:00

"""

from alembic import op

revision: str = "d9e1a4c2b807"
down_revision: str | None = "c4b8e2f1a903"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None

_FUNCTION = """
CREATE OR REPLACE FUNCTION validate_deposits_confirmed_by()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.confirmed_by IS NULL OR NEW.confirmed_by = 'system' THEN
    RETURN NEW;
  END IF;
  IF NOT (
    length(NEW.confirmed_by) = 36
    AND substr(NEW.confirmed_by, 9, 1) = '-'
    AND substr(NEW.confirmed_by, 14, 1) = '-'
    AND substr(NEW.confirmed_by, 19, 1) = '-'
    AND substr(NEW.confirmed_by, 24, 1) = '-'
  ) THEN
    RAISE EXCEPTION 'deposits.confirmed_by must be system or a user id';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM users WHERE id = NEW.confirmed_by::uuid) THEN
    RAISE EXCEPTION 'deposits.confirmed_by must reference an existing user';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

_TRIGGER = """
CREATE TRIGGER trg_deposits_confirmed_by
BEFORE INSERT OR UPDATE OF confirmed_by ON deposits
FOR EACH ROW EXECUTE FUNCTION validate_deposits_confirmed_by();
"""


def upgrade() -> None:
    op.execute(_FUNCTION)
    op.execute(_TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_deposits_confirmed_by ON deposits;")
    op.execute("DROP FUNCTION IF EXISTS validate_deposits_confirmed_by();")
