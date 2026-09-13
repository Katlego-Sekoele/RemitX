from typing import Literal

from remitx_api.models.schemas.base import Schema


class HealthRead(Schema):
    status: Literal["ok"]
