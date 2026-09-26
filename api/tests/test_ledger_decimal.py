from decimal import Decimal

from pydantic import BaseModel
from remitx_api.models.schemas.base import LedgerDecimal


class _Sample(BaseModel):
    amount: LedgerDecimal


def test_ledger_decimal_json_never_uses_scientific_notation():
    payload = _Sample(amount=Decimal("0E-8")).model_dump(mode="json")
    assert payload["amount"] == "0.00000000"
    assert "E" not in payload["amount"]
