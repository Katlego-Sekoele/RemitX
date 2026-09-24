"""add platform_account read permission

``platform_account:read`` lets staff see RemitX's own account balances — the
bank, fee revenue and treasury accounts — on ``GET /admin/platform-accounts``.
The Treasury Operator role gets it, so every treasurer can see them.

The RBAC migration (a4f8c2e91d03) seeds from the live catalogue, so on a
database created after this revision the permission and its grant are already
there. Both inserts below skip a row that exists.

Revision ID: f126ff62af9a
Revises: 198395894d4a
Create Date: 2026-09-24 12:55:10.519244+00:00

"""

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from remitx_api.models.orm.permission import PermissionCode
from remitx_api.models.orm.rbac_seed import (
    PERMISSION_SEEDS,
    precompute_permission_id_given_permission_code,
    precompute_role_id_given_role_name,
    precompute_role_permission_id_given_role_and_permission,
)

# revision identifiers, used by Alembic.
revision: str = "f126ff62af9a"
down_revision: str | None = "198395894d4a"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None

_CONSTRAINT = "permissions_permission_valid"
_PERMISSION = PermissionCode.PLATFORM_ACCOUNT_READ
_ROLE = "treasury_operator"

_PERMISSION_ID = precompute_permission_id_given_permission_code(_PERMISSION)
_ROLE_ID = precompute_role_id_given_role_name(_ROLE)


def _permission_check(codes) -> str:
    return "permission IN ({})".format(", ".join(f"'{code.value}'" for code in codes))


def upgrade() -> None:
    op.drop_constraint(_CONSTRAINT, "permissions", type_="check")
    op.create_check_constraint(
        _CONSTRAINT, "permissions", _permission_check(PermissionCode)
    )

    description = next(
        seed.description for seed in PERMISSION_SEEDS if seed.code == _PERMISSION
    )
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "INSERT INTO permissions (permission_id, permission, description) "
            "SELECT :permission_id, :permission, :description "
            "WHERE NOT EXISTS "
            "(SELECT 1 FROM permissions WHERE permission = :permission)"
        ),
        {
            "permission_id": _PERMISSION_ID,
            "permission": _PERMISSION.value,
            "description": description,
        },
    )
    connection.execute(
        sa.text(
            "INSERT INTO role_permissions "
            "(role_permission_id, role_id, permission_id, granted_at) "
            "SELECT :role_permission_id, :role_id, :permission_id, :granted_at "
            "WHERE NOT EXISTS (SELECT 1 FROM role_permissions "
            "WHERE role_id = :role_id AND permission_id = :permission_id "
            "AND revoked_at IS NULL)"
        ),
        {
            "role_permission_id": (
                precompute_role_permission_id_given_role_and_permission(
                    _ROLE, _PERMISSION
                )
            ),
            "role_id": _ROLE_ID,
            "permission_id": _PERMISSION_ID,
            "granted_at": datetime.now(UTC),
        },
    )


def downgrade() -> None:
    # role_permissions cascades from permissions.
    op.execute(
        sa.text("DELETE FROM permissions WHERE permission = :permission").bindparams(
            permission=_PERMISSION.value
        )
    )
    op.drop_constraint(_CONSTRAINT, "permissions", type_="check")
    op.create_check_constraint(
        _CONSTRAINT,
        "permissions",
        _permission_check(code for code in PermissionCode if code != _PERMISSION),
    )
