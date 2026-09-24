"""
Record the Treasury Wallet's real, pre-funded uctusd balance as a one-time
`treasury_funding` transaction (see ECO5040W's clarifications: the lecturer
funds the platform wallet directly on the testnet — RemitX never buys or
mints tokens), so `accounts.account_balance` matches the real on-chain
balance instead of silently starting at 0.

Not a migration because it reads the balance from the XRPL testnet. The
platform accounts it books against come from `alembic upgrade head` (see
remitx_api/models/orm/platform_account_seed.py), so run that first.

To Run:
    cd api && source .venv/bin/activate
    alembic upgrade head
    python scripts/record_treasury_funding.py

Requires PLATFORM_WALLET_ADDRESS and network access to XRPL_TESTNET_URL — if
either is unavailable, it is skipped with a warning rather than failing.
Re-running skips a funding already recorded.
"""

import os
import sys
from datetime import UTC, datetime
from decimal import Decimal

from remitx_api.config import Config
from remitx_api.extensions import db
from remitx_api.models.orm.account import CURRENCY_TOKEN
from remitx_api.models.orm.platform_account_seed import (
    ISSUER_LABEL,
    TREASURY_WALLET_LABEL,
)
from remitx_api.models.orm.transaction import (
    STATUS_CONFIRMED,
    TYPE_TREASURY_FUNDING,
    Transaction,
)
from remitx_api.repositories.account_repository import AccountRepository
from remitx_api.repositories.transaction_repository import TransactionRepository


def main() -> None:
    config = Config()
    db.init(config.DATABASE_URL)
    token = db.open_session()
    try:
        _record_treasury_funding()
    finally:
        db.close_session(token)


def _record_treasury_funding() -> None:
    """Record the Treasury Wallet's real, pre-funded uctusd balance as a
    one-time `treasury_funding` transaction. Idempotent — skips if already
    recorded, and skips with a warning if the on-chain balance can't be read
    right now.
    """
    account_repo = AccountRepository()
    treasury_account = account_repo.get_platform_account_by_label(TREASURY_WALLET_LABEL)
    issuer_account = account_repo.get_platform_account_by_label(ISSUER_LABEL)
    if treasury_account is None or issuer_account is None:
        print(
            "The platform accounts are missing — run `alembic upgrade head` first",
            file=sys.stderr,
        )
        sys.exit(1)

    transaction_repo = TransactionRepository()
    if (
        transaction_repo.get_by_transaction_type_and_debit_account(
            TYPE_TREASURY_FUNDING, treasury_account.account_id
        )
        is not None
    ):
        print("Skipped (already recorded): treasury funding")
        return

    address = os.environ.get("PLATFORM_WALLET_ADDRESS", "")
    if not address:
        print(
            "PLATFORM_WALLET_ADDRESS is not set — skipping treasury funding record",
            file=sys.stderr,
        )
        return

    try:
        balance = _query_uctusd_balance(address)
    except Exception as exc:  # noqa: BLE001 — see rationale below
        # Deliberately broad: this is a one-off setup step, not the request
        # path — a network hiccup here shouldn't be any noisier than "try
        # again later".
        print(f"Could not query on-chain balance for {address}: {exc}", file=sys.stderr)
        return

    if balance <= 0:
        print(
            f"Treasury wallet {address} has no uctusd balance on-chain yet — skipping"
        )
        return

    transaction_repo.add(
        Transaction(
            type=TYPE_TREASURY_FUNDING,
            credit_account_id=issuer_account.account_id,
            debit_account_id=treasury_account.account_id,
            amount=balance,
            currency=CURRENCY_TOKEN,
            status=STATUS_CONFIRMED,
            confirmed_at=datetime.now(UTC),
        )
    )
    account_repo.decrease_balance(issuer_account.account_id, balance)
    account_repo.increase_balance(treasury_account.account_id, balance)
    db.session.commit()
    print(f"Recorded treasury funding: {balance} uctusd")


def _query_uctusd_balance(address: str) -> Decimal:
    """The real on-chain uctusd balance for `address`, via the XRPL testnet.

    Ported from platform_wallet/scripts/create_xprl_platform_wallet.py's
    `uctusd_balance` rather than imported from it — that script is a
    standalone setup tool with its own pyproject.toml; this keeps the two
    packages uncoupled.
    """
    from xrpl.clients import JsonRpcClient
    from xrpl.models.requests import AccountLines

    testnet_url = os.environ.get(
        "XRPL_TESTNET_URL", "https://s.altnet.rippletest.net:51234/"
    )
    issuer = os.environ.get("UCTUSD_ISSUER", "rELez4x4Zqv3KYqboYVfrYPF8521Ycbxa5")
    currency_hex = os.environ.get(
        "UCTUSD_CURRENCY_CODE_HEX", "5543545553440000000000000000000000000000"
    )

    client = JsonRpcClient(testnet_url)
    lines = client.request(
        AccountLines(account=address, peer=issuer, ledger_index="validated")
    ).result["lines"]
    for line in lines:
        if line["currency"] == currency_hex:
            return Decimal(line["balance"])
    return Decimal("0")


if __name__ == "__main__":
    main()
