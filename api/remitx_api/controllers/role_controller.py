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
                permissions=sorted(entry["permissions"]),
            )
            for entry in grouped.values()
        ]
