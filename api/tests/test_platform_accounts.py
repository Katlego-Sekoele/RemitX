"""Who an account may belong to, and the platform accounts every environment
is seeded with.

A customer's account must reference a real user; RemitX's own platform
accounts belong to no one. The CHECK and the foreign key on `accounts`
enforce it, in SQLite here as in Postgres.
"""

import uuid

import pytest
from remitx_api.controllers.user_controller import UserController
from remitx_api.extensions import db
from remitx_api.models.orm.account import (
    CURRENCY_ZAR,
    PAYOUT_CURRENCIES,
    TYPE_PLATFORM_FIAT,
    TYPE_PLATFORM_REVENUE,
    TYPE_USER,
    Account,
)
from remitx_api.models.orm.platform_account_seed import PLATFORM_ACCOUNT_SEEDS
from remitx_api.repositories.account_repository import AccountRepository
from remitx_api.services.remittance_service import (
    REMITX_TREASURY_WALLET_LABEL,
    TOKEN_ISSUER_LABEL,
)
from sqlalchemy.exc import IntegrityError
from tests.platform_account_helpers import seed_platform_accounts


def _customer_account(user_id: uuid.UUID | None) -> Account:
    return Account(
        user_id=user_id,
        type=TYPE_USER,
        reference=f"owner-{uuid.uuid4().hex[:8]}-zar",
        account_currency=CURRENCY_ZAR,
        label="(ZAR Account)",
    )


def _refused(account: Account) -> None:
    db.session.add(account)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_a_customer_account_must_belong_to_a_user(app_context):
    _refused(_customer_account(None))


def test_a_customer_account_must_belong_to_a_real_user(app_context):
    _refused(_customer_account(uuid.uuid4()))


def test_a_platform_account_cannot_belong_to_a_user(app_context):
    user = UserController().ensure_provisioned(
        "user_platform_owner", lambda: "owner@example.com", lambda: "Owner"
    )
    _refused(
        Account(
            user_id=user.id,
            type=TYPE_PLATFORM_FIAT,
            account_currency=CURRENCY_ZAR,
            label="RemitX SA Bank Account",
        )
    )


def test_the_seeded_platform_accounts_belong_to_no_user(app_context):
    seed_platform_accounts()

    assert all(
        account.user_id is None
        for account in db.session.query(Account).filter(Account.type != TYPE_USER)
    )


def test_the_seed_has_every_platform_account_the_services_look_up(app_context):
    """The migration inserts `PLATFORM_ACCOUNT_SEEDS`, so a label the services
    find by, or a (type, currency) pair they need, missing from it would only
    surface as a failed deposit or transfer."""
    seed_platform_accounts()
    accounts = AccountRepository()

    for label in (REMITX_TREASURY_WALLET_LABEL, TOKEN_ISSUER_LABEL):
        assert accounts.get_platform_account_by_label(label) is not None, label
    for currency in PAYOUT_CURRENCIES:
        for type_ in (TYPE_PLATFORM_FIAT, TYPE_PLATFORM_REVENUE):
            assert accounts.get_platform_account(type_, currency) is not None, (
                type_,
                currency,
            )


def test_platform_account_seeds_are_unique():
    labels = [seed.label for seed in PLATFORM_ACCOUNT_SEEDS]
    pairs = [(seed.type, seed.currency) for seed in PLATFORM_ACCOUNT_SEEDS]
    ids = [seed.account_id for seed in PLATFORM_ACCOUNT_SEEDS]

    assert len(set(labels)) == len(labels)
    # `get_platform_account` looks up by (type, currency) and takes the first.
    assert len(set(pairs)) == len(pairs)
    assert len(set(ids)) == len(ids)
