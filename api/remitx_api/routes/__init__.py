from fastapi import FastAPI

from remitx_api.routes.accounts import router as accounts_router
from remitx_api.routes.admin.bank_accounts import (
    router as admin_bank_accounts_router,
)
from remitx_api.routes.admin.deposits import router as admin_deposits_router
from remitx_api.routes.admin.kyc import router as admin_kyc_router
from remitx_api.routes.admin.kyc_documents import (
    router as admin_kyc_documents_router,
)
from remitx_api.routes.admin.roles import router as admin_roles_router
from remitx_api.routes.admin.user_roles import router as admin_user_roles_router
from remitx_api.routes.admin.withdrawals import router as admin_withdrawals_router
from remitx_api.routes.bank_accounts import router as bank_accounts_router
from remitx_api.routes.beneficiaries import router as beneficiaries_router
from remitx_api.routes.health import router as health_router
from remitx_api.routes.integration_messages import (
    router as integration_messages_router,
)
from remitx_api.routes.kyc import router as kyc_router
from remitx_api.routes.kyc_documents import router as kyc_documents_router
from remitx_api.routes.me import router as me_router
from remitx_api.routes.quotes import router as quotes_router
from remitx_api.routes.remittances import router as remittances_router
from remitx_api.routes.withdrawals import router as withdrawals_router


def register_routers(app: FastAPI) -> None:
    # Public — no router-level auth gate.
    app.include_router(health_router)

    # Customer — every handler inherits get_current_user from the router.
    app.include_router(me_router)
    app.include_router(integration_messages_router)
    app.include_router(kyc_router)
    app.include_router(kyc_documents_router)
    app.include_router(beneficiaries_router)
    app.include_router(quotes_router)
    app.include_router(remittances_router)
    app.include_router(accounts_router)
    app.include_router(bank_accounts_router)
    app.include_router(withdrawals_router)

    # Admin — mounted under /admin with a permission declared on the router.
    app.include_router(admin_roles_router)
    app.include_router(admin_user_roles_router)
    app.include_router(admin_deposits_router)
    app.include_router(admin_bank_accounts_router)
    app.include_router(admin_withdrawals_router)
    app.include_router(admin_kyc_router)
    app.include_router(admin_kyc_documents_router)
