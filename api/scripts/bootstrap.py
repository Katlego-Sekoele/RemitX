"""
One-off setup for a new environment: the two steps a migration can't do,
because each needs a service outside the database. RemitX's platform accounts
themselves come from `alembic upgrade head` (see
remitx_api/models/orm/platform_account_seed.py), so run that first.

1. The admin (needs ADMIN_CLERK_USER_ID and Clerk). User rows are normally
   created just-in-time on first Clerk login (see
   UserController.ensure_provisioned). This provisions the admin's row through
   that same path, so their eventual real login finds it instead of creating a
   duplicate, and grants it every staff role in the RBAC catalogue — which is
   what opens the admin portal and its permission-gated routes.

2. Treasury funding (needs PLATFORM_WALLET_ADDRESS and network access to
   XRPL_TESTNET_URL). Records the Treasury Wallet's real, pre-funded uctusd
   balance as a one-time `treasury_funding` transaction (see ECO5040W's
   clarifications: the lecturer funds the platform wallet directly on the
   testnet — RemitX never buys or mints tokens), so
   `accounts.account_balance` matches the real on-chain balance instead of
   silently starting at 0.

To Run:
    cd api && source .venv/bin/activate
    alembic upgrade head
    python scripts/bootstrap.py

A step whose settings are missing, or whose service can't be reached, is
skipped with a warning rather than failing the whole run. Re-running skips
whatever's already there instead of creating duplicates.
"""

import os
import sys
from datetime import UTC, datetime
from decimal import Decimal

from remitx_api.auth.clerk import fetch_user_email, fetch_user_first_name
from remitx_api.config import Config
from remitx_api.controllers.user_controller import UserController
from remitx_api.extensions import db
from remitx_api.models.orm.account import CURRENCY_TOKEN
from remitx_api.models.orm.platform_account_seed import (
    ISSUER_LABEL,
    TREASURY_WALLET_LABEL,
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


def main() -> None:
    config = Config()
    db.init(config.DATABASE_URL)
    token = db.open_session()
    try:
        admin_clerk_id = os.environ.get("ADMIN_CLERK_USER_ID")
        if admin_clerk_id:
            _ensure_admin(admin_clerk_id, config)
        else:
            print(
                "ADMIN_CLERK_USER_ID is not set — skipping the admin "
                "(see .env.example)",
                file=sys.stderr,
            )
        _seed_treasury_funding()
    finally:
        db.close_session(token)


def _ensure_admin(clerk_user_id: str, config: Config) -> None:
    """Provision the admin's User row and grant it every staff role, idempotently."""
    admin = UserController().ensure_provisioned(
        clerk_user_id,
        lambda: fetch_user_email(clerk_user_id, config),
        lambda: fetch_user_first_name(clerk_user_id, config),
    )
    _grant_every_staff_role(admin)
    print(f"Admin: {admin.id} ({admin.email or clerk_user_id})")


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


def _seed_treasury_funding() -> None:
    """Record the Treasury Wallet's real, pre-funded uctusd balance as a
    one-time `treasury_funding` transaction. Idempotent — skips if already
    recorded, and skips (rather than failing the whole script) if the
    on-chain balance can't be read right now.
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
