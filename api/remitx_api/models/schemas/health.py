from typing import Literal

from remitx_api.models.schemas.base import Schema


class HealthRead(Schema):
    status: Literal["ok"]
    # Ledger currency code for the settlement token (Config.UCTUSD_TOKEN_NAME).
    settlement_token_currency: str
