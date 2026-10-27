"""Manual release of one stokvel round (R3-10, #247)."""

import uuid
from typing import Annotated

from fastapi import Depends, Path, status
from remitx_api.auth.dependencies import get_current_user
from remitx_api.controllers.stokvel_admin_controller import StokvelAdminController
from remitx_api.models.orm.permission import PermissionCode
from remitx_api.models.orm.user import User
from remitx_api.models.schemas.stokvel_contract import (
    AdminStokvelRoundRead,
    StokvelRoundFinaliseResponse,
)
from remitx_api.openapi import Tag, error_responses
from remitx_api.routes.routers import create_admin_router

router = create_admin_router(
    permission=PermissionCode.STOKVEL_ROUND_FINALISE,
    prefix="/admin/stokvels",
    tags=[Tag.ADMIN_STOKVELS],
)
controller = StokvelAdminController()


@router.get(
    "/rounds",
    response_model=list[AdminStokvelRoundRead],
    summary="List stokvel rounds for manual release",
)
def list_admin_stokvel_rounds():
    """Each active cycle's next unreleased round: paid counts, payout time and
    release status. Needs ``stokvel:round:finalise``."""
    return controller.list_rounds()


@router.post(
    "/{stokvel_id}/rounds/{round}/finalise",
    response_model=StokvelRoundFinaliseResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Release one stokvel round by hand",
    responses=error_responses(404, 409, 422, 503),
)
def finalise_stokvel_round(
    stokvel_id: uuid.UUID,
    round: Annotated[int, Path(ge=0, le=255)],
    user: User = Depends(get_current_user),
):
    """Queue `finalise` for round `round` (0-based) of the stokvel's open
    cycle, and write `stokvel.round.finalised_manually` in that same
    transaction. The contract still decides: a round that is not ready
    answers 409 `round_not_finalisable`, and one already released answers
    409 `round_already_finalised`. A payout left `processing` or `failed`
    answers 409 `round_release_not_pending`. A registered cycle the vault
    does not have open answers 503 `stokvel_chain_mismatch`. Needs
    ``stokvel:round:finalise``."""
    return controller.finalise_round(user.id, stokvel_id, round)
