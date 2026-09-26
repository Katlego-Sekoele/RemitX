"""Edge cases across the whole remittance flow: quote -> confirm -> worker
settlement (Transaction_Flow_Context.md §2 Phases B2/C).

The per-component suites (test_quote_service, test_remittance_service,
test_worker_*) each stop at their own boundary. These tests cross them: the
API service writes the legs, then the real worker tasks settle them against
the same database, so ledger-wide invariants (zero-sum per currency, exactly
one burn, held funds released on failure) can be checked end to end.

The worker gets a session factory bound to the app's engine. TestConfig's
in-memory SQLite is pinned to one connection (StaticPool), so the app
session commits before any task runs and expires its cache after.
Broker enqueues are captured and drained by hand, so redelivery and
out-of-order messages can be played deliberately.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError
from remitx_api.controllers.beneficiary_controller import BeneficiaryController
from remitx_api.controllers.user_controller import UserController
from remitx_api.extensions import db
from remitx_api.models.orm.account import (
    CURRENCY_TOKEN,
    CURRENCY_ZAR,
    CURRENCY_ZWL,
    TYPE_PLATFORM_FIAT,
    TYPE_PLATFORM_REVENUE,
    Account,
)
from remitx_api.models.orm.bank_account import BankAccount
from remitx_api.models.orm.exchange_rate import ExchangeRate
from remitx_api.models.orm.kyc_lifecycle import KYC_TIER_VERIFIED, KycStatus
from remitx_api.models.orm.quote import STATUS_ACTIVE
from remitx_api.models.orm.transaction import (
    STATUS_CONFIRMED,
    STATUS_FAILED,
    STATUS_PROCESSING,
    TYPE_TOKEN_BURN,
    Transaction,
)
from remitx_api.models.schemas.withdrawal import WithdrawalCreateRequest
from remitx_api.repositories.account_repository import AccountRepository
from remitx_api.repositories.kyc_application_repository import (
    KycApplicationRepository,
)
from remitx_api.repositories.quote_repository import QuoteRepository
from remitx_api.services import (
    deposit_service,
    queue_service,
    quote_service,
    remittance_service,
    withdrawal_service,
)
from remitx_api.services.remittance_service import (
    REMITX_TREASURY_WALLET_LABEL,
    TOKEN_ISSUER_LABEL,
)
from remitx_worker import db as worker_db, tasks
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from tests.kyc_helpers import insert_application
from tests.platform_account_helpers import seed_platform_accounts

# --- fixtures ---


@pytest.fixture
def broker(monkeypatch):
    """Every remittance enqueue, captured in order as (task, args)."""
    messages = []
    monkeypatch.setattr(
        queue_service,
        "enqueue_settle_remittance",
        lambda quote_id: messages.append(("settle", (quote_id,))),
    )
    monkeypatch.setattr(
        queue_service,
        "enqueue_burn_treasury_tokens",
        lambda quote_id: messages.append(("burn", (quote_id,))),
    )
    monkeypatch.setattr(
        queue_service,
        "enqueue_confirm_treasury_burn",
        lambda quote_id, tx_hash, error=None: messages.append(
            ("confirm", (quote_id, tx_hash, error))
        ),
    )
    return messages


@pytest.fixture
def xrpl(monkeypatch):
    """Stand-in for the one real XRPL call. Records each burn amount;
    set `.fail` to make the next burns raise."""

    class FakeXrpl:
        def __init__(self):
            self.burns = []
            self.fail = False

        def burn_tokens(self, amount):
            self.burns.append(amount)
            if self.fail:
                raise RuntimeError("tecPATH_DRY")
            return f"HASH{len(self.burns)}"

    fake = FakeXrpl()
    monkeypatch.setattr(tasks.xrpl_service, "burn_tokens", fake.burn_tokens)
    return fake


@pytest.fixture
def ledger(app_context, broker, xrpl):
    """Rates, platform accounts, a KYC-approved sender and a ZWL
    beneficiary, with the worker pointed at the app's database."""
    _store_rate("18.50")  # USD -> ZAR
    _store_rate("16.22", base_currency="ZAR", quote_currency="ZWL")
    seed_platform_accounts()

    sender = UserController().ensure_provisioned(
        "user_flow_sender", lambda: "flow-sender@example.com", lambda: "Sender"
    )
    insert_application(
        sender.id, status=KycStatus.APPROVED, tier_granted=KYC_TIER_VERIFIED
    )
    recipient = UserController().ensure_provisioned(
        "user_flow_recipient", lambda: "flow-recipient@example.com", lambda: "Recip"
    )
    AccountRepository().get_or_create_user_account(
        recipient.id, recipient.base_reference, CURRENCY_ZWL
    )
    beneficiary = (
        BeneficiaryController()
        .create(
            sender_user_id=sender.id,
            linked_user_id=recipient.id,
            payout_currency="ZWL",
            relationship="sibling",
        )
        .beneficiary
    )

    worker_db.configure(sessionmaker(bind=db.engine, autoflush=False))
    yield {
        "sender": sender,
        "recipient": recipient,
        "beneficiary": beneficiary,
        "broker": broker,
        "xrpl": xrpl,
    }
    worker_db.configure(None)


# --- helpers ---


def _store_rate(rate, base_currency="USD", quote_currency="ZAR"):
    now = datetime.now(UTC)
    db.session.add(
        ExchangeRate(
            base_currency=base_currency,
            quote_currency=quote_currency,
            rate=Decimal(rate),
            fetched_at=now,
            valid_until=now + timedelta(hours=1),
        )
    )
    db.session.commit()


def _fund(user, amount):
    accounts = AccountRepository()
    account = accounts.get_user_account(user.id, CURRENCY_ZAR)
    accounts.increase_balance(account.account_id, Decimal(amount))
    db.session.commit()


def _quote(env, amount):
    return quote_service.create_quote(
        env["sender"].id,
        env["beneficiary"].beneficiary_id,
        Decimal(amount),
        sender_currency=CURRENCY_ZAR,
        receiver_payout_currency="ZWL",
    )


def _drain(broker, *, redeliver=False):
    """Run every captured message through its worker task, as a broker
    would, until the queue is empty. With `redeliver`, each message is
    delivered twice (acks_late redelivery after a worker crash)."""
    handlers = {
        "settle": tasks.settle_remittance,
        "burn": tasks.burn_treasury_tokens,
        "confirm": tasks.confirm_treasury_burn,
    }
    db.session.commit()
    results = []
    while broker:
        name, args = broker.pop(0)
        for _ in range(2 if redeliver else 1):
            results.append((name, handlers[name](*args)))
    db.session.expire_all()
    return results


def _all_balances():
    db.session.expire_all()
    return {
        row.account_id: (row.account_currency, row.account_balance)
        for row in db.session.scalars(select(Account))
    }


def _legs(quote_id):
    db.session.expire_all()
    return db.session.scalars(
        select(Transaction).where(Transaction.quote_id == quote_id)
    ).all()


def _balance(account):
    db.session.expire_all()
    return db.session.get(Account, account.account_id).account_balance


# --- end to end: service + worker ---


def test_full_settlement_moves_exactly_the_quoted_amounts(ledger):
    env = ledger
    _fund(env["sender"], "1000")
    before = _all_balances()
    quote = _quote(env, "1000")

    remittance_service.confirm_remittance(env["sender"].id, quote.quote_id)
    results = _drain(env["broker"])

    assert [name for name, _ in results] == ["settle", "burn", "confirm"]
    assert results[-1] == ("confirm", "settled")
    assert {leg.status for leg in _legs(quote.quote_id)} == {STATUS_CONFIRMED}
    # Exactly one on-chain burn, of exactly the quoted token amount.
    assert env["xrpl"].burns == [quote.token_amount]

    accounts = AccountRepository()
    sender_zar = accounts.get_user_account(env["sender"].id, CURRENCY_ZAR)
    sender_tok = accounts.get_user_account(env["sender"].id, CURRENCY_TOKEN)
    recip_tok = accounts.get_user_account(env["recipient"].id, CURRENCY_TOKEN)
    recip_zwl = accounts.get_user_account(env["recipient"].id, CURRENCY_ZWL)
    revenue = accounts.get_platform_account(TYPE_PLATFORM_REVENUE, CURRENCY_ZAR)
    sa_bank = accounts.get_platform_account(TYPE_PLATFORM_FIAT, CURRENCY_ZAR)
    zim_bank = accounts.get_platform_account(TYPE_PLATFORM_FIAT, CURRENCY_ZWL)
    treasury = accounts.get_platform_account_by_label(REMITX_TREASURY_WALLET_LABEL)
    issuer = accounts.get_platform_account_by_label(TOKEN_ISSUER_LABEL)

    fees = quote.sender_transaction_fee + quote.exchange_rate_margin
    assert _balance(sender_zar) == Decimal("0")
    assert _balance(revenue) == fees
    assert _balance(sa_bank) == Decimal("1000") - fees
    assert _balance(sender_tok) == Decimal("0")
    assert _balance(recip_tok) == Decimal("0")
    assert _balance(treasury) == -quote.token_amount
    assert _balance(issuer) == quote.token_amount
    assert _balance(recip_zwl) == quote.receiver_amount
    assert _balance(zim_bank) == -quote.receiver_amount

    # Zero-sum: in every currency, what the remittance moved nets to nothing.
    after = _all_balances()
    net_by_currency = {}
    for account_id, (currency, balance) in after.items():
        delta = balance - before.get(account_id, (currency, Decimal("0")))[1]
        net_by_currency[currency] = net_by_currency.get(currency, 0) + delta
    assert all(net == 0 for net in net_by_currency.values()), net_by_currency


def test_every_message_delivered_twice_still_burns_and_credits_once(ledger):
    env = ledger
    _fund(env["sender"], "1000")
    quote = _quote(env, "1000")

    remittance_service.confirm_remittance(env["sender"].id, quote.quote_id)
    _drain(env["broker"], redeliver=True)

    assert len(env["xrpl"].burns) == 1
    recip_zwl = AccountRepository().get_user_account(env["recipient"].id, CURRENCY_ZWL)
    assert _balance(recip_zwl) == quote.receiver_amount
    sender_zar = AccountRepository().get_user_account(env["sender"].id, CURRENCY_ZAR)
    assert _balance(sender_zar) == Decimal("0")


def test_a_failed_burn_releases_the_held_funds(ledger):
    env = ledger
    _fund(env["sender"], "1000")
    before = _all_balances()
    quote = _quote(env, "1000")
    env["xrpl"].fail = True

    remittance_service.confirm_remittance(env["sender"].id, quote.quote_id)
    results = _drain(env["broker"])

    assert results[-1] == ("confirm", "failed")
    assert {leg.status for leg in _legs(quote.quote_id)} == {STATUS_FAILED}
    assert _all_balances() == before
    # Failed legs no longer hold the money: the sender can spend all of it.
    sender_zar = AccountRepository().get_user_account(env["sender"].id, CURRENCY_ZAR)
    assert AccountRepository().get_available_balance(sender_zar.account_id) == Decimal(
        "1000"
    )
    env["xrpl"].fail = False
    retry = _quote(env, "1000")
    remittance_service.confirm_remittance(env["sender"].id, retry.quote_id)
    assert _drain(env["broker"])[-1] == ("confirm", "settled")


def test_a_late_success_after_a_recorded_failure_credits_nothing(ledger):
    """Out-of-order or duplicate outcomes: once the group is failed, a stray
    success message must not resurrect it and credit the beneficiary."""
    env = ledger
    _fund(env["sender"], "1000")
    quote = _quote(env, "1000")
    remittance_service.confirm_remittance(env["sender"].id, quote.quote_id)
    env["broker"].clear()
    db.session.commit()

    assert tasks.burn_treasury_tokens(str(quote.quote_id)) == "burned"
    env["broker"].clear()
    before = _all_balances()
    assert tasks.confirm_treasury_burn(str(quote.quote_id), None, "boom") == "failed"
    assert tasks.confirm_treasury_burn(str(quote.quote_id), "LATEHASH") == "skipped"

    db.session.expire_all()
    assert _all_balances() == before
    assert {leg.status for leg in _legs(quote.quote_id)} == {STATUS_FAILED}
    burn = next(leg for leg in _legs(quote.quote_id) if leg.type == TYPE_TOKEN_BURN)
    assert burn.xrpl_tx_hash is None


def test_funds_stay_held_while_the_burn_is_in_flight(ledger):
    """Between `burn_treasury_tokens` claiming the legs and
    `confirm_treasury_burn` recording the outcome, every leg is
    `processing` and no balance has moved. The raw balance still shows the
    money, so only the hold stops it being spent twice."""
    env = ledger
    _fund(env["sender"], "1000")
    quote = _quote(env, "1000")
    remittance_service.confirm_remittance(env["sender"].id, quote.quote_id)
    env["broker"].clear()
    db.session.commit()
    tasks.burn_treasury_tokens(str(quote.quote_id))
    db.session.expire_all()

    assert {leg.status for leg in _legs(quote.quote_id)} == {STATUS_PROCESSING}
    sender_zar = AccountRepository().get_user_account(env["sender"].id, CURRENCY_ZAR)
    assert _balance(sender_zar) == Decimal("1000")
    with pytest.raises(quote_service.InsufficientBalanceError):
        _quote(env, "100")


def test_settlement_does_not_start_until_the_confirm_commits(ledger, monkeypatch):
    """Brief: the RLUSD transfer may not start before the send is recorded.
    If the confirm's commit fails, nothing may be enqueued."""
    env = ledger
    _fund(env["sender"], "1000")
    quote = _quote(env, "1000")

    def failing_commit():
        raise RuntimeError("database went away")

    monkeypatch.setattr(db.session, "commit", failing_commit)
    with pytest.raises(RuntimeError):
        remittance_service.confirm_remittance(env["sender"].id, quote.quote_id)
    assert env["broker"] == []


# --- confirm-time edge cases ---


def test_insufficient_balance_at_confirm_leaves_the_quote_reusable(ledger):
    """The failed confirm rolls back its own ACTIVE -> USED flip, writes no
    legs and enqueues nothing, so the sender can top up and retry the
    same quote before it expires."""
    env = ledger
    _fund(env["sender"], "1000")
    quote = _quote(env, "1000")
    sender_zar = AccountRepository().get_user_account(env["sender"].id, CURRENCY_ZAR)
    AccountRepository().decrease_balance(sender_zar.account_id, Decimal("1"))
    db.session.commit()

    with pytest.raises(remittance_service.InsufficientBalanceError):
        remittance_service.confirm_remittance(env["sender"].id, quote.quote_id)

    db.session.expire_all()
    assert QuoteRepository().get_by_id(quote.quote_id).status == STATUS_ACTIVE
    assert _legs(quote.quote_id) == []
    assert env["broker"] == []

    _fund(env["sender"], "1")
    remittance_service.confirm_remittance(env["sender"].id, quote.quote_id)
    assert len(_legs(quote.quote_id)) == 7


def test_the_recipient_cannot_confirm_the_senders_quote(ledger):
    env = ledger
    _fund(env["sender"], "1000")
    quote = _quote(env, "1000")

    with pytest.raises(remittance_service.QuoteNotFoundError):
        remittance_service.confirm_remittance(env["recipient"].id, quote.quote_id)


def test_the_full_available_balance_can_be_sent(ledger):
    env = ledger
    _fund(env["sender"], "250.37")
    quote = _quote(env, "250.37")
    remittance_service.confirm_remittance(env["sender"].id, quote.quote_id)
    _drain(env["broker"])

    sender_zar = AccountRepository().get_user_account(env["sender"].id, CURRENCY_ZAR)
    assert _balance(sender_zar) == Decimal("0")


def test_a_cent_over_the_available_balance_is_refused(ledger):
    env = ledger
    _fund(env["sender"], "250.37")
    with pytest.raises(quote_service.InsufficientBalanceError):
        _quote(env, "250.38")


# --- quote-time edge cases ---


def test_the_daily_limit_is_inclusive(ledger):
    env = ledger
    limit = KycApplicationRepository().get_standing(env["sender"].id).daily_limit_zar
    _fund(env["sender"], limit + 1)

    assert _quote(env, limit).sender_amount == limit
    with pytest.raises(quote_service.LimitExceededError):
        _quote(env, limit + Decimal("0.01"))


@pytest.mark.parametrize(
    "amount",
    ["20.00", "20.01", "33.33", "99.99", "100.005", "1234.56", "2999.99", "3000"],
)
def test_the_fiat_legs_always_sum_to_the_sender_amount(ledger, amount):
    """Fee, margin and net are rounded separately; the two fiat legs taken
    from the sender must still add up to exactly what they were quoted,
    and every leg must be a positive 2dp amount."""
    env = ledger
    _fund(env["sender"], "5000")
    quote = _quote(env, amount)
    remittance_service.confirm_remittance(env["sender"].id, quote.quote_id)

    legs = _legs(quote.quote_id)
    sender_zar = AccountRepository().get_user_account(env["sender"].id, CURRENCY_ZAR)
    taken = sum(
        leg.amount for leg in legs if leg.credit_account_id == sender_zar.account_id
    )
    assert taken == quote.sender_amount
    for leg in legs:
        assert leg.amount > 0
        assert leg.amount == leg.amount.quantize(Decimal("0.01"))


def test_an_amount_that_only_covers_the_fees_is_refused(ledger):
    env = ledger
    _fund(env["sender"], "100")
    # Fixed fee alone is FIXED_FEE_ZAR; anything at or under it nets <= 0.
    with pytest.raises(ValueError):
        _quote(env, "1")


def test_an_unmatched_deposit_cannot_be_sent_until_approved(ledger):
    """Brief: the RLUSD transfer may not start until the ZAR cash-in is
    confirmed. A statement line with no matching reference sits pending
    and must not be spendable."""
    env = ledger
    result = deposit_service.process_deposits(
        [
            {
                "reference": "nobody-zar",
                "amount": "1000.00",
                "currency": CURRENCY_ZAR,
                "date": "2026-09-10",
            }
        ]
    )
    [deposit] = result.deposits

    with pytest.raises(quote_service.InsufficientBalanceError):
        _quote(env, "500")

    admin = UserController().ensure_provisioned(
        "user_flow_admin", lambda: "flow-admin@example.com", lambda: "Admin"
    )
    deposit_service.approve_pending_deposit(
        deposit.deposit_id, f"{env['sender'].base_reference}-zar", admin.id
    )
    assert _quote(env, "500").sender_amount == Decimal("500")


def test_a_withdrawal_cannot_spend_money_held_by_a_pending_remittance(ledger):
    env = ledger
    _fund(env["sender"], "1000")
    bank = BankAccount(
        user_id=env["sender"].id,
        account_holder_name="Sender",
        bank_name="FNB",
        account_number="62000000000",
        currency=CURRENCY_ZAR,
        status="verified",
    )
    db.session.add(bank)
    db.session.commit()
    quote = _quote(env, "800")
    remittance_service.confirm_remittance(env["sender"].id, quote.quote_id)

    with pytest.raises(withdrawal_service.InsufficientBalanceError):
        withdrawal_service.request_withdrawal(
            env["sender"].id, bank.bank_account_id, CURRENCY_ZAR, Decimal("300")
        )


@pytest.mark.parametrize("amount", ["1e26", "1e30", "1000000000000", "0", "-5"])
def test_a_withdrawal_amount_the_ledger_cannot_hold_is_refused(amount):
    """`round_amount` quantizes to 0.01, which overflows Decimal's 28-digit
    context from 1e26 up. The request model refuses such amounts (a 422)
    before `request_withdrawal` runs, rather than a 500 from
    InvalidOperation."""
    with pytest.raises(ValidationError):
        WithdrawalCreateRequest(
            bank_account_id=uuid.uuid4(), currency=CURRENCY_ZAR, amount=amount
        )
