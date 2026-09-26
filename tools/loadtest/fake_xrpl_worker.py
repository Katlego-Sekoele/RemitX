"""The settlement worker with its one XRPL call simulated.

Runs what the Render worker runs (`python -m remitx_worker`: the health server
plus Celery), after replacing `remitx_worker.xrpl_service.burn_tokens`. Every
other step of settlement is the real code: the three tasks, the claims and the
balance updates. The replacement happens before Celery forks its pool, so every
child process inherits it.

A simulated burn takes about as long as a real testnet one: a lognormal delay
through the median and 95th percentile of QA's real settlements
(qa_xrpl_timings.sql), overridable with LOADTEST_BURN_P50_S and
LOADTEST_BURN_P95_S. Its hashes start 10AD ("load"), so they can never be
mistaken for real ones or for the seeder's (5EED).
"""

import math
import os
import random
import secrets
import time
from decimal import Decimal

from remitx_worker import xrpl_service

HASH_PREFIX = "10AD"
# z-score of the 95th percentile of a standard normal distribution.
Z_95 = 1.6449


def _setting(name: str, default: str) -> float:
    # `or`, not a get() default: compose passes an unset knob through as "".
    return float(os.environ.get(name) or default)


# Placeholders until QA's numbers are in (see qa_xrpl_timings.sql).
BURN_P50_S = _setting("LOADTEST_BURN_P50_S", "4.0")
BURN_P95_S = _setting("LOADTEST_BURN_P95_S", "8.0")
# Share of burns that fail the way a rejected Payment does. Zero by default so
# the report measures the happy path; raise it to see failures under load.
FAILURE_RATE = _setting("LOADTEST_BURN_FAILURE_RATE", "0")

if not 0 < BURN_P50_S <= BURN_P95_S:
    raise ValueError("need 0 < LOADTEST_BURN_P50_S <= LOADTEST_BURN_P95_S")

_MU = math.log(BURN_P50_S)
_SIGMA = (math.log(BURN_P95_S) - _MU) / Z_95
# The OS's randomness, not the module's: every forked pool child would
# otherwise start from the same seed and draw the same delays.
_rng = random.SystemRandom()


def simulated_burn(amount: Decimal) -> str:
    """Stand-in for `xrpl_service.burn_tokens`: block for a testnet-like time,
    then return a synthetic hash or raise like a failed Payment."""
    time.sleep(_rng.lognormvariate(_MU, _SIGMA))
    if _rng.random() < FAILURE_RATE:
        raise RuntimeError("burn Payment failed: tecPATH_DRY (simulated)")
    return HASH_PREFIX + secrets.token_hex(30).upper()


def main() -> None:
    xrpl_service.burn_tokens = simulated_burn

    from remitx_worker.__main__ import main as run_worker

    run_worker()


if __name__ == "__main__":
    main()
