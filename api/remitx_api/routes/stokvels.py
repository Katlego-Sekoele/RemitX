from fastapi import Depends, status

from remitx_api.auth.dependencies import get_current_user
from remitx_api.controllers.stokvel_controller import StokvelController
from remitx_api.models.orm.user import User
from remitx_api.models.schemas.stokvel import (
    StokvelCreateRequest,
    StokvelListRead,
    StokvelRead,
)
from remitx_api.openapi import Tag, error_responses
from remitx_api.routes.routers import create_customer_router

router = create_customer_router(prefix="/stokvels", tags=[Tag.STOKVELS])
controller = StokvelController()


@router.post(
    "",
    response_model=StokvelRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a stokvel",
    responses=error_responses(400, 403, 422),
)
def create_stokvel(
    payload: StokvelCreateRequest,
    user: User = Depends(get_current_user),
):
    """Create a stokvel with the caller as its Organiser and first Member.
    The caller's contributions are paid from their own fiat account in the
    Stokvel currency.

    Refusals: 403 if the caller is not KYC-verified; 400 if they hold no
    account in `currency` (they open one with `POST /accounts` first); 422
    for an invalid name, currency or amount."""
    return StokvelRead.from_view(
        controller.create_stokvel(
            user.id,
            name=payload.name,
            currency=payload.currency.value,
            contribution_amount=payload.contribution_amount,
        )
    )


@router.get(
    "",
    response_model=StokvelListRead,
    summary="List my stokvels and invitations",
)
def list_stokvels(user: User = Depends(get_current_user)):
    """The stokvels the caller is a current member of, and the invitations
    to join one that they have not answered yet, each newest first. A
    stokvel the caller has left is not listed."""
    return StokvelListRead.from_view(controller.list_stokvels(user.id))
