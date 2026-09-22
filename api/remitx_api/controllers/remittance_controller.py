import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from remitx_api.repositories.quote_repository import QuoteRepository
from remitx_api.repositories.transaction_repository import TransactionRepository
from remitx_api.services import remittance_service


@dataclass(frozen=True)
class RemittanceView:
    """A confirmation receipt — joins `Remittance` with the `Quote` it
    confirmed, since `Remittance` itself deliberately doesn't duplicate any
    priced field `Quote` already froze (models/orm/remittance.py)."""

    remittance_id: uuid.UUID
    quote_id: uuid.UUID
    tx_id: uuid.UUID
    status: str
    sender_amount: Decimal
    sender_currency: str
    token_amount: Decimal
    token_name: str
    receiver_amount: Decimal
    receiver_currency: str
    created_at: datetime


class RemittanceController:
    def __init__(self) -> None:
        self._quotes = QuoteRepository()
        self._transactions = TransactionRepository()

    def confirm(self, sender_user_id: uuid.UUID, quote_id: uuid.UUID) -> RemittanceView:
        remittance = remittance_service.confirm_remittance(sender_user_id, quote_id)
        return self._view(remittance)

    def _view(self, remittance) -> RemittanceView:
        quote = self._quotes.get_by_id(remittance.quote_id)
        settlement_leg = self._transactions.get_by_id(remittance.tx_id)
        return RemittanceView(
            remittance_id=remittance.remittance_id,
            quote_id=remittance.quote_id,
            tx_id=remittance.tx_id,
            status=settlement_leg.status,
            sender_amount=quote.sender_amount,
            sender_currency=quote.sender_currency,
            token_amount=quote.token_amount,
            token_name=quote.token_name,
            receiver_amount=quote.receiver_amount,
            receiver_currency=quote.receiver_currency,
            created_at=remittance.created_at,
        )
