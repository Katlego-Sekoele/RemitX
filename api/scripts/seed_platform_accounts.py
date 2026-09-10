"""
Seed RemitX's platform accounts, and the admin who owns them.

Platform accounts (RemitX's bank account, treasury wallet, fee revenue) need
a real admin's user_id — but User rows are normally only created just-in-time
on first Clerk login (see UserController.ensure_provisioned). This script
provisions that admin User row directly, using the same provisioning path a
real first login takes, so their eventual real login finds this row instead
of creating a duplicate.

To Run:
    cd api && source .venv/bin/activate
    python scripts/seed_platform_accounts.py

Requires ADMIN_CLERK_USER_ID in .env (see .env.example) — the real Clerk
`sub` claim of whoever will administer this system.

Re-running skips whatever's already there instead of creating duplicates.
"""

import os
import sys

from remitx_api.auth.clerk import fetch_user_email, fetch_user_first_name
from remitx_api.config import Config
from remitx_api.controllers.user_controller import UserController
from remitx_api.extensions import db
from remitx_api.models.orm.account import (
    CURRENCY_TOKEN,
    CURRENCY_ZAR,
    TYPE_PLATFORM_FIAT,
    TYPE_PLATFORM_REVENUE,
    TYPE_XRPL_WALLET,
    Account,
)
from remitx_api.models.orm.user import ROLE_ADMIN, User
from remitx_api.repositories.account_repository import AccountRepository
from remitx_api.repositories.user_repository import UserRepository

PLATFORM_ACCOUNTS = (
    ("RemitX SA Bank Account", TYPE_PLATFORM_FIAT, CURRENCY_ZAR),
    ("RemitX Treasury Wallet", TYPE_XRPL_WALLET, CURRENCY_TOKEN),
    ("RemitX Fee Revenue", TYPE_PLATFORM_REVENUE, CURRENCY_ZAR),
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
        _seed_platform_accounts(admin.id)
    finally:
        db.close_session(token)


def _ensure_admin(clerk_user_id: str, config: Config) -> User:
    """Provision the admin's User row and promote it, idempotently."""
    admin = UserController().ensure_provisioned(
        clerk_user_id,
        lambda: fetch_user_email(clerk_user_id, config),
        lambda: fetch_user_first_name(clerk_user_id, config),
    )
    if admin.role != ROLE_ADMIN:
        admin.role = ROLE_ADMIN
        UserRepository().save(admin)
    print(f"Admin: {admin.id} ({admin.email or clerk_user_id})")
    return admin


def _seed_platform_accounts(admin_id) -> None:
    account_repo = AccountRepository()
    for label, account_type, currency in PLATFORM_ACCOUNTS:
        if account_repo.get_platform_account(label) is not None:
            print(f"Skipped (already exists): {label}")
            continue
        account = Account(
            user_id=admin_id,
            type=account_type,
            account_currency=currency,
            label=label,
        )
        account_repo.save(account)
        print(f"Created: {label}")


if __name__ == "__main__":
    main()
