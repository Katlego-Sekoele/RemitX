import uuid

from remitx_api.models.schemas.me import MyPermissionResponse, MyRoleResponse
from remitx_api.models.schemas.role import RoleRead
from remitx_api.repositories.role_repository import RoleRepository


class RoleController:
    def __init__(self) -> None:
        self._repository = RoleRepository()

    def list_roles(self) -> list[RoleRead]:
        grouped: dict = {}
        for role, permission in self._repository.list_with_active_permissions():
            entry = grouped.setdefault(
                role.role_id,
                {"role": role, "permissions": []},
            )
            if permission is not None:
                entry["permissions"].append(permission)

        return [
            RoleRead(
                role_id=entry["role"].role_id,
                name=entry["role"].name,
                role_display_name=entry["role"].role_display_name,
                description=entry["role"].description,
                is_admin=entry["role"].is_admin,
                permissions=sorted(entry["permissions"]),
            )
            for entry in grouped.values()
        ]

    def list_my_roles(self, user_id: uuid.UUID) -> list[MyRoleResponse]:
        grouped: dict = {}
        for role, permission in self._repository.list_active_roles_for_user(user_id):
            entry = grouped.setdefault(
                role.role_id,
                {"role": role, "permissions": []},
            )
            if permission is not None:
                entry["permissions"].append(
                    MyPermissionResponse(
                        permission=permission.permission,
                        description=permission.description,
                    )
                )

        return [
            MyRoleResponse(
                name=entry["role"].name,
                display_name=entry["role"].role_display_name,
                description=entry["role"].description,
                permissions=sorted(
                    entry["permissions"],
                    key=lambda item: item.permission,
                ),
            )
            for entry in grouped.values()
        ]
