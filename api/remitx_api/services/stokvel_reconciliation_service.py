"""The Treasury Wallet's UCTUSD against the ledger (R3-08, #245).

Expected float is confirmed UCTUSD into the treasury account minus confirmed
UCTUSD out: funding, contributions sent to the contract, releases back,
burns, and a payout's two remittance legs (they cancel). `STOKVEL` balances
are tokens still in the contract, reported apart from that float.

Every confirmed UCTUSD leg counts, so a rate-difference leg would too.
Contributions are a fixed UCTUSD amount (D13); #298 booked no such leg.
"""

from dataclasses import dataclass
from decimal import Decimal

from remitx_api.models.orm.account import CURRENCY_TOKEN, TYPE_EVM_WALLET
from remitx_api.repositories.account_repository import AccountRepository
from remitx_api.repositories.transaction_repository import TransactionRepository


@dataclass(frozen=True)
class PoolReconciliation:
    expected: Decimal
    on_chain: Decimal
    contract_held: Decimal

    @property
    def matches(self) -> bool:
        return self.expected == self.on_chain


def check_pool_reconciliation(on_chain: Decimal) -> PoolReconciliation:
    """Compare `on_chain` UCTUSD with the treasury float the ledger expects.

    `on_chain` is read by the caller. This module stays free of the worker,
    which is the only place that talks to the chain.
    """
    accounts = AccountRepository()
    treasury = accounts.get_platform_account(TYPE_EVM_WALLET, CURRENCY_TOKEN)
    if treasury is None:
        raise RuntimeError("no treasury token account")
    return PoolReconciliation(
        expected=TransactionRepository().confirmed_net(
            treasury.account_id, CURRENCY_TOKEN
        ),
        on_chain=on_chain,
        contract_held=accounts.sum_stokvel_balances(),
    )
