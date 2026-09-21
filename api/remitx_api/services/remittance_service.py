"""Remittance confirmation (Transaction_Flow_Context.md §2 Phase B2).

Turns an ACTIVE `Quote` into an actual send: seven `pending` ledger legs
sharing one `quote_id`, the quote flipped to USED, then settlement enqueued
— never touches an account's `account_balance` itself. Nothing does, for any
of the seven, until `remitx_worker.tasks.confirm_treasury_burn` confirms and
credits them all together, once the treasury's on-chain burn (leg 6) has
resolved; `settle_remittance` and `burn_treasury_tokens` only hand off along
the way.

The beneficiary never holds a resting uctusd balance: their token account is
a momentary pass-through (legs 3-4 credit it then debit it straight back to
the treasury via leg 5), and the platform auto-converts straight to their
own local fiat currency (leg 7, the payout) — a deliberate deviation from
the brief's literal "recipient holds and views RLUSD, chooses when to cash
out" wording. Leg 6, the burn, returns that same amount from the treasury to
the UCTUSD issuer on-chain; nothing in this group confirms until it has (see
`remitx_worker.tasks.confirm_treasury_burn`).
"""

import uuid
from datetime import UTC, datetime

from remitx_api.extensions import db
from remitx_api.models.orm.account import (
    CURRENCY_TOKEN,
    TYPE_PLATFORM_FIAT,
    TYPE_PLATFORM_REVENUE,
)
from remitx_api.models.orm.remittance import Remittance
from remitx_api.models.orm.transaction import (
    STATUS_PENDING,
    TYPE_BENEFICIARY_PAYOUT,
    TYPE_FEE,
    TYPE_REMITTANCE,
    TYPE_TOKEN_BURN,
    Transaction,
)
from remitx_api.repositories.account_repository import AccountRepository
from remitx_api.repositories.quote_repository import QuoteRepository
from remitx_api.repositories.remittance_repository import RemittanceRepository
from remitx_api.repositories.transaction_repository import TransactionRepository
from remitx_api.repositories.user_repository import UserRepository
from remitx_api.services import queue_service

# The treasury leg is uctusd-only by construction — it's always the
# settlement token, never a fiat currency, so there's nothing to match here.
# The fiat bank and fee-revenue accounts are both looked up by the sender's
# actual currency instead (see `AccountRepository.get_platform_account`) —
# `scripts/seed_platform_accounts.py` seeds one `REMITX_FIAT`/`REMITX_REVENUE`
# pair per currency, so a non-ZAR sender, if that ever becomes reachable via
# `quote_service.create_quote`, still lands in the right pair rather than ZAR's.
REMITX_TREASURY_WALLET_LABEL = "RemitX XRPL Treasury Wallet"
UCTUSD_ISSUER_LABEL = "UCTUSD Issuer (Exchange)"


class QuoteNotFoundError(Exception):
    """`quote_id` doesn't exist, or doesn't belong to this sender — collapsed
    into one outcome so a caller can't tell "wrong id" from "someone else's
    id" apart, same as `quote_service.UnknownBeneficiaryError`."""


class QuoteNotActiveError(Exception):
    """The quote exists and is this sender's, but its state refuses
    confirmation — already used, or expired."""


class InsufficientBalanceError(Exception):
    """Sender's *available* balance can't cover the quote's `sender_amount`
    any more. Re-checked here (not just at quote-creation time) because
    confirmation is what actually creates the pending legs a *different*
    quote's own check would need to see (Open Question #5)."""


def confirm_remittance(sender_user_id: uuid.UUID, quote_id: uuid.UUID) -> Remittance:
    quotes = QuoteRepository()
    accounts = AccountRepository()
    transactions = TransactionRepository()
    remittances = RemittanceRepository()

    quote = quotes.get_for_sender(quote_id, sender_user_id)
    if quote is None:
        raise QuoteNotFoundError(str(quote_id))

    # Mark the quote as used
    now = datetime.now(UTC)
    if not quotes.mark_used(quote.quote_id, now):
        raise QuoteNotActiveError(str(quote_id))

    sender_account = accounts.get_user_account(
        quote.sender_user_id, quote.sender_currency
    )

    # Check the sender's available balance covers the quote's sender amount
    available = accounts.get_available_balance(sender_account.account_id)
    if available < quote.sender_amount:
        # Revert the quote status back to ACTIVE if the balance is insufficient
        db.session.rollback()
        raise InsufficientBalanceError(
            f"available balance {available} is less than {quote.sender_amount}"
        )

    sender_token_account = accounts.get_user_account(sender_user_id, CURRENCY_TOKEN)
    beneficiary_token_account = accounts.get_user_account(
        quote.beneficiary_user_id, CURRENCY_TOKEN
    )
    beneficiary_user = UserRepository().require_by_id(quote.beneficiary_user_id)
    beneficiary_fiat_account = accounts.get_or_create_user_account(
        beneficiary_user.id, beneficiary_user.base_reference, quote.receiver_currency
    )
    fee_revenue_account = accounts.get_platform_account(
        TYPE_PLATFORM_REVENUE, quote.sender_currency
    )
    bank_account = accounts.get_platform_account(
        TYPE_PLATFORM_FIAT, quote.sender_currency
    )
    beneficiary_bank_account = accounts.get_platform_account(
        TYPE_PLATFORM_FIAT, quote.receiver_currency
    )
    treasury_account = accounts.get_platform_account_by_label(
        REMITX_TREASURY_WALLET_LABEL
    )
    uctusd_issuer_account = accounts.get_platform_account_by_label(UCTUSD_ISSUER_LABEL)

    ### TRANSACTION LEGS ###
    # Fee (+ margin) leg: sender's fiat currency account -> RemitX fiat fee revenue.
    transactions.add(
        Transaction(
            type=TYPE_FEE,
            credit_account_id=sender_account.account_id,
            debit_account_id=fee_revenue_account.account_id,
            amount=quote.sender_transaction_fee + quote.exchange_rate_margin,
            currency=quote.sender_currency,
            status=STATUS_PENDING,
            quote_id=quote.quote_id,
        )
    )
    # Net remittance leg: sender's fiat currency account -> RemitX fiat bank account.
    transactions.add(
        Transaction(
            type=TYPE_REMITTANCE,
            credit_account_id=sender_account.account_id,
            debit_account_id=bank_account.account_id,
            amount=quote.sender_amount
            - quote.sender_transaction_fee
            - quote.exchange_rate_margin,
            currency=quote.sender_currency,
            status=STATUS_PENDING,
            quote_id=quote.quote_id,
        )
    )
    # Pass-through leg: platform treasury token account -> sender's token account.
    transactions.add(
        Transaction(
            type=TYPE_REMITTANCE,
            credit_account_id=treasury_account.account_id,
            debit_account_id=sender_token_account.account_id,
            amount=quote.token_amount,
            currency=CURRENCY_TOKEN,
            status=STATUS_PENDING,
            quote_id=quote.quote_id,
        )
    )
    # Settlement leg: sender's token account -> beneficiary's token account.
    transactions.add(
        Transaction(
            type=TYPE_REMITTANCE,
            credit_account_id=sender_token_account.account_id,
            debit_account_id=beneficiary_token_account.account_id,
            amount=quote.token_amount,
            currency=CURRENCY_TOKEN,
            status=STATUS_PENDING,
            quote_id=quote.quote_id,
        )
    )
    # Pass-through leg: beneficiary's token account -> platform treasury token account.
    # Completes the beneficiary's own pass-through (mirrors the sender's) —
    # they never hold a resting uctusd balance.
    transactions.add(
        Transaction(
            type=TYPE_REMITTANCE,
            credit_account_id=beneficiary_token_account.account_id,
            debit_account_id=treasury_account.account_id,
            amount=quote.token_amount,
            currency=CURRENCY_TOKEN,
            status=STATUS_PENDING,
            quote_id=quote.quote_id,
        )
    )
    # Burn leg: platform treasury token account -> UCTUSD issuer. Records the
    # on-chain burn (remitx_worker.tasks.burn_treasury_tokens) that returns
    # the beneficiary pass-through's tokens to the issuer, destroying them.
    # The payout leg below may not confirm until this one has, with an
    # xrpl_tx_hash recorded.
    transactions.add(
        Transaction(
            type=TYPE_TOKEN_BURN,
            credit_account_id=treasury_account.account_id,
            debit_account_id=uctusd_issuer_account.account_id,
            amount=quote.token_amount,
            currency=CURRENCY_TOKEN,
            status=STATUS_PENDING,
            quote_id=quote.quote_id,
        )
    )
    # Payout leg: RemitX fiat bank account in the beneficiary's country -> the
    # beneficiary's own fiat account. The final leg that represents whether
    # this remittance has actually reached the beneficiary. Its own type
    # (rather than TYPE_REMITTANCE) is what lets the worker confirm it on its
    # own, gated on the burn leg above.
    payout_leg = transactions.add(
        Transaction(
            type=TYPE_BENEFICIARY_PAYOUT,
            credit_account_id=beneficiary_bank_account.account_id,
            debit_account_id=beneficiary_fiat_account.account_id,
            amount=quote.receiver_amount,
            currency=quote.receiver_currency,
            status=STATUS_PENDING,
            quote_id=quote.quote_id,
        )
    )

    remittance = remittances.add(
        Remittance(
            quote_id=quote.quote_id,
            tx_id=payout_leg.tx_id,
        )
    )

    db.session.commit()

    # Enqueue only after the commit above — publishing inside the
    # transaction races the worker against a row it cannot yet read (same
    # rule integration_message_controller.py already documents).
    queue_service.enqueue_settle_remittance(str(quote.quote_id))

    return remittance
