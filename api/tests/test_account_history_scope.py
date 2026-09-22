"""Public history lookups only return rows the caller is a party to.

SQLite does not run the Postgres policies in
``V20260922_2245__enable_ledger_rls``, so these tests are what enforces that
rule here. A burn hash lives on a platform-to-platform leg; the quote's
parties are what make it visible.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from remitx_api.extensions import db
from remitx_api.models.orm.account import (
    CURRENCY_TOKEN,
    CURRENCY_ZAR,
    TYPE_EXTERNAL,
    TYPE_XRPL_WALLET,
    Account,
)
from remitx_api.models.orm.exchange_rate import ExchangeRate
from remitx_api.models.orm.quote import Quote
from remitx_api.models.orm.remittance import Remittance
from remitx_api.models.orm.transaction import (
    STATUS_CONFIRMED,
    TYPE_DEPOSIT,
    TYPE_TOKEN_BURN,
    Transaction,
)
from remitx_api.repositories.account_repository import AccountRepository
from remitx_api.repositories.quote_repository import QuoteRepository
from remitx_api.repositories.remittance_repository import RemittanceRepository
from remitx_api.repositories.transaction_repository import TransactionRepository
from tests.kyc_helpers import make_user


def test_history_lookups_omit_a_strangers_quote(app_context):
    sender = make_user("hist-sender")
    beneficiary = make_user("hist-beneficiary")
    stranger = make_user("hist-stranger")
    sender_zar = AccountRepository().get_or_create_user_account(
        sender.id, sender.base_reference, CURRENCY_ZAR
    )
    quote_id, remittance_id, burn_hash = _confirmed_send(
        sender.id, beneficiary.id, sender_zar.account_id
    )
    db.session.commit()

    quotes = QuoteRepository()
    remittances = RemittanceRepository()
    transactions = TransactionRepository()
    quote_ids = {quote_id}

    assert set(quotes.get_many(quote_ids, sender.id)) == {quote_id}
    assert set(quotes.get_many(quote_ids, beneficiary.id)) == {quote_id}
    assert quotes.get_many(quote_ids, stranger.id) == {}

    assert remittances.get_ids_by_quote_ids(quote_ids, sender.id) == {
        quote_id: remittance_id
    }
    assert remittances.get_ids_by_quote_ids(quote_ids, beneficiary.id) == {
        quote_id: remittance_id
    }
    assert remittances.get_ids_by_quote_ids(quote_ids, stranger.id) == {}

    assert transactions.get_burn_hashes(quote_ids, sender.id) == {quote_id: burn_hash}
    assert transactions.get_burn_hashes(quote_ids, beneficiary.id) == {
        quote_id: burn_hash
    }
    assert transactions.get_burn_hashes(quote_ids, stranger.id) == {}

    assert (
        transactions.list_account_transactions(
            sender_zar.account_id, user_id=stranger.id
        )
        == []
    )
    own_legs = transactions.list_account_transactions(
        sender_zar.account_id, user_id=sender.id
    )
    assert [leg.tx_id for leg in own_legs]
    # Settlement still reads a platform account without a customer id.
    assert transactions.list_account_transactions(sender_zar.account_id)


def _confirmed_send(
    sender_id: uuid.UUID, beneficiary_id: uuid.UUID, sender_account_id: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID, str]:
    now = datetime.now(UTC)
    rate = ExchangeRate(
        base_currency=CURRENCY_ZAR,
        quote_currency=CURRENCY_ZAR,
        rate=Decimal("1"),
        fetched_at=now,
        valid_until=now + timedelta(hours=1),
    )
    db.session.add(rate)
    db.session.flush()

    quote = Quote(
        sender_user_id=sender_id,
        beneficiary_user_id=beneficiary_id,
        sender_amount=Decimal("1000"),
        sender_currency=CURRENCY_ZAR,
        sender_transaction_fee=Decimal("20"),
        token_amount=Decimal("50"),
        token_name=CURRENCY_TOKEN,
        fiat_to_token_exchange_rate=Decimal("0.05"),
        fiat_exchange_rate_id=rate.id,
        fiat_exchange_rate=Decimal("1"),
        exchange_rate_margin=Decimal("10"),
        receiver_amount=Decimal("970"),
        receiver_currency=CURRENCY_ZAR,
        receiver_payout_fee=Decimal("0"),
        receiver_payout_estimate=Decimal("970"),
        expires_at=now + timedelta(minutes=15),
    )
    treasury = Account(
        user_id=sender_id,
        type=TYPE_XRPL_WALLET,
        account_currency=CURRENCY_TOKEN,
        label="history-scope treasury",
    )
    issuer = Account(
        user_id=None,
        type=TYPE_EXTERNAL,
        account_currency=CURRENCY_TOKEN,
        label="history-scope issuer",
    )
    db.session.add_all([quote, treasury, issuer])
    db.session.flush()

    burn_hash = "A" * 64
    burn = Transaction(
        type=TYPE_TOKEN_BURN,
        credit_account_id=treasury.account_id,
        debit_account_id=issuer.account_id,
        amount=Decimal("50"),
        currency=CURRENCY_TOKEN,
        status=STATUS_CONFIRMED,
        quote_id=quote.quote_id,
        xrpl_tx_hash=burn_hash,
    )
    deposit = Transaction(
        type=TYPE_DEPOSIT,
        credit_account_id=treasury.account_id,
        debit_account_id=sender_account_id,
        amount=Decimal("1000"),
        currency=CURRENCY_ZAR,
        status=STATUS_CONFIRMED,
    )
    db.session.add_all([burn, deposit])
    db.session.flush()
    remittance = Remittance(quote_id=quote.quote_id, tx_id=deposit.tx_id)
    db.session.add(remittance)
    db.session.flush()
    return quote.quote_id, remittance.remittance_id, burn_hash
