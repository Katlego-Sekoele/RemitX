from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from remitx_api.config import Config
from remitx_api.controllers.beneficiary_controller import BeneficiaryController
from remitx_api.controllers.user_controller import UserController
from remitx_api.extensions import db
from remitx_api.models.orm.account import CURRENCY_TOKEN, CURRENCY_ZAR
from remitx_api.models.orm.exchange_rate import ExchangeRate
from remitx_api.models.orm.transaction import (
    STATUS_PENDING,
    TYPE_REMITTANCE,
    Transaction,
)
from remitx_api.models.orm.user import KYC_APPROVED
from remitx_api.repositories.account_repository import AccountRepository
from remitx_api.repositories.user_repository import UserRepository
from remitx_api.services import exchange_rate_service, quote_service
from remitx_api.services.exchange_rate_provider import RateFetchError


def _approve(user):
    user.kyc_status = KYC_APPROVED
    return UserRepository().save(user)


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
            "user_quote_sender", lambda: "sender@example.com", lambda: "Sender"
        )
    )
    recipient = UserController().ensure_provisioned(
        "user_quote_recipient", lambda: "recipient@example.com", lambda: "Recipient"
    )
    beneficiary, _linked_user = BeneficiaryController().create(
        sender_user_id=sender.id,
        linked_user_id=recipient.id,
        payout_currency="ZWL",
        relationship="sibling",
    )
    return sender, recipient, beneficiary


def test_create_quote_computes_every_field(app_context):
    _store_rate("18.50")  # sender leg: USD -> ZAR, needed for token math
    _store_rate("16.22", base_currency="ZAR", quote_currency="ZWL")  # direct cross leg
    sender, recipient, beneficiary = _make_sender_and_beneficiary()
    account_repo = AccountRepository()
    sender_zar = account_repo.get_user_account(sender.id, CURRENCY_ZAR)
    account_repo.increase_balance(sender_zar.account_id, Decimal("1000"))

    quote = quote_service.create_quote(
        sender.id, beneficiary.beneficiary_id, Decimal("1000")
    )

    # ZAR sender leg — FIXED_FEE_ZAR applies directly, no conversion needed.
    fee = Decimal("15") + Decimal("0.005") * Decimal("1000")  # 15 + 5 = 20
    margin = Decimal("0.01") * Decimal("1000")  # 10
    net = Decimal("1000") - fee - margin  # 970
    # Token units per 1 ZAR — the inverse of the stored ZAR/USD quote (see
    # quote_service._token_rate), quantized before use so token_amount is
    # computed by multiplying, not dividing.
    expected_rate = (Decimal("1") / Decimal("18.50")).quantize(Decimal("0.00000001"))
    expected_token_amount = (net * expected_rate).quantize(Decimal("0.00000001"))
    # receiver_amount/payout_fee/estimate are in the beneficiary's payout
    # currency (ZWL), converted directly from `net` via fiat_exchange_rate —
    # not routed through the token/USD leg.
    expected_receiver_amount = (net * Decimal("16.22")).quantize(Decimal("0.00000001"))
    expected_payout_fee = (Decimal("0.0075") * expected_receiver_amount).quantize(
        Decimal("0.00000001")
    )
    expected_payout_estimate = expected_receiver_amount - expected_payout_fee

    assert quote.sender_amount == Decimal("1000")
    assert quote.sender_currency == CURRENCY_ZAR
    assert quote.sender_transaction_fee == fee
    assert quote.exchange_rate_margin == margin
    assert quote.fiat_to_token_exchange_rate == expected_rate
    assert quote.token_amount == expected_token_amount
    assert quote.token_name == CURRENCY_TOKEN
    assert quote.status == "ACTIVE"
    # Direct fetch — the stored ZAR/ZWL row, not derived from the USD legs.
    assert quote.fiat_exchange_rate == Decimal("16.22")
    assert quote.receiver_currency == "ZWL"
    assert quote.receiver_amount == expected_receiver_amount
    assert quote.receiver_payout_fee == expected_payout_fee
    assert quote.receiver_payout_estimate == expected_payout_estimate
    assert (
        quote.beneficiary_account_id
        == account_repo.get_user_account(recipient.id, CURRENCY_TOKEN).account_id
    )


def test_direct_rate_unavailable_blocks_quote_creation(app_context, monkeypatch):
    """No direct ZAR/ZWL rate stored and the live provider fails — this rate
    doesn't feed settlement math, but a quote still can't be issued without
    it (per explicit product decision: no silent nulls). The sender leg
    (USD/ZAR) is already stored, so it never reaches the live provider —
    only the ZAR/ZWL lookup does.
    """
    _store_rate("18.50")
    sender, _recipient, beneficiary = _make_sender_and_beneficiary()
    account_repo = AccountRepository()
    sender_zar = account_repo.get_user_account(sender.id, CURRENCY_ZAR)
    account_repo.increase_balance(sender_zar.account_id, Decimal("1000"))

    def _fail(self, base, quote):
        raise RateFetchError("network unreachable")

    monkeypatch.setattr(
        "remitx_api.services.exchange_rate_provider.ExchangeRateApiProvider.get_rate",
        _fail,
    )

    with pytest.raises(exchange_rate_service.RateUnavailableError):
        quote_service.create_quote(
            sender.id, beneficiary.beneficiary_id, Decimal("1000")
        )


def test_fixed_fee_converts_into_a_non_zar_sender_currency(app_context):
    """FIXED_FEE_ZAR is ZAR-denominated; for a non-ZAR sender it must be
    converted via each currency's USD peg, not applied as a raw ZAR number
    or dropped entirely (Transaction_Flow_Context.md §8)."""
    _store_rate("18.50")  # USD -> ZAR peg, needed to convert the ZAR fixed fee
    # Direct leg for the (USD -> USD) preview currency — required now that
    # fiat_exchange_rate is never null, even when the currencies match.
    _store_rate("1", base_currency="USD", quote_currency="USD")

    pricing = quote_service.preview_quote(Decimal("100"), "USD", "USD")

    # Token units per 1 ZAR (see quote_service._token_rate).
    zar_rate = (Decimal("1") / Decimal("18.50")).quantize(Decimal("0.00000001"))
    fiat_to_token_exchange_rate = Decimal("1")  # USD short-circuits to 1
    expected_fixed_fee = (
        Decimal("15") * zar_rate / fiat_to_token_exchange_rate
    ).quantize(Decimal("0.00000001"))
    expected_fee = expected_fixed_fee + Decimal("0.005") * Decimal("100")
    margin = Decimal("0.01") * Decimal("100")
    net = Decimal("100") - expected_fee - margin
    expected_token_amount = (net * fiat_to_token_exchange_rate).quantize(
        Decimal("0.00000001")
    )

    assert pricing.sender_transaction_fee == expected_fee
    assert pricing.token_amount == expected_token_amount


def test_insufficient_available_balance_is_rejected_even_with_raw_balance_to_spare(
    app_context,
):
    """The actual double-spend fix (Open Question #5): a pending outgoing leg
    already committed against the sender's balance must count, even though
    the raw `account_balance` column hasn't moved yet.
    """
    _store_rate()
    sender, recipient, beneficiary = _make_sender_and_beneficiary()
    account_repo = AccountRepository()
    sender_zar = account_repo.get_user_account(sender.id, CURRENCY_ZAR)
    account_repo.increase_balance(sender_zar.account_id, Decimal("1000"))

    other_zar = account_repo.get_user_account(recipient.id, CURRENCY_ZAR)
    db.session.add(
        Transaction(
            type=TYPE_REMITTANCE,
            credit_account_id=sender_zar.account_id,
            debit_account_id=other_zar.account_id,
            amount=Decimal("900"),
            currency=CURRENCY_ZAR,
            status=STATUS_PENDING,
        )
    )
    db.session.commit()

    # Raw balance (1000) covers this, available balance (100) does not.
    with pytest.raises(quote_service.InsufficientBalanceError):
        quote_service.create_quote(
            sender.id, beneficiary.beneficiary_id, Decimal("500")
        )


def test_unverified_sender_is_rejected(app_context):
    _store_rate()
    sender = UserController().ensure_provisioned(
        "user_quote_unverified", lambda: "unverified@example.com", lambda: "Unverified"
    )
    recipient = UserController().ensure_provisioned(
        "user_quote_unverified_target", lambda: "target@example.com", lambda: "Target"
    )
    beneficiary, _linked_user = BeneficiaryController().create(
        sender_user_id=sender.id,
        linked_user_id=recipient.id,
        payout_currency="ZWL",
        relationship="friend",
    )

    with pytest.raises(quote_service.KycNotApprovedError):
        quote_service.create_quote(
            sender.id, beneficiary.beneficiary_id, Decimal("100")
        )


def test_amount_over_the_daily_ceiling_is_rejected(app_context):
    _store_rate()
    sender, recipient, beneficiary = _make_sender_and_beneficiary()
    account_repo = AccountRepository()
    sender_zar = account_repo.get_user_account(sender.id, CURRENCY_ZAR)
    account_repo.increase_balance(sender_zar.account_id, Config.DAILY_LIMIT_ZAR * 2)

    with pytest.raises(quote_service.LimitExceededError):
        quote_service.create_quote(
            sender.id,
            beneficiary.beneficiary_id,
            Config.DAILY_LIMIT_ZAR + Decimal("1"),
        )


def test_beneficiary_not_owned_by_caller_is_rejected(app_context):
    _store_rate()
    sender, _recipient, beneficiary = _make_sender_and_beneficiary()
    other_sender = _approve(
        UserController().ensure_provisioned(
            "user_quote_other_sender", lambda: "other@example.com", lambda: "Other"
        )
    )

    with pytest.raises(quote_service.UnknownBeneficiaryError):
        quote_service.create_quote(
            other_sender.id, beneficiary.beneficiary_id, Decimal("100")
        )


def test_quote_expires_fifteen_minutes_from_now(app_context):
    _store_rate()
    sender, _recipient, beneficiary = _make_sender_and_beneficiary()
    account_repo = AccountRepository()
    sender_zar = account_repo.get_user_account(sender.id, CURRENCY_ZAR)
    account_repo.increase_balance(sender_zar.account_id, Decimal("1000"))

    before = datetime.now(UTC)
    quote = quote_service.create_quote(
        sender.id, beneficiary.beneficiary_id, Decimal("100")
    )
    after = datetime.now(UTC)

    expires_at = quote.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)

    assert before + timedelta(minutes=15) <= expires_at <= after + timedelta(minutes=15)
