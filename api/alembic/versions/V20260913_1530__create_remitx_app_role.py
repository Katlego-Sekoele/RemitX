"""create remitx app role

Row-level security is skipped for superusers and for roles with BYPASSRLS —
FORCE ROW LEVEL SECURITY does not change that. The Docker `POSTGRES_USER` is a
superuser and Neon's `neondb_owner` has BYPASSRLS, so an API connected as
either sees every KYC application no matter what the policy says.

`remitx_app` is the role the API and worker switch to on connect (see
``remitx_api.db.rls``): no login, no BYPASSRLS, only DML on the schema.
Migrations keep running as the owner. The migrating role is granted
membership so it can ``SET ROLE``, which a non-superuser owner needs.

Revision ID: f3a9c2d15e47
Revises: e1c8a4b73d20
Create Date: 2026-09-13 15:30:00.000000+00:00
"""

from alembic import op

revision: str = "f3a9c2d15e47"
down_revision: str | None = "e1c8a4b73d20"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None

_ROLE = "remitx_app"


def upgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{_ROLE}') THEN
            CREATE ROLE {_ROLE} NOLOGIN NOSUPERUSER NOBYPASSRLS;
          END IF;
        END
        $$
        """
    )
    op.execute(f"GRANT {_ROLE} TO CURRENT_USER")
    op.execute(f"GRANT USAGE ON SCHEMA public TO {_ROLE}")
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public "
        f"TO {_ROLE}"
    )
    op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {_ROLE}")
    # Tables later migrations create, as this same owner.
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {_ROLE}"
    )
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"GRANT USAGE, SELECT ON SEQUENCES TO {_ROLE}"
    )


def downgrade() -> None:
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"REVOKE USAGE, SELECT ON SEQUENCES FROM {_ROLE}"
    )
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM {_ROLE}"
    )
    op.execute(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {_ROLE}")
    op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {_ROLE}")
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {_ROLE}")
    op.execute(f"DROP ROLE IF EXISTS {_ROLE}")
