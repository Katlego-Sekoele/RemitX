"""Remittance confirmation (Transaction_Flow_Context.md §2 Phase B2).

Turns an ACTIVE `Quote` into an actual send: four `pending` ledger legs
sharing one `quote_id`, the quote flipped to USED, then settlement enqueued
— never touches an account's `account_balance` itself (that only happens
once `remitx_worker.tasks.settle_remittance` confirms the group).
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
    TYPE_FEE,
    TYPE_REMITTANCE,
    Transaction,
)
from remitx_api.repositories.account_repository import AccountRepository
from remitx_api.repositories.quote_repository import QuoteRepository
from remitx_api.repositories.remittance_repository import RemittanceRepository
from remitx_api.repositories.transaction_repository import TransactionRepository
from remitx_api.services import queue_service

# The treasury leg is uctusd-only by construction — it's always the
# settlement token, never a fiat currency, so there's nothing to match here.
# The fiat bank and fee-revenue accounts are both looked up by the sender's
# actual currency instead (see `AccountRepository.get_platform_account`) —
# `scripts/seed_platform_accounts.py` seeds one `REMITX_FIAT`/`REMITX_REVENUE`
# pair per currency, so a non-ZAR sender, if that ever becomes reachable via
# `quote_service.create_quote`, still lands in the right pair rather than ZAR's.
REMITX_TREASURY_WALLET_LABEL = "RemitX XRPL Treasury Wallet"


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

    # Check the sender's available balance covers the quote's sender amount
    available = accounts.get_available_balance(quote.sender_account_id)
    if available < quote.sender_amount:
        # Revert the quote status back to ACTIVE if the balance is insufficient
        db.session.rollback()
        raise InsufficientBalanceError(
            f"available balance {available} is less than {quote.sender_amount}"
        )

    sender_token_account = accounts.get_user_account(sender_user_id, CURRENCY_TOKEN)
    fee_revenue_account = accounts.get_platform_account(
        TYPE_PLATFORM_REVENUE, quote.sender_currency
    )
    bank_account = accounts.get_platform_account(
        TYPE_PLATFORM_FIAT, quote.sender_currency
    )
    treasury_account = accounts.get_platform_account_by_label(
        REMITX_TREASURY_WALLET_LABEL
    )

    # Fee (+ margin) leg: sender's fiat currency account -> RemitX fee revenue.
    transactions.add(
        Transaction(
            type=TYPE_FEE,
            credit_account_id=quote.sender_account_id,
            debit_account_id=fee_revenue_account.account_id,
            amount=quote.sender_transaction_fee + quote.exchange_rate_margin,
            currency=quote.sender_currency,
            status=STATUS_PENDING,
            quote_id=quote.quote_id,
        )
    )
    # Net remittance leg: sender's fiat currency account -> RemitX bank account.
    transactions.add(
        Transaction(
            type=TYPE_REMITTANCE,
            credit_account_id=quote.sender_account_id,
            debit_account_id=bank_account.account_id,
            amount=quote.sender_amount
            - quote.sender_transaction_fee
            - quote.exchange_rate_margin,
            currency=quote.sender_currency,
            status=STATUS_PENDING,
            quote_id=quote.quote_id,
        )
    )
    # Pass-through leg: platform treasury -> sender's token account.
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
    settlement_leg = transactions.add(
        Transaction(
            type=TYPE_REMITTANCE,
            credit_account_id=sender_token_account.account_id,
            debit_account_id=quote.beneficiary_account_id,
            amount=quote.token_amount,
            currency=CURRENCY_TOKEN,
            status=STATUS_PENDING,
            quote_id=quote.quote_id,
        )
    )
    # TODO: figure out if the fiat amount should be shown on the
    # beneficiary's account as well as the token amount.
    remittance = remittances.add(
        Remittance(
            quote_id=quote.quote_id,
            tx_id=settlement_leg.tx_id,
            confirmed_by=sender_user_id,
        )
    )

    db.session.commit()

    # Enqueue only after the commit above — publishing inside the
    # transaction races the worker against a row it cannot yet read (same
    # rule integration_message_controller.py already documents).
    queue_service.enqueue_settle_remittance(str(quote.quote_id))

    return remittance
