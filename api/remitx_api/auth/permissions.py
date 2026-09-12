"""
Request-scoped permission resolution and enforcement.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status

from remitx_api.auth.dependencies import get_current_user
from remitx_api.models.orm.permission import PermissionCode
from remitx_api.models.orm.user import User
from remitx_api.repositories.permission_repository import PermissionRepository

_permissions_repository = PermissionRepository()


def resolve_effective_permissions(user: User) -> frozenset[PermissionCode]:
    """Return permissions granted to the caller through active roles."""
    return _permissions_repository.get_effective_permissions(user.id)


def get_effective_permissions(
    user: User = Depends(get_current_user),
) -> frozenset[PermissionCode]:
    """Dependency that returns the caller's effective permissions."""
    return resolve_effective_permissions(user)


class RequirePermission:
    """Raise 403 when the caller lacks a specific permission.

    Composes on ``get_current_user`` (401 when unauthenticated).
    """

    __slots__ = ("permission",)

    def __init__(self, permission: PermissionCode) -> None:
        self.permission = permission

    def __call__(
        self,
        user: User = Depends(get_current_user),
    ) -> None:
        effective = resolve_effective_permissions(user)
        if self.permission not in effective:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permission: {self.permission.value}",
            )
