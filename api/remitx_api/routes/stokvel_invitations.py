import uuid

from fastapi import Depends, status

from remitx_api.auth.dependencies import get_current_user
from remitx_api.controllers.stokvel_invitation_controller import (
    StokvelInvitationController,
)
from remitx_api.models.orm.user import User
from remitx_api.models.schemas.stokvel import StokvelRead
from remitx_api.openapi import Tag, error_responses
from remitx_api.routes.routers import create_customer_router

router = create_customer_router(prefix="/invitations", tags=[Tag.STOKVELS])
controller = StokvelInvitationController()


@router.post(
    "/{invitation_id}/accept",
    response_model=StokvelRead,
    summary="Accept a stokvel invitation",
    responses=error_responses(400, 403, 404, 409, 422),
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
    or lapsed, and `stokvel_deactivated`; 422 `too_many_members` when the
    stokvel is full; 403 if the caller is no longer verified; 400 if they
    hold no account in the Stokvel currency (they open one with
    `POST /accounts` first)."""
    return StokvelRead.from_view(controller.accept(user.id, invitation_id))


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
