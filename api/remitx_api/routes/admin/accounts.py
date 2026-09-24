"""Admin view of RemitX's own platform accounts.

Gated by `platform_account:read`, which the `treasury_operator` role carries
(models/orm/rbac_seed.py), so every treasurer can see the platform's
balances. Read-only: money only moves on these accounts as a leg of a deposit,
a transfer or a burn.
"""

from fastapi import APIRouter
from remitx_api.controllers.account_controller import AccountController
from remitx_api.models.orm.permission import PermissionCode
from remitx_api.models.schemas.account import PlatformAccountRead, TreasuryCoverageRead
from remitx_api.openapi import Tag
from remitx_api.routes.routers import create_admin_router

router: APIRouter = create_admin_router(
    permission=PermissionCode.PLATFORM_ACCOUNT_READ,
    prefix="/admin/platform-accounts",
    tags=[Tag.ADMIN_ACCOUNTS],
)
controller = AccountController()


@router.get(
    "",
    response_model=list[PlatformAccountRead],
    summary="List RemitX's platform accounts",
)
def list_platform_accounts():
    """RemitX's bank and fee revenue accounts per settlement country, the XRPL
    treasury wallet, and the uctusd issuer, each with its ledger and available
    balance. Bank accounts come first, then fee revenue, the treasury wallet
    and the issuer; ZAR leads within each. Needs ``platform_account:read``."""
    return [
        PlatformAccountRead(
            account_id=view.account_id,
            label=view.label,
            type=view.type,
            currency=view.currency,
            kind=view.kind,
            balance=view.balance,
            available_balance=view.available_balance,
        )
        for view in controller.get_platform_accounts()
    ]


@router.get(
    "/coverage",
    response_model=TreasuryCoverageRead,
    summary="Read treasury token coverage",
)
def get_treasury_coverage():
    """Token still available on the treasury wallet, and the token customers
    hold. Needs ``platform_account:read``."""
    view = controller.get_treasury_coverage()
    return TreasuryCoverageRead(
        token_available=view.token_available,
        customer_token_balances=view.customer_token_balances,
    )
