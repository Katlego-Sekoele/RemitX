"""record treasury funding

Gives the platform accounts the starting balances the old
``scripts/seed_platform_accounts.py`` gave them. That script left every account
at zero except one ``treasury_funding`` transaction, issuer → treasury wallet,
for the wallet's real uctusd balance on the XRPL testnet (ECO5040W
clarifications: the lecturer funds the platform wallet directly — RemitX never
buys or mints tokens). This revision records the same transaction, reading the
balance of ``PLATFORM_WALLET_ADDRESS`` at deploy time, once per database.

- Already recorded (environments that ran the script): nothing to do.
- No ``PLATFORM_WALLET_ADDRESS`` (CI, tests, a local stack without a wallet):
  skipped, and the treasury starts at zero.
- A wallet with nothing on-chain yet: skipped, as the script did.
- A wallet whose balance can't be read: the migration fails. A skipped
  revision never runs again, so failing is what lets the next deploy retry.

The downgrade removes the funding this revision recorded, found by its
deterministic id, and takes its amount back off both balances.

Revision ID: a77cbaf94587
Revises: f126ff62af9a
Create Date: 2026-09-24 13:52:48.402207+00:00

"""

import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import sqlalchemy as sa
from alembic import op
from remitx_api.config import Config
from remitx_api.models.orm.account import CURRENCY_TOKEN
from remitx_api.models.orm.platform_account_seed import (
    ISSUER_LABEL,
    PLATFORM_ACCOUNT_NAMESPACE,
    TREASURY_WALLET_LABEL,
)

# revision identifiers, used by Alembic.
revision: str = "a77cbaf94587"
down_revision: str | None = "f126ff62af9a"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None

log = logging.getLogger("alembic.runtime.migration")

_FUNDING_TX_ID = uuid.uuid5(PLATFORM_ACCOUNT_NAMESPACE, "treasury_funding:initial")

_accounts = sa.table(
    "accounts",
    sa.column("account_id", sa.Uuid()),
    sa.column("label", sa.Text()),
    sa.column("type", sa.Text()),
    sa.column("account_balance", sa.Numeric(20, 8)),
)
_transactions = sa.table(
    "transactions",
    sa.column("tx_id", sa.Uuid()),
    sa.column("type", sa.Text()),
    sa.column("credit_account_id", sa.Uuid()),
    sa.column("debit_account_id", sa.Uuid()),
    sa.column("amount", sa.Numeric(20, 8)),
    sa.column("currency", sa.Text()),
    sa.column("status", sa.Text()),
    sa.column("created_at", sa.DateTime(timezone=True)),
    sa.column("confirmed_at", sa.DateTime(timezone=True)),
)


def _platform_account_id(connection, label: str) -> uuid.UUID:
    account_id = connection.scalar(
        sa.select(_accounts.c.account_id).where(
            _accounts.c.label == label, _accounts.c.type != "USER"
        )
    )
    if account_id is None:
        raise RuntimeError(f"Platform account {label!r} is missing")
    return account_id


def _on_chain_uctusd_balance(config: Config, address: str) -> Decimal:
    """The wallet's uctusd trust-line balance, as the old script read it."""
    from xrpl.clients import JsonRpcClient
    from xrpl.models.requests import AccountLines

    result = (
        JsonRpcClient(config.XRPL_TESTNET_URL)
        .request(
            AccountLines(
                account=address, peer=config.UCTUSD_ISSUER, ledger_index="validated"
            )
        )
        .result
    )
    if "lines" not in result:
        raise RuntimeError(f"XRPL testnet answered without trust lines: {result}")
    for line in result["lines"]:
        if line["currency"] == config.UCTUSD_CURRENCY_CODE_HEX:
            return Decimal(line["balance"])
    return Decimal("0")


def _move(connection, account_id: uuid.UUID, amount: Decimal) -> None:
    connection.execute(
        _accounts.update()
        .where(_accounts.c.account_id == account_id)
        .values(account_balance=_accounts.c.account_balance + amount)
    )


def upgrade() -> None:
    connection = op.get_bind()
    treasury_id = _platform_account_id(connection, TREASURY_WALLET_LABEL)
    issuer_id = _platform_account_id(connection, ISSUER_LABEL)

    already_funded = connection.scalar(
        sa.select(sa.func.count())
        .select_from(_transactions)
        .where(
            _transactions.c.type == "treasury_funding",
            _transactions.c.debit_account_id == treasury_id,
        )
    )
    if already_funded:
        log.info("Treasury funding already recorded: nothing to do")
        return

    config = Config()
    address = config.PLATFORM_WALLET_ADDRESS
    if not address:
        log.info("PLATFORM_WALLET_ADDRESS is not set: the treasury starts at zero")
        return

    try:
        balance = _on_chain_uctusd_balance(config, address)
    except Exception as exc:
        raise RuntimeError(
            f"Could not read the uctusd balance of {address} from "
            f"{config.XRPL_TESTNET_URL}. This revision records it once, so it "
            "fails rather than skip; retry when the testnet is reachable, or "
            "unset PLATFORM_WALLET_ADDRESS to start the treasury at zero."
        ) from exc

    if balance <= 0:
        log.info("%s holds no uctusd on-chain: the treasury starts at zero", address)
        return

    now = datetime.now(UTC)
    connection.execute(
        _transactions.insert().values(
            tx_id=_FUNDING_TX_ID,
            type="treasury_funding",
            credit_account_id=issuer_id,
            debit_account_id=treasury_id,
            amount=balance,
            currency=CURRENCY_TOKEN,
            status="confirmed",
            created_at=now,
            confirmed_at=now,
        )
    )
    _move(connection, issuer_id, -balance)
    _move(connection, treasury_id, balance)
    log.info("Recorded treasury funding of %s uctusd from %s", balance, address)


def downgrade() -> None:
    connection = op.get_bind()
    funding = connection.execute(
        sa.select(
            _transactions.c.amount,
            _transactions.c.credit_account_id,
            _transactions.c.debit_account_id,
        ).where(_transactions.c.tx_id == _FUNDING_TX_ID)
    ).first()
    if funding is None:
        return
    amount, issuer_id, treasury_id = funding
    connection.execute(
        _transactions.delete().where(_transactions.c.tx_id == _FUNDING_TX_ID)
    )
    _move(connection, issuer_id, amount)
    _move(connection, treasury_id, -amount)
