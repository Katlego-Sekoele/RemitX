from decimal import Decimal

from fastapi import Depends, HTTPException, Request, status

from remitx_api.auth.dependencies import get_current_user
from remitx_api.controllers.trustmebank_controller import TrustMeBankController
from remitx_api.errors.trustmebank import (
    TrustMeBankDepositNotFoundError,
    TrustMeBankDisabledError,
    TrustMeBankKycRequiredError,
    TrustMeBankNotLinkedError,
    TrustMeBankOAuthStateError,
)
from remitx_api.models.orm.user import User
from remitx_api.models.schemas.trustmebank import (
    TrustMeBankAccountRead,
    TrustMeBankConnectRead,
    TrustMeBankDepositStartRead,
    TrustMeBankDepositStartRequest,
    TrustMeBankDepositSyncRead,
    TrustMeBankLinkRead,
    TrustMeBankOAuthCompleteRead,
    TrustMeBankOAuthCompleteRequest,
    TrustMeBankStatusRead,
)
from remitx_api.openapi import Tag, error_responses
from remitx_api.routes.routers import create_customer_router, create_public_router
from remitx_api.services.trustmebank_client import TrustMeBankClientError

controller = TrustMeBankController()

public_router = create_public_router(prefix="/trustmebank", tags=[Tag.TRUSTMEBANK])
customer_router = create_customer_router(
    prefix="/trustmebank", tags=[Tag.TRUSTMEBANK]
)
webhook_router = create_public_router(tags=[Tag.TRUSTMEBANK])


@public_router.get(
    "/status",
    response_model=TrustMeBankStatusRead,
    summary="Whether TrustMeBank deposits are enabled",
)
def trustmebank_status():
    return controller.status()


@customer_router.get(
    "/link",
    response_model=TrustMeBankLinkRead,
    summary="TrustMeBank connection status for the caller",
    responses=error_responses(404),
)
def trustmebank_link(user: User = Depends(get_current_user)):
    try:
        return controller.link_status(user.id)
    except TrustMeBankDisabledError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@customer_router.post(
    "/connect",
    response_model=TrustMeBankConnectRead,
    summary="Start TrustMeBank OAuth",
    responses=error_responses(404),
)
def trustmebank_connect(user: User = Depends(get_current_user)):
    try:
        return {"authorize_url": controller.connect_url(user.id)}
    except TrustMeBankDisabledError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@customer_router.post(
    "/oauth/callback",
    response_model=TrustMeBankOAuthCompleteRead,
    summary="Complete TrustMeBank OAuth after redirect",
    responses=error_responses(400, 404),
)
def trustmebank_oauth_callback(
    payload: TrustMeBankOAuthCompleteRequest,
    user: User = Depends(get_current_user),
):
    try:
        return controller.complete_oauth(
            user.id, code=payload.code, state=payload.state
        )
    except TrustMeBankDisabledError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except TrustMeBankOAuthStateError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except TrustMeBankClientError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@customer_router.get(
    "/accounts",
    response_model=list[TrustMeBankAccountRead],
    summary="List TrustMeBank accounts for the linked customer",
    responses=error_responses(400, 404),
)
def trustmebank_accounts(user: User = Depends(get_current_user)):
    try:
        return controller.list_accounts(user.id)
    except TrustMeBankDisabledError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except TrustMeBankNotLinkedError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except TrustMeBankClientError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@customer_router.post(
    "/deposits",
    response_model=TrustMeBankDepositStartRead,
    summary="Start a TrustMeBank deposit",
    responses=error_responses(400, 403, 404),
)
def trustmebank_start_deposit(
    payload: TrustMeBankDepositStartRequest,
    user: User = Depends(get_current_user),
):
    try:
        result = controller.start_deposit(
            user.id,
            amount=Decimal(str(payload.amount)),
            debtor_account_id=payload.debtor_account_id,
        )
    except TrustMeBankDisabledError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except TrustMeBankKycRequiredError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except TrustMeBankNotLinkedError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except (TrustMeBankClientError, ValueError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {
        "deposit_id": result["deposit_id"],
        "payment_id": result["payment_id"],
        "authorisation_url": result["authorisation_url"],
    }


@customer_router.post(
    "/deposits/{payment_id}/sync",
    response_model=TrustMeBankDepositSyncRead,
    summary="Poll TrustMeBank for a deposit outcome",
    responses=error_responses(404),
)
def trustmebank_sync_deposit(
    payment_id: str,
    user: User = Depends(get_current_user),
):
    try:
        return controller.sync_deposit(user.id, payment_id)
    except TrustMeBankDisabledError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except TrustMeBankDepositNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except TrustMeBankNotLinkedError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except TrustMeBankClientError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@webhook_router.post(
    "/webhooks/trustmebank",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="TrustMeBank payment webhook",
    responses=error_responses(400, 404),
)
async def trustmebank_webhook(request: Request):
    body = await request.body()
    signature = request.headers.get("X-TrustMeBank-Signature", "")
    try:
        controller.handle_webhook(body, signature)
    except TrustMeBankDisabledError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
