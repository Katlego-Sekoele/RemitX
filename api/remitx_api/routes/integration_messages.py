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
from remitx_api.openapi import Tag
from remitx_api.routes.routers import create_customer_router

router: APIRouter = create_customer_router(
    prefix="/integration-messages",
    tags=[Tag.INTEGRATION],
)
controller = IntegrationMessageController()


@router.post(
    "",
    response_model=IntegrationMessageRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Send a test message through the queue",
)
def create_integration_message(payload: IntegrationMessageCreate):
    """Stored as pending and handed to the worker, which marks it processed."""
    return controller.create(payload)


@router.get(
    "",
    response_model=list[IntegrationMessageRead],
    summary="List recent test messages",
)
def list_integration_messages(
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
):
    """Newest first."""
    return controller.list_recent(limit)
