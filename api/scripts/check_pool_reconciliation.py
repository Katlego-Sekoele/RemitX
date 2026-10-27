"""Compare the Treasury Wallet's on-chain UCTUSD with the ledger float.

    python scripts/check_pool_reconciliation.py

Run from ``api/``. Uses the repo-root ``.env``. Exit 0 when they match.
Read-only: it does not load the treasury key and it sends nothing.

A database from before the EVM switch still opens the treasury from the
XRPL balance (section 8 of docs/stokvel_integration.md). This command then
prints FAIL until that balance is rebased. That FAIL is the rebase, not a
stokvel over-burn.

A burn's hash is stored before the send. While that leg is still
`processing`, `in-flight` is its net and it is not part of `ledger`. If the
chain has already moved by that net, the FAIL line says so.

The chain read lives in ``remitx_worker.evm_service``. This file is a demo
command, not the API process, which must not import the worker.
"""

import sys

from remitx_api.config import Config
from remitx_api.extensions import db
from remitx_api.services.stokvel_reconciliation_service import check_pool_reconciliation
from remitx_worker.evm_service import get_token_balance, treasury_address


def main() -> int:
    db.init(Config.DATABASE_URL)
    token = db.open_session()
    try:
        result = check_pool_reconciliation(get_token_balance(treasury_address()))
    finally:
        db.close_session(token)
    print(f"ledger    {result.expected}")
    print(f"on-chain  {result.on_chain}")
    print(f"in-flight {result.in_flight}")
    print(f"contract  {result.contract_held}")
    if result.matches:
        print("PASS")
        return 0
    print("FAIL")
    if result.gap_is_in_flight:
        print(
            "the gap is processing legs that already have a hash; "
            "the hash is written before the send, so they stay out of ledger"
        )
    return 1


if __name__ == "__main__":
    sys.exit(main())
