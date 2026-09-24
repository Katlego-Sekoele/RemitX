"""Quote generation

Two entry points share one pricing helper, `price_remittance`:

- `create_quote` — the real, beneficiary-bound flow. Produces a priced,
  time-boxed `Quote` row. Does not touch `transactions` or any account
  balance — nothing is spent until a remittance is confirmed against this
  quote. This is the main entry point for creating a quote, and it checks the
  balances/limits to decide whether a quote may be issued at all.
- `preview_quote` — a stateless "what would X currency become in Y
  currency" calculation with no beneficiary and nothing persisted, for
  browsing rates before picking (or without) a beneficiary contact.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from remitx_api.config import Config
from remitx_api.extensions import db
from remitx_api.models.orm.account import CURRENCY_TOKEN, CURRENCY_USD, CURRENCY_ZAR
from remitx_api.models.orm.quote import STATUS_ACTIVE, Quote
from remitx_api.repositories.account_repository import AccountRepository
from remitx_api.repositories.beneficiary_repository import BeneficiaryRepository
from remitx_api.repositories.kyc_application_repository import (
    KycApplicationRepository,
)
from remitx_api.repositories.user_repository import UserRepository
from remitx_api.services import exchange_rate_service

# Every monetary *amount* is quantized to this before it's stored or returned,
# so SQLite/Postgres can't disagree on the value and every leg agrees on
# what "the amount" is. Conversion *rates* (fiat_to_token_exchange_rate,
# fiat_exchange_rate) are deliberately not rounded this way — they still
# need their extra precision so multiplying by a large sender_amount
# doesn't itself introduce error.
AMOUNT_QUANTUM = Decimal("0.01")


def round_amount(value: Decimal) -> Decimal:
    return value.quantize(AMOUNT_QUANTUM, rounding=ROUND_HALF_UP)


# Custom exceptions for quote creation.
class KycNotApprovedError(Exception):
    """Sender's KYC standing isn't verified — brief: "Only approved users may
    send remittances." A sender who never verified, or whose verification
    was rejected, is turned away outright, never just limited. Standing is
    derived from `kyc_applications` (KycApplicationRepository.get_standing),
    not stored on `User` — see models/orm/user.py."""


class LimitExceededError(Exception):
    """`sender_amount` alone exceeds the sender's tier ceiling.

    This is a SIMPLIFIED check: it compares the requested amount against
    Config.DAILY_LIMIT_ZAR directly, not a true running daily/monthly total, because
    no `remittances` table exists yet to sum actual confirmed sends against
    (Transaction_Flow_Context.md §7/§8). Revisit once remittances exist.
    """


class UnknownBeneficiaryError(Exception):
    """`beneficiary_id` doesn't exist, or doesn't belong to this sender."""


class UnknownSenderAccountError(Exception):
    """Sender has no account in the requested `sender_currency`. Only ZAR
    and uctusd are created eagerly at signup (Transaction_Flow_Context.md
    §7), so any other sender_currency legitimately has no account yet —
    this is a real, reachable outcome, not a defensive check."""


class InsufficientBalanceError(Exception):
    """Sender's *available* balance (raw minus their own pending outgoing
    legs — Open Question #5) can't cover `sender_amount`."""


@dataclass
class RemittancePricing:
    """Exists to let `price_remittance` be shared between `create_quote` and
    `preview_quote`, which need the same math but not the same data."""

    sender_currency: str
    sender_transaction_fee: Decimal
    exchange_rate_margin: Decimal
    token_amount: Decimal
    token_name: str
    # Required: token units per 1 sender_currency (multiply, not divide, to
    # get token_amount — see _token_rate). Id is None only when
    # sender_currency == CURRENCY_USD (no ExchangeRate row to reference).
    fiat_to_token_exchange_rate_id: uuid.UUID | None
    fiat_to_token_exchange_rate: Decimal
    # Required: the direct sender_currency -> receiver_payout_currency rate,
    # always backed by a real ExchangeRate row (even when sender_currency ==
    # receiver_payout_currency). Doesn't feed settlement math (token_amount),
    # but a quote can't be issued without it — RateUnavailableError
    # propagates rather than silently omitting it.
    fiat_exchange_rate_id: uuid.UUID
    fiat_exchange_rate: Decimal
    receiver_payout_currency: str
    # The real cash-out estimate, in receiver_payout_currency: net converted
    # directly via fiat_exchange_rate (not routed through the token leg),
    # then Config.CASH_OUT_FEE_RATE applied. No real cash-out flow exists yet (see
    # models/orm/quote.py) — this is a display estimate only.
    receiver_amount: Decimal
    receiver_payout_fee: Decimal
    receiver_payout_estimate: Decimal


def _token_rate(currency: str) -> tuple[Decimal, uuid.UUID | None]:
    """(rate, fiat_to_token_exchange_rate_id): units of token (uctusd/RLUSD,
    pegged 1:1 to USD) per 1 unit of `currency` — i.e. the inverse of
    `currency`'s USD quote, so callers compute token_amount by multiplying
    (`amount * rate`), not dividing. Required, not best-effort — (1, None)
    for USD, otherwise defers to exchange_rate_service.get_active_rate and
    lets its errors propagate. Inverted and quantized here (not left to the
    Numeric(20,8) column) so SQLite/Postgres can't disagree on the stored
    value.
    """
    if currency == CURRENCY_USD:
        # USD peg, no ExchangeRate row to reference.
        return Decimal("1"), None
    rate = exchange_rate_service.get_active_rate(
        base_currency=CURRENCY_USD, quote_currency=currency
    )
    return (Decimal("1") / rate.rate).quantize(Decimal("0.00000001")), rate.id


def _direct_fiat_rate(
    base_currency: str, quote_currency: str
) -> tuple[Decimal, uuid.UUID]:
    """(rate, fiat_exchange_rate_id): a direct base<->quote fetch, for
    display (sender currency -> payout currency).
    """
    rate = exchange_rate_service.get_active_rate(
        base_currency=base_currency, quote_currency=quote_currency
    )
    return rate.rate, rate.id


def _convert_zar_fee_to_sender_currency(
    fee_zar: Decimal, sender_currency: str, fiat_to_token_exchange_rate: Decimal
) -> Decimal:
    """Convert a ZAR-denominated fee (e.g. Config.FIXED_FEE_ZAR) into sender_currency
    units via each currency's USD/token peg (see _token_rate) — reuses the
    sender leg's already-fetched rate rather than looking it up twice, and
    only fetches ZAR's rate when actually needed. 1:1, no extra lookup, when
    sender_currency is already ZAR (resolves Transaction_Flow_Context.md
    §8's currency-generality gap).
    """
    if sender_currency == CURRENCY_ZAR:
        return fee_zar
    zar_rate, _ = _token_rate(CURRENCY_ZAR)
    return round_amount(fee_zar * zar_rate / fiat_to_token_exchange_rate)


def price_remittance(
    sender_amount: Decimal, sender_currency: str, receiver_payout_currency: str
) -> RemittancePricing:
    if sender_amount <= 0:
        raise ValueError("sender_amount must be positive")
    # Round the input itself, not just what's derived from it — a caller
    # sending e.g. 1000.456 shouldn't leave that extra precision alive in
    # net/fee/token_amount below.
    sender_amount = round_amount(sender_amount)

    # Required — the sender leg is what token_amount is actually computed
    # from, so RateUnavailableError/UnsupportedCurrencyError propagate.
    fiat_to_token_exchange_rate, fiat_to_token_exchange_rate_id = _token_rate(
        sender_currency
    )

    fixed_fee = _convert_zar_fee_to_sender_currency(
        Config.FIXED_FEE_ZAR, sender_currency, fiat_to_token_exchange_rate
    )
    fee = round_amount(fixed_fee + Config.PERCENTAGE_FEE_RATE * sender_amount)
    margin = round_amount(Config.FX_MARGIN_RATE * sender_amount)
    net = sender_amount - fee - margin
    if net <= 0:
        raise ValueError("sender_amount is too small to cover fees")
    # Quantized explicitly rather than relying on the column's Numeric(20,8)
    # to truncate on storage — SQLite doesn't enforce that the way Postgres
    # does, so the two backends could otherwise disagree.
    token_amount = round_amount(net * fiat_to_token_exchange_rate)

    # Direct fiat conversion leg — sender currency straight to the
    # beneficiary's payout currency (e.g. ZAR -> ZWL), not derived from two
    # separate USD-relative rates. Doesn't feed settlement math (token_amount
    # above), but is required: unavailability raises rather than being
    # silently omitted.
    fiat_exchange_rate, fiat_exchange_rate_id = _direct_fiat_rate(
        sender_currency, receiver_payout_currency
    )

    # Real cash-out estimate, in receiver_payout_currency: net (post-fee,
    # pre-token-conversion) converted directly via fiat_exchange_rate — not
    # routed through the token/USD leg — then Config.CASH_OUT_FEE_RATE applied. No
    # real redemption happens at quote time, so this is a display estimate.
    receiver_amount = round_amount(net * fiat_exchange_rate)
    payout_fee = round_amount(Config.CASH_OUT_FEE_RATE * receiver_amount)
    payout_estimate = receiver_amount - payout_fee

    return RemittancePricing(
        sender_currency=sender_currency,
        sender_transaction_fee=fee,
        exchange_rate_margin=margin,
        token_amount=token_amount,
        token_name=CURRENCY_TOKEN,
        fiat_to_token_exchange_rate_id=fiat_to_token_exchange_rate_id,
        fiat_to_token_exchange_rate=fiat_to_token_exchange_rate,
        fiat_exchange_rate_id=fiat_exchange_rate_id,
        fiat_exchange_rate=fiat_exchange_rate,
        receiver_payout_currency=receiver_payout_currency,
        receiver_amount=receiver_amount,
        receiver_payout_fee=payout_fee,
        receiver_payout_estimate=payout_estimate,
    )


def create_quote(
    sender_user_id: uuid.UUID,
    beneficiary_id: uuid.UUID,
    sender_amount: Decimal,
    sender_currency: str,
    receiver_payout_currency: str,
) -> Quote:
    users = UserRepository()
    accounts = AccountRepository()
    beneficiaries = BeneficiaryRepository()

    # Rounded up front so the limit/balance checks below, the stored
    # Quote.sender_amount, and price_remittance's own internal rounding all
    # agree on the same value — see AMOUNT_QUANTUM.
    sender_amount = round_amount(sender_amount)

    sender = users.get_by_id(sender_user_id)
    if sender is None:
        raise ValueError(f"User {sender_user_id} does not exist")
    if not KycApplicationRepository().get_standing(sender_user_id).is_verified:
        raise KycNotApprovedError(str(sender_user_id))

    # Simplified ceiling check — see LimitExceededError.
    if sender_amount > Config.DAILY_LIMIT_ZAR:
        raise LimitExceededError(
            f"{sender_amount} exceeds the daily limit of {Config.DAILY_LIMIT_ZAR}"
        )
    # Get the beneficiary and check that it belongs to this sender. The
    # beneficiary's linked_user_id is the one who will receive the remittance.
    beneficiary = beneficiaries.get_by_id(beneficiary_id)
    if beneficiary is None or beneficiary.sender_user_id != sender_user_id:
        raise UnknownBeneficiaryError(str(beneficiary_id))

    sender_account = accounts.get_user_account(sender_user_id, sender_currency)
    if sender_account is None:
        raise UnknownSenderAccountError(
            f"sender {sender_user_id} has no account in {sender_currency}"
        )
    # Get the beneficiary's token account — the remittance is settled in
    # the USD-pegged token, not the payout currency, so we need to check
    # that the beneficiary has a token account to receive it.
    beneficiary_token_account = accounts.get_user_account(
        beneficiary.linked_user_id, CURRENCY_TOKEN
    )
    if beneficiary_token_account is None:
        # Should never happen post-eager-creation — defensive, not a normal
        # path. Unlike sender_account above, every user gets a uctusd
        # account at signup regardless of sender_currency.
        raise ValueError("beneficiary is missing their uctusd account")

    # Check the sender's available balance
    available = accounts.get_available_balance(sender_account.account_id)
    if available < sender_amount:
        raise InsufficientBalanceError(
            f"available balance {available} is less than {sender_amount}"
        )
    # Price the remittance
    pricing = price_remittance(sender_amount, sender_currency, receiver_payout_currency)

    now = datetime.now(UTC)
    quote = Quote(
        sender_user_id=sender_user_id,
        beneficiary_user_id=beneficiary.linked_user_id,
        sender_amount=sender_amount,
        sender_currency=pricing.sender_currency,
        sender_transaction_fee=pricing.sender_transaction_fee,
        token_amount=pricing.token_amount,
        token_name=pricing.token_name,
        fiat_to_token_exchange_rate_id=pricing.fiat_to_token_exchange_rate_id,
        fiat_to_token_exchange_rate=pricing.fiat_to_token_exchange_rate,
        fiat_exchange_rate_id=pricing.fiat_exchange_rate_id,
        fiat_exchange_rate=pricing.fiat_exchange_rate,
        exchange_rate_margin=pricing.exchange_rate_margin,
        receiver_amount=pricing.receiver_amount,
        receiver_currency=pricing.receiver_payout_currency,
        receiver_payout_fee=pricing.receiver_payout_fee,
        receiver_payout_estimate=pricing.receiver_payout_estimate,
        created_at=now,
        expires_at=now + timedelta(minutes=Config.QUOTE_TTL_MINUTES),
        status=STATUS_ACTIVE,
    )
    db.session.add(quote)
    db.session.commit()
    return quote


def preview_quote(
    sender_amount: Decimal, sender_currency: str, receiver_payout_currency: str
) -> RemittancePricing:
    """Stateless rate preview — no beneficiary, no sender context, nothing
    persisted. Unlike `create_quote`, doesn't check KYC/balance/limits:
    there's no real sender committed to anything here."""
    return price_remittance(sender_amount, sender_currency, receiver_payout_currency)
