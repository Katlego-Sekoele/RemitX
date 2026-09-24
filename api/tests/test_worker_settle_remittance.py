"""The worker half of remittance settlement (Transaction_Flow_Context.md §2
Phase C).

`settle_remittance` no longer confirms or credits anything itself — every
one of a remittance's seven legs stays pending until the treasury burn
resolves (see test_worker_burn_treasury_tokens.py for that). Its only job
here is handing off to `burn_treasury_tokens`, guarded by nothing more than
"is there still a pending burn leg for this quote" — the burn leg's own
claim (in `burn_treasury_tokens`) is what actually makes redelivery safe.

Runs the task function directly against a scratch SQLite file — no broker
involved, mirroring test_integration_message_task.py exactly.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from remitx_api.extensions import Base, build_engine
from remitx_api.models.orm.account import (
    CURRENCY_TOKEN,
    CURRENCY_ZAR,
    TYPE_EXTERNAL,
    TYPE_USER,
    TYPE_XRPL_WALLET,
    Account,
)
from remitx_api.models.orm.exchange_rate import ExchangeRate
from remitx_api.models.orm.quote import Quote
from remitx_api.models.orm.transaction import (
    STATUS_PENDING,
    STATUS_PROCESSING,
    TYPE_TOKEN_BURN,
    Transaction,
)
from remitx_api.models.orm.user import User
from remitx_worker import db as worker_db, tasks
from remitx_worker.tasks import settle_remittance
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def session_factory(tmp_path):
    engine = build_engine(f"sqlite:///{tmp_path / 'worker.db'}")
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    worker_db.configure(factory)
    yield factory
    worker_db.configure(None)


@pytest.fixture
def enqueued_burn(monkeypatch):
    """Capture `enqueue_burn_treasury_tokens` calls instead of publishing —
    CI has no Redis."""
    calls = []
    monkeypatch.setattr(
        tasks.queue_service, "enqueue_burn_treasury_tokens", calls.append
    )
    return calls


def _user(session) -> uuid.UUID:
    user_id = uuid.uuid4()
    session.add(
        User(
            id=user_id,
            clerk_user_id=f"user_{user_id}",
            base_reference=f"wrk{user_id.int}",
        )
    )
    session.commit()
    return user_id


def _account(session, *, type_, currency, balance="0") -> uuid.UUID:
    account_id = uuid.uuid4()
    account = Account(
        account_id=account_id,
        user_id=_user(session) if type_ == TYPE_USER else None,
        type=type_,
        reference=f"{account_id}-{currency}" if type_ == TYPE_USER else None,
        account_currency=currency,
        account_balance=Decimal(balance),
        label=f"{type_} {currency}",
    )
    session.add(account)
    session.commit()
    return account.account_id


def _quote(session, *, sender_account_id, beneficiary_account_id) -> uuid.UUID:
    now = datetime.now(UTC)
    rate = ExchangeRate(
        base_currency=CURRENCY_ZAR,
        quote_currency=CURRENCY_ZAR,
        rate=Decimal("1"),
        fetched_at=now,
        valid_until=now + timedelta(hours=1),
    )
    session.add(rate)
    session.commit()

    quote = Quote(
        sender_user_id=session.get(Account, sender_account_id).user_id,
        beneficiary_user_id=session.get(Account, beneficiary_account_id).user_id,
        sender_amount=Decimal("1000"),
        sender_currency=CURRENCY_ZAR,
        sender_transaction_fee=Decimal("20"),
        token_amount=Decimal("52.432432"),
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
    session.add(quote)
    session.commit()
    return quote.quote_id


def _burn_leg(session, *, quote_id, treasury, issuer, status=STATUS_PENDING) -> None:
    session.add(
        Transaction(
            tx_id=uuid.uuid4(),
            type=TYPE_TOKEN_BURN,
            credit_account_id=treasury,
            debit_account_id=issuer,
            amount=Decimal("52.432432"),
            currency=CURRENCY_TOKEN,
            status=status,
            quote_id=quote_id,
        )
    )
    session.commit()


@pytest.fixture
def quote_with_pending_burn_leg(session_factory):
    with session_factory() as session:
        sender_token = _account(session, type_=TYPE_USER, currency=CURRENCY_TOKEN)
        beneficiary_token = _account(session, type_=TYPE_USER, currency=CURRENCY_TOKEN)
        treasury = _account(
            session, type_=TYPE_XRPL_WALLET, currency=CURRENCY_TOKEN, balance="1000"
        )
        issuer = _account(session, type_=TYPE_EXTERNAL, currency=CURRENCY_TOKEN)
        quote_id = _quote(
            session,
            sender_account_id=sender_token,
            beneficiary_account_id=beneficiary_token,
        )
        _burn_leg(session, quote_id=quote_id, treasury=treasury, issuer=issuer)

    return quote_id


def test_settle_remittance_enqueues_burn_when_burn_leg_pending(
    session_factory, quote_with_pending_burn_leg, enqueued_burn
):
    result = settle_remittance(str(quote_with_pending_burn_leg))

    assert result == "queued"
    assert enqueued_burn == [str(quote_with_pending_burn_leg)]


def test_settle_remittance_is_skipped_once_burn_leg_is_no_longer_pending(
    session_factory, quote_with_pending_burn_leg, enqueued_burn
):
    """Once `burn_treasury_tokens` has claimed the burn leg (or it has
    resolved), a redelivered `settle_remittance` message has nothing left to
    kick off."""
    with session_factory() as session:
        session.execute(
            Transaction.__table__.update()
            .where(Transaction.quote_id == quote_with_pending_burn_leg)
            .values(status=STATUS_PROCESSING)
        )
        session.commit()

    result = settle_remittance(str(quote_with_pending_burn_leg))

    assert result == "skipped"
    assert enqueued_burn == []


def test_unknown_quote_is_skipped(session_factory, enqueued_burn):
    assert settle_remittance(str(uuid.uuid4())) == "skipped"
    assert enqueued_burn == []


@pytest.mark.parametrize(
    "quote_id", ["not-a-uuid", "", None], ids=["junk", "empty", "none"]
)
def test_malformed_quote_id_is_skipped_not_an_error(session_factory, quote_id):
    assert settle_remittance(quote_id) == "skipped"
