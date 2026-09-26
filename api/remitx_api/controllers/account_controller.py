import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from remitx_api.errors.accounts import KycNotApprovedToOpenAccountError
from remitx_api.models.orm.account import (
    CURRENCY_TOKEN,
    CURRENCY_ZAR,
    TYPE_EXTERNAL,
    TYPE_PLATFORM_FIAT,
    TYPE_PLATFORM_REVENUE,
    TYPE_USER,
    TYPE_XRPL_WALLET,
    Account,
)
from remitx_api.models.orm.quote import Quote
from remitx_api.models.orm.transaction import (
    STATUS_CONFIRMED,
    TYPE_BENEFICIARY_PAYOUT,
    TYPE_DEPOSIT,
    TYPE_FEE,
    TYPE_REMITTANCE,
    TYPE_WITHDRAWAL,
    Transaction,
)
from remitx_api.models.orm.user import short_display_name
from remitx_api.repositories.account_repository import AccountRepository
from remitx_api.repositories.kyc_application_repository import KycApplicationRepository
from remitx_api.repositories.quote_repository import QuoteRepository
from remitx_api.repositories.remittance_repository import RemittanceRepository
from remitx_api.repositories.transaction_repository import TransactionRepository
from remitx_api.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)

DIRECTION_IN = "in"
DIRECTION_OUT = "out"

# What an account is for, so a client can tell the settlement token's wallet
# apart from a spendable currency account without hard-coding the token name.
KIND_FIAT = "fiat"
KIND_SETTLEMENT = "settlement"

DEFAULT_HISTORY_LIMIT = 50
MAX_HISTORY_LIMIT = 200

# Amounts leave the API at 2 dp, the same quantum quote_service stores them at.
AMOUNT_QUANTUM = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    return value.quantize(AMOUNT_QUANTUM, rounding=ROUND_HALF_UP)


def account_kind(currency: str) -> str:
    return KIND_SETTLEMENT if currency == CURRENCY_TOKEN else KIND_FIAT


def _display_order(account: Account) -> tuple[int, str]:
    """ZAR first, then the other fiat currencies alphabetically, then the
    settlement token's wallet last."""
    if account.account_currency == CURRENCY_ZAR:
        return (0, "")
    if account.account_currency == CURRENCY_TOKEN:
        return (2, "")
    return (1, account.account_currency)


# Platform accounts read in the order money moves through them: bank accounts,
# the fees earned against them, the treasury wallet, then the issuer it is
# funded from and burns back to.
_PLATFORM_TYPE_ORDER = (
    TYPE_PLATFORM_FIAT,
    TYPE_PLATFORM_REVENUE,
    TYPE_XRPL_WALLET,
    TYPE_EXTERNAL,
)


def _platform_display_order(account: Account) -> tuple[int, tuple[int, str], str]:
    """By type (see `_PLATFORM_TYPE_ORDER`), then currency the same way as a
    customer's accounts (ZAR first), then label."""
    return (
        _PLATFORM_TYPE_ORDER.index(account.type),
        _display_order(account),
        account.label,
    )


class UnknownAccountError(Exception):
    """`account_id` doesn't exist, or doesn't belong to this caller —
    collapsed into one outcome so a caller can't tell the two apart, same as
    `quote_service.UnknownBeneficiaryError`."""


@dataclass(frozen=True)
class TreasuryCoverageView:
    """Token the house wallet can still spend, against token customers hold."""

    token_available: Decimal
    customer_token_balances: Decimal


@dataclass(frozen=True)
class AccountView:
    account_id: uuid.UUID
    currency: str
    reference: str
    kind: str
    # The ledger balance. `available_balance` nets out this account's own
    # in-flight outgoing legs, so the difference is what's still pending.
    balance: Decimal
    available_balance: Decimal


@dataclass(frozen=True)
class PlatformAccountView:
    account_id: uuid.UUID
    label: str
    type: str
    currency: str
    kind: str
    # Platform balances can be negative: the issuer's is what it has paid in
    # to the treasury wallet, net of burns.
    balance: Decimal
    available_balance: Decimal


@dataclass(frozen=True)
class AccountTransactionView:
    tx_id: uuid.UUID
    type: str
    direction: str
    amount: Decimal
    currency: str
    status: str
    created_at: datetime
    confirmed_at: datetime | None
    # What the leg was, from this account's owner's point of view.
    description: str
    # The other customer in a transfer; None off a transfer, or when that
    # person has no name on file.
    counterparty_name: str | None
    remittance_id: uuid.UUID | None
    # The transfer's burn hash on the XRPL Testnet, on every leg of a
    # confirmed transfer.
    xrpl_tx_hash: str | None


@dataclass(frozen=True)
class _Transfer:
    """What every leg of one transfer shares, looked up once per page."""

    quote: Quote
    # True when this account's owner sent the transfer, False when they
    # received it.
    sent: bool
    counterparty_name: str | None
    remittance_id: uuid.UUID | None
    xrpl_tx_hash: str | None


def describe_leg(
    leg_type: str,
    direction: str,
    kind: str,
    transfer: _Transfer | None,
) -> str:
    """A plain-language label for one leg, as its account's owner sees it.

    A transfer puts two legs (fee and net) on the sender's fiat account, an
    in-and-out pair on each party's settlement wallet, and a payout on the
    recipient's fiat account; each reads as what it did for that person.
    """
    if leg_type == TYPE_DEPOSIT:
        return "Deposit"
    if leg_type == TYPE_WITHDRAWAL:
        return "Withdrawal"
    if leg_type == TYPE_FEE:
        return "Transfer fee"
    if transfer is None:
        return leg_type.replace("_", " ").capitalize()

    name = transfer.counterparty_name
    sent_to = f"Sent to {name}" if name else "Sent to a recipient"
    received_from = f"Received from {name}" if name else "Received from a sender"

    if leg_type == TYPE_BENEFICIARY_PAYOUT:
        return received_from if name else "Payout"
    if leg_type != TYPE_REMITTANCE:
        return leg_type.replace("_", " ").capitalize()
    if kind == KIND_FIAT:
        return sent_to
    # The settlement wallet: the sender's is funded from their fiat and pays
    # the recipient's, which is converted straight into their payout currency.
    if transfer.sent:
        if direction == DIRECTION_IN:
            return f"Converted from {transfer.quote.sender_currency}"
        return sent_to
    if direction == DIRECTION_IN:
        return received_from
    return f"Converted to {transfer.quote.receiver_currency}"


class AccountController:
    def __init__(self) -> None:
        self._accounts = AccountRepository()
        self._applications = KycApplicationRepository()
        self._transactions = TransactionRepository()
        self._quotes = QuoteRepository()
        self._remittances = RemittanceRepository()
        self._users = UserRepository()

    def open_account(self, user_id: uuid.UUID, currency: str) -> AccountView:
        """Open a fiat payout account the caller does not hold yet."""
        standing = self._applications.get_standing(user_id)
        if not standing.is_verified:
            raise KycNotApprovedToOpenAccountError()

        user = self._users.get_by_id(user_id)
        if user is None:
            raise ValueError(f"User {user_id} does not exist")

        account = self._accounts.open_user_account(
            user_id, user.base_reference, currency
        )
        return AccountView(
            account_id=account.account_id,
            currency=account.account_currency,
            reference=account.reference,
            kind=account_kind(account.account_currency),
            balance=_money(account.account_balance),
            available_balance=_money(
                self._accounts.get_available_balance(account.account_id)
            ),
        )

    def get_accounts(self, user_id: uuid.UUID) -> list[AccountView]:
        """Every currency account the caller holds: ZAR and uctusd from
        signup, plus any payout currency received since. Returns whatever
        `AccountRepository.list_user_accounts` finds rather than assuming
        exactly those, in display order (see `_display_order`)."""
        accounts = sorted(
            self._accounts.list_user_accounts(user_id), key=_display_order
        )
        return [
            AccountView(
                account_id=account.account_id,
                currency=account.account_currency,
                reference=account.reference,
                kind=account_kind(account.account_currency),
                balance=_money(account.account_balance),
                available_balance=_money(
                    self._accounts.get_available_balance(account.account_id)
                ),
            )
            for account in accounts
        ]

    def get_platform_accounts(self) -> list[PlatformAccountView]:
        """Every account RemitX holds or settles against, for treasury staff,
        in display order (see `_platform_display_order`)."""
        accounts = sorted(
            self._accounts.list_platform_accounts(), key=_platform_display_order
        )
        return [
            PlatformAccountView(
                account_id=account.account_id,
                label=account.label,
                type=account.type,
                currency=account.account_currency,
                kind=account_kind(account.account_currency),
                balance=_money(account.account_balance),
                available_balance=_money(
                    self._accounts.get_available_balance(account.account_id)
                ),
            )
            for account in accounts
        ]

    def get_treasury_coverage(self) -> TreasuryCoverageView:
        """Available token on the treasury wallet against customer token balances.

        Coverage is what settlement can still pay out. Customer balances are
        ledger balances, including token already credited and not yet withdrawn.
        """
        wallets = [
            account
            for account in self._accounts.list_platform_accounts()
            if account.type == TYPE_XRPL_WALLET
            and account.account_currency == CURRENCY_TOKEN
        ]
        available = sum(
            (
                self._accounts.get_available_balance(wallet.account_id)
                for wallet in wallets
            ),
            Decimal("0"),
        )
        owed = self._accounts.sum_user_balances(CURRENCY_TOKEN)
        return TreasuryCoverageView(
            token_available=_money(available),
            customer_token_balances=_money(owed),
        )

    def get_account_history(
        self,
        user_id: uuid.UUID,
        account_id: uuid.UUID,
        limit: int = DEFAULT_HISTORY_LIMIT,
        before: datetime | None = None,
    ) -> list[AccountTransactionView]:
        """One page of an account's legs, newest first, each described from
        the owner's side. `before` is the previous page's last `created_at`.
        """
        account = self._accounts.get_by_id(account_id)
        if account is None or account.type != TYPE_USER or account.user_id != user_id:
            logger.warning(
                "get_account_history: account %s not found or not owned by user %s",
                account_id,
                user_id,
            )
            raise UnknownAccountError(str(account_id))

        if before is not None:
            # Rows are stored in UTC, and SQLite compares them as text with
            # the offset dropped, so the cursor is normalised to UTC first. A
            # naive cursor is taken to be UTC already.
            before = (
                before.astimezone(UTC) if before.tzinfo else before.replace(tzinfo=UTC)
            )
        legs = self._transactions.list_account_transactions(
            account_id, limit=limit, before=before, user_id=user_id
        )
        transfers = self._transfers(user_id, legs)
        kind = account_kind(account.account_currency)
        return [
            self._leg_view(leg, account_id, kind, transfers.get(leg.quote_id))
            for leg in legs
        ]

    def _transfers(
        self, user_id: uuid.UUID, legs: list[Transaction]
    ) -> dict[uuid.UUID, _Transfer]:
        """The transfer behind each leg that belongs to one, keyed by
        `quote_id`, in a fixed handful of queries however long the page."""
        quote_ids = {leg.quote_id for leg in legs if leg.quote_id is not None}
        quotes = self._quotes.get_many(quote_ids, user_id)
        remittance_ids = self._remittances.get_ids_by_quote_ids(quote_ids, user_id)
        burn_hashes = self._transactions.get_burn_hashes(quote_ids, user_id)
        users = self._users.get_many(
            {q.sender_user_id for q in quotes.values()}
            | {q.beneficiary_user_id for q in quotes.values()}
        )

        transfers = {}
        for quote_id, quote in quotes.items():
            sent = quote.sender_user_id == user_id
            other = users.get(
                quote.beneficiary_user_id if sent else quote.sender_user_id
            )
            transfers[quote_id] = _Transfer(
                quote=quote,
                sent=sent,
                counterparty_name=(
                    short_display_name(other.first_name, other.last_name)
                    if other
                    else None
                ),
                remittance_id=remittance_ids.get(quote_id),
                xrpl_tx_hash=burn_hashes.get(quote_id),
            )
        return transfers

    def _leg_view(
        self,
        leg: Transaction,
        account_id: uuid.UUID,
        kind: str,
        transfer: _Transfer | None,
    ) -> AccountTransactionView:
        # credit=source, debit=destination (models/orm/transaction.py) — this
        # account received the money iff it's the leg's debit side.
        direction = (
            DIRECTION_IN if leg.debit_account_id == account_id else DIRECTION_OUT
        )
        return AccountTransactionView(
            tx_id=leg.tx_id,
            type=leg.type,
            direction=direction,
            amount=_money(leg.amount),
            currency=leg.currency,
            status=leg.status,
            created_at=leg.created_at,
            confirmed_at=leg.confirmed_at,
            description=describe_leg(leg.type, direction, kind, transfer),
            counterparty_name=transfer.counterparty_name if transfer else None,
            remittance_id=transfer.remittance_id if transfer else None,
            # Every leg of a transfer confirms in the same commit as the burn
            # hash is recorded, so a confirmed leg's hash is the transfer's.
            xrpl_tx_hash=(
                transfer.xrpl_tx_hash
                if transfer and leg.status == STATUS_CONFIRMED
                else None
            ),
        )
