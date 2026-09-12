"""Role administration: who holds what, and the grant/revoke that changes it.

Three permissions, three levels of reach, so the router declares the read
baseline (`role:read`) and each mutating route escalates on top of it —
`role:grant` to hand a role out, `role:revoke` to take one back. Searching
users escalates to `user:read` instead, because finding a colleague by email
is a user-directory capability that happens to be used from this page.

HTTP only, as the layering says. Nothing here decides access — that is
`RequirePermission`, which has already run by the time a handler does — and
nothing here maps a domain refusal to a status code either: controllers
raise from ``remitx_api.errors`` and the handler registered in app.py turns
those into responses.
"""

import uuid

from fastapi import APIRouter, Depends, Query
from remitx_api.auth.dependencies import get_current_user
from remitx_api.auth.permissions import RequirePermission
from remitx_api.controllers.user_role_controller import UserRoleController
from remitx_api.models.orm.permission import PermissionCode
from remitx_api.models.orm.user import User
from remitx_api.models.schemas.role import (
    AdminMemberRead,
    RoleGrantRequest,
    RoleGrantResult,
    RoleRevokeRequest,
    UserAccessRead,
    UserRoleRead,
    UserSearchRead,
)
from remitx_api.repositories.user_repository import UserRepository
from remitx_api.routes.routers import create_admin_router

router: APIRouter = create_admin_router(
    permission=PermissionCode.ROLE_READ,
    prefix="/admin/users",
    tags=["admin"],
)
controller = UserRoleController()
users = UserRepository()


@router.get("/admins", response_model=list[AdminMemberRead])
def list_admins():
    return controller.list_admins()


@router.get(
    "/search",
    response_model=list[UserSearchRead],
    dependencies=[Depends(RequirePermission(PermissionCode.USER_READ))],
)
def search_users(email: str = Query(min_length=3, description="Email fragment.")):
    return users.search_by_email(email)


@router.get("/{user_id}/roles", response_model=UserAccessRead)
def get_user_access(user_id: uuid.UUID):
    return controller.get_access(user_id)


@router.post(
    "/{user_id}/roles",
    response_model=RoleGrantResult,
    dependencies=[Depends(RequirePermission(PermissionCode.ROLE_GRANT))],
)
def grant_user_role(
    user_id: uuid.UUID,
    payload: RoleGrantRequest,
    # Not a gate — the dependency above is. The grant records who made it,
    # and whether that is the same person receiving it.
    actor: User = Depends(get_current_user),
):
    """Grant a role. Already held means the existing grant back, not a duplicate."""
    return controller.grant(user_id, payload, actor.id)


@router.delete(
    "/{user_id}/roles/{role}",
    response_model=UserRoleRead,
    dependencies=[Depends(RequirePermission(PermissionCode.ROLE_REVOKE))],
)
def revoke_user_role(
    user_id: uuid.UUID,
    role: str,
    payload: RoleRevokeRequest,
    actor: User = Depends(get_current_user),
):
    """Revoke a role: stamps the row, never deletes it."""
    return controller.revoke(user_id, role, payload.reason, actor.id)
