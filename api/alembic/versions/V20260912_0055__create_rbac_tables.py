"""create rbac tables

Revision ID: a4f8c2e91d03
Revises: cb7d0365d3f7
Create Date: 2026-09-12 00:55:00.000000+00:00

"""

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from remitx_api.models.orm.permission import PermissionCode
from remitx_api.models.orm.rbac_seed import (
    PERMISSION_SEEDS,
    ROLE_SEEDS,
    precompute_permission_id_given_permission_code,
    precompute_role_id_given_role_name,
    precompute_role_permission_id_given_role_and_permission,
)

# revision identifiers, used by Alembic.
revision: str = "a4f8c2e91d03"
down_revision: str | None = "cb7d0365d3f7"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None

_PERMISSION_CHECK_VALUES = ", ".join(f"'{code.value}'" for code in PermissionCode)


def upgrade() -> None:
    op.create_table(
        "permissions",
        sa.Column("permission_id", sa.Uuid(), nullable=False),
        sa.Column("permission", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.CheckConstraint(
            f"permission IN ({_PERMISSION_CHECK_VALUES})",
            name="permissions_permission_valid",
        ),
        sa.PrimaryKeyConstraint("permission_id"),
        sa.UniqueConstraint("permission"),
    )
    op.create_table(
        "roles",
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("role_display_name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("role_id"),
    )
    op.create_index(op.f("ix_roles_name"), "roles", ["name"], unique=True)
    op.create_table(
        "role_permissions",
        sa.Column("role_permission_id", sa.Uuid(), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("permission_id", sa.Uuid(), nullable=False),
        sa.Column("granted_by", sa.Uuid(), nullable=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["granted_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["permission_id"], ["permissions.permission_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["role_id"], ["roles.role_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("role_permission_id"),
    )
    op.create_index(
        op.f("ix_role_permissions_permission_id"),
        "role_permissions",
        ["permission_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_role_permissions_role_id"),
        "role_permissions",
        ["role_id"],
        unique=False,
    )
    op.create_index(
        "uq_role_permissions_active",
        "role_permissions",
        ["role_id", "permission_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
        sqlite_where=sa.text("revoked_at IS NULL"),
    )
    op.create_table(
        "user_roles",
        sa.Column("user_role_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("granted_by", sa.Uuid(), nullable=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["granted_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.role_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_role_id"),
    )
    op.create_index(
        op.f("ix_user_roles_role_id"), "user_roles", ["role_id"], unique=False
    )
    op.create_index(
        op.f("ix_user_roles_user_id"), "user_roles", ["user_id"], unique=False
    )
    op.create_index(
        "uq_user_roles_active",
        "user_roles",
        ["user_id", "role_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
        sqlite_where=sa.text("revoked_at IS NULL"),
    )

    seeded_at = datetime.now(UTC)
    permissions_table = sa.table(
        "permissions",
        sa.column("permission_id", sa.Uuid()),
        sa.column("permission", sa.Text()),
        sa.column("description", sa.Text()),
    )
    roles_table = sa.table(
        "roles",
        sa.column("role_id", sa.Uuid()),
        sa.column("name", sa.Text()),
        sa.column("role_display_name", sa.Text()),
        sa.column("description", sa.Text()),
    )
    role_permissions_table = sa.table(
        "role_permissions",
        sa.column("role_permission_id", sa.Uuid()),
        sa.column("role_id", sa.Uuid()),
        sa.column("permission_id", sa.Uuid()),
        sa.column("granted_by", sa.Uuid()),
        sa.column("granted_at", sa.DateTime(timezone=True)),
        sa.column("revoked_at", sa.DateTime(timezone=True)),
    )

    op.bulk_insert(
        permissions_table,
        [
            {
                "permission_id": precompute_permission_id_given_permission_code(
                    seed.code
                ),
                "permission": seed.code.value,
                "description": seed.description,
            }
            for seed in PERMISSION_SEEDS
        ],
    )
    op.bulk_insert(
        roles_table,
        [
            {
                "role_id": precompute_role_id_given_role_name(role.name),
                "name": role.name,
                "role_display_name": role.display_name,
                "description": role.description,
            }
            for role in ROLE_SEEDS
        ],
    )
    role_permission_rows: list[dict] = []
    for role in ROLE_SEEDS:
        for permission in role.permissions:
            role_permission_rows.append(
                {
                    "role_permission_id": (
                        precompute_role_permission_id_given_role_and_permission(
                            role.name, permission
                        )
                    ),
                    "role_id": precompute_role_id_given_role_name(role.name),
                    "permission_id": (
                        precompute_permission_id_given_permission_code(permission)
                    ),
                    "granted_by": None,
                    "granted_at": seeded_at,
                    "revoked_at": None,
                }
            )
    op.bulk_insert(role_permissions_table, role_permission_rows)


def downgrade() -> None:
    op.drop_index("uq_user_roles_active", table_name="user_roles")
    op.drop_index(op.f("ix_user_roles_user_id"), table_name="user_roles")
    op.drop_index(op.f("ix_user_roles_role_id"), table_name="user_roles")
    op.drop_table("user_roles")
    op.drop_index("uq_role_permissions_active", table_name="role_permissions")
    op.drop_index(op.f("ix_role_permissions_role_id"), table_name="role_permissions")
    op.drop_index(
        op.f("ix_role_permissions_permission_id"), table_name="role_permissions"
    )
    op.drop_table("role_permissions")
    op.drop_index(op.f("ix_roles_name"), table_name="roles")
    op.drop_table("roles")
    op.drop_table("permissions")
