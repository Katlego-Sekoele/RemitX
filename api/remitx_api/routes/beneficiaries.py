from fastapi import Depends, HTTPException, Query, status

from remitx_api.auth.dependencies import get_current_user
from remitx_api.controllers.beneficiary_controller import (
    SORT_NEWEST,
    BeneficiaryController,
    CannotAddSelfError,
    InvalidSortOptionError,
    LookupByReferenceError,
    MissingContactInfoError,
    NotAFiatAccountError,
    UnknownLinkedUserError,
)
from remitx_api.models.orm.user import User
from remitx_api.models.schemas.beneficiary import (
    BeneficiaryCreateRequest,
    BeneficiaryLookupResponse,
    BeneficiaryRead,
)
from remitx_api.routes.routers import create_customer_router

router = create_customer_router(prefix="/beneficiaries", tags=["beneficiaries"])
controller = BeneficiaryController()


@router.get("/lookup-by-reference", response_model=BeneficiaryLookupResponse)
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
    beneficiary."""
    try:
        return controller.lookup_by_fiat_account_reference(user.id, account_reference)
    except LookupByReferenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No account found for that reference",
        ) from exc
    except NotAFiatAccountError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "That reference is the uctusd settlement account, not a fiat account"
            ),
        ) from exc
    except CannotAddSelfError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You can't add yourself as a beneficiary",
        ) from exc


@router.post("/create-beneficiary", response_model=BeneficiaryRead)
def create_beneficiary(
    payload: BeneficiaryCreateRequest,
    user: User = Depends(get_current_user),
):
    """Create a new beneficiary for the current user."""
    try:
        # Create using the controller
        beneficiary, linked_user = controller.create(
            sender_user_id=user.id,
            linked_user_id=payload.linked_user_id,
            payout_currency=payload.payout_currency,
            relationship=payload.relationship,
        )
        return BeneficiaryRead.from_beneficiary_and_user(beneficiary, linked_user)
    except UnknownLinkedUserError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="linked_user_id does not exist",
        ) from exc
    except MissingContactInfoError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The linked user has no mobile_number or email on file",
        ) from exc


@router.get("/get-beneficiary-list", response_model=list[BeneficiaryRead])
def list_my_beneficiaries(
    user: User = Depends(get_current_user),  # Get the current authenticated user
    sort: str = Query(SORT_NEWEST, description="Order the caller's beneficiaries by."),
):
    """List the current user's beneficiaries, sorted by the specified criteria."""
    try:
        results = controller.list_beneficiaries(user.id, sort=sort)
    except InvalidSortOptionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="invalid sort option.",
        ) from exc
    return [
        BeneficiaryRead.from_beneficiary_and_user(beneficiary, linked_user)
        for beneficiary, linked_user in results
    ]
