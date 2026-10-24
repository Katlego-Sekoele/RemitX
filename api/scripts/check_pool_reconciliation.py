"""Compare the Treasury Wallet's on-chain UCTUSD with the ledger float.

    python scripts/check_pool_reconciliation.py

Run from ``api/``. Uses the repo-root ``.env``. Exit 0 when they match.
Read-only: it does not load the treasury key and it sends nothing.

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
    print(f"contract  {result.contract_held}")
    print("PASS" if result.matches else "FAIL")
    return 0 if result.matches else 1


if __name__ == "__main__":
    sys.exit(main())
