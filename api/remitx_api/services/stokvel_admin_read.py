"""Admin reads for the stokvel vault and round list (R4-09 follow-up)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import and_, func, select
from web3 import Web3

from remitx_api.clock import utcnow
from remitx_api.config import Config
from remitx_api.extensions import db
from remitx_api.models.orm.audit_log import (
    STOKVEL_CONTRACT_SUBJECT_ID,
    AuditAction,
    AuditLog,
    AuditSubject,
)
from remitx_api.models.orm.platform_account_seed import CURRENCY_TOKEN, TYPE_EVM_WALLET
from remitx_api.models.orm.stokvel import Stokvel
from remitx_api.models.orm.stokvel_cycle import StokvelCycle, StokvelCycleStatus
from remitx_api.models.orm.stokvel_cycle_member import StokvelCycleMember
from remitx_api.models.orm.stokvel_member import StokvelMember
from remitx_api.models.orm.stokvel_payout import (
    StokvelPayout,
    StokvelPayoutReleaseStatus,
)
from remitx_api.models.orm.stokvel_round import StokvelRound
from remitx_api.models.orm.user import User, short_display_name
from remitx_api.repositories.account_repository import AccountRepository
from remitx_api.repositories.stokvel_contribution_repository import (
    StokvelContributionRepository,
)
from remitx_api.repositories.stokvel_payout_repository import StokvelPayoutRepository
from remitx_api.services.stokvel_contract_read import is_paused

EVM_NETWORK_LABEL = "XRPL EVM Testnet"

_BALANCE_OF_ABI = [
    {
        "name": "balanceOf",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "account", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
    }
]


@dataclass(frozen=True)
class StokvelContractStatusView:
    address: str
    network: str
    paused: bool
    paused_at: datetime | None
    paused_reason: str | None
    treasury_token_balance: Decimal


@dataclass(frozen=True)
class AdminStokvelRoundView:
    stokvel_id: uuid.UUID
    stokvel_name: str
    round: int
    total_rounds: int
    recipient_name: str | None
    paid_count: int
    member_count: int
    payout_time: datetime
    release_status: str | None
    release_tx_hash: str | None
    manual_release_allowed: bool


def round_manual_release_allowed(
    *,
    cycle_id: uuid.UUID,
    round_: int,
    total_rounds: int,
    payout_time: datetime,
    release_status: str | None,
    now: datetime | None = None,
) -> bool:
    """Whether an admin may queue manual release (D5, D12): payout time
    passed, every member confirmed for this round and the next (unless last),
    and the payout is missing or still `pending`."""
    when = utcnow() if now is None else now
    if release_status in (
        StokvelPayoutReleaseStatus.RELEASED.value,
        StokvelPayoutReleaseStatus.PROCESSING.value,
        StokvelPayoutReleaseStatus.FAILED.value,
    ):
        return False
    if payout_time > when:
        return False
    return _contributions_fully_paid(cycle_id, round_, total_rounds)


def _contributions_fully_paid(
    cycle_id: uuid.UUID, round_: int, total_rounds: int
) -> bool:
    """Same rule as the scheduled release sweep (D5)."""
    contributions = StokvelContributionRepository()
    rounds = [round_] if round_ + 1 == total_rounds else [round_, round_ + 1]
    return all(
        len(contributions.get_paid_member_ids(cycle_id, r)) == total_rounds
        for r in rounds
    )


def read_contract_status() -> StokvelContractStatusView:
    """Vault address, pause flag, audit pause context, and treasury token."""
    config = Config()
    address = config.STOKVEL_CONTRACT_ADDRESS
    checksum = ""
    if address:
        checksum = Web3.to_checksum_address(address)
    paused = is_paused() if address else False
    paused_at, paused_reason = _latest_pause_audit() if paused else (None, None)
    return StokvelContractStatusView(
        address=checksum,
        network=EVM_NETWORK_LABEL,
        paused=paused,
        paused_at=paused_at,
        paused_reason=paused_reason,
        treasury_token_balance=_treasury_token_balance(config),
    )


def list_admin_rounds() -> list[AdminStokvelRoundView]:
    """Each active, registered cycle's earliest round not yet released."""
    released = (
        select(StokvelPayout.id)
        .where(
            StokvelPayout.cycle_id == StokvelRound.cycle_id,
            StokvelPayout.round == StokvelRound.round,
            StokvelPayout.release_status == StokvelPayoutReleaseStatus.RELEASED.value,
        )
        .exists()
    )
    next_round = (
        select(StokvelRound.cycle_id, func.min(StokvelRound.round).label("round"))
        .where(~released)
        .group_by(StokvelRound.cycle_id)
        .subquery()
    )
    rows = db.session.execute(
        select(
            Stokvel.id,
            Stokvel.name,
            StokvelCycle.id,
            StokvelCycle.total_rounds,
            StokvelRound.round,
            StokvelRound.payout_time,
        )
        .select_from(StokvelCycle)
        .join(Stokvel, Stokvel.id == StokvelCycle.stokvel_id)
        .join(next_round, next_round.c.cycle_id == StokvelCycle.id)
        .join(
            StokvelRound,
            and_(
                StokvelRound.cycle_id == StokvelCycle.id,
                StokvelRound.round == next_round.c.round,
            ),
        )
        .where(
            StokvelCycle.status == StokvelCycleStatus.ACTIVE.value,
            StokvelCycle.registered_at.is_not(None),
            StokvelCycle.total_rounds.is_not(None),
        )
        .order_by(Stokvel.name, StokvelRound.round)
    ).all()

    contributions = StokvelContributionRepository()
    payouts = StokvelPayoutRepository()
    views: list[AdminStokvelRoundView] = []
    for (
        stokvel_id,
        stokvel_name,
        cycle_id,
        total_rounds,
        round_,
        payout_time,
    ) in rows:
        member_count = int(total_rounds)
        paid_count = len(contributions.get_paid_member_ids(cycle_id, round_))
        payout = payouts.get_round_payout(cycle_id, round_)
        release_status = None if payout is None else payout.release_status
        views.append(
            AdminStokvelRoundView(
                stokvel_id=stokvel_id,
                stokvel_name=stokvel_name,
                round=int(round_),
                total_rounds=member_count,
                recipient_name=_recipient_name(cycle_id, int(round_)),
                paid_count=paid_count,
                member_count=member_count,
                payout_time=payout_time,
                release_status=release_status,
                release_tx_hash=None if payout is None else payout.release_tx_hash,
                manual_release_allowed=round_manual_release_allowed(
                    cycle_id=cycle_id,
                    round_=int(round_),
                    total_rounds=member_count,
                    payout_time=payout_time,
                    release_status=release_status,
                ),
            )
        )
    return views


def _latest_pause_audit() -> tuple[datetime | None, str | None]:
    subject = AuditSubject.STOKVEL_CONTRACT.value
    paused = db.session.scalar(
        select(AuditLog)
        .where(
            AuditLog.subject_type == subject,
            AuditLog.subject_id == STOKVEL_CONTRACT_SUBJECT_ID,
            AuditLog.action == AuditAction.STOKVEL_CONTRACT_PAUSED.value,
        )
        .order_by(AuditLog.created_at.desc(), AuditLog.audit_id.desc())
        .limit(1)
    )
    if paused is None:
        return None, None
    unpaused = db.session.scalar(
        select(AuditLog)
        .where(
            AuditLog.subject_type == subject,
            AuditLog.subject_id == STOKVEL_CONTRACT_SUBJECT_ID,
            AuditLog.action == AuditAction.STOKVEL_CONTRACT_UNPAUSED.value,
        )
        .order_by(AuditLog.created_at.desc(), AuditLog.audit_id.desc())
        .limit(1)
    )
    if unpaused is not None and unpaused.created_at > paused.created_at:
        return None, None
    return paused.created_at, paused.reason


def _recipient_name(cycle_id: uuid.UUID, round_: int) -> str | None:
    row = db.session.execute(
        select(User.first_name, User.last_name)
        .select_from(StokvelCycleMember)
        .join(StokvelMember, StokvelMember.id == StokvelCycleMember.member_id)
        .join(User, User.id == StokvelMember.user_id)
        .where(
            StokvelCycleMember.cycle_id == cycle_id,
            StokvelCycleMember.payout_position == round_,
        )
        .limit(1)
    ).first()
    if row is None:
        return None
    return short_display_name(row[0], row[1])


def _treasury_token_balance(config: Config) -> Decimal:
    accounts = AccountRepository()
    wallet = next(
        (
            account
            for account in accounts.list_platform_accounts()
            if account.type == TYPE_EVM_WALLET
            and account.account_currency == CURRENCY_TOKEN
        ),
        None,
    )
    if wallet is not None:
        return accounts.get_available_balance(wallet.account_id)
    treasury = config.EVM_TREASURY_ADDRESS
    token = config.UCTUSD_CONTRACT_ADDRESS
    if not treasury or not token:
        return Decimal("0")
    try:
        w3 = Web3(Web3.HTTPProvider(config.EVM_RPC_URL, request_kwargs={"timeout": 10}))
        contract = w3.eth.contract(
            address=Web3.to_checksum_address(token), abi=_BALANCE_OF_ABI
        )
        raw = contract.functions.balanceOf(Web3.to_checksum_address(treasury)).call()
        scale = Decimal(10) ** config.UCTUSD_EVM_DECIMALS
        return Decimal(raw) / scale
    except Exception:
        return Decimal("0")
