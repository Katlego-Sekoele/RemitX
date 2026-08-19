"""Request/response schemas for the integration smoke-test endpoints."""

import uuid
from datetime import datetime, timezone
from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, StringConstraints, field_serializer

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

    @field_serializer("created_at", "processed_at")
    def _as_utc(self, value: Optional[datetime]) -> Optional[str]:
        """Always emit an offset, whatever the backend stored.

        Postgres TIMESTAMPTZ round-trips as aware, but SQLite silently drops
        the offset, so the same row would serialize as "...T00:40:00" there and
        "...T00:40:00+00:00" in production. A JS client parses the offsetless
        form as *local* time, so the two differ by the viewer's UTC offset.
        Timestamps are written as UTC, so naive values are tagged as UTC here.
        """
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
