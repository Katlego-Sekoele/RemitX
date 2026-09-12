"""Reads and writes over the append-only ``user_roles`` table.

Nothing here deletes. Revoking is ``UserRole.revoked_at`` being stamped by
the controller, which commits the whole use case in one transaction — see
CLAUDE.md on why multi-entity work does not chain ``Repository.save``.
"""

import uuid

from sqlalchemy import func, select

from remitx_api.extensions import db
from remitx_api.models.orm.role import Role
from remitx_api.models.orm.user import User
from remitx_api.models.orm.user_role import UserRole
from remitx_api.repositories.repository import Repository


class UserRoleRepository(Repository[UserRole, uuid.UUID]):
    def __init__(self) -> None:
        super().__init__(UserRole)

    def get_active(self, user_id: uuid.UUID, role_id: uuid.UUID) -> UserRole | None:
        """The live grant of one role to one user, if the user holds it."""
        return db.session.scalars(
            select(UserRole)
            .where(UserRole.user_id == user_id)
            .where(UserRole.role_id == role_id)
            .where(UserRole.revoked_at.is_(None))
        ).first()

    def list_history_for_user(
        self,
        user_id: uuid.UUID,
    ) -> list[tuple[UserRole, Role]]:
        """Every grant ever made to a user, newest first, revoked ones included.

        The revoked rows are the point of an append-only table: a staff list
        that only shows what is live cannot answer who held what in March.
        """
        return db.session.execute(
            select(UserRole, Role)
            .join(Role, Role.role_id == UserRole.role_id)
            .where(UserRole.user_id == user_id)
            .order_by(UserRole.granted_at.desc(), Role.name)
        ).all()

    def count_active_holders(self, role_id: uuid.UUID) -> int:
        """How many people currently hold a role."""
        return (
            db.session.scalar(
                select(func.count())
                .select_from(UserRole)
                .where(UserRole.role_id == role_id)
                .where(UserRole.revoked_at.is_(None))
            )
            or 0
        )

    def list_admins(self) -> list[tuple[User, Role, UserRole]]:
        """Everyone holding at least one active role, with that role.

        Role holders, deliberately — not the user table. A remittance
        platform's admin list is short and its customer list is not, so the
        access page lists people who have been given something rather than
        everyone who ever signed up.
        """
        return db.session.execute(
            select(User, Role, UserRole)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.role_id == UserRole.role_id)
            .where(UserRole.revoked_at.is_(None))
            .order_by(User.email, Role.name)
        ).all()
