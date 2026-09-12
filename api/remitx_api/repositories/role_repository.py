import uuid

from sqlalchemy import select

from remitx_api.extensions import db
from remitx_api.models.orm.permission import Permission
from remitx_api.models.orm.role import Role
from remitx_api.models.orm.role_permission import RolePermission
from remitx_api.models.orm.user_role import UserRole
from remitx_api.repositories.repository import Repository


class RoleRepository(Repository[Role, uuid.UUID]):
    def __init__(self) -> None:
        super().__init__(Role)

    def get_by_name(self, name: str) -> Role | None:
        return db.session.scalars(select(Role).where(Role.name == name)).first()

    def list_with_active_permissions(self) -> list[tuple[Role, str | None]]:
        """Return each role paired with an active permission, or ``None`` if none."""
        return db.session.execute(
            select(Role, Permission.permission)
            .outerjoin(
                RolePermission,
                (RolePermission.role_id == Role.role_id)
                & (RolePermission.revoked_at.is_(None)),
            )
            .outerjoin(
                Permission,
                Permission.permission_id == RolePermission.permission_id,
            )
            .order_by(Role.name, Permission.permission)
        ).all()

    def user_has_admin_role(self, user_id: uuid.UUID) -> bool:
        """True when the user holds an active role flagged ``is_admin``."""
        query = (
            select(Role.role_id)
            .join(UserRole, UserRole.role_id == Role.role_id)
            .where(UserRole.user_id == user_id)
            .where(UserRole.revoked_at.is_(None))
            .where(Role.is_admin.is_(True))
            .limit(1)
        )
        return db.session.scalar(query) is not None

    def list_active_roles_for_user(
        self,
        user_id: uuid.UUID,
    ) -> list[tuple[Role, Permission | None]]:
        """Return each active role assignment paired with a permission, if any."""
        return db.session.execute(
            select(Role, Permission)
            .join(UserRole, UserRole.role_id == Role.role_id)
            .outerjoin(
                RolePermission,
                (RolePermission.role_id == Role.role_id)
                & (RolePermission.revoked_at.is_(None)),
            )
            .outerjoin(
                Permission,
                Permission.permission_id == RolePermission.permission_id,
            )
            .where(UserRole.user_id == user_id)
            .where(UserRole.revoked_at.is_(None))
            .order_by(Role.name, Permission.permission)
        ).all()
