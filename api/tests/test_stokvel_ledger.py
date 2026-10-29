"""A stokvel's place in the ledger (R3-01, R3-02): its `STOKVEL` account, the
stokvel transaction types, and a quote sent by a stokvel. The CHECKs hold in
SQLite here as in Postgres."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from remitx_api.extensions import db
from remitx_api.models.orm.account import (
    CURRENCY_TOKEN,
    CURRENCY_ZAR,
    TYPE_STOKVEL,
    Account,
)
from remitx_api.models.orm.exchange_rate import ExchangeRate
from remitx_api.models.orm.quote import Quote
from remitx_api.models.orm.stokvel import Stokvel
from remitx_api.models.orm.transaction import (
    STATUS_CONFIRMED,
    TYPE_STOKVEL_CONTRIBUTION,
    TYPE_STOKVEL_POOL_RELEASE,
    Transaction,
)
from remitx_api.repositories.account_repository import AccountRepository
from sqlalchemy.exc import IntegrityError
from tests.kyc_helpers import make_user
from tests.platform_account_helpers import seed_platform_accounts


def _stokvel() -> Stokvel:
    stokvel = Stokvel(
        organiser_user_id=make_user().id,
        name="Savings club",
        currency=CURRENCY_ZAR,
        contribution_amount=Decimal("500"),
    )
    db.session.add(stokvel)
    db.session.flush()
    return stokvel


def _refused(write) -> None:
    with pytest.raises(IntegrityError):
        write()
        db.session.flush()
    db.session.rollback()


def test_a_stokvel_gets_its_own_token_account(app_context):
    stokvel = _stokvel()
    accounts = AccountRepository()

    account = accounts.create_stokvel_account(stokvel)
    db.session.commit()

    assert account.type == TYPE_STOKVEL
    assert account.account_currency == CURRENCY_TOKEN
    assert account.user_id is None
    assert account.reference is None
    assert stokvel.account_id == account.account_id
    assert accounts.get_stokvel_account(stokvel.id) == account


def test_a_stokvel_without_an_account_has_none(app_context):
    assert AccountRepository().get_stokvel_account(_stokvel().id) is None


def test_two_stokvels_cannot_share_an_account(app_context):
    account = AccountRepository().create_stokvel_account(_stokvel())
    other = _stokvel()

    _refused(lambda: setattr(other, "account_id", account.account_id))


def test_a_stokvel_account_belongs_to_no_user(app_context):
    _refused(
        lambda: db.session.add(
            Account(
                user_id=make_user().id,
                type=TYPE_STOKVEL,
                account_currency=CURRENCY_TOKEN,
                label="Stokvel owned by a user",
            )
        )
    )


def test_a_stokvel_balance_cannot_go_negative(app_context):
    account = AccountRepository().create_stokvel_account(_stokvel())

    _refused(lambda: setattr(account, "account_balance", Decimal("-0.01")))


def test_a_stokvel_account_is_not_a_platform_account(app_context):
    seed_platform_accounts()
    AccountRepository().create_stokvel_account(_stokvel())
    db.session.commit()

    platform_types = {a.type for a in AccountRepository().list_platform_accounts()}

    assert TYPE_STOKVEL not in platform_types


@pytest.mark.parametrize(
    "type_", [TYPE_STOKVEL_CONTRIBUTION, TYPE_STOKVEL_POOL_RELEASE]
)
def test_the_stokvel_transaction_types_are_accepted(app_context, type_):
    member = make_user()
    accounts = AccountRepository()
    member_token = accounts.get_or_create_user_account(
        member.id, member.base_reference, CURRENCY_TOKEN
    )
    stokvel_account = accounts.create_stokvel_account(_stokvel())

    db.session.add(
        Transaction(
            type=type_,
            credit_account_id=member_token.account_id,
            debit_account_id=stokvel_account.account_id,
            amount=Decimal("25"),
            currency=CURRENCY_TOKEN,
            status=STATUS_CONFIRMED,
        )
    )
    db.session.commit()


def _quote(**sender) -> Quote:
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
    return Quote(
        **sender,
        beneficiary_user_id=make_user().id,
        sender_amount=Decimal("1500"),
        sender_currency=CURRENCY_ZAR,
        sender_transaction_fee=Decimal("0"),
        token_amount=Decimal("81"),
        token_name=CURRENCY_TOKEN,
        fiat_to_token_exchange_rate=Decimal("0.054"),
        fiat_exchange_rate_id=rate.id,
        fiat_exchange_rate=Decimal("1"),
        exchange_rate_margin=Decimal("0"),
        receiver_amount=Decimal("1500"),
        receiver_currency=CURRENCY_ZAR,
        receiver_payout_fee=Decimal("0"),
        receiver_payout_estimate=Decimal("1500"),
        expires_at=now + timedelta(minutes=15),
    )


def test_a_stokvel_can_send_a_quote(app_context):
    stokvel = _stokvel()
    quote = _quote(stokvel_id=stokvel.id)
    db.session.add(quote)
    db.session.commit()

    assert quote.sender_user_id is None
    assert quote.stokvel_id == stokvel.id


def test_a_quote_has_one_sender_not_two(app_context):
    stokvel = _stokvel()

    _refused(
        lambda: db.session.add(
            _quote(sender_user_id=make_user().id, stokvel_id=stokvel.id)
        )
    )


def test_a_quote_needs_a_sender(app_context):
    _refused(lambda: db.session.add(_quote()))
