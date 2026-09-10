from remitx_api.controllers.user_controller import UserController
from remitx_api.models.orm.account import CURRENCY_TOKEN, CURRENCY_ZAR
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


def test_get_by_reference_does_not_cross_currencies(app_context):
    """The single highest-value test in this change: a user's uctusd
    reference must never resolve when looked up for ZAR, and vice versa —
    this is the whole mechanism that keeps a token account undepositable.
    """
    user = UserController().ensure_provisioned(
        "user_scoped", lambda: "scoped@example.com", lambda: "Scoped"
    )
    account_repo = AccountRepository()

    zar_reference = f"{user.base_reference}-zar"
    token_reference = f"{user.base_reference}-tok"

    assert account_repo.get_by_reference(zar_reference, CURRENCY_ZAR) is not None
    assert account_repo.get_by_reference(zar_reference, CURRENCY_TOKEN) is None
    assert account_repo.get_by_reference(token_reference, CURRENCY_TOKEN) is not None
    assert account_repo.get_by_reference(token_reference, CURRENCY_ZAR) is None
