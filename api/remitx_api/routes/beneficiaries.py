from typing import Literal

from fastapi import Depends, HTTPException, Query, status

from remitx_api.auth.dependencies import get_current_user
from remitx_api.controllers.beneficiary_controller import (
    SORT_NEWEST,
    BeneficiaryController,
    InvalidSortOptionError,
)
from remitx_api.models.orm.user import User
from remitx_api.models.schemas.beneficiary import (
    BeneficiaryCreateRequest,
    BeneficiaryLookupResponse,
    BeneficiaryRead,
)
from remitx_api.openapi import Tag, error_responses
from remitx_api.routes.routers import create_customer_router

router = create_customer_router(prefix="/beneficiaries", tags=[Tag.BENEFICIARIES])
controller = BeneficiaryController()


@router.get(
    "/lookup-by-reference",
    response_model=BeneficiaryLookupResponse,
    summary="Look up who an account reference belongs to",
    responses=error_responses(400, 404),
)
def lookup_beneficiary_by_reference(
    account_reference: str = Query(
        ...,
        description=(
            "The beneficiary's fiat account reference "
            '(e.g. "tendai1-zwl") they shared off-platform — the same one '
            "they quote for EFT deposits."
        ),
    ),
    user: User = Depends(get_current_user),
):
    """Preview who an account reference resolves to, before adding them as a
    beneficiary: their short name, country and the account's currency, never
    their contact details.

    Answers 404 for an unknown reference, and 400 for a settlement (`-tok`)
    reference or one of the caller's own. Each `detail` is written for the
    sender to read.
    """
    return BeneficiaryLookupResponse.from_lookup(
        controller.lookup_by_fiat_account_reference(user.id, account_reference)
    )


@router.post(
    "/create-beneficiary",
    response_model=BeneficiaryRead,
    summary="Add a beneficiary",
    responses=error_responses(400, 409),
)
def create_beneficiary(
    payload: BeneficiaryCreateRequest,
    user: User = Depends(get_current_user),
):
    """Save a registered RemitX user as one of the caller's beneficiaries.

    Answers 409 when that person is already one of the caller's
    beneficiaries, or has no email or mobile on file; 400 when
    `linked_user_id` is not a user.
    """
    row = controller.create(
        sender_user_id=user.id,
        linked_user_id=payload.linked_user_id,
        payout_currency=payload.payout_currency,
        relationship=payload.relationship,
    )
    return BeneficiaryRead.from_row(row)


@router.get(
    "/get-beneficiary-list",
    response_model=list[BeneficiaryRead],
    summary="List my beneficiaries",
)
def list_my_beneficiaries(
    user: User = Depends(get_current_user),  # Get the current authenticated user
    sort: Literal["newest", "alphabetical"] = Query(
        SORT_NEWEST,
        description="Newest first, or A-Z by name.",
    ),
):
    """List the current user's beneficiaries. Each one's name and country
    are their verified ones once their KYC is approved, and their email and
    mobile are masked."""
    try:
        results = controller.list_beneficiaries(user.id, sort=sort)
    except InvalidSortOptionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="invalid sort option.",
        ) from exc
    return [BeneficiaryRead.from_row(row) for row in results]
