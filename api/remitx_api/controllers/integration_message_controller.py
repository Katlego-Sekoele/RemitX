from remitx_api.models.orm.integration_message import (
    STATUS_PENDING,
    IntegrationMessage,
)
from remitx_api.models.schemas.integration_message import (
    IntegrationMessageCreate,
    IntegrationMessageRead,
)
from remitx_api.repositories.integration_message_repository import (
    IntegrationMessageRepository,
)
from remitx_api.services import queue_service

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


class IntegrationMessageController:
    def __init__(self) -> None:
        self._repository = IntegrationMessageRepository()

    def create(self, payload: IntegrationMessageCreate) -> IntegrationMessageRead:
        message = IntegrationMessage(body=payload.body, status=STATUS_PENDING)
        self._repository.save(message)

        # Enqueue only after the commit above. Publishing inside the
        # transaction races the worker against a row it cannot yet read.
        queue_service.enqueue_integration_message(str(message.id))

        return IntegrationMessageRead.model_validate(message)

    def list_recent(self, limit: int = DEFAULT_LIMIT) -> list:
        # The route validates the range and returns 422 outside it; silently
        # clamping here would give the same input two different contracts.
        messages = self._repository.list_recent(limit)
        return [IntegrationMessageRead.model_validate(m) for m in messages]
