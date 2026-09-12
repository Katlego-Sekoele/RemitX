"""Seed RBAC catalogue rows in throwaway test databases."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from remitx_api.extensions import db
from remitx_api.models.orm.permission import Permission
from remitx_api.models.orm.rbac_seed import (
    PERMISSION_SEEDS,
    ROLE_SEEDS,
    precompute_permission_id_given_permission_code,
    precompute_role_id_given_role_name,
    precompute_role_permission_id_given_role_and_permission,
)
from remitx_api.models.orm.role import Role
from remitx_api.models.orm.role_permission import RolePermission
from remitx_api.models.orm.user_role import UserRole


def seed_rbac_catalogue() -> None:
    for seed in PERMISSION_SEEDS:
        db.session.add(
            Permission(
                permission_id=precompute_permission_id_given_permission_code(seed.code),
                permission=seed.code.value,
                description=seed.description,
            )
        )

    for role_seed in ROLE_SEEDS:
        db.session.add(
            Role(
                role_id=precompute_role_id_given_role_name(role_seed.name),
                name=role_seed.name,
                role_display_name=role_seed.display_name,
                description=role_seed.description,
                is_admin=role_seed.is_admin,
            )
        )

    seeded_at = datetime.now(UTC)
    for role_seed in ROLE_SEEDS:
        for permission in role_seed.permissions:
            db.session.add(
                RolePermission(
                    role_permission_id=(
                        precompute_role_permission_id_given_role_and_permission(
                            role_seed.name,
                            permission,
                        )
                    ),
                    role_id=precompute_role_id_given_role_name(role_seed.name),
                    permission_id=precompute_permission_id_given_permission_code(
                        permission
                    ),
                    granted_at=seeded_at,
                )
            )

    db.session.commit()


def grant_role(
    user_id: uuid.UUID,
    role_name: str,
    *,
    granted_by: uuid.UUID | None = None,
) -> UserRole:
    assignment = UserRole(
        user_id=user_id,
        role_id=precompute_role_id_given_role_name(role_name),
        granted_by=granted_by,
    )
    db.session.add(assignment)
    db.session.commit()
    return assignment


def revoke_role(assignment: UserRole) -> None:
    assignment.revoked_at = datetime.now(UTC)
    db.session.commit()
