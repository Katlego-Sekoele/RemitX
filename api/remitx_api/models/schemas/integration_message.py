"""Request/response schemas for the integration smoke-test endpoints."""

import uuid
from datetime import datetime
from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, StringConstraints

from remitx_api.models.orm.integration_message import BODY_MAX_LENGTH

MessageBody = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=BODY_MAX_LENGTH,
    ),
]


class IntegrationMessageCreate(BaseModel):
    body: MessageBody


class IntegrationMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    body: str
    status: str
    created_at: datetime
    processed_at: Optional[datetime] = None
