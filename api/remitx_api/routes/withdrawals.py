from fastapi import Depends, HTTPException, status

from remitx_api.auth.dependencies import get_current_user
from remitx_api.controllers.withdrawal_controller import WithdrawalController
from remitx_api.models.orm.user import User
from remitx_api.models.schemas.withdrawal import WithdrawalCreateRequest, WithdrawalRead
from remitx_api.openapi import Tag, error_responses
from remitx_api.routes.routers import create_customer_router
from remitx_api.services.bank_account_service import BankAccountNotFoundError
from remitx_api.services.withdrawal_service import (
    BankAccountNotVerifiedError,
    BankAccountRejectedError,
    CurrencyMismatchError,
    InsufficientBalanceError,
    InvalidAmountError,
    WithdrawalNotPendingError,
)

router = create_customer_router(prefix="/withdrawals", tags=[Tag.WITHDRAWALS])
controller = WithdrawalController()


@router.post(
    "",
    response_model=WithdrawalRead,
    summary="Request a withdrawal from a fiat account to a bank account",
    responses=error_responses(400, 409),
)
def request_withdrawal(
    payload: WithdrawalCreateRequest,
    user: User = Depends(get_current_user),
):
    """Make a withdrawal request from the user's fiat account to a bank account.
    The bank account must be verified and match the currency of the withdrawal."""
    try:
        # get the view model for the withdrawal request
        view = controller.request(
            user.id, payload.bank_account_id, payload.currency, payload.amount
        )
    except (BankAccountNotFoundError, CurrencyMismatchError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except (InsufficientBalanceError, InvalidAmountError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except BankAccountNotVerifiedError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bank account has not been verified yet",
        ) from exc
    except BankAccountRejectedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bank account was rejected and cannot receive funds",
        ) from exc
    except WithdrawalNotPendingError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Withdrawal could not be settled; nothing was withdrawn",
        ) from exc
    return WithdrawalRead.model_validate(view)


@router.get(
    "",
    response_model=list[WithdrawalRead],
    summary="List the caller's own withdrawals",
)
def list_withdrawals(user: User = Depends(get_current_user)):
    """List every withdrawal this user has ever made, newest first."""
    return [
        WithdrawalRead.model_validate(view)
        for view in controller.list_user_withdrawal_history(user.id)
    ]
