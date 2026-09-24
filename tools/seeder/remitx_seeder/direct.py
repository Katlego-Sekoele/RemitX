"""The only writes the seeder makes that no product flow makes.

Every other write goes through the backend's own controllers and services, so
the business rules apply by construction. A function here exists because the
product has no flow for it yet, and each one says which flow it stands in for.
Adding to this module is a visible, reviewable decision to bypass the rules;
`verify` runs after every seed run to catch anything these writes get wrong.

Rules for this module:

- Use the backend's repositories and models, never raw SQL, so a column
  rename breaks here loudly rather than writing the wrong thing.
- Keep the ledger invariant: an account balance only changes together with a
  `confirmed` transaction that explains it, in the same commit.
- Say which missing product flow the function stands in for.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from remitx_api.config import Config
from remitx_api.extensions import db
from remitx_api.models.orm.account import CURRENCY_TOKEN, Account
from remitx_api.models.orm.transaction import (
    STATUS_CONFIRMED,
    TYPE_TREASURY_FUNDING,
    Transaction,
)
from remitx_api.repositories.account_repository import AccountRepository
from remitx_api.services.remittance_service import REMITX_TREASURY_WALLET_LABEL


def open_payout_account(
    user_id: uuid.UUID, base_reference: str, currency: str
) -> Account:
    """Give a recipient a fiat account in their payout currency.

    Stands in for: opening a USD, ZWL or NAD wallet. Signup creates only ZAR
    and uctusd accounts, and a beneficiary can only be added in a currency the
    recipient already holds, so without this no ZWL, NAD or USD corridor could
    exist. Uses `AccountRepository.get_or_create_user_account`, the same call
    settlement makes when it pays a recipient in a new currency.
    """
    account = AccountRepository().get_or_create_user_account(
        user_id, base_reference, currency
    )
    db.session.commit()
    return account


def record_treasury_top_up(amount: Decimal) -> Transaction | None:
    """Put back into the treasury what simulated settlements burned.

    Stands in for: nothing, deliberately. A simulated burn lowers the
    treasury's ledger balance without any tokens leaving the chain, so the
    ledger would read less than the real wallet holds. One `treasury_funding`
    row per seed run (issuer -> treasury, confirmed) restores the match. The
    run manifest records its id, so it can always be told apart from any
    other funding row.
    """
    if amount <= 0:
        return None
    accounts = AccountRepository()
    treasury = accounts.get_platform_account_by_label(REMITX_TREASURY_WALLET_LABEL)
    issuer = accounts.get_platform_account_by_label(Config().UCTUSD_ISSUER_LABEL)
    if treasury is None or issuer is None:
        raise RuntimeError(
            "Treasury or issuer account missing: run `alembic upgrade head` "
            "(or Reset) first"
        )
    transaction = Transaction(
        type=TYPE_TREASURY_FUNDING,
        credit_account_id=issuer.account_id,
        debit_account_id=treasury.account_id,
        amount=amount,
        currency=CURRENCY_TOKEN,
        status=STATUS_CONFIRMED,
    )
    db.session.add(transaction)
    db.session.flush()
    transaction.processed_at = transaction.created_at
    transaction.confirmed_at = transaction.created_at
    accounts.decrease_balance(issuer.account_id, amount)
    accounts.increase_balance(treasury.account_id, amount)
    db.session.commit()
    return transaction
