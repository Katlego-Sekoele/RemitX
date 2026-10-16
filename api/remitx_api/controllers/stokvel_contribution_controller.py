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
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy.exc import IntegrityError

from remitx_api.db.transaction import db_transaction
from remitx_api.errors.stokvels import (
    ContributionAlreadyPaidError,
    ContributionInsufficientBalanceError,
    CycleNotOpenError,
    NoOpenRoundError,
    NotACycleMemberError,
    StokvelNotFoundError,
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
from remitx_api.models.orm.stokvel_cycle import StokvelCycle, StokvelCycleStatus
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
from remitx_api.services.quote_service import to_zar, token_to_fiat
from remitx_api.services.send_limits import require_can_send

_NO_FEE = Decimal("0.00")


def contribution_fee_share(stokvel: Stokvel, cycle: StokvelCycle) -> Decimal:
    """The member's share of the round's payout fee, paid on top of their
    contribution, in the Stokvel currency (product question 4, option A).

    Not decided yet: how the share is worked out before the payout's own quote
    exists. Until product confirms it this is zero, so no fee leg is written.
    The one place to change when it is decided.
    """
    return _NO_FEE


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
        queue_service.enqueue_submit_contribution(str(view.contribution_id))
        return view

    @db_transaction
    def _record(
        self, user_id: uuid.UUID, stokvel_id: uuid.UUID
    ) -> StokvelContributionView:
        # Held until the commit. The limit and balance checks read what this
        # member has already done, so their contributions run one at a time.
        self._users.lock(user_id)

        stokvel = self._stokvels.get_by_id(stokvel_id)
        if stokvel is None:
            raise StokvelNotFoundError()
        member = self._members.get_active_member(stokvel.id, user_id)
        if member is None:
            raise NotACycleMemberError()
        cycle = self._cycles.get_open_cycle(stokvel.id)
        if cycle is None or cycle.status != StokvelCycleStatus.ACTIVE.value:
            raise CycleNotOpenError()
        cycle_member_ids = {
            row.member_id for row in self._cycles.get_cycle_members(cycle.id)
        }
        if member.id not in cycle_member_ids:
            raise NotACycleMemberError()

        round_ = self._contributions.open_round(
            cycle.id,
            member_count=len(cycle_member_ids),
            total_rounds=cycle.total_rounds or 0,
        )
        if round_ is None:
            raise NoOpenRoundError()
        if self._contributions.get_member_contribution(cycle.id, round_, member.id):
            raise ContributionAlreadyPaidError()

        currency = stokvel.currency
        amount_token = stokvel.contribution_amount
        amount_fiat = token_to_fiat(amount_token, currency)
        fee = contribution_fee_share(stokvel, cycle)
        total = amount_fiat + fee
        # What leaves the member's account, fee included, counts against
        # their own limits (D8), as a remittance counts its gross amount.
        amount_zar = to_zar(total, currency)
        require_can_send(
            self._applications.get_standing(user_id),
            amount_zar,
            amount=total,
            currency=currency,
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
            # uq_stokvel_contributions_once: a concurrent request for the same
            # member and round got there first. The decorator rolls back.
            raise ContributionAlreadyPaidError() from exc

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
    def _stokvel_account_id(stokvel: Stokvel) -> uuid.UUID:
        if stokvel.account_id is None:
            # Created with the stokvel (R2-07); never missing once in service.
            raise RuntimeError(f"stokvel {stokvel.id} has no STOKVEL account")
        return stokvel.account_id
