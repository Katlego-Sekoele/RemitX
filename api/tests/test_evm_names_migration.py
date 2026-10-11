"""The EVM names (R3-02): burn hashes recorded before
`transactions.evm_tx_hash` existed are copied into it, and the treasury
wallet's type and label are renamed. Migrations only ever run on Postgres, so
this runs in the `postgres` lane (TEST_DATABASE_URL)."""

import uuid

import pytest
from remitx_api.models.orm.account import TYPE_EVM_WALLET
from remitx_api.models.orm.platform_account_seed import (
    ISSUER_LABEL,
    TREASURY_WALLET_LABEL,
)
from sqlalchemy import create_engine, text
from tests.postgres_helpers import migrate

pytestmark = pytest.mark.postgres

# The migration before `evm_tx_hash` is added: hashes live in
# `xrpl_tx_hash` only, and the treasury still has its XRPL type and label.
BEFORE_RENAME = "7895afbbf058"
BURN_HASH = "0xabc123"


def _account_id(connection, label: str) -> uuid.UUID:
    return connection.scalar(
        text("SELECT account_id FROM accounts WHERE label = :label"),
        {"label": label},
    )


def test_old_burn_hashes_and_the_treasury_wallet_are_renamed(empty_postgres_url):
    migrate(empty_postgres_url, BEFORE_RENAME)
    engine = create_engine(empty_postgres_url)
    try:
        with engine.begin() as connection:
            treasury = _account_id(connection, "RemitX XRPL Treasury Wallet")
            connection.execute(
                text(
                    "INSERT INTO transactions (tx_id, type, credit_account_id,"
                    " debit_account_id, amount, currency, status, created_at,"
                    " xrpl_tx_hash) VALUES (:tx_id, 'token_burn', :treasury,"
                    " :issuer, 10, 'uctusd', 'confirmed', now(), :hash)"
                ),
                {
                    "tx_id": uuid.uuid4(),
                    "treasury": treasury,
                    "issuer": _account_id(connection, ISSUER_LABEL),
                    "hash": BURN_HASH,
                },
            )

        migrate(empty_postgres_url)

        with engine.connect() as connection:
            hashes = connection.execute(
                text("SELECT xrpl_tx_hash, evm_tx_hash FROM transactions")
            ).all()
            wallet = connection.execute(
                text("SELECT type, label FROM accounts WHERE account_id = :id"),
                {"id": treasury},
            ).one()
    finally:
        engine.dispose()

    assert hashes == [(BURN_HASH, BURN_HASH)]
    assert tuple(wallet) == (TYPE_EVM_WALLET, TREASURY_WALLET_LABEL)
