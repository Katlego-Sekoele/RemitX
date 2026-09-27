"""Transfers written straight into the ledger tables.

For tests about what has been sent rather than how: the dashboard's figures
and the sending limits' running totals. Only what those reads join is
written — the quote, the settlement leg whose status is the transfer's, and
the remittance tying them together — not the full group of legs
`remittance_service.confirm_remittance` inserts, and no limit is checked.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import EllipsisType

from remitx_api.extensions import db
from remitx_api.models.orm.account import CURRENCY_TOKEN, CURRENCY_ZAR
from remitx_api.models.orm.exchange_rate import ExchangeRate
from remitx_api.models.orm.quote import Quote
from remitx_api.models.orm.remittance import Remittance
from remitx_api.models.orm.transaction import (
    STATUS_CONFIRMED,
    STATUS_PENDING,
    TYPE_REMITTANCE,
    Transaction,
)
from remitx_api.repositories.account_repository import AccountRepository


def record_transfer(
    sender,
    recipient,
    *,
    sender_amount: Decimal,
    token_amount: Decimal = Decimal("1"),
    receiver_amount: Decimal | None = None,
    receiver_currency: str | None = None,
    status: str = STATUS_PENDING,
    at: datetime | None = None,
    sender_currency: str = CURRENCY_ZAR,
    sender_amount_zar: Decimal | None | EllipsisType = ...,
) -> Remittance:
    """A transfer from `sender` to `recipient`, confirmed at `at` (now by
    default), whose settlement leg is at `status`. Flushed, not committed.

    `sender_amount_zar` is the rand value the quote locked: the amount itself
    for a ZAR send unless given, and required for any other currency. None
    records a quote from before that column existed."""
    if sender_amount_zar is ...:
        if sender_currency != CURRENCY_ZAR:
            raise ValueError("a non-ZAR transfer needs its sender_amount_zar")
        sender_amount_zar = sender_amount
    now = datetime.now(UTC)
    # Stored as UTC, like every timestamp the API writes: SQLite drops the
    # offset of whatever it binds.
    at = (at or now).astimezone(UTC)
    rate = ExchangeRate(
        base_currency=sender_currency,
        quote_currency=sender_currency,
        rate=Decimal("1"),
        fetched_at=now,
        valid_until=now + timedelta(hours=1),
    )
    db.session.add(rate)
    db.session.flush()
    quote = Quote(
        sender_user_id=sender.id,
        beneficiary_user_id=recipient.id,
        sender_amount=sender_amount,
        sender_currency=sender_currency,
        sender_amount_zar=sender_amount_zar,
        sender_transaction_fee=Decimal("0"),
        token_amount=token_amount,
        token_name=CURRENCY_TOKEN,
        fiat_to_token_exchange_rate=Decimal("0.05"),
        fiat_exchange_rate_id=rate.id,
        fiat_exchange_rate=Decimal("1"),
        exchange_rate_margin=Decimal("0"),
        receiver_amount=(
            receiver_amount if receiver_amount is not None else sender_amount
        ),
        receiver_currency=receiver_currency or sender_currency,
        receiver_payout_fee=Decimal("0"),
        receiver_payout_estimate=sender_amount,
        created_at=at,
        expires_at=at + timedelta(minutes=15),
    )
    db.session.add(quote)
    db.session.flush()
    accounts = AccountRepository()
    source = accounts.get_or_create_user_account(
        sender.id, sender.base_reference, CURRENCY_TOKEN
    )
    destination = accounts.get_or_create_user_account(
        recipient.id, recipient.base_reference, CURRENCY_TOKEN
    )
    leg = Transaction(
        type=TYPE_REMITTANCE,
        credit_account_id=source.account_id,
        debit_account_id=destination.account_id,
        amount=token_amount,
        currency=CURRENCY_TOKEN,
        status=status,
        quote_id=quote.quote_id,
        confirmed_at=at if status == STATUS_CONFIRMED else None,
    )
    db.session.add(leg)
    db.session.flush()
    remittance = Remittance(quote_id=quote.quote_id, tx_id=leg.tx_id, created_at=at)
    db.session.add(remittance)
    db.session.flush()
    return remittance
