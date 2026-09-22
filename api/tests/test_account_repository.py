from decimal import Decimal

from remitx_api.controllers.user_controller import UserController
from remitx_api.extensions import db
from remitx_api.models.orm.account import CURRENCY_TOKEN, CURRENCY_ZAR
from remitx_api.models.orm.transaction import (
    STATUS_PENDING,
    STATUS_PROCESSING,
    TYPE_REMITTANCE,
    Transaction,
)
from remitx_api.repositories.account_repository import AccountRepository


def test_eager_accounts_share_one_base_reference(app_context):
    user = UserController().ensure_provisioned(
        "user_dual", lambda: "dual@example.com", lambda: "Dual"
    )

    zar = AccountRepository().get_user_account(user.id, CURRENCY_ZAR)
    token = AccountRepository().get_user_account(user.id, CURRENCY_TOKEN)

    assert zar.reference == f"{user.base_reference}-zar"
    assert token.reference == f"{user.base_reference}-tok"


def test_second_same_named_signup_gets_the_next_number(app_context):
    UserController().ensure_provisioned(
        "user_a", lambda: "a@example.com", lambda: "Sian"
    )
    second = UserController().ensure_provisioned(
        "user_b", lambda: "b@example.com", lambda: "Sian"
    )

    assert second.base_reference == "sian2"
    zar = AccountRepository().get_user_account(second.id, CURRENCY_ZAR)
    assert zar.reference == "sian2-zar"


def test_get_by_reference_finds_the_matching_account(app_context):
    """A reference is globally unique and already carries its own currency
    suffix (e.g. "-zar" vs "-tok"), so looking it up alone must return the
    one account it belongs to.
    """
    user = UserController().ensure_provisioned(
        "user_scoped", lambda: "scoped@example.com", lambda: "Scoped"
    )
    account_repo = AccountRepository()

    zar_reference = f"{user.base_reference}-zar"
    token_reference = f"{user.base_reference}-tok"

    zar_account = account_repo.get_user_account_by_reference(zar_reference)
    token_account = account_repo.get_user_account_by_reference(token_reference)

    assert zar_account is not None
    assert zar_account.account_currency == CURRENCY_ZAR
    assert token_account is not None
    assert token_account.account_currency == CURRENCY_TOKEN


def test_available_balance_excludes_own_pending_outgoing_legs(app_context):
    """Open Question #5 (Transaction_Flow_Context.md §8): a quote must check
    available balance, not the raw column, or two quotes could both pass
    against funds one of them has already, silently, committed to spend.
    """
    account_repo = AccountRepository()
    sender = UserController().ensure_provisioned(
        "user_avail", lambda: "avail@example.com", lambda: "Avail"
    )
    sender_zar = account_repo.get_user_account(sender.id, CURRENCY_ZAR)
    account_repo.increase_balance(sender_zar.account_id, Decimal("1000"))

    other = UserController().ensure_provisioned(
        "user_avail_other", lambda: "other@example.com", lambda: "Other"
    )
    other_zar = account_repo.get_user_account(other.id, CURRENCY_ZAR)

    # An in-flight remittance leg debiting the sender's ZAR account, not yet
    # confirmed — exactly the window Open Question #5 describes.
    db.session.add(
        Transaction(
            type=TYPE_REMITTANCE,
            credit_account_id=sender_zar.account_id,
            debit_account_id=other_zar.account_id,
            amount=Decimal("300"),
            currency=CURRENCY_ZAR,
            status=STATUS_PENDING,
        )
    )
    db.session.commit()

    assert account_repo.get_available_balance(sender_zar.account_id) == Decimal("700")
    # The raw column is untouched until the leg confirms (§1) — this is the
    # exact discrepancy the available-balance check exists to catch.
    assert account_repo.get_by_id(sender_zar.account_id).account_balance == Decimal(
        "1000"
    )


def test_available_balance_excludes_own_processing_outgoing_legs(app_context):
    """`burn_treasury_tokens` claims a quote's legs into `processing` before
    its XRPL call resolves (api/remitx_worker/tasks.py), before the group is
    confirmed or failed. If `get_available_balance` stopped excluding a leg
    the moment it left `pending`, that committed amount would look spendable
    again for the whole burn/confirm window.
    """
    account_repo = AccountRepository()
    sender = UserController().ensure_provisioned(
        "user_avail_processing", lambda: "avail_processing@example.com", lambda: "Avail"
    )
    sender_zar = account_repo.get_user_account(sender.id, CURRENCY_ZAR)
    account_repo.increase_balance(sender_zar.account_id, Decimal("1000"))

    other = UserController().ensure_provisioned(
        "user_avail_processing_other",
        lambda: "other_processing@example.com",
        lambda: "Other",
    )
    other_zar = account_repo.get_user_account(other.id, CURRENCY_ZAR)

    db.session.add(
        Transaction(
            type=TYPE_REMITTANCE,
            credit_account_id=sender_zar.account_id,
            debit_account_id=other_zar.account_id,
            amount=Decimal("300"),
            currency=CURRENCY_ZAR,
            status=STATUS_PROCESSING,
        )
    )
    db.session.commit()

    assert account_repo.get_available_balance(sender_zar.account_id) == Decimal("700")
