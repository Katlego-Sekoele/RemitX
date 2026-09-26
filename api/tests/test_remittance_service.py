import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from remitx_api.controllers.beneficiary_controller import BeneficiaryController
from remitx_api.controllers.user_controller import UserController
from remitx_api.errors.remittances import KycNotApprovedError, LimitExceededError
from remitx_api.extensions import db
from remitx_api.models.orm.account import (
    CURRENCY_TOKEN,
    CURRENCY_ZAR,
    CURRENCY_ZWL,
)
from remitx_api.models.orm.exchange_rate import ExchangeRate
from remitx_api.models.orm.kyc_lifecycle import KYC_TIER_VERIFIED, KycStatus
from remitx_api.models.orm.quote import STATUS_ACTIVE, STATUS_USED
from remitx_api.models.orm.transaction import (
    STATUS_PENDING,
    TYPE_BENEFICIARY_PAYOUT,
    TYPE_FEE,
    TYPE_REMITTANCE,
    TYPE_TOKEN_BURN,
    Transaction,
)
from remitx_api.repositories.account_repository import AccountRepository
from remitx_api.repositories.kyc_application_repository import (
    KycApplicationRepository,
)
from remitx_api.repositories.quote_repository import QuoteRepository
from remitx_api.repositories.remittance_repository import RemittanceRepository
from remitx_api.repositories.transaction_repository import TransactionRepository
from remitx_api.services import queue_service, quote_service, remittance_service
from remitx_api.services.quote_service import UnknownBeneficiaryPayoutAccountError
from remitx_api.services.remittance_service import (
    TOKEN_ISSUER_LABEL,
)
from sqlalchemy import func, select
from tests.kyc_helpers import insert_application
from tests.platform_account_helpers import seed_platform_accounts


@pytest.fixture
def enqueued(monkeypatch):
    """Capture `enqueue_settle_remittance` calls instead of publishing to
    Redis — this module's own version of conftest's `enqueued` fixture,
    which only patches the integration-message enqueue."""
    calls = []
    monkeypatch.setattr(
        queue_service,
        "enqueue_settle_remittance",
        calls.append,
    )
    return calls


def _approve(user):
    insert_application(
        user.id, status=KycStatus.APPROVED, tier_granted=KYC_TIER_VERIFIED
    )
    return user


def _store_rate(
    rate: str = "18.50", base_currency: str = "USD", quote_currency: str = "ZAR"
) -> ExchangeRate:
    now = datetime.now(UTC)
    row = ExchangeRate(
        base_currency=base_currency,
        quote_currency=quote_currency,
        rate=Decimal(rate),
        fetched_at=now,
        valid_until=now + timedelta(hours=1),
    )
    db.session.add(row)
    db.session.commit()
    return row


def _make_sender_and_beneficiary():
    sender = _approve(
        UserController().ensure_provisioned(
            "user_remit_sender", lambda: "remit-sender@example.com", lambda: "Sender"
        )
    )
    recipient = UserController().ensure_provisioned(
        "user_remit_recipient", lambda: "remit-recipient@example.com", lambda: "Recip"
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
    return sender, recipient, beneficiary


def _fund_and_quote(sender, beneficiary, amount: Decimal):
    account_repo = AccountRepository()
    sender_zar = account_repo.get_user_account(sender.id, CURRENCY_ZAR)
    account_repo.increase_balance(sender_zar.account_id, amount)
    db.session.commit()
    return quote_service.create_quote(
        sender.id,
        beneficiary.beneficiary_id,
        amount,
        sender_currency=CURRENCY_ZAR,
        receiver_payout_currency="ZWL",
    )


def test_confirm_refuses_when_beneficiary_lacks_payout_account(app_context):
    _store_rate("18.50")
    _store_rate("16.22", base_currency="ZAR", quote_currency="ZWL")
    seed_platform_accounts()
    sender, recipient, beneficiary = _make_sender_and_beneficiary()
    quote = _fund_and_quote(sender, beneficiary, Decimal("1000"))
    quote.receiver_currency = "USD"
    db.session.commit()

    with pytest.raises(UnknownBeneficiaryPayoutAccountError):
        remittance_service.confirm_remittance(sender.id, quote.quote_id)

    reloaded = QuoteRepository().get_for_sender(quote.quote_id, sender.id)
    assert reloaded is not None
    assert reloaded.status == STATUS_ACTIVE


def test_confirming_a_quote_creates_seven_pending_legs(app_context, enqueued):
    _store_rate("18.50")
    _store_rate("16.22", base_currency="ZAR", quote_currency="ZWL")
    seed_platform_accounts()
    sender, recipient, beneficiary = _make_sender_and_beneficiary()
    quote = _fund_and_quote(sender, beneficiary, Decimal("1000"))

    remittance = remittance_service.confirm_remittance(sender.id, quote.quote_id)

    account_repo = AccountRepository()
    sender_account = account_repo.get_user_account(sender.id, CURRENCY_ZAR)
    sender_token_account = account_repo.get_user_account(sender.id, CURRENCY_TOKEN)
    beneficiary_token_account = account_repo.get_user_account(
        recipient.id, CURRENCY_TOKEN
    )
    beneficiary_fiat_account = account_repo.get_user_account(recipient.id, "ZWL")
    issuer_account = account_repo.get_platform_account_by_label(TOKEN_ISSUER_LABEL)
    transaction_repo = TransactionRepository()
    touched = {
        leg.tx_id: leg
        for leg in (
            transaction_repo.list_account_transactions(sender_account.account_id)
            + transaction_repo.list_account_transactions(
                sender_token_account.account_id
            )
            + transaction_repo.list_account_transactions(
                beneficiary_token_account.account_id
            )
            + transaction_repo.list_account_transactions(
                beneficiary_fiat_account.account_id
            )
            + transaction_repo.list_account_transactions(issuer_account.account_id)
        )
    }
    legs = [leg for leg in touched.values() if leg.quote_id == quote.quote_id]
    assert len(legs) == 7
    assert all(leg.status == STATUS_PENDING for leg in legs)

    fee_leg = next(leg for leg in legs if leg.type == TYPE_FEE)
    assert fee_leg.amount == quote.sender_transaction_fee + quote.exchange_rate_margin
    assert fee_leg.currency == CURRENCY_ZAR

    fiat_leg = next(
        leg
        for leg in legs
        if leg.type == TYPE_REMITTANCE
        and leg.currency == CURRENCY_ZAR
        and leg.credit_account_id == sender_account.account_id
    )
    assert fiat_leg.amount == (
        quote.sender_amount - quote.sender_transaction_fee - quote.exchange_rate_margin
    )

    treasury_in_leg = next(
        leg for leg in legs if leg.debit_account_id == sender_token_account.account_id
    )
    assert treasury_in_leg.amount == quote.token_amount
    assert treasury_in_leg.currency == CURRENCY_TOKEN

    settlement_leg = next(
        leg
        for leg in legs
        if leg.debit_account_id == beneficiary_token_account.account_id
    )
    assert settlement_leg.amount == quote.token_amount

    pass_through_leg = next(
        leg
        for leg in legs
        if leg.credit_account_id == beneficiary_token_account.account_id
    )
    assert pass_through_leg.amount == quote.token_amount
    assert pass_through_leg.currency == CURRENCY_TOKEN

    burn_leg = next(leg for leg in legs if leg.type == TYPE_TOKEN_BURN)
    assert burn_leg.credit_account_id == pass_through_leg.debit_account_id  # treasury
    assert burn_leg.debit_account_id == issuer_account.account_id
    assert burn_leg.amount == quote.token_amount
    assert burn_leg.currency == CURRENCY_TOKEN

    payout_leg = next(
        leg
        for leg in legs
        if leg.debit_account_id == beneficiary_fiat_account.account_id
    )
    assert payout_leg.type == TYPE_BENEFICIARY_PAYOUT
    assert payout_leg.amount == quote.receiver_amount
    assert payout_leg.currency == quote.receiver_currency
    assert settlement_leg.tx_id == remittance.tx_id

    # No balance moves yet — everything above is still pending.
    assert account_repo.get_by_id(sender_account.account_id).account_balance == (
        Decimal("1000")
    )


def test_confirming_a_quote_flips_it_to_used(app_context, enqueued):
    _store_rate("18.50")
    _store_rate("16.22", base_currency="ZAR", quote_currency="ZWL")
    seed_platform_accounts()
    sender, recipient, beneficiary = _make_sender_and_beneficiary()
    quote = _fund_and_quote(sender, beneficiary, Decimal("1000"))

    remittance_service.confirm_remittance(sender.id, quote.quote_id)

    assert QuoteRepository().get_by_id(quote.quote_id).status == STATUS_USED


def test_confirming_records_the_remittance_row(app_context, enqueued):
    _store_rate("18.50")
    _store_rate("16.22", base_currency="ZAR", quote_currency="ZWL")
    seed_platform_accounts()
    sender, recipient, beneficiary = _make_sender_and_beneficiary()
    quote = _fund_and_quote(sender, beneficiary, Decimal("1000"))

    remittance = remittance_service.confirm_remittance(sender.id, quote.quote_id)

    stored = RemittanceRepository().get_by_quote_id(quote.quote_id)
    assert stored.remittance_id == remittance.remittance_id


def test_confirming_enqueues_settlement_after_commit(app_context, enqueued):
    _store_rate("18.50")
    _store_rate("16.22", base_currency="ZAR", quote_currency="ZWL")
    seed_platform_accounts()
    sender, recipient, beneficiary = _make_sender_and_beneficiary()
    quote = _fund_and_quote(sender, beneficiary, Decimal("1000"))

    remittance_service.confirm_remittance(sender.id, quote.quote_id)

    assert enqueued == [str(quote.quote_id)]


def test_unknown_quote_is_rejected(app_context, enqueued):
    seed_platform_accounts()
    sender, _recipient, _beneficiary = _make_sender_and_beneficiary()

    with pytest.raises(remittance_service.QuoteNotFoundError):
        remittance_service.confirm_remittance(sender.id, uuid.uuid4())


def test_someone_elses_quote_is_rejected(app_context, enqueued):
    _store_rate("18.50")
    _store_rate("16.22", base_currency="ZAR", quote_currency="ZWL")
    seed_platform_accounts()
    sender, recipient, beneficiary = _make_sender_and_beneficiary()
    quote = _fund_and_quote(sender, beneficiary, Decimal("1000"))
    other = _approve(
        UserController().ensure_provisioned(
            "user_remit_other", lambda: "other-remit@example.com", lambda: "Other"
        )
    )

    with pytest.raises(remittance_service.QuoteNotFoundError):
        remittance_service.confirm_remittance(other.id, quote.quote_id)


def test_already_confirmed_quote_cannot_be_confirmed_again(app_context, enqueued):
    _store_rate("18.50")
    _store_rate("16.22", base_currency="ZAR", quote_currency="ZWL")
    seed_platform_accounts()
    sender, recipient, beneficiary = _make_sender_and_beneficiary()
    quote = _fund_and_quote(sender, beneficiary, Decimal("1000"))
    remittance_service.confirm_remittance(sender.id, quote.quote_id)

    with pytest.raises(remittance_service.QuoteNotActiveError):
        remittance_service.confirm_remittance(sender.id, quote.quote_id)


def test_expired_quote_cannot_be_confirmed(app_context, enqueued):
    _store_rate("18.50")
    _store_rate("16.22", base_currency="ZAR", quote_currency="ZWL")
    seed_platform_accounts()
    sender, recipient, beneficiary = _make_sender_and_beneficiary()
    quote = _fund_and_quote(sender, beneficiary, Decimal("1000"))
    quote.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.session.commit()

    with pytest.raises(remittance_service.QuoteNotActiveError):
        remittance_service.confirm_remittance(sender.id, quote.quote_id)


def test_second_active_quote_fails_available_balance_check_after_first_confirms(
    app_context, enqueued
):
    """The Open Question #5 gap this closes: `create_quote` nets a sender's
    pending legs, but confirming the FIRST of two ACTIVE quotes is what
    actually creates those legs — nothing re-checked balance at confirm
    time before this. Two ACTIVE quotes against one balance must not both
    be confirmable.
    """
    _store_rate("18.50")
    _store_rate("16.22", base_currency="ZAR", quote_currency="ZWL")
    seed_platform_accounts()
    sender, recipient, beneficiary = _make_sender_and_beneficiary()
    account_repo = AccountRepository()
    sender_zar = account_repo.get_user_account(sender.id, CURRENCY_ZAR)
    account_repo.increase_balance(sender_zar.account_id, Decimal("1000"))
    db.session.commit()

    first_quote = quote_service.create_quote(
        sender.id,
        beneficiary.beneficiary_id,
        Decimal("600"),
        sender_currency=CURRENCY_ZAR,
        receiver_payout_currency="ZWL",
    )
    second_quote = quote_service.create_quote(
        sender.id,
        beneficiary.beneficiary_id,
        Decimal("600"),
        sender_currency=CURRENCY_ZAR,
        receiver_payout_currency="ZWL",
    )

    remittance_service.confirm_remittance(sender.id, first_quote.quote_id)

    with pytest.raises(remittance_service.InsufficientBalanceError):
        remittance_service.confirm_remittance(sender.id, second_quote.quote_id)


def _quote(sender, beneficiary, amount: str):
    return quote_service.create_quote(
        sender.id,
        beneficiary.beneficiary_id,
        Decimal(amount),
        sender_currency=CURRENCY_ZAR,
        receiver_payout_currency="ZWL",
    )


def _legs_for(quote_id) -> int:
    return db.session.scalar(
        select(func.count())
        .select_from(Transaction)
        .where(Transaction.quote_id == quote_id)
    )


def test_confirming_counts_what_was_sent_since_the_quote(app_context, enqueued):
    """Quotes are checked against what was sent when they were issued, and
    several can be issued against one allowance, so confirming is the real
    gate: after R2,000 goes, R1,000.01 more is refused and R1,000 still fits
    the R3,000 day exactly."""
    _store_rate("18.50")
    _store_rate("16.22", base_currency="ZAR", quote_currency="ZWL")
    seed_platform_accounts()
    sender, _recipient, beneficiary = _make_sender_and_beneficiary()
    account_repo = AccountRepository()
    sender_zar = account_repo.get_user_account(sender.id, CURRENCY_ZAR)
    account_repo.increase_balance(sender_zar.account_id, Decimal("10000"))
    db.session.commit()
    first = _quote(sender, beneficiary, "2000").quote_id
    over = _quote(sender, beneficiary, "1000.01").quote_id
    exact = _quote(sender, beneficiary, "1000").quote_id

    remittance_service.confirm_remittance(sender.id, first)
    with pytest.raises(LimitExceededError) as refused:
        remittance_service.confirm_remittance(sender.id, over)
    remittance_service.confirm_remittance(sender.id, exact)

    assert refused.value.detail == (
        "This would exceed your daily limit. You can send up to R 1,000.00 today."
    )
    # The refused quote is left as it was: active, with no legs.
    assert QuoteRepository().get_by_id(over).status == STATUS_ACTIVE
    assert _legs_for(over) == 0
    assert enqueued == [str(first), str(exact)]


def test_a_sender_no_longer_verified_cannot_confirm(app_context, enqueued):
    """Standing can change between quote and confirm — here a newer
    application now defines it — so confirming checks it again."""
    _store_rate("18.50")
    _store_rate("16.22", base_currency="ZAR", quote_currency="ZWL")
    seed_platform_accounts()
    sender, _recipient, beneficiary = _make_sender_and_beneficiary()
    quote_id = _fund_and_quote(sender, beneficiary, Decimal("1000")).quote_id
    insert_application(
        sender.id,
        status=KycStatus.REJECTED,
        created_at=datetime.now(UTC) + timedelta(seconds=1),
    )

    with pytest.raises(KycNotApprovedError):
        remittance_service.confirm_remittance(sender.id, quote_id)

    assert QuoteRepository().get_by_id(quote_id).status == STATUS_ACTIVE
    assert _legs_for(quote_id) == 0
    assert enqueued == []


def test_a_quote_issued_before_its_beneficiary_is_removed_still_confirms(
    app_context, enqueued
):
    """Quotes and remittances point at the recipient's user id, not the
    beneficiary row, so removing a beneficiary is a hard delete that leaves
    an issued quote, and the transfer it becomes, intact."""
    _store_rate("18.50")
    _store_rate("16.22", base_currency="ZAR", quote_currency="ZWL")
    seed_platform_accounts()
    sender, _recipient, beneficiary = _make_sender_and_beneficiary()
    quote = _fund_and_quote(sender, beneficiary, Decimal("1000"))

    BeneficiaryController().delete(sender.id, beneficiary.beneficiary_id)
    remittance = remittance_service.confirm_remittance(sender.id, quote.quote_id)

    assert QuoteRepository().get_by_id(quote.quote_id).status == STATUS_USED
    assert remittance.quote_id == quote.quote_id


def _dollar_sender_with_quotes(*amounts: str):
    """A tier-1 sender holding USD 1,000.00, with a quote to a ZWL
    beneficiary for each amount, priced at R18.50 to the dollar."""
    _store_rate("18.50")
    _store_rate("300.07", base_currency="USD", quote_currency="ZWL")
    seed_platform_accounts()
    sender, _recipient, beneficiary = _make_sender_and_beneficiary()
    accounts = AccountRepository()
    usd = accounts.get_or_create_user_account(sender.id, sender.base_reference, "USD")
    accounts.increase_balance(usd.account_id, Decimal("1000"))
    db.session.commit()
    quote_ids = [
        quote_service.create_quote(
            sender.id,
            beneficiary.beneficiary_id,
            Decimal(amount),
            sender_currency="USD",
            receiver_payout_currency="ZWL",
        ).quote_id
        for amount in amounts
    ]
    return sender, quote_ids


def test_confirming_counts_the_rand_value_the_quote_locked(app_context, enqueued):
    """A rate move after the quote changes nothing: USD 100.00 counts as the
    R1,850.00 locked at R18.50, not the R4,000.00 it would be at R40."""
    sender, (quote_id,) = _dollar_sender_with_quotes("100")
    _store_rate("40")

    remittance_service.confirm_remittance(sender.id, quote_id)

    standing = KycApplicationRepository().get_standing(sender.id)
    assert standing.daily_used_zar == Decimal("1850.00")


def test_a_dollar_confirm_refusal_estimates_at_the_quotes_rate(app_context, enqueued):
    """Two USD 100.00 quotes, R1,850.00 each: once one is sent, R1,150.00 is
    left, about USD 62.16 at the rate the refused quote locked."""
    sender, (first, second) = _dollar_sender_with_quotes("100", "100")
    remittance_service.confirm_remittance(sender.id, first)

    with pytest.raises(LimitExceededError) as refused:
        remittance_service.confirm_remittance(sender.id, second)

    assert refused.value.detail == (
        "This would exceed your daily limit. You can send up to R 1,150.00 "
        "(about USD 62.16) today."
    )
