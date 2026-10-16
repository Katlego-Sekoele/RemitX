"""Settling seeded remittances with the real worker code and a simulated chain.

`remittance_service.confirm_remittance` enqueues `settle_remittance` on Redis.
During a seed run the three queue calls are rerouted: the settle message
becomes a timeline event a few seconds later, and each hand-off after it
(`burn_treasury_tokens`, then `confirm_treasury_burn`) runs inline. Those are
the worker's own task functions, so the pending -> processing -> confirmed or
failed transitions and every balance update are real worker code.

The simulated calls are the chain's: `evm_service.burn_tokens` and
`evm_service.wait_for_receipt`. The burn hands the worker a synthetic hash
(recognisable: it starts `5EED`) through `on_signed`, as the real one does
before sending, and the receipt confirms it at once. At the scenario's
failure rate the burn instead fails before anything is signed, so the group
fails with no hash. `evm_service.get_web3` raises, so nothing reaches an
EVM RPC, and no treasury tokens are spent.
"""

from __future__ import annotations

import logging
from contextlib import ExitStack
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from remitx_seeder.context import RunContext
from remitx_seeder.sim import Simulation

SYNTHETIC_HASH_PREFIX = "5EED"
# What stops a real burn before it is signed: gas estimation reverting because
# the Treasury Wallet is short of UCTUSD, no test XRP for gas, or an RPC that
# does not answer.
FAILURE_RESULTS = (
    "execution reverted: ERC20InsufficientBalance",
    "insufficient funds for gas * price + value",
    "EVM RPC request timed out",
)


def synthetic_hash(ctx: RunContext) -> str:
    tail = "".join(ctx.rng.choice("0123456789ABCDEF") for _ in range(60))
    return SYNTHETIC_HASH_PREFIX + tail


def _no_rpc():
    raise RuntimeError("the seeder simulates the chain; nothing may reach an EVM RPC")


class _ExpectedFailureFilter(logging.Filter):
    """The worker logs a failed burn at error level, traceback included. When
    the seeder failed it on purpose, that is expected: shown as info, without
    the traceback. Anything else the worker logs keeps its level."""

    def __init__(self, settlement: SimulatedSettlement) -> None:
        super().__init__()
        self._settlement = settlement

    def filter(self, record: logging.LogRecord) -> bool:
        if self._settlement.forcing_failure:
            record.levelno, record.levelname = logging.INFO, "INFO"
            record.exc_info = None
            record.msg = f"(simulated) {record.msg}"
        return True


class SimulatedSettlement:
    def __init__(self, ctx: RunContext, sim: Simulation) -> None:
        self.ctx = ctx
        self.sim = sim
        self._fail_next = False
        self.forcing_failure = False

    def install(self, stack: ExitStack) -> None:
        from remitx_api.services import queue_service
        from remitx_worker import evm_service

        stack.enter_context(
            mock.patch.object(
                queue_service, "enqueue_settle_remittance", self._enqueue_settle
            )
        )
        stack.enter_context(
            mock.patch.object(
                queue_service, "enqueue_burn_treasury_tokens", self._run_burn
            )
        )
        stack.enter_context(
            mock.patch.object(
                queue_service, "enqueue_confirm_treasury_burn", self._run_confirm
            )
        )
        stack.enter_context(
            mock.patch.object(evm_service, "burn_tokens", self._simulated_burn)
        )
        stack.enter_context(
            mock.patch.object(evm_service, "wait_for_receipt", self._simulated_receipt)
        )
        stack.enter_context(mock.patch.object(evm_service, "get_web3", _no_rpc))
        worker_log = logging.getLogger("remitx_worker.tasks")
        expected = _ExpectedFailureFilter(self)
        worker_log.addFilter(expected)
        stack.callback(worker_log.removeFilter, expected)

    # --- rerouted queue --------------------------------------------------

    def _enqueue_settle(self, quote_id: str) -> None:
        delay = timedelta(seconds=self.ctx.rng.uniform(4, 75))
        self.sim.schedule(
            self.ctx.clock.now() + delay,
            "settlement",
            lambda: self._settle(quote_id),
        )

    def _settle(self, quote_id: str) -> None:
        from remitx_worker import tasks

        self._fail_next = (
            self.ctx.rng.random() < self.ctx.scenario.money.settlement_failure_rate
        )
        self.forcing_failure = self._fail_next
        try:
            tasks.settle_remittance(quote_id)
        finally:
            self.forcing_failure = False

    def _run_burn(self, quote_id: str) -> None:
        from remitx_worker import tasks

        tasks.burn_treasury_tokens(quote_id)

    def _run_confirm(
        self, quote_id: str, tx_hash: str | None, error: str | None = None
    ) -> None:
        from remitx_worker import tasks

        outcome = tasks.confirm_treasury_burn(quote_id, tx_hash, error)
        self.ctx.count(f"settlement.{outcome}")

    # --- the simulated chain ---------------------------------------------

    def _simulated_burn(self, amount: Decimal, *, on_signed=None, w3=None) -> str:
        """Stand-in for `evm_service.burn_tokens`. A forced failure raises
        before `on_signed`, like a burn that fails before it is signed."""
        if self._fail_next:
            self._fail_next = False
            raise RuntimeError(
                f"burn failed before signing: {self.ctx.rng.choice(FAILURE_RESULTS)}"
            )
        tx_hash = synthetic_hash(self.ctx)
        if on_signed is not None:
            on_signed(tx_hash)
        self.ctx.simulated_burn_total += Decimal(amount)
        self.ctx.synthetic_hashes.append(tx_hash)
        return tx_hash

    def _simulated_receipt(self, tx_hash: str, timeout: float = 120, w3=None):
        """Stand-in for `evm_service.wait_for_receipt`: mined at once."""
        return {"transactionHash": tx_hash, "status": 1, "blockNumber": 0}
