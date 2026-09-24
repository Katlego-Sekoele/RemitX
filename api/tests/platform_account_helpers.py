"""RemitX's platform accounts in throwaway test databases, as the
platform-accounts migration inserts them: every row in
`PLATFORM_ACCOUNT_SEEDS`, owned by no user, at a zero balance.
"""

from __future__ import annotations

from remitx_api.extensions import db
from remitx_api.models.orm.account import Account
from remitx_api.models.orm.platform_account_seed import PLATFORM_ACCOUNT_SEEDS


def seed_platform_accounts() -> dict[str, Account]:
    """Insert every platform account and return them by label."""
    accounts = {
        seed.label: Account(
            account_id=seed.account_id,
            user_id=None,
            type=seed.type,
            account_currency=seed.currency,
            label=seed.label,
        )
        for seed in PLATFORM_ACCOUNT_SEEDS
    }
    db.session.add_all(accounts.values())
    db.session.commit()
    return accounts
