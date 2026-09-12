from remitx_api.models.orm.permission import PermissionCode


class PermissionController:
    def list_for_user(self, permissions: frozenset[PermissionCode]) -> list[str]:
        return sorted(permission.value for permission in permissions)
