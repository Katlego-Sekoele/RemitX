"""Settling seeded remittances with the real worker code and a simulated chain.

`remittance_service.confirm_remittance` enqueues `settle_remittance` on Redis.
During a seed run the three queue calls are rerouted: the settle message
becomes a timeline event a few seconds later, and each hand-off after it
(`burn_treasury_tokens`, then `confirm_treasury_burn`) runs inline. Those are
the worker's own task functions, so the pending -> processing -> confirmed or
failed transitions and every balance update are real worker code.

The one simulated call is `xrpl_service.burn_tokens`. It returns a synthetic
hash (recognisable: it starts `5EED`) or raises the kind of error a failed
Payment raises, at the scenario's failure rate. Nothing reaches the XRPL, and
no treasury tokens are spent.
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
FAILURE_RESULTS = ("tecPATH_DRY", "tecUNFUNDED_PAYMENT", "tefPAST_SEQ")


def synthetic_hash(ctx: RunContext) -> str:
    tail = "".join(ctx.rng.choice("0123456789ABCDEF") for _ in range(60))
    return SYNTHETIC_HASH_PREFIX + tail


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
        from remitx_worker import xrpl_service

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
            mock.patch.object(xrpl_service, "burn_tokens", self._simulated_burn)
        )
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

    def _simulated_burn(self, amount: Decimal) -> str:
        if self._fail_next:
            self._fail_next = False
            raise RuntimeError(
                f"burn Payment failed: {self.ctx.rng.choice(FAILURE_RESULTS)}"
            )
        tx_hash = synthetic_hash(self.ctx)
        self.ctx.simulated_burn_total += Decimal(amount)
        self.ctx.synthetic_hashes.append(tx_hash)
        return tx_hash
