"""Router factories that enforce auth at mount time, not per handler."""

from fastapi import APIRouter, Depends

from remitx_api.auth.dependencies import get_current_user
from remitx_api.auth.permissions import RequirePermission
from remitx_api.models.orm.permission import PermissionCode


def create_public_router(**kwargs) -> APIRouter:
    """Routes reachable without authentication (health probes, docs, etc.)."""
    return APIRouter(**kwargs)


def create_customer_router(**kwargs) -> APIRouter:
    """Every route on this router requires an authenticated session."""
    return APIRouter(dependencies=[Depends(get_current_user)], **kwargs)


def create_admin_router(permission: PermissionCode, **kwargs) -> APIRouter:
    """Admin routes live under ``/admin`` and require a specific permission.

    ``permission`` is the baseline every route on the router needs — usually
    the read capability for whatever the router exposes. A route that does
    more than read escalates by declaring its own gate on top::

        @router.post(
            "/process",
            dependencies=[Depends(RequirePermission(PermissionCode.CASHIN_CONFIRM))],
        )

    Handlers never check permissions themselves, and nothing under ``/admin``
    gates on a role name or on a flag on the User row.
    """
    return APIRouter(
        dependencies=[
            Depends(get_current_user),
            Depends(RequirePermission(permission)),
        ],
        **kwargs,
    )
