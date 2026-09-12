import uuid

from sqlalchemy import select

from remitx_api.extensions import db
from remitx_api.models.orm.permission import Permission, PermissionCode
from remitx_api.models.orm.role_permission import RolePermission
from remitx_api.models.orm.user_role import UserRole


class PermissionRepository:
    def get_effective_permissions(
        self,
        user_id: uuid.UUID,
    ) -> frozenset[PermissionCode]:
        """Return permissions granted through active role assignments."""
        query = (
            select(Permission.permission)
            .join(
                RolePermission,
                RolePermission.permission_id == Permission.permission_id,
            )
            .join(UserRole, UserRole.role_id == RolePermission.role_id)
            .where(UserRole.user_id == user_id)
            .where(UserRole.revoked_at.is_(None))
            .where(RolePermission.revoked_at.is_(None))
        )
        return frozenset(
            PermissionCode(permission) for permission in db.session.scalars(query).all()
        )
