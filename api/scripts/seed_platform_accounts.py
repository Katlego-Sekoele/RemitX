"""
Seed RemitX's platform accounts, and the admin who owns them.

Platform accounts (RemitX's per-country bank accounts, XRPL treasury wallet,
fee revenue) need a real admin's user_id — but User rows are normally only
created just-in-time
on first Clerk login (see UserController.ensure_provisioned). This script
provisions that admin User row directly, using the same provisioning path a
real first login takes, so their eventual real login finds this row instead
of creating a duplicate.

Also records the Treasury Wallet's real, pre-funded uctusd balance as a
one-time `treasury_funding` transaction (see ECO5040W's clarifications: the
lecturer funds the platform wallet directly on the testnet — RemitX never
buys or mints tokens), so `accounts.account_balance` matches the real
on-chain balance instead of silently starting at 0.

To Run:
    cd api && source .venv/bin/activate
    python scripts/seed_platform_accounts.py

Requires ADMIN_CLERK_USER_ID in .env (see .env.example) — the real Clerk
`sub` claim of whoever will administer this system. That account is granted
every staff role in the RBAC catalogue (`alembic upgrade head` seeds it), which
is what actually opens the admin portal and its permission-gated routes.

Recording the treasury funding additionally requires PLATFORM_WALLET_ADDRESS
and network access to XRPL_TESTNET_URL — if either is unavailable, that one
step is skipped with a warning rather than failing the whole run.

Re-running skips whatever's already there instead of creating duplicates.
"""

import os
import sys
from datetime import UTC, datetime
from decimal import Decimal

from remitx_api.auth.clerk import fetch_user_email, fetch_user_first_name
from remitx_api.config import Config
from remitx_api.controllers.user_controller import UserController
from remitx_api.extensions import db
from remitx_api.models.orm.account import (
    CURRENCY_NAD,
    CURRENCY_TOKEN,
    CURRENCY_USD,
    CURRENCY_ZAR,
    CURRENCY_ZWL,
    TYPE_EXTERNAL,
    TYPE_PLATFORM_FIAT,
    TYPE_PLATFORM_REVENUE,
    TYPE_XRPL_WALLET,
    Account,
)
from remitx_api.models.orm.role import Role
from remitx_api.models.orm.transaction import (
    STATUS_CONFIRMED,
    TYPE_TREASURY_FUNDING,
    Transaction,
)
from remitx_api.models.orm.user import User
from remitx_api.models.orm.user_role import UserRole
from remitx_api.repositories.account_repository import AccountRepository
from remitx_api.repositories.transaction_repository import TransactionRepository
from sqlalchemy import select

# One real bank account per country RemitX settles fiat in, each in that
# country's own currency. Every one of these gets a matching Fee Revenue
# account in the same currency below — a ZAR fee can't be booked into a USD
# revenue account any more than it could be booked into the USD bank account.
COUNTRY_BANK_ACCOUNTS = (
    ("RemitX SA", CURRENCY_ZAR),
    ("RemitX US", CURRENCY_USD),
    ("RemitX ZIM", CURRENCY_ZWL),
    ("RemitX NAM", CURRENCY_NAD),
)

TREASURY_WALLET_LABEL = "RemitX XRPL Treasury Wallet"
# The issuing address (ECO5040W clarifications) — the same account plays
# both roles: source of the one-time pre-funding, destination of every
# future withdrawal burn. Sourced from Config.UCTUSD_ISSUER_LABEL so this
# seeded label can't drift from the one services/remittance_service.py
# looks up.
ISSUER_LABEL = Config().UCTUSD_ISSUER_LABEL

PLATFORM_ACCOUNTS = (
    *(
        (f"{prefix} Bank Account", TYPE_PLATFORM_FIAT, currency)
        for prefix, currency in COUNTRY_BANK_ACCOUNTS
    ),
    (TREASURY_WALLET_LABEL, TYPE_XRPL_WALLET, CURRENCY_TOKEN),
    *(
        (f"{prefix} Fee Revenue", TYPE_PLATFORM_REVENUE, currency)
        for prefix, currency in COUNTRY_BANK_ACCOUNTS
    ),
    (ISSUER_LABEL, TYPE_EXTERNAL, CURRENCY_TOKEN),
)


def main() -> None:
    admin_clerk_id = os.environ.get("ADMIN_CLERK_USER_ID")
    if not admin_clerk_id:
        print("ADMIN_CLERK_USER_ID is not set — see .env.example", file=sys.stderr)
        sys.exit(1)

    config = Config()
    db.init(config.DATABASE_URL)
    token = db.open_session()
    try:
        admin = _ensure_admin(admin_clerk_id, config)
        accounts_by_label = _seed_platform_accounts(admin.id)
        _seed_treasury_funding(
            accounts_by_label[TREASURY_WALLET_LABEL], accounts_by_label[ISSUER_LABEL]
        )
    finally:
        db.close_session(token)


def _ensure_admin(clerk_user_id: str, config: Config) -> User:
    """Provision the admin's User row and grant it every staff role, idempotently."""
    admin = UserController().ensure_provisioned(
        clerk_user_id,
        lambda: fetch_user_email(clerk_user_id, config),
        lambda: fetch_user_first_name(clerk_user_id, config),
    )
    _grant_every_staff_role(admin)
    print(f"Admin: {admin.id} ({admin.email or clerk_user_id})")
    return admin


def _grant_every_staff_role(admin: User) -> None:
    """Grant each `is_admin` role in the catalogue to the local super admin.

    Deliberately broad, and only because this is the one-off local bootstrap:
    there is no in-app way to grant a role yet, so the account named by
    ADMIN_CLERK_USER_ID has to arrive holding all of them to exercise the
    staff portal end to end. Real access is per role, per permission — the
    routes gate on `PermissionCode` (auth/permissions.py), and nothing reads
    a flag on the User row.
    """
    staff_roles = db.session.scalars(
        select(Role).where(Role.is_admin.is_(True)).order_by(Role.name)
    ).all()
    held = set(
        db.session.scalars(
            select(UserRole.role_id)
            .where(UserRole.user_id == admin.id)
            .where(UserRole.revoked_at.is_(None))
        ).all()
    )

    granted = []
    for role in staff_roles:
        if role.role_id in held:
            continue
        db.session.add(UserRole(user_id=admin.id, role_id=role.role_id))
        granted.append(role.name)

    if granted:
        db.session.commit()
        print(f"Granted roles: {', '.join(granted)}")
    else:
        print("Skipped (already granted): every staff role")


def _seed_platform_accounts(admin_id) -> dict[str, Account]:
    """Create every platform/external account not already there.

    EXTERNAL accounts (the issuer/exchange) have no admin owner — everything
    else does. Returns every account by label, newly created or not, so the
    caller always has a real Account to work with either way.
    """
    account_repo = AccountRepository()
    accounts_by_label: dict[str, Account] = {}
    for label, account_type, currency in PLATFORM_ACCOUNTS:
        existing = account_repo.get_platform_account_by_label(label)
        if existing is not None:
            print(f"Skipped (already exists): {label}")
            accounts_by_label[label] = existing
            continue
        account = Account(
            user_id=None if account_type == TYPE_EXTERNAL else admin_id,
            type=account_type,
            account_currency=currency,
            label=label,
        )
        accounts_by_label[label] = account_repo.save(account)
        print(f"Created: {label}")
    return accounts_by_label


def _seed_treasury_funding(treasury_account: Account, issuer_account: Account) -> None:
    """Record the Treasury Wallet's real, pre-funded uctusd balance as a
    one-time `treasury_funding` transaction. Idempotent — skips if already
    recorded, and skips (rather than failing the whole script) if the
    on-chain balance can't be read right now.
    """
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
        # again later", and should never take down the rest of this script.
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
    account_repo = AccountRepository()
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
