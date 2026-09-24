"""Admin visibility into withdrawals.

Router exposes is a customer's withdrawal history for the admin portal's
user-profile page.
Gated by the payout_operator role's `cashout:read` permission.
"""

import uuid

from fastapi import APIRouter
from remitx_api.controllers.withdrawal_controller import WithdrawalController
from remitx_api.models.orm.permission import PermissionCode
from remitx_api.models.schemas.withdrawal import WithdrawalRead
from remitx_api.openapi import Tag
from remitx_api.routes.routers import create_admin_router

router: APIRouter = create_admin_router(
    permission=PermissionCode.CASHOUT_READ,
    prefix="/admin/withdrawals",
    tags=[Tag.ADMIN_WITHDRAWALS],
)
controller = WithdrawalController()


@router.get(
    "/users/{user_id}",
    response_model=list[WithdrawalRead],
    summary="List a user's withdrawals",
)
def list_withdrawals_for_user(user_id: uuid.UUID):
    """The admin portal's user-profile page: every withdrawal this customer
    has ever made, newest first."""
    return [
        WithdrawalRead.model_validate(view)
        for view in controller.list_user_withdrawal_history(user_id)
    ]
