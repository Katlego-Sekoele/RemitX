"""Seed RBAC catalogue rows in throwaway test databases, and serve a client
whose caller holds real granted roles.

Tests gate on permissions the same way routes do: nothing here fakes a
`RequirePermission` result — the rows are written and the dependency resolves
them out of the database on every request.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from remitx_api.app import create_app
from remitx_api.auth.dependencies import get_current_user
from remitx_api.config import TestConfig
from remitx_api.extensions import db
from remitx_api.models.orm.permission import Permission, PermissionCode
from remitx_api.models.orm.rbac_seed import (
    PERMISSION_SEEDS,
    ROLE_SEEDS,
    precompute_permission_id_given_permission_code,
    precompute_role_id_given_role_name,
    precompute_role_permission_id_given_role_and_permission,
)
from remitx_api.models.orm.role import Role
from remitx_api.models.orm.role_permission import RolePermission
from remitx_api.models.orm.user import User
from remitx_api.models.orm.user_role import UserRole
from remitx_api.repositories.user_repository import UserRepository


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


def grant_permissions(
    user_id: uuid.UUID,
    *permissions: PermissionCode,
    role_name: str = "ad_hoc",
) -> UserRole:
    """Grant exactly these permissions through a role invented for one test.

    The seeded catalogue has no role that holds, say, `cashin:read` without
    `cashin:confirm`, so proving a route escalates beyond its router's
    baseline needs a role built for the occasion.
    """
    role_id = precompute_role_id_given_role_name(role_name)
    db.session.add(
        Role(
            role_id=role_id,
            name=role_name,
            role_display_name=role_name,
            description=f"Ad-hoc test role: {role_name}",
            is_admin=True,
        )
    )
    granted_at = datetime.now(UTC)
    for permission in permissions:
        db.session.add(
            RolePermission(
                role_permission_id=(
                    precompute_role_permission_id_given_role_and_permission(
                        role_name, permission
                    )
                ),
                role_id=role_id,
                permission_id=precompute_permission_id_given_permission_code(
                    permission
                ),
                granted_at=granted_at,
            )
        )
    assignment = UserRole(user_id=user_id, role_id=role_id)
    db.session.add(assignment)
    db.session.commit()
    return assignment


def make_user(suffix: str) -> User:
    return User(
        id=uuid.uuid4(),
        clerk_user_id=f"user_{suffix}",
        email=f"{suffix}@example.com",
        base_reference=f"{suffix}1",
    )


@contextmanager
def rbac_client(
    user: User,
    *,
    roles: tuple[str, ...] = (),
    permissions: tuple[PermissionCode, ...] = (),
) -> Iterator[TestClient]:
    """One app + database: seed catalogue, persist user, grant access, serve.

    The session stays open for the body, so a test can seed its own fixtures
    (accounts, other users) without opening one itself.
    """
    app = create_app(TestConfig)
    app.dependency_overrides[get_current_user] = lambda: user
    with TestClient(app) as client:
        token = db.open_session()
        try:
            UserRepository().save(user)
            seed_rbac_catalogue()
            for role_name in roles:
                grant_role(user.id, role_name)
            if permissions:
                grant_permissions(user.id, *permissions)
            yield client
        finally:
            db.close_session(token)
