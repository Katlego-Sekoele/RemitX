"""Remittance confirmation.

Uses an active ACTIVE `Quote` to initiate an actual remittance send: seven
`pending` ledger legs sharing one `quote_id`, the quote is flipped to USED,
then settlement is enqueued. Confirming is the real gate for who may send and
how much (services/send_limits.py): the sender must still be verified, and the
quote must fit what is left of their daily and monthly allowance now, not when
it was issued. For each of the seven transactions,
`remitx_worker.tasks.confirm_treasury_burn` confirms and credits them all
together, once the treasury's on-chain burn (leg 6) has resolved;
`settle_remittance` and `burn_treasury_tokens` only hand off along the way.

The beneficiary never holds a resting uctusd balance: their token account is
a momentary pass-through (legs 3-4 credit it then debit it straight back to
the treasury via leg 5), and the platform auto-converts straight to their
own local fiat currency (leg 7, the payout). Leg 6, the burn, returns
that same amount from the treasury to the Token issuer on-chain.
"""

import logging
import uuid
from datetime import UTC, datetime

from remitx_api.config import Config
from remitx_api.errors.base import DomainError
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
from remitx_api.repositories.kyc_application_repository import (
    KycApplicationRepository,
)
from remitx_api.repositories.quote_repository import QuoteRepository
from remitx_api.repositories.remittance_repository import RemittanceRepository
from remitx_api.repositories.transaction_repository import TransactionRepository
from remitx_api.repositories.user_repository import UserRepository
from remitx_api.services import queue_service
from remitx_api.services.quote_service import UnknownBeneficiaryPayoutAccountError
from remitx_api.services.send_limits import require_can_send

logger = logging.getLogger(__name__)

REMITX_TREASURY_WALLET_LABEL = "RemitX XRPL Treasury Wallet"
# Sourced from Config rather than hardcoded.
TOKEN_ISSUER_LABEL = Config().UCTUSD_ISSUER_LABEL


class QuoteNotFoundError(Exception):
    """`quote_id` doesn't exist, or doesn't belong to this sender — collapsed
    into one outcome so a caller can't tell "wrong id" from "someone else's
    id" apart, same as `quote_service.UnknownBeneficiaryError`."""


class QuoteNotActiveError(Exception):
    """The quote exists and is this sender's, but its state refuses
    confirmation — already used, or expired."""


class InsufficientBalanceError(Exception):
    """Sender's *available* balance can't cover the quote's `sender_amount`
    any more."""


def confirm_remittance(sender_user_id: uuid.UUID, quote_id: uuid.UUID) -> Remittance:
    quotes = QuoteRepository()
    accounts = AccountRepository()
    transactions = TransactionRepository()
    remittances = RemittanceRepository()

    # Held until the commit below. The limit check reads what this sender has
    # already sent, so their next confirm waits here until this one has
    # inserted its legs (or rolled back) instead of reading the same total.
    UserRepository().lock(sender_user_id)

    quote = quotes.get_for_sender(quote_id, sender_user_id)
    if quote is None:
        logger.info(
            "confirm_remittance: quote %s not found for sender %s",
            quote_id,
            sender_user_id,
        )
        raise QuoteNotFoundError(str(quote_id))

    # Mark the quote as used
    now = datetime.now(UTC)
    if not quotes.mark_used(quote.quote_id, now):
        logger.info(
            "confirm_remittance: quote %s is no longer active (used or expired)",
            quote_id,
        )
        raise QuoteNotActiveError(str(quote_id))

    # Checked again, not trusted from the quote: standing can change after a
    # quote is issued, and several quotes can be issued against one allowance.
    # The send counts at the rand value the quote locked, so a rate move since
    # changes nothing.
    try:
        require_can_send(
            KycApplicationRepository().get_standing(sender_user_id),
            quote.value_zar,
            amount=quote.sender_amount,
            currency=quote.sender_currency,
        )
    except DomainError as exc:
        # Revert the quote status back to ACTIVE, as for a short balance below
        db.session.rollback()
        logger.info(
            "confirm_remittance: sender %s refused for quote %s: %s; quote "
            "reverted to ACTIVE",
            sender_user_id,
            quote_id,
            exc.detail,
        )
        raise

    sender_account = accounts.get_user_account(
        quote.sender_user_id, quote.sender_currency
    )

    available = accounts.get_available_balance_locked(sender_account.account_id)
    if available < quote.sender_amount:
        # Revert the quote status back to ACTIVE if the balance is insufficient
        db.session.rollback()
        logger.info(
            "confirm_remittance: sender %s available balance %s < quote %s "
            "amount %s, quote reverted to ACTIVE",
            sender_user_id,
            available,
            quote_id,
            quote.sender_amount,
        )
        raise InsufficientBalanceError(
            f"available balance {available} is less than {quote.sender_amount}"
        )

    sender_token_account = accounts.get_user_account(sender_user_id, CURRENCY_TOKEN)
    beneficiary_token_account = accounts.get_user_account(
        quote.beneficiary_user_id, CURRENCY_TOKEN
    )
    beneficiary_fiat_account = accounts.get_user_account(
        quote.beneficiary_user_id, quote.receiver_currency
    )
    if beneficiary_fiat_account is None:
        db.session.rollback()
        logger.info(
            "confirm_remittance: beneficiary %s has no %s account for quote %s; "
            "quote reverted to ACTIVE",
            quote.beneficiary_user_id,
            quote.receiver_currency,
            quote_id,
        )
        raise UnknownBeneficiaryPayoutAccountError(
            f"beneficiary has no account in {quote.receiver_currency}"
        )
    RemitX_fee_revenue_account = accounts.get_platform_account(
        TYPE_PLATFORM_REVENUE, quote.sender_currency
    )
    RemitX_debited_bank_account = accounts.get_platform_account(
        TYPE_PLATFORM_FIAT, quote.sender_currency
    )
    RemitX_credited_bank_account = accounts.get_platform_account(
        TYPE_PLATFORM_FIAT, quote.receiver_currency
    )
    RemitX_treasury_account = accounts.get_platform_account_by_label(
        REMITX_TREASURY_WALLET_LABEL
    )
    token_issuer_account = accounts.get_platform_account_by_label(TOKEN_ISSUER_LABEL)

    ### --- TRANSACTION LEGS --- ###
    # Fee (+ margin) leg: sender's fiat currency account -> RemitX fiat fee revenue.
    transactions.add(
        Transaction(
            type=TYPE_FEE,  # Transation type
            # Money leaving the sender's account
            credit_account_id=sender_account.account_id,
            # Money going to RemitX's fee revenue account
            debit_account_id=RemitX_fee_revenue_account.account_id,
            # fee + margin fee
            amount=quote.sender_transaction_fee + quote.exchange_rate_margin,
            currency=quote.sender_currency,
            # Only confirmed once the beneficiary payout leg has confirmed
            status=STATUS_PENDING,
            quote_id=quote.quote_id,
        )
    )
    # Net remittance leg: sender's fiat currency account -> RemitX fiat bank account.
    transactions.add(
        Transaction(
            type=TYPE_REMITTANCE,
            credit_account_id=sender_account.account_id,
            debit_account_id=RemitX_debited_bank_account.account_id,
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
            # tokens leaving the treasury
            credit_account_id=RemitX_treasury_account.account_id,
            # tokens going to the sender's token account
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
            debit_account_id=beneficiary_token_account.account_id,
            amount=quote.token_amount,
            currency=CURRENCY_TOKEN,
            status=STATUS_PENDING,
            quote_id=quote.quote_id,
        )
    )
    # Conversion leg: beneficiary's token account -> platform treasury token account.
    # receiver never holds a resting uctusd balance.
    transactions.add(
        Transaction(
            type=TYPE_REMITTANCE,
            credit_account_id=beneficiary_token_account.account_id,
            debit_account_id=RemitX_treasury_account.account_id,
            amount=quote.token_amount,
            currency=CURRENCY_TOKEN,
            status=STATUS_PENDING,
            quote_id=quote.quote_id,
        )
    )
    # Burn leg: platform treasury token account -> token issuer. Records the
    # on-chain burn (remitx_worker.tasks.burn_treasury_tokens) that returns
    # the beneficiary pass-through's tokens to the issuer, destroying them.
    # The payout leg below may not confirm until this one has, with an
    # xrpl_tx_hash recorded.
    transactions.add(
        Transaction(
            type=TYPE_TOKEN_BURN,
            credit_account_id=RemitX_treasury_account.account_id,
            debit_account_id=token_issuer_account.account_id,
            amount=quote.token_amount,
            currency=CURRENCY_TOKEN,
            status=STATUS_PENDING,
            quote_id=quote.quote_id,
        )
    )
    # Payout leg: RemitX fiat bank account in the beneficiary's country -> the
    # beneficiary's own fiat currency account. The final leg that represents whether
    # this remittance has actually reached the beneficiary. Its own type
    # (rather than TYPE_REMITTANCE) is what lets the worker confirm it on its
    # own, gated on the burn leg above.
    transactions.add(
        Transaction(
            type=TYPE_BENEFICIARY_PAYOUT,
            # Fiat leaving RemitX's bank account in the beneficiary's country
            credit_account_id=RemitX_credited_bank_account.account_id,
            # Fiat going to the beneficiary's own fiat account
            debit_account_id=beneficiary_fiat_account.account_id,
            # Gross amount the beneficiary receives in their own currency
            amount=quote.receiver_amount,
            currency=quote.receiver_currency,
            status=STATUS_PENDING,
            quote_id=quote.quote_id,
        )
    )
    remittance = remittances.add(
        Remittance(
            quote_id=quote.quote_id,
            tx_id=settlement_leg.tx_id,
        )
    )

    # commit the quote flip, the seven pending legs, and the remittance record
    db.session.commit()

    # Enqueue only after the commit above. The seven legs are already
    # committed as `pending` at this point — if this enqueue is lost, the
    # remittance sits pending forever with nothing to drive it forward, so
    # a failure here is logged loudly before propagating rather than left to
    # a bare stack trace.
    try:
        queue_service.enqueue_settle_remittance(str(quote.quote_id))
    except Exception:
        logger.exception(
            "confirm_remittance: failed to enqueue settle_remittance for "
            "quote %s (remittance %s) — legs are committed pending but "
            "settlement was never queued",
            quote.quote_id,
            remittance.remittance_id,
        )
        raise

    return remittance  # return the remittance record
