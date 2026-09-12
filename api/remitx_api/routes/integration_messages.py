from fastapi import APIRouter, Query, status

from remitx_api.controllers.integration_message_controller import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    IntegrationMessageController,
)
from remitx_api.models.schemas.integration_message import (
    IntegrationMessageCreate,
    IntegrationMessageRead,
)
from remitx_api.routes.routers import create_customer_router

router: APIRouter = create_customer_router(
    prefix="/integration-messages",
    tags=["integration"],
)
controller = IntegrationMessageController()


@router.post(
    "",
    response_model=IntegrationMessageRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_integration_message(payload: IntegrationMessageCreate):
    return controller.create(payload)


@router.get("", response_model=list[IntegrationMessageRead])
def list_integration_messages(
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
):
    return controller.list_recent(limit)
