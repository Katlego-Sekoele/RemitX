"""The worker half of the on-chain treasury burn + fully-gated settlement
(Transaction_Flow_Context.md §2 Phase C).

Same conventions as test_worker_settle_remittance.py: task functions called
directly against a scratch SQLite file, no broker involved. The chain calls
(`evm_service.burn_tokens` and `evm_service.wait_for_receipt`) are faked, and
`evm_service.get_web3` raises, so nothing can reach a real RPC. The
`confirm_treasury_burn` enqueue is captured too: `burn_treasury_tokens`
hands off to it rather than confirming itself, so its own tests assert on
what it claims, the burn hash it stores, and what it would enqueue;
`confirm_treasury_burn`'s own tests call it directly, the same way a worker
consuming that follow-up message would.

`confirm_treasury_burn` is where *every* leg of a remittance — not just the
burn and payout — finally confirms and credits, or (on a failed burn) fails
together. Nothing anywhere in this pipeline credits a balance before this
task runs, so a failed burn needs no reversal.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from remitx_api.extensions import Base, build_engine
from remitx_api.models.orm.account import (
    CURRENCY_TOKEN,
    CURRENCY_ZAR,
    CURRENCY_ZWL,
    TYPE_EVM_WALLET,
    TYPE_EXTERNAL,
    TYPE_PLATFORM_FIAT,
    TYPE_PLATFORM_REVENUE,
    TYPE_USER,
    Account,
)
from remitx_api.models.orm.exchange_rate import ExchangeRate
from remitx_api.models.orm.quote import Quote
from remitx_api.models.orm.transaction import (
    STATUS_CONFIRMED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_PROCESSING,
    TYPE_BENEFICIARY_PAYOUT,
    TYPE_FEE,
    TYPE_REMITTANCE,
    TYPE_TOKEN_BURN,
    Transaction,
)
from remitx_api.models.orm.user import User
from remitx_worker import db as worker_db, evm_service, tasks
from remitx_worker.tasks import burn_treasury_tokens, confirm_treasury_burn
from sqlalchemy.orm import sessionmaker
from web3.exceptions import TimeExhausted

BURN_HASH = "0x" + "be" * 32


@pytest.fixture(autouse=True)
def _no_rpc(monkeypatch):
    """Every chain call in these tests is faked; anything unfaked that asks
    for a client fails loudly instead of reaching the testnet RPC."""

    def no_rpc():
        raise AssertionError("a test tried to reach the EVM RPC")

    monkeypatch.setattr(evm_service, "get_web3", no_rpc)


@pytest.fixture
def session_factory(tmp_path):
    engine = build_engine(f"sqlite:///{tmp_path / 'worker.db'}")
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    worker_db.configure(factory)
    yield factory
    worker_db.configure(None)


@pytest.fixture
def enqueued_confirm(monkeypatch):
    """Capture `enqueue_confirm_treasury_burn` calls instead of publishing —
    `burn_treasury_tokens` never touches the DB after its own claim, so its
    tests assert against what it would have handed to the follow-up task."""
    calls = []
    monkeypatch.setattr(
        tasks.queue_service,
        "enqueue_confirm_treasury_burn",
        lambda quote_id, tx_hash, error=None: calls.append((quote_id, tx_hash, error)),
    )
    return calls


class FakeChain:
    """`evm_service.burn_tokens` and `wait_for_receipt`, without a chain.

    `burn_tokens` behaves like the real one: it hands the hash to
    `on_signed` before "sending", and sends nothing if that raises. Set
    `fail_before_signing` or `fail_after_signing` to an exception to make a
    burn fail at that point, and `receipt` to an exception (or a callable
    that raises) to make every wait fail."""

    def __init__(self):
        self.burns = []
        self.sent = []
        self.waits = []
        self.fail_before_signing = None
        self.fail_after_signing = None
        self.before_on_signed = None
        self.receipt = None

    def burn_tokens(self, amount, *, on_signed=None, w3=None):
        self.burns.append(amount)
        if self.fail_before_signing is not None:
            raise self.fail_before_signing
        if self.before_on_signed is not None:
            self.before_on_signed()
        if on_signed is not None:
            on_signed(BURN_HASH)
        if self.fail_after_signing is not None:
            raise self.fail_after_signing
        self.sent.append(BURN_HASH)
        return BURN_HASH

    def wait_for_receipt(self, tx_hash, timeout=120, w3=None):
        self.waits.append(tx_hash)
        receipt = self.receipt
        if callable(receipt) and not isinstance(receipt, BaseException):
            receipt = receipt(tx_hash)
        if isinstance(receipt, BaseException):
            raise receipt
        return {"transactionHash": tx_hash, "status": 1, "blockNumber": 1}


@pytest.fixture
def chain(monkeypatch):
    fake = FakeChain()
    monkeypatch.setattr(evm_service, "burn_tokens", fake.burn_tokens)
    monkeypatch.setattr(evm_service, "wait_for_receipt", fake.wait_for_receipt)
    return fake


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
        receiver_currency=CURRENCY_ZWL,
        receiver_payout_fee=Decimal("0"),
        receiver_payout_estimate=Decimal("970"),
        expires_at=now + timedelta(minutes=15),
    )
    session.add(quote)
    session.commit()
    return quote.quote_id


def _leg(
    session, *, quote_id, credit_account_id, debit_account_id, amount, currency, type_
) -> uuid.UUID:
    tx = Transaction(
        tx_id=uuid.uuid4(),
        type=type_,
        credit_account_id=credit_account_id,
        debit_account_id=debit_account_id,
        amount=Decimal(amount),
        currency=currency,
        status=STATUS_PENDING,
        quote_id=quote_id,
    )
    session.add(tx)
    session.commit()
    return tx.tx_id


@pytest.fixture
def pending_remittance(session_factory):
    """A quote's full seven pending legs, mirroring
    `remittance_service.confirm_remittance` exactly — every leg still
    `pending`, since nothing confirms anything before the burn resolves.
    """
    with session_factory() as session:
        # 1000 covers the fee (30) + net remittance (970) legs below, so
        # debiting the sender's own account as their source never dips it
        # negative (Account's user-balance-nonneg CHECK constraint).
        sender_zar = _account(
            session, type_=TYPE_USER, currency=CURRENCY_ZAR, balance="1000"
        )
        sender_token = _account(session, type_=TYPE_USER, currency=CURRENCY_TOKEN)
        beneficiary_token = _account(session, type_=TYPE_USER, currency=CURRENCY_TOKEN)
        beneficiary_fiat = _account(session, type_=TYPE_USER, currency=CURRENCY_ZWL)
        fee_revenue = _account(
            session, type_=TYPE_PLATFORM_REVENUE, currency=CURRENCY_ZAR
        )
        bank = _account(session, type_=TYPE_PLATFORM_FIAT, currency=CURRENCY_ZAR)
        beneficiary_bank = _account(
            session, type_=TYPE_PLATFORM_FIAT, currency=CURRENCY_ZWL
        )
        treasury = _account(
            session, type_=TYPE_EVM_WALLET, currency=CURRENCY_TOKEN, balance="1000"
        )
        issuer = _account(session, type_=TYPE_EXTERNAL, currency=CURRENCY_TOKEN)
        quote_id = _quote(
            session,
            sender_account_id=sender_zar,
            beneficiary_account_id=beneficiary_token,
        )

        fee_tx_id = _leg(
            session,
            quote_id=quote_id,
            credit_account_id=sender_zar,
            debit_account_id=fee_revenue,
            amount="30",
            currency=CURRENCY_ZAR,
            type_=TYPE_FEE,
        )
        net_remittance_tx_id = _leg(
            session,
            quote_id=quote_id,
            credit_account_id=sender_zar,
            debit_account_id=bank,
            amount="970",
            currency=CURRENCY_ZAR,
            type_=TYPE_REMITTANCE,
        )
        treasury_pass_through_tx_id = _leg(
            session,
            quote_id=quote_id,
            credit_account_id=treasury,
            debit_account_id=sender_token,
            amount="52.432432",
            currency=CURRENCY_TOKEN,
            type_=TYPE_REMITTANCE,
        )
        settlement_tx_id = _leg(
            session,
            quote_id=quote_id,
            credit_account_id=sender_token,
            debit_account_id=beneficiary_token,
            amount="52.432432",
            currency=CURRENCY_TOKEN,
            type_=TYPE_REMITTANCE,
        )
        beneficiary_pass_through_tx_id = _leg(
            session,
            quote_id=quote_id,
            credit_account_id=beneficiary_token,
            debit_account_id=treasury,
            amount="52.432432",
            currency=CURRENCY_TOKEN,
            type_=TYPE_REMITTANCE,
        )
        burn_tx_id = _leg(
            session,
            quote_id=quote_id,
            credit_account_id=treasury,
            debit_account_id=issuer,
            amount="52.432432",
            currency=CURRENCY_TOKEN,
            type_=TYPE_TOKEN_BURN,
        )
        payout_tx_id = _leg(
            session,
            quote_id=quote_id,
            credit_account_id=beneficiary_bank,
            debit_account_id=beneficiary_fiat,
            amount="970",
            currency=CURRENCY_ZWL,
            type_=TYPE_BENEFICIARY_PAYOUT,
        )

    return {
        "quote_id": quote_id,
        "sender_zar": sender_zar,
        "fee_revenue": fee_revenue,
        "bank": bank,
        "sender_token": sender_token,
        "beneficiary_token": beneficiary_token,
        "treasury": treasury,
        "issuer": issuer,
        "beneficiary_fiat": beneficiary_fiat,
        "leg_ids": {
            fee_tx_id,
            net_remittance_tx_id,
            treasury_pass_through_tx_id,
            settlement_tx_id,
            beneficiary_pass_through_tx_id,
            burn_tx_id,
            payout_tx_id,
        },
        "burn_tx_id": burn_tx_id,
        "payout_tx_id": payout_tx_id,
    }


def _balance(session_factory, account_id) -> Decimal:
    with session_factory() as session:
        return session.get(Account, account_id).account_balance


def _leg_row(session_factory, tx_id) -> Transaction:
    with session_factory() as session:
        row = session.get(Transaction, tx_id)
        session.expunge(row)
        return row


def _leg_statuses(session_factory, quote_id) -> set[str]:
    with session_factory() as session:
        return {
            row.status
            for row in session.query(Transaction)
            .filter(Transaction.quote_id == quote_id)
            .all()
        }


def _claim_burn_leg(session_factory, burn_tx_id) -> None:
    """Simulate `burn_treasury_tokens` having already claimed the burn leg —
    `confirm_treasury_burn`'s own tests start from this state, the same way
    the real follow-up task always would."""
    with session_factory() as session:
        session.execute(
            Transaction.__table__.update()
            .where(Transaction.tx_id == burn_tx_id)
            .values(status=STATUS_PROCESSING)
        )
        session.commit()


def _set_burn_leg(session_factory, quote_id, burn_tx_id, *, tx_hash) -> None:
    """Leave a group as a crashed delivery would: every leg claimed, and the
    burn leg's hash stored or not."""
    with session_factory() as session:
        session.execute(
            Transaction.__table__.update()
            .where(Transaction.quote_id == quote_id)
            .values(status=STATUS_PROCESSING, processed_at=datetime.now(UTC))
        )
        if tx_hash is not None:
            session.execute(
                Transaction.__table__.update()
                .where(Transaction.tx_id == burn_tx_id)
                .values(evm_tx_hash=tx_hash, xrpl_tx_hash=tx_hash)
            )
        session.commit()


# --- burn_treasury_tokens: claim, burn, wait, hand off the rest ---


def test_burn_claims_the_group_stores_the_hash_first_and_enqueues_confirm(
    session_factory, pending_remittance, enqueued_confirm, chain
):
    seen_at_wait = []

    def receipt(tx_hash):
        seen_at_wait.append(_leg_row(session_factory, pending_remittance["burn_tx_id"]))

    chain.receipt = receipt

    result = burn_treasury_tokens(str(pending_remittance["quote_id"]))

    assert result == "burned"
    assert enqueued_confirm == [(str(pending_remittance["quote_id"]), BURN_HASH, None)]
    assert chain.waits == [BURN_HASH]

    # By the time the receipt is awaited the hash is already committed, in
    # both columns while the #239 rename dual-writes.
    (at_wait,) = seen_at_wait
    assert at_wait.status == STATUS_PROCESSING
    assert at_wait.evm_tx_hash == BURN_HASH
    assert at_wait.xrpl_tx_hash == BURN_HASH

    burn_leg = _leg_row(session_factory, pending_remittance["burn_tx_id"])
    assert burn_leg.status == STATUS_PROCESSING
    assert burn_leg.processed_at is not None
    # Every leg in the group is claimed together, not just the burn leg —
    # confirming and crediting is still confirm_treasury_burn's job, not
    # this one's, but every leg's processed_at should now reflect that
    # settlement started here.
    other_statuses = _leg_statuses(session_factory, pending_remittance["quote_id"])
    assert other_statuses == {STATUS_PROCESSING}
    assert _balance(session_factory, pending_remittance["fee_revenue"]) == Decimal("0")


def test_burn_burns_exactly_the_burn_leg_amount_not_the_treasury_balance(
    session_factory, pending_remittance, enqueued_confirm, chain
):
    burn_tokens_amount = _leg_row(session_factory, pending_remittance["burn_tx_id"])

    burn_treasury_tokens(str(pending_remittance["quote_id"]))

    # The Treasury holds 1000 (float for other remittances); only this
    # remittance's tokens are burned.
    assert chain.burns == [Decimal("52.432432")]
    assert chain.burns == [burn_tokens_amount.amount]
    assert _balance(session_factory, pending_remittance["treasury"]) == Decimal("1000")


def test_burn_twice_does_not_double_submit(
    session_factory, pending_remittance, enqueued_confirm, chain
):
    """The graded requirement: a redelivered burn message must not send a
    second burn, and the remittance is credited once."""
    first = burn_treasury_tokens(str(pending_remittance["quote_id"]))
    assert first == "burned"

    # Redelivered before confirm ran: waits on the same hash, sends nothing.
    second = burn_treasury_tokens(str(pending_remittance["quote_id"]))

    assert second == "burned"
    assert len(chain.burns) == 1
    assert chain.sent == [BURN_HASH]
    assert chain.waits == [BURN_HASH, BURN_HASH]
    assert [hash_ for _, hash_, _ in enqueued_confirm] == [BURN_HASH, BURN_HASH]

    # Both confirms are delivered; only the first credits.
    quote_id = str(pending_remittance["quote_id"])
    assert confirm_treasury_burn(quote_id, BURN_HASH) == "settled"
    assert confirm_treasury_burn(quote_id, BURN_HASH) == "skipped"
    assert _balance(session_factory, pending_remittance["fee_revenue"]) == Decimal("30")

    # And once confirmed, a further redelivery does nothing at all.
    assert burn_treasury_tokens(quote_id) == "skipped"
    assert len(chain.waits) == 2


def test_a_retry_with_a_stored_hash_waits_on_it_and_sends_nothing(
    session_factory, pending_remittance, enqueued_confirm, chain, caplog
):
    """A worker crashed after the hash was stored: the retry waits on that
    burn instead of sending another."""
    _set_burn_leg(
        session_factory,
        pending_remittance["quote_id"],
        pending_remittance["burn_tx_id"],
        tx_hash=BURN_HASH,
    )

    with caplog.at_level(logging.INFO, logger="remitx_worker.tasks"):
        result = burn_treasury_tokens(str(pending_remittance["quote_id"]))

    assert result == "burned"
    assert chain.burns == []
    assert chain.waits == [BURN_HASH]
    assert enqueued_confirm == [(str(pending_remittance["quote_id"]), BURN_HASH, None)]
    assert "event=settlement.burn_resumed" in caplog.text


def test_a_claimed_group_with_no_hash_is_left_alone(
    session_factory, pending_remittance, enqueued_confirm, chain, caplog
):
    """Claimed but never signed (or being signed by another delivery right
    now): nothing is sent, nothing is failed."""
    _set_burn_leg(
        session_factory,
        pending_remittance["quote_id"],
        pending_remittance["burn_tx_id"],
        tx_hash=None,
    )

    with caplog.at_level(logging.WARNING, logger="remitx_worker.tasks"):
        result = burn_treasury_tokens(str(pending_remittance["quote_id"]))

    assert result == "skipped"
    assert chain.burns == []
    assert chain.waits == []
    assert enqueued_confirm == []
    assert "event=settlement.burn_unsigned" in caplog.text
    assert _leg_statuses(session_factory, pending_remittance["quote_id"]) == {
        STATUS_PROCESSING
    }


def test_burn_failure_before_signing_enqueues_confirm_with_no_hash(
    session_factory, pending_remittance, enqueued_confirm, chain
):
    chain.fail_before_signing = RuntimeError("execution reverted: gas estimate")

    result = burn_treasury_tokens(str(pending_remittance["quote_id"]))

    assert result == "burn_failed"
    assert enqueued_confirm == [
        (
            str(pending_remittance["quote_id"]),
            None,
            "execution reverted: gas estimate",
        )
    ]
    assert chain.waits == []
    burn_leg = _leg_row(session_factory, pending_remittance["burn_tx_id"])
    assert burn_leg.status == STATUS_PROCESSING
    assert burn_leg.evm_tx_hash is None


def test_a_reverted_burn_fails_the_group_and_keeps_the_hash(
    session_factory, pending_remittance, enqueued_confirm, chain
):
    chain.receipt = evm_service.TransactionReverted(
        f"EVM transaction {BURN_HASH} reverted"
    )

    result = burn_treasury_tokens(str(pending_remittance["quote_id"]))

    assert result == "burn_failed"
    assert enqueued_confirm == [
        (
            str(pending_remittance["quote_id"]),
            None,
            f"EVM transaction {BURN_HASH} reverted",
        )
    ]
    # Kept for investigation; readers only show a confirmed burn's hash.
    burn_leg = _leg_row(session_factory, pending_remittance["burn_tx_id"])
    assert burn_leg.evm_tx_hash == BURN_HASH

    assert confirm_treasury_burn(*enqueued_confirm[0]) == "failed"
    assert _leg_statuses(session_factory, pending_remittance["quote_id"]) == {
        STATUS_FAILED
    }
    assert _balance(session_factory, pending_remittance["treasury"]) == Decimal("1000")


def test_a_receipt_timeout_retries_and_never_fails_the_group(
    session_factory, pending_remittance, enqueued_confirm, chain
):
    """Called directly (no worker), Celery's retry re-raises the error; in a
    worker it schedules the retry. Either way the group stays processing with
    its hash, and nothing is failed or confirmed."""
    chain.receipt = TimeExhausted("not mined in 120s")

    with pytest.raises(TimeExhausted):
        burn_treasury_tokens(str(pending_remittance["quote_id"]))

    assert enqueued_confirm == []
    assert len(chain.burns) == 1
    burn_leg = _leg_row(session_factory, pending_remittance["burn_tx_id"])
    assert burn_leg.status == STATUS_PROCESSING
    assert burn_leg.evm_tx_hash == BURN_HASH


def test_receipt_retries_wait_on_the_same_hash_then_leave_it_for_a_person(
    session_factory, pending_remittance, enqueued_confirm, chain, caplog
):
    """Run eagerly, so every retry runs in turn: the wait is retried on the
    one stored hash, never a new burn, and after the last retry the group is
    left processing with a greppable log line."""
    chain.receipt = TimeExhausted("not mined in 120s")

    with caplog.at_level(logging.WARNING, logger="remitx_worker.tasks"):
        result = burn_treasury_tokens.apply(
            args=[str(pending_remittance["quote_id"])]
        ).get()

    assert result == "awaiting_receipt"
    assert len(chain.burns) == 1
    assert chain.waits == [BURN_HASH] * (tasks.BURN_RECEIPT_MAX_RETRIES + 1)
    assert enqueued_confirm == []
    assert "event=settlement.burn_unconfirmed" in caplog.text
    assert caplog.text.count("event=settlement.burn_receipt_retry") == (
        tasks.BURN_RECEIPT_MAX_RETRIES
    )
    assert _leg_statuses(session_factory, pending_remittance["quote_id"]) == {
        STATUS_PROCESSING
    }


def test_a_send_that_raises_after_the_hash_is_stored_is_waited_on_not_failed(
    session_factory, pending_remittance, enqueued_confirm, chain, caplog
):
    """The send may have reached the chain even though it raised."""
    chain.fail_after_signing = ConnectionError("RPC dropped the connection")

    with caplog.at_level(logging.WARNING, logger="remitx_worker.tasks"):
        result = burn_treasury_tokens(str(pending_remittance["quote_id"]))

    assert result == "burned"
    assert chain.waits == [BURN_HASH]
    assert enqueued_confirm == [(str(pending_remittance["quote_id"]), BURN_HASH, None)]
    assert "event=settlement.burn_send_uncertain" in caplog.text


def test_nothing_is_sent_if_the_hash_cannot_be_stored(
    session_factory, pending_remittance, enqueued_confirm, chain, caplog
):
    """The guard in `record`: if the burn leg gained a hash between the claim
    and the signing, the signed burn is not sent and the group is not failed."""

    def another_hash_lands():
        with session_factory() as session:
            session.execute(
                Transaction.__table__.update()
                .where(Transaction.tx_id == pending_remittance["burn_tx_id"])
                .values(evm_tx_hash="0x" + "0f" * 32)
            )
            session.commit()

    chain.before_on_signed = another_hash_lands

    with caplog.at_level(logging.ERROR, logger="remitx_worker.tasks"):
        result = burn_treasury_tokens(str(pending_remittance["quote_id"]))

    assert result == "skipped"
    assert chain.sent == []
    assert chain.waits == []
    assert enqueued_confirm == []
    assert "event=settlement.burn_not_recorded" in caplog.text
    assert _leg_statuses(session_factory, pending_remittance["quote_id"]) == {
        STATUS_PROCESSING
    }


def test_burn_unknown_quote_is_skipped(session_factory, enqueued_confirm):
    assert burn_treasury_tokens(str(uuid.uuid4())) == "skipped"
    assert enqueued_confirm == []


@pytest.mark.parametrize(
    "quote_id", ["not-a-uuid", "", None], ids=["junk", "empty", "none"]
)
def test_burn_malformed_quote_id_is_skipped_not_an_error(session_factory, quote_id):
    assert burn_treasury_tokens(quote_id) == "skipped"


# --- confirm_treasury_burn: gates and settles every leg together ---


def test_confirm_success_settles_and_credits_every_leg(
    session_factory, pending_remittance
):
    _claim_burn_leg(session_factory, pending_remittance["burn_tx_id"])

    result = confirm_treasury_burn(str(pending_remittance["quote_id"]), "ABCDEF0123")

    assert result == "settled"
    assert _leg_statuses(session_factory, pending_remittance["quote_id"]) == {
        STATUS_CONFIRMED
    }

    burn_leg = _leg_row(session_factory, pending_remittance["burn_tx_id"])
    assert burn_leg.evm_tx_hash == "ABCDEF0123"
    # The deprecated column is dual-written until the #239 rename finishes.
    assert burn_leg.xrpl_tx_hash == "ABCDEF0123"
    assert burn_leg.confirmed_at is not None

    # Sender's ZAR account was this remittance's source for both fiat legs
    # (fee + net) — 1000 - 30 - 970 = 0, actually debited now, not just
    # left at its starting balance.
    assert _balance(session_factory, pending_remittance["sender_zar"]) == Decimal("0")
    assert _balance(session_factory, pending_remittance["fee_revenue"]) == Decimal("30")
    assert _balance(session_factory, pending_remittance["bank"]) == Decimal("970")
    # Both token pass-through accounts net to exactly zero: each is credited
    # by one leg and debited by the next for the same amount
    # (Transaction_Flow_Context.md §2 B2 — "never holds a resting balance").
    assert _balance(session_factory, pending_remittance["sender_token"]) == Decimal("0")
    assert _balance(
        session_factory, pending_remittance["beneficiary_token"]
    ) == Decimal("0")
    # Treasury started at 1000: -52.432432 funding the sender's pass-through,
    # +52.432432 from the beneficiary pass-through landing back in it,
    # -52.432432 burned to the issuer — nets to 1000 - 52.432432.
    assert _balance(session_factory, pending_remittance["treasury"]) == Decimal(
        "947.567568"
    )
    assert _balance(session_factory, pending_remittance["issuer"]) == Decimal(
        "52.432432"
    )
    assert _balance(session_factory, pending_remittance["beneficiary_fiat"]) == Decimal(
        "970"
    )


def test_confirm_twice_does_not_double_credit(session_factory, pending_remittance):
    _claim_burn_leg(session_factory, pending_remittance["burn_tx_id"])

    first = confirm_treasury_burn(str(pending_remittance["quote_id"]), "HASH1")
    assert first == "settled"

    second = confirm_treasury_burn(str(pending_remittance["quote_id"]), "HASH1")

    assert second == "skipped"
    assert _balance(session_factory, pending_remittance["fee_revenue"]) == Decimal("30")
    assert _balance(session_factory, pending_remittance["beneficiary_fiat"]) == Decimal(
        "970"
    )


def test_confirm_failure_fails_every_leg_with_no_balance_changes(
    session_factory, pending_remittance
):
    """The core requirement: if the burn fails before anything confirms,
    every leg sharing the quote_id fails together, and — because nothing
    was ever credited — this is a pure status change, no reversal needed."""
    _claim_burn_leg(session_factory, pending_remittance["burn_tx_id"])

    result = confirm_treasury_burn(str(pending_remittance["quote_id"]), None)

    assert result == "failed"
    assert _leg_statuses(session_factory, pending_remittance["quote_id"]) == {
        STATUS_FAILED
    }
    burn_leg = _leg_row(session_factory, pending_remittance["burn_tx_id"])
    assert burn_leg.evm_tx_hash is None

    for account_id, expected in [
        (pending_remittance["fee_revenue"], "0"),
        (pending_remittance["bank"], "0"),
        (pending_remittance["sender_token"], "0"),
        (pending_remittance["beneficiary_token"], "0"),
        (pending_remittance["treasury"], "1000"),
        (pending_remittance["issuer"], "0"),
        (pending_remittance["beneficiary_fiat"], "0"),
    ]:
        assert _balance(session_factory, account_id) == Decimal(expected)


def test_confirm_failure_twice_does_not_refail_or_change_balances(
    session_factory, pending_remittance
):
    _claim_burn_leg(session_factory, pending_remittance["burn_tx_id"])

    first = confirm_treasury_burn(str(pending_remittance["quote_id"]), None)
    assert first == "failed"

    second = confirm_treasury_burn(str(pending_remittance["quote_id"]), None)

    assert second == "skipped"
    assert _leg_statuses(session_factory, pending_remittance["quote_id"]) == {
        STATUS_FAILED
    }


def test_confirm_unknown_quote_is_skipped(session_factory):
    assert confirm_treasury_burn(str(uuid.uuid4()), "HASH1") == "skipped"


@pytest.mark.parametrize(
    "quote_id", ["not-a-uuid", "", None], ids=["junk", "empty", "none"]
)
def test_confirm_malformed_quote_id_is_skipped_not_an_error(session_factory, quote_id):
    assert confirm_treasury_burn(quote_id, "HASH1") == "skipped"
