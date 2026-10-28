"""Contributing to a stokvel round (R2-11, #233).

A member pays into their stokvel's open round. Nothing is paid yet when this
returns: it records the intent as a `pending` contribution with its pending
ledger legs, in one transaction, and then queues the worker task that sends
`contribute` on-chain (`stokvel.submit_contribution`, R2-12). The contribution
is `confirmed` only once that transaction is mined.

The legs (doc section 3, agreed with R3-01's owner):

- fiat: the member's account in the Stokvel currency -> RemitX's bank account
  in that currency, `amount_fiat` (the fixed UCTUSD contribution at the live
  rate, D13)
- token: Treasury Wallet -> the stokvel's `STOKVEL` account, the fixed UCTUSD
  `contribution_amount`. On-chain the Treasury pays the contract, so the
  `STOKVEL` balance is the stokvel's unreleased pools in the contract
- fee: the member's account -> RemitX fee revenue, their share of the payout
  fee paid on top (`contribution_fee_share`), only when it is not zero

The contribution row points at each leg (`fiat_tx_id`, `token_tx_id`,
`fee_tx_id`), so the legs need no grouping column of their own.

The shape is `remittance_service.confirm_remittance`'s: lock the user, check
standing, limits and balance, write everything pending, then enqueue after the
commit so the worker can never see a contribution that might still roll back.
Unlike a remittance, a contribution is priced here, so its rates are looked up
before the lock: a lookup may fetch a live rate and commit, which would end
the transaction and release the lock before the checks run.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_UP, Decimal

from sqlalchemy.exc import IntegrityError

from remitx_api.db.transaction import db_transaction
from remitx_api.errors.stokvels import (
    ContributionAlreadyPaidError,
    ContributionInsufficientBalanceError,
    CycleNotOpenError,
    CycleStartingError,
    NoOpenRoundError,
    NotACycleMemberError,
    StokvelNotFoundError,
    StokvelPausedError,
)
from remitx_api.models.orm.account import (
    CURRENCY_TOKEN,
    TYPE_EVM_WALLET,
    TYPE_PLATFORM_FIAT,
    TYPE_PLATFORM_REVENUE,
    Account,
)
from remitx_api.models.orm.stokvel import Stokvel
from remitx_api.models.orm.stokvel_contribution import StokvelContribution
from remitx_api.models.orm.stokvel_cycle import StokvelCycleStatus
from remitx_api.models.orm.transaction import (
    STATUS_PENDING,
    TYPE_FEE,
    TYPE_STOKVEL_CONTRIBUTION,
    Transaction,
)
from remitx_api.repositories.account_repository import AccountRepository
from remitx_api.repositories.kyc_application_repository import KycApplicationRepository
from remitx_api.repositories.stokvel_contribution_repository import (
    StokvelContributionRepository,
)
from remitx_api.repositories.stokvel_cycle_repository import StokvelCycleRepository
from remitx_api.repositories.stokvel_member_repository import StokvelMemberRepository
from remitx_api.repositories.stokvel_repository import StokvelRepository
from remitx_api.repositories.transaction_repository import TransactionRepository
from remitx_api.repositories.user_repository import UserRepository
from remitx_api.services import queue_service
from remitx_api.services.quote_service import (
    TokenRates,
    remittance_fee_and_margin,
    to_zar,
    token_rates,
    token_to_fiat,
)
from remitx_api.services.send_limits import (
    require_verified,
    require_within_monthly_limit,
)
from remitx_api.services.stokvel_contract_read import is_paused

logger = logging.getLogger(__name__)

_CENT = Decimal("0.01")
_ONCE_CONSTRAINT = "uq_stokvel_contributions_once"
# SQLite names no constraint in its error, only the columns of a unique one.
_ONCE_SQLITE_MESSAGE = (
    "UNIQUE constraint failed: stokvel_contributions.cycle_id, "
    "stokvel_contributions.round, stokvel_contributions.member_id"
)


def _is_paid_twice(exc: IntegrityError) -> bool:
    """Whether `exc` is a violation of `uq_stokvel_contributions_once`.
    Postgres (psycopg2) names the constraint in the error's diagnostics;
    SQLite gives only the unique columns in its message."""
    diag = getattr(exc.orig, "diag", None)
    if diag is not None:
        return diag.constraint_name == _ONCE_CONSTRAINT
    return _ONCE_SQLITE_MESSAGE in str(exc.orig)


def contribution_fee_share(
    amount_fiat: Decimal,
    rates: TokenRates,
    *,
    member_count: int,
    payout_currency: str,
) -> Decimal:
    """Each member's share of the round's payout fee, paid on top of their
    contribution, in the Stokvel currency (product question 4, option A:
    the beneficiary then receives the full pool).

    The round's payout is one remittance of the pool (`amount_fiat` from
    every member) to its recipient's beneficiary, so its fee and margin are
    FSE's usual ones on that pool (`remittance_fee_and_margin`): no margin
    when the recipient is paid in the Stokvel currency. The total is split
    equally and rounded up to the cent, so the members always cover it. The
    recipient's payout currency is locked when the cycle starts, so it is the
    same for every member of the round.

    Worked out at the rate when the member pays, as the contribution is. In a
    stokvel whose currency is not ZAR, members who pay at different rates pay
    slightly different shares, and the shares need not add up exactly to the
    fee on the pool paid out (D6). The one place to change if the rule does.
    """
    pool = amount_fiat * member_count
    fee, margin = remittance_fee_and_margin(
        pool,
        rates.currency,
        payout_currency,
        fiat_to_token_exchange_rate=rates.token_per_unit,
        zar_token_rate=rates.zar_token_per_unit,
    )
    return ((fee + margin) / member_count).quantize(_CENT, rounding=ROUND_UP)


@dataclass(frozen=True)
class StokvelContributionView:
    contribution_id: uuid.UUID
    stokvel_id: uuid.UUID
    cycle_number: int
    round: int
    status: str
    currency: str
    amount_token: Decimal
    amount_fiat: Decimal
    fee_amount: Decimal
    amount_zar: Decimal
    created_at: datetime


class StokvelContributionController:
    def __init__(self) -> None:
        self._accounts = AccountRepository()
        self._applications = KycApplicationRepository()
        self._contributions = StokvelContributionRepository()
        self._cycles = StokvelCycleRepository()
        self._members = StokvelMemberRepository()
        self._stokvels = StokvelRepository()
        self._transactions = TransactionRepository()
        self._users = UserRepository()

    def contribute(
        self, user_id: uuid.UUID, stokvel_id: uuid.UUID
    ) -> StokvelContributionView:
        """Pay the caller's contribution to their stokvel's open round: record
        it pending, then queue it for the chain. Enqueued only after the
        commit, as for a remittance's settlement."""
        view = self._record(user_id, stokvel_id)
        # The contribution and its legs are committed `pending` now. If this
        # enqueue is lost, the contribution holds its round and the member's
        # balance with nothing to drive it on, so the failure is logged
        # loudly before it propagates, as in `confirm_remittance`.
        try:
            queue_service.enqueue_submit_contribution(str(view.contribution_id))
        except Exception:
            logger.exception(
                "contribute: failed to enqueue submit_contribution for "
                "contribution %s (stokvel %s, round %s); it is committed "
                "pending but was never queued",
                view.contribution_id,
                view.stokvel_id,
                view.round,
            )
            raise
        return view

    @db_transaction
    def _record(
        self, user_id: uuid.UUID, stokvel_id: uuid.UUID
    ) -> StokvelContributionView:
        """Record the caller's contribution to their stokvel's open round, pending"""
        if is_paused():
            raise StokvelPausedError()
        stokvel = self._stokvels.get_by_id(stokvel_id)
        if stokvel is None:
            raise StokvelNotFoundError()
        # Before the lock: a lookup may fetch a live rate and commit, which
        # would release the lock. Everything below prices from these.
        rates = token_rates(stokvel.currency)
        # Held until the commit. The limit and balance checks read what this
        # member has already done, so their contributions run one at a time.
        self._users.lock(user_id)

        # Not a current member: the same 404 as an unknown id. On Postgres,
        # row-level security hides the stokvel from outsiders anyway, so this
        # keeps SQLite's answer the same and reveals nothing about the id.
        member = self._members.get_active_member(stokvel.id, user_id)
        if member is None:
            raise StokvelNotFoundError()
        cycle = self._cycles.get_open_cycle(stokvel.id)
        if cycle is None or cycle.status != StokvelCycleStatus.ACTIVE.value:
            raise CycleNotOpenError()
        if cycle.registered_at is None:
            # Started, but `startCycle` is not mined yet (R2-10): the contract
            # has no open cycle, so the contribution would revert.
            raise CycleStartingError()
        # A member who left before the cycle started must count neither
        # toward the round nor as a member of it.
        cycle_members = self._cycles.get_locked_members(cycle.id)
        cycle_member_ids = {row.member_id for row in cycle_members}
        if member.id not in cycle_member_ids:
            raise NotACycleMemberError()
        if cycle.total_rounds is None:
            # Set when the cycle starts (stokvel_cycles_started_has_total_rounds
            # holds it): never reported as a round that isn't open.
            raise RuntimeError(f"active cycle {cycle.id} has no total_rounds")

        round_ = self._contributions.open_round(
            cycle.id,
            member_count=len(cycle_member_ids),
            total_rounds=cycle.total_rounds,
        )
        if round_ is None:
            raise NoOpenRoundError()
        if self._contributions.get_member_contribution(cycle.id, round_, member.id):
            raise ContributionAlreadyPaidError()

        currency = stokvel.currency
        amount_token = stokvel.contribution_amount
        amount_fiat = token_to_fiat(amount_token, rates)
        fee = contribution_fee_share(
            amount_fiat,
            rates,
            member_count=len(cycle_member_ids),
            payout_currency=self._recipient_currency(cycle_members, round_),
        )
        total = amount_fiat + fee
        # What leaves the member's account, fee included, counts against
        # their own limits (D8), as a remittance counts its gross amount.
        # Only the monthly limit is checked: a round is due in the month, not
        # on the day it is paid.
        amount_zar = to_zar(total, currency, rates=rates)
        standing = self._applications.get_standing(user_id)
        require_verified(standing)
        require_within_monthly_limit(
            standing, amount_zar, amount=total, currency=currency
        )
        available = self._accounts.get_available_balance_locked(member.account_id)
        if available < total:
            raise ContributionInsufficientBalanceError(available, total, currency)

        bank = self._platform(TYPE_PLATFORM_FIAT, currency)
        fiat_leg = self._transactions.add(
            Transaction(
                type=TYPE_STOKVEL_CONTRIBUTION,
                credit_account_id=member.account_id,
                debit_account_id=bank.account_id,
                amount=amount_fiat,
                currency=currency,
                status=STATUS_PENDING,
            )
        )
        token_leg = self._transactions.add(
            Transaction(
                type=TYPE_STOKVEL_CONTRIBUTION,
                credit_account_id=self._platform(
                    TYPE_EVM_WALLET, CURRENCY_TOKEN
                ).account_id,
                debit_account_id=self._stokvel_account_id(stokvel),
                amount=amount_token,
                currency=CURRENCY_TOKEN,
                status=STATUS_PENDING,
            )
        )
        fee_leg = None
        if fee > 0:
            fee_leg = self._transactions.add(
                Transaction(
                    type=TYPE_FEE,
                    credit_account_id=member.account_id,
                    debit_account_id=self._platform(
                        TYPE_PLATFORM_REVENUE, currency
                    ).account_id,
                    amount=fee,
                    currency=currency,
                    status=STATUS_PENDING,
                )
            )

        try:
            contribution = self._contributions.add(
                StokvelContribution(
                    cycle_id=cycle.id,
                    round=round_,
                    member_id=member.id,
                    amount_token=amount_token,
                    amount_fiat=amount_fiat,
                    amount_zar=amount_zar,
                    fiat_tx_id=fiat_leg.tx_id,
                    token_tx_id=token_leg.tx_id,
                    fee_tx_id=None if fee_leg is None else fee_leg.tx_id,
                )
            )
        except IntegrityError as exc:
            # Only uq_stokvel_contributions_once means a concurrent request
            # for the same member and round got there first. Any other
            # constraint is a fault, raised as is. The decorator rolls back.
            if _is_paid_twice(exc):
                raise ContributionAlreadyPaidError() from exc
            raise

        return StokvelContributionView(
            contribution_id=contribution.id,
            stokvel_id=stokvel.id,
            cycle_number=cycle.cycle_number,
            round=round_,
            status=contribution.status,
            currency=currency,
            amount_token=amount_token,
            amount_fiat=amount_fiat,
            fee_amount=fee,
            amount_zar=amount_zar,
            created_at=contribution.created_at,
        )

    def _platform(self, type_: str, currency: str) -> Account:
        account = self._accounts.get_platform_account(type_, currency)
        if account is None:
            # Seeded by migration for every settlement currency: a missing
            # one is a deployment fault, not something the member can fix.
            raise RuntimeError(f"no {type_} platform account in {currency}")
        return account

    @staticmethod
    def _recipient_currency(cycle_members, round_: int) -> str:
        """The payout currency of the member the round pays (the one whose
        payout position is the round). Locked when the cycle starts, so every
        member of a round prices the fee on the same currency."""
        recipient = next(
            (row for row in cycle_members if row.payout_position == round_), None
        )
        if recipient is None or not recipient.locked:
            # An active cycle's members are all locked with a position and a
            # beneficiary (stokvel_cycle_members_locked_is_complete).
            raise RuntimeError(f"round {round_} has no locked recipient")
        return recipient.payout_currency

    @staticmethod
    def _stokvel_account_id(stokvel: Stokvel) -> uuid.UUID:
        if stokvel.account_id is None:
            # Created with the stokvel (R2-07); never missing once in service.
            raise RuntimeError(f"stokvel {stokvel.id} has no STOKVEL account")
        return stokvel.account_id
