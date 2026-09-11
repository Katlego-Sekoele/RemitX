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
