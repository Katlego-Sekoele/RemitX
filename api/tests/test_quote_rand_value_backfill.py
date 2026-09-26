"""The backfill that gives quotes from before `quotes.sender_amount_zar` their
rand value. Migrations only ever run on Postgres, so this runs in the
`postgres` lane (TEST_DATABASE_URL)."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from remitx_api.models.orm.exchange_rate import ExchangeRate
from remitx_api.models.orm.quote import Quote
from remitx_api.models.orm.user import User
from sqlalchemy import create_engine, select
from tests.postgres_helpers import migrate

pytestmark = pytest.mark.postgres

# The migration that adds the column. The backfill is the one after it.
COLUMN_ADDED = "46b798718ccd"
QUOTED_AT = datetime(2026, 9, 1, 12, tzinfo=UTC)


def _rate(value: str, fetched_at: datetime) -> dict:
    return {
        "id": uuid.uuid4(),
        "base_currency": "USD",
        "quote_currency": "ZAR",
        "rate": Decimal(value),
        "fetched_at": fetched_at,
        "valid_until": fetched_at + timedelta(hours=1),
    }


def _quote(sender, recipient, rate_id, *, amount: str, currency: str, per_unit: str):
    """A quote as it was written before the column: no rand value.
    `per_unit` is its token (USD) per unit of `currency`."""
    return {
        "quote_id": uuid.uuid4(),
        "sender_user_id": sender,
        "beneficiary_user_id": recipient,
        "sender_amount": Decimal(amount),
        "sender_currency": currency,
        "sender_transaction_fee": Decimal("0"),
        "token_amount": Decimal("1"),
        "token_name": "uctusd",
        "fiat_to_token_exchange_rate": Decimal(per_unit),
        "fiat_exchange_rate_id": rate_id,
        "fiat_exchange_rate": Decimal("1"),
        "exchange_rate_margin": Decimal("0"),
        "receiver_amount": Decimal(amount),
        "receiver_currency": currency,
        "receiver_payout_fee": Decimal("0"),
        "receiver_payout_estimate": Decimal(amount),
        "created_at": QUOTED_AT,
        "expires_at": QUOTED_AT + timedelta(minutes=15),
    }


def test_quotes_from_before_the_column_get_their_rand_value(empty_postgres_url):
    """A ZAR quote is worth its own amount. Another currency is valued
    through the USD peg at the USD/ZAR rate in force when it was quoted,
    R18.50 here, not the R40 fetched after it."""
    migrate(empty_postgres_url, COLUMN_ADDED)
    engine = create_engine(empty_postgres_url)
    try:
        sender, recipient = uuid.uuid4(), uuid.uuid4()
        in_force = _rate("18.50", QUOTED_AT - timedelta(hours=1))
        later = _rate("40", QUOTED_AT + timedelta(hours=1))
        zar = _quote(
            sender,
            recipient,
            in_force["id"],
            amount="1000",
            currency="ZAR",
            per_unit="0.05405405",
        )
        usd = _quote(
            sender,
            recipient,
            in_force["id"],
            amount="100",
            currency="USD",
            per_unit="1",
        )
        with engine.begin() as connection:
            connection.execute(
                User.__table__.insert(),
                [
                    {
                        "id": sender,
                        "clerk_user_id": "user_bf_s",
                        "base_reference": "bfs1",
                    },
                    {
                        "id": recipient,
                        "clerk_user_id": "user_bf_r",
                        "base_reference": "bfr1",
                    },
                ],
            )
            connection.execute(ExchangeRate.__table__.insert(), [in_force, later])
            connection.execute(Quote.__table__.insert(), [zar, usd])

        migrate(empty_postgres_url)

        with engine.connect() as connection:
            values = dict(
                connection.execute(
                    select(Quote.quote_id, Quote.sender_amount_zar)
                ).all()
            )
    finally:
        engine.dispose()

    assert values[zar["quote_id"]] == Decimal("1000.00")
    assert values[usd["quote_id"]] == Decimal("1850.00")
