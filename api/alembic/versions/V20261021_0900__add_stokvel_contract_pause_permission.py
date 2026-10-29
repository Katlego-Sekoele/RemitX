"""add stokvel contract pause permission

``stokvel:contract:pause`` lets compliance staff pause and resume the shared
vault (R3-07, #244).

Revision ID: f4a8c2e91b03
Revises: 3e7b9d2c4a51
Create Date: 2026-10-21 09:00:00.000000+00:00

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

revision: str = "f4a8c2e91b03"
down_revision: str | None = "3e7b9d2c4a51"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None

_CONSTRAINT = "permissions_permission_valid"
_PERMISSION = PermissionCode.STOKVEL_CONTRACT_PAUSE
_ROLES = ("compliance_officer",)

_PERMISSION_ID = precompute_permission_id_given_permission_code(_PERMISSION)


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
    for role_name in _ROLES:
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
                        role_name, _PERMISSION
                    )
                ),
                "role_id": precompute_role_id_given_role_name(role_name),
                "permission_id": _PERMISSION_ID,
                "granted_at": datetime.now(UTC),
            },
        )


def downgrade() -> None:
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
