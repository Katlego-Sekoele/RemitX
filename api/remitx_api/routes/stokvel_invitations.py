import uuid

from fastapi import Depends, HTTPException, status

from remitx_api.auth.dependencies import get_current_user
from remitx_api.controllers.stokvel_invitation_controller import (
    StokvelInvitationController,
)
from remitx_api.models.orm.user import User
from remitx_api.models.schemas.stokvel import StokvelRead
from remitx_api.openapi import Tag, error_responses
from remitx_api.routes.routers import create_customer_router
from remitx_api.services.exchange_rate_service import RateUnavailableError

router = create_customer_router(prefix="/invitations", tags=[Tag.STOKVELS])
controller = StokvelInvitationController()


@router.post(
    "/{invitation_id}/accept",
    response_model=StokvelRead,
    summary="Accept a stokvel invitation",
    responses=error_responses(400, 403, 404, 409, 422, 503),
)
def accept_stokvel_invitation(
    invitation_id: uuid.UUID,
    user: User = Depends(get_current_user),
):
    """Accept the caller's invitation. They become a Member, paying
    contributions from their own account in the Stokvel currency, and get
    back the stokvel they joined.

    Refusals: 404 for an unknown invitation, or one the caller cannot see;
    403 `not_invitee` for a fellow member, who can see it but not answer it;
    409 `invitation_not_pending` once it has been accepted, declined, revoked
    or lapsed, `stokvel_deactivated`, and `monthly_limit_too_low` when what
    is left of the caller's monthly limit does not cover one contribution;
    422 `too_many_members` when the stokvel is full; 403 if the caller is no
    longer verified; 400 if they hold no account in the Stokvel currency
    (they open one with `POST /accounts` first). 503 when no exchange rate is
    available to price the contribution: nothing changes."""
    try:
        view = controller.accept(user.id, invitation_id)
    except RateUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Exchange rate unavailable; try again shortly",
        ) from exc
    return StokvelRead.from_view(view)


@router.post(
    "/{invitation_id}/decline",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Decline a stokvel invitation",
    responses=error_responses(403, 404, 409),
)
def decline_stokvel_invitation(
    invitation_id: uuid.UUID,
    user: User = Depends(get_current_user),
):
    """Decline the caller's invitation. They do not become a Member, and the
    Organiser may invite them again.

    Refusals: 404 for an unknown invitation, or one the caller cannot see;
    403 `not_invitee` for a fellow member, who can see it but not answer it;
    409 `invitation_not_pending` once it has been accepted, declined, revoked
    or lapsed."""
    controller.decline(user.id, invitation_id)


@router.post(
    "/{invitation_id}/revoke",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a stokvel invitation",
    responses=error_responses(403, 404, 409),
)
def revoke_stokvel_invitation(
    invitation_id: uuid.UUID,
    user: User = Depends(get_current_user),
):
    """Take back a pending invitation, as the stokvel's Organiser. The
    invitee may be invited again.

    Refusals: 404 for an unknown invitation, or one the caller cannot see;
    403 `not_organiser` for the invitee or a fellow member, who can see it
    but not revoke it; 409 `invitation_not_pending` once it has been
    accepted, declined, revoked or lapsed."""
    controller.revoke(user.id, invitation_id)
