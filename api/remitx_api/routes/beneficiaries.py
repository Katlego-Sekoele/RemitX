import uuid
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
    BeneficiaryUpdateRequest,
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
            '(e.g. "sian1-zar") they shared off-platform — the same one '
            "they quote for EFT deposits."
        ),
    ),
    user: User = Depends(get_current_user),
):
    """Preview who an account reference resolves to, before adding them as a
    beneficiary: their short name, country, the account's currency, and the
    payout accounts they already hold. Never their contact details.

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
    `linked_user_id` is not a user, or when they do not hold an account in
    `payout_currency`.
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


@router.patch(
    "/{beneficiary_id}",
    response_model=BeneficiaryRead,
    summary="Edit a beneficiary",
    responses=error_responses(400, 404),
)
def update_beneficiary(
    beneficiary_id: uuid.UUID,
    payload: BeneficiaryUpdateRequest,
    user: User = Depends(get_current_user),
):
    """Change one of the caller's beneficiaries' payout currency or
    relationship, or both. The person can't be changed: a different person is
    a different beneficiary (remove, then add).

    Answers 400 when the new payout currency is not an account they hold.
    Someone else's beneficiary answers 404, the same as an unknown id.
    """
    row = controller.update(
        user.id,
        beneficiary_id,
        payout_currency=payload.payout_currency,
        relationship=payload.relationship,
    )
    return BeneficiaryRead.from_row(row)


@router.delete(
    "/{beneficiary_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a beneficiary",
    responses=error_responses(404),
)
def delete_beneficiary(
    beneficiary_id: uuid.UUID,
    user: User = Depends(get_current_user),
) -> None:
    """Remove one of the caller's beneficiaries for good. Past transfers keep
    their recipient: they point at the person, not this entry.

    Someone else's beneficiary answers 404, the same as an unknown id.
    """
    controller.delete(user.id, beneficiary_id)
