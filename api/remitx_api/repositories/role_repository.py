import uuid

from sqlalchemy import select

from remitx_api.extensions import db
from remitx_api.models.orm.permission import Permission
from remitx_api.models.orm.role import Role
from remitx_api.models.orm.role_permission import RolePermission
from remitx_api.repositories.repository import Repository


class RoleRepository(Repository[Role, uuid.UUID]):
    def __init__(self) -> None:
        super().__init__(Role)

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
