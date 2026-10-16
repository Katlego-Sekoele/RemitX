import uuid

from fastapi import Depends, status

from remitx_api.auth.dependencies import get_current_user
from remitx_api.controllers.stokvel_contribution_controller import (
    StokvelContributionController,
)
from remitx_api.controllers.stokvel_controller import StokvelController
from remitx_api.models.orm.user import User
from remitx_api.models.schemas.stokvel import (
    StokvelContributionRead,
    StokvelCreateRequest,
    StokvelListRead,
    StokvelRead,
)
from remitx_api.openapi import Tag, error_responses
from remitx_api.routes.routers import create_customer_router

router = create_customer_router(prefix="/stokvels", tags=[Tag.STOKVELS])
controller = StokvelController()
contributions = StokvelContributionController()


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


@router.post(
    "/{stokvel_id}/contributions",
    response_model=StokvelContributionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Contribute to the stokvel's current round",
    responses=error_responses(400, 403, 404, 409),
)
def contribute_to_stokvel(
    stokvel_id: uuid.UUID,
    user: User = Depends(get_current_user),
):
    """Pay the caller's fixed contribution into their stokvel's open round:
    the first round that does not yet have a contribution from every member,
    as on the contract. No body: the member, round and amount are the
    stokvel's. The member is debited the UCTUSD contribution at the live rate
    from their account in the Stokvel currency, and it counts toward their
    own sending limits. Returns the contribution `pending`; it is confirmed
    once the worker's on-chain `contribute` is mined.

    Refusals carry a `code` (doc section 6): 404 for an unknown stokvel or
    one the caller is not a current member of (the same answer, so an id
    reveals nothing); 403 `not_a_member` for a member outside its current
    cycle; 409
    `cycle_not_open` with no active cycle, `wrong_round` once every round is
    paid, `contribution_already_paid` for a second payment to the open round.
    Plain 400 / 403 refusals, without a code, as for `POST /remittances`: a
    short available balance, a send over the daily or monthly limit, or a
    caller who is not verified."""
    return StokvelContributionRead.from_view(
        contributions.contribute(user.id, stokvel_id)
    )
