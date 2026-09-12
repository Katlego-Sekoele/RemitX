import uuid

from remitx_api.models.orm.permission import PermissionCode
from remitx_api.models.schemas.me import MeAccessResponse
from remitx_api.repositories.role_repository import RoleRepository


class PermissionController:
    def __init__(self) -> None:
        self._roles_repository = RoleRepository()

    def list_for_user(self, permissions: frozenset[PermissionCode]) -> list[str]:
        return sorted(permission.value for permission in permissions)

    def get_access(
        self,
        user_id: uuid.UUID,
        permissions: frozenset[PermissionCode],
    ) -> MeAccessResponse:
        return MeAccessResponse(
            permissions=self.list_for_user(permissions),
            is_admin=self._roles_repository.user_has_admin_role(user_id),
        )
