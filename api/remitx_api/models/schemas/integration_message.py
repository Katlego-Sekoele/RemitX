"""Request/response schemas for the integration smoke-test endpoints."""

import uuid
from typing import Annotated

from pydantic import ConfigDict, StringConstraints

from remitx_api.models.orm.integration_message import BODY_MAX_LENGTH
from remitx_api.models.schemas.base import Schema, UtcDateTime

MessageBody = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=BODY_MAX_LENGTH,
    ),
]


class IntegrationMessageCreate(Schema):
    body: MessageBody


class IntegrationMessageRead(Schema):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    body: str
    status: str
    created_at: UtcDateTime
    processed_at: UtcDateTime | None = None
