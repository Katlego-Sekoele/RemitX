import uuid

from fastapi import Depends, HTTPException, status

from remitx_api.auth.dependencies import get_current_user
from remitx_api.controllers.stokvel_contribution_controller import (
    StokvelContributionController,
)
from remitx_api.controllers.stokvel_controller import StokvelController
from remitx_api.controllers.stokvel_cycle_controller import StokvelCycleController
from remitx_api.controllers.stokvel_invitation_controller import (
    StokvelInvitationController,
)
from remitx_api.controllers.stokvel_setup_controller import StokvelSetupController
from remitx_api.models.orm.user import User
from remitx_api.models.schemas.stokvel import (
    SentStokvelInvitationRead,
    StokvelBeneficiaryRead,
    StokvelBeneficiaryRequest,
    StokvelContinuationRead,
    StokvelContinuationRequest,
    StokvelContributionRead,
    StokvelCreateRequest,
    StokvelCycleRead,
    StokvelCycleStartRequest,
    StokvelDetailRead,
    StokvelInvitationCreateRequest,
    StokvelListRead,
    StokvelPayoutOrderRead,
    StokvelPayoutOrderRequest,
    StokvelRead,
)
from remitx_api.openapi import Tag, error_responses
from remitx_api.routes.routers import create_customer_router
from remitx_api.services.exchange_rate_service import RateUnavailableError

router = create_customer_router(prefix="/stokvels", tags=[Tag.STOKVELS])
controller = StokvelController()
contributions = StokvelContributionController()
cycles = StokvelCycleController()
invitations = StokvelInvitationController()
setup = StokvelSetupController()


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


@router.get(
    "/{stokvel_id}",
    response_model=StokvelDetailRead,
    summary="Read one stokvel",
    responses=error_responses(404),
)
def get_stokvel(
    stokvel_id: uuid.UUID,
    user: User = Depends(get_current_user),
):
    """The member screen for one stokvel: the group, its current cycle,
    who has paid, and each round's payout once one exists.

    404 for an unknown stokvel or one the caller is not a current member of,
    the same answer, so an id reveals nothing. `contribution_fiat_estimate`
    is null when no exchange rate is available. `fee_amount` is set only on
    the caller's own contributions. `pool_fiat_amount` is null.
    `remittance_id` is the payout reference."""
    return StokvelDetailRead.from_view(controller.get_stokvel(user.id, stokvel_id))


@router.post(
    "/{stokvel_id}/contributions",
    response_model=StokvelContributionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Contribute to the stokvel's current round",
    responses=error_responses(400, 403, 404, 409, 503),
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
    `cycle_not_open` with no active cycle, `cycle_starting` while a started
    cycle is not yet open on-chain (try again shortly), `wrong_round` once
    every round is paid, `contribution_already_paid` for a second payment to
    the open round.
    Plain 400 / 403 refusals, without a code, as for `POST /remittances`: a
    short available balance, a send over the daily or monthly limit, or a
    caller who is not verified. 503 when no exchange rate is available, as
    for a quote: nothing is recorded."""
    try:
        view = contributions.contribute(user.id, stokvel_id)
    except RateUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Exchange rate unavailable; try again shortly",
        ) from exc
    return StokvelContributionRead.from_view(view)


@router.post(
    "/{stokvel_id}/invitations",
    response_model=SentStokvelInvitationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Invite a user to the stokvel",
    responses=error_responses(400, 403, 404, 409, 422),
)
def invite_to_stokvel(
    stokvel_id: uuid.UUID,
    payload: StokvelInvitationCreateRequest,
    user: User = Depends(get_current_user),
):
    """Invite someone to the caller's stokvel: the owner of
    `account_reference`, or the person one of the caller's beneficiaries
    links to (`beneficiary_id`). They become a Member only if they accept.
    Invitations may outnumber the free places: the member cap holds when an
    invitation is accepted.

    Refusals carry a `code` where doc section 6 gives one: 404 for an unknown
    stokvel or one the caller is not a member of, for an unknown reference,
    and for a beneficiary that isn't the caller's; 403 `not_organiser` for a
    member who is not the Organiser; 403 `invitee_not_verified` for an
    invitee who is not KYC-verified; 422 `invitee_currency_mismatch` for an
    account not in the Stokvel currency, or a beneficiary with no account in
    it; 422 `too_many_members` when the stokvel is full; 409
    `already_a_member`, `invitation_already_pending` or
    `stokvel_deactivated`; 400 for the caller's own reference."""
    return SentStokvelInvitationRead.from_view(
        invitations.invite(
            user.id,
            stokvel_id,
            account_reference=payload.account_reference,
            beneficiary_id=payload.beneficiary_id,
        )
    )


@router.put(
    "/{stokvel_id}/payout-order",
    response_model=StokvelPayoutOrderRead,
    summary="Set the payout order",
    responses=error_responses(403, 404, 409, 422),
)
def set_payout_order(
    stokvel_id: uuid.UUID,
    payload: StokvelPayoutOrderRequest,
    user: User = Depends(get_current_user),
):
    """Enter the payout order the members agreed off the platform (D3) for
    the stokvel's next cycle: `member_ids[0]` is paid in round 0. It must
    list every current member exactly once, and replaces any earlier order.
    It can be changed as often as needed until the cycle starts.

    Refusals carry a `code` where doc section 6 gives one: 404 for an
    unknown stokvel or one the caller is not a current member of; 403
    `not_organiser` for a member who is not the Organiser; 409
    `stokvel_deactivated`, `cycle_locked` once the cycle has started, or
    `cycle_not_forming` when the last cycle has closed and the next is not
    open yet; 422 `invalid_payout_order` for a duplicate, a former member,
    someone who is not a member, or a current member left out."""
    return StokvelPayoutOrderRead.from_view(
        setup.set_payout_order(user.id, stokvel_id, payload.member_ids)
    )


@router.put(
    "/{stokvel_id}/members/me/beneficiary",
    response_model=StokvelBeneficiaryRead,
    summary="Choose my payout beneficiary",
    responses=error_responses(400, 404, 409, 422),
)
def set_my_beneficiary(
    stokvel_id: uuid.UUID,
    payload: StokvelBeneficiaryRequest,
    user: User = Depends(get_current_user),
):
    """Choose which of the caller's own beneficiaries the stokvel pays their
    pool to in its next cycle, in that beneficiary's payout currency.
    Replaces any earlier choice, and can be changed until the cycle starts.

    Refusals carry a `code` where doc section 6 gives one: 404 for an
    unknown stokvel or one the caller is not a current member of, and for a
    beneficiary that is unknown or not the caller's; 400 if the recipient
    no longer holds an account in the beneficiary's payout currency; 409
    `stokvel_deactivated`, `cycle_locked` once the cycle has started, or
    `cycle_not_forming` when there is no cycle to set up yet."""
    return StokvelBeneficiaryRead.from_view(
        setup.set_beneficiary(user.id, stokvel_id, payload.beneficiary_id)
    )


@router.post(
    "/{stokvel_id}/cycles",
    response_model=StokvelCycleRead,
    status_code=status.HTTP_201_CREATED,
    summary="Start the stokvel's cycle",
    responses=error_responses(403, 404, 409, 422),
)
def start_stokvel_cycle(
    stokvel_id: uuid.UUID,
    payload: StokvelCycleStartRequest,
    user: User = Depends(get_current_user),
):
    """Start the stokvel's forming cycle with the given round schedule, one
    round per current member in payout order. Every current member needs a
    place in the payout order and a payout beneficiary first, and there must
    be at least two. Invitations still pending lapse; the members, payout
    order and beneficiaries are locked for the cycle.

    The cycle is then registered on the stokvel contract by the worker:
    `registered_at` stays null until that is mined, and contributions are
    refused with 409 `cycle_starting` until then.

    Refusals carry a `code` where doc section 6 gives one: 404 for an
    unknown stokvel or one the caller is not a current member of; 403
    `not_organiser` for a member who is not the Organiser; 409
    `stokvel_deactivated`, `cycle_not_forming` when there is no forming
    cycle, `cycle_in_progress` once it has started, `too_few_members`, or
    `cycle_not_ready` when a member has no place in the payout order or no
    beneficiary, or the members changed since the order was set; 422
    `too_many_members`, or `invalid_schedule` for the wrong number of rounds
    or times out of order."""
    return StokvelCycleRead.from_view(
        cycles.start_cycle(user.id, stokvel_id, payload.schedule())
    )


@router.post(
    "/{stokvel_id}/members/me/continuation",
    response_model=StokvelContinuationRead,
    summary="Continue or leave after a cycle",
    responses=error_responses(400, 404, 409, 422),
)
def continue_or_leave_stokvel(
    stokvel_id: uuid.UUID,
    payload: StokvelContinuationRequest,
    user: User = Depends(get_current_user),
):
    """After a cycle closes, continue into the stokvel's next cycle or leave
    it. Allowed until the Organiser starts the next cycle; a member who has
    not chosen by then is treated as leaving.

    Continuing can name a new beneficiary (checked as for `PUT
    /members/me/beneficiary`); without one, the current choice is kept or
    carried over from the closed cycle. It can be repeated. Leaving is
    final. The Organiser is always continued and cannot leave.

    Refusals carry a `code` where doc section 6 gives one: 404 for an
    unknown stokvel or one the caller is not a current member of, and for a
    beneficiary that is unknown or not the caller's; 400 if the recipient
    no longer holds an account in the beneficiary's payout currency; 409
    `stokvel_deactivated`, `nothing_to_continue` before any cycle has
    finished, `cycle_locked` once the next cycle has started,
    `cycle_not_forming` while the Organiser has not opened it, or
    `organiser_cannot_leave`; 422 for an invalid request body."""
    return StokvelContinuationRead.from_view(
        setup.continue_or_leave(
            user.id, stokvel_id, payload.choice, payload.beneficiary_id
        )
    )
