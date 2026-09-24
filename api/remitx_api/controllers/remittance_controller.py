import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from remitx_api.errors.remittances import UnknownRemittanceError
from remitx_api.models.orm.transaction import STATUS_CONFIRMED
from remitx_api.models.orm.user import User
from remitx_api.repositories.quote_repository import QuoteRepository
from remitx_api.repositories.remittance_repository import (
    RemittanceRecord,
    RemittanceRepository,
)
from remitx_api.repositories.transaction_repository import TransactionRepository
from remitx_api.services import remittance_service
from remitx_api.services.transfer_timeline import TimelineStage, transfer_timeline

DIRECTION_SENT = "sent"
DIRECTION_RECEIVED = "received"


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


@dataclass(frozen=True)
class TransferView:
    """One transfer as the caller sees it, from either side.

    The sender's own fee lines (`sender_amount`, `sender_transaction_fee`,
    `exchange_rate_margin`) are None for the recipient: they see what they
    received, from whom, when, and the hash — not what the sender paid.
    """

    remittance_id: uuid.UUID
    quote_id: uuid.UUID
    direction: str
    counterparty_user_id: uuid.UUID
    counterparty_name: str | None
    # The settlement leg's: pending, processing, confirmed or failed.
    status: str
    created_at: datetime
    processed_at: datetime | None
    settled_at: datetime | None
    # The burn leg's, once the group has confirmed.
    xrpl_tx_hash: str | None
    sender_amount: Decimal | None
    sender_currency: str
    sender_transaction_fee: Decimal | None
    exchange_rate_margin: Decimal | None
    fiat_to_token_exchange_rate: Decimal
    fiat_exchange_rate: Decimal
    token_amount: Decimal
    token_name: str
    receiver_amount: Decimal
    receiver_currency: str
    receiver_payout_fee: Decimal
    receiver_payout_estimate: Decimal
    timeline_step: int
    timeline: list[TimelineStage]


def _full_name(user: User) -> str | None:
    return " ".join(part for part in (user.first_name, user.last_name) if part) or None


def _transfer_view(record: RemittanceRecord, caller_id: uuid.UUID) -> TransferView:
    quote = record.quote
    sent = quote.sender_user_id == caller_id
    leg = record.settlement_leg
    confirmed = leg.status == STATUS_CONFIRMED
    burn = record.burn_leg
    settled_at = leg.confirmed_at if confirmed else None
    timeline, timeline_step = transfer_timeline(
        leg.status,
        record.remittance.created_at,
        leg.processed_at,
        settled_at,
    )
    return TransferView(
        remittance_id=record.remittance.remittance_id,
        quote_id=quote.quote_id,
        direction=DIRECTION_SENT if sent else DIRECTION_RECEIVED,
        counterparty_user_id=(record.recipient if sent else record.sender).id,
        counterparty_name=_full_name(record.recipient if sent else record.sender),
        status=leg.status,
        created_at=record.remittance.created_at,
        processed_at=leg.processed_at,
        settled_at=settled_at,
        xrpl_tx_hash=burn.xrpl_tx_hash if confirmed and burn is not None else None,
        sender_amount=quote.sender_amount if sent else None,
        sender_currency=quote.sender_currency,
        sender_transaction_fee=quote.sender_transaction_fee if sent else None,
        exchange_rate_margin=quote.exchange_rate_margin if sent else None,
        fiat_to_token_exchange_rate=quote.fiat_to_token_exchange_rate,
        fiat_exchange_rate=quote.fiat_exchange_rate,
        token_amount=quote.token_amount,
        token_name=quote.token_name,
        receiver_amount=quote.receiver_amount,
        receiver_currency=quote.receiver_currency,
        receiver_payout_fee=quote.receiver_payout_fee,
        receiver_payout_estimate=quote.receiver_payout_estimate,
        timeline_step=timeline_step,
        timeline=timeline,
    )


class RemittanceController:
    def __init__(self) -> None:
        self._quotes = QuoteRepository()
        self._transactions = TransactionRepository()
        self._remittances = RemittanceRepository()

    def list_transfers(self, user_id: uuid.UUID, limit: int) -> list[TransferView]:
        """The caller's transfers, sent and received, newest first."""
        return [
            _transfer_view(record, user_id)
            for record in self._remittances.list_for_user(user_id, limit)
        ]

    def get_transfer(
        self, user_id: uuid.UUID, remittance_id: uuid.UUID
    ) -> TransferView:
        """One transfer the caller sent or received; anyone else gets 404."""
        record = self._remittances.get_for_user(remittance_id, user_id)
        if record is None:
            raise UnknownRemittanceError(remittance_id)
        return _transfer_view(record, user_id)

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
