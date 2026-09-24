"""Staff view of cash-in volume and the settlement pipeline.

Gated by ``transaction:read_any``, which compliance, treasury, payout,
support and audit roles carry. Queue counts for KYC, deposits and bank
accounts stay on their own routers so a role without this permission still
sees the queues it can open.
"""

from fastapi import APIRouter
from remitx_api.controllers.operations_controller import OperationsController
from remitx_api.models.orm.permission import PermissionCode
from remitx_api.models.schemas.operations import OperationsRead
from remitx_api.openapi import Tag
from remitx_api.routes.routers import create_admin_router

router: APIRouter = create_admin_router(
    permission=PermissionCode.TRANSACTION_READ_ANY,
    prefix="/admin/operations",
    tags=[Tag.ADMIN_OPERATIONS],
)
controller = OperationsController()


@router.get(
    "",
    response_model=OperationsRead,
    summary="Read settlement volume and pipeline",
)
def get_operations():
    """The last 30 UTC days of confirmed ZAR cash-in and token settlement,
    transfers created each day by status, and how many settlements are failed
    now. Needs ``transaction:read_any``."""
    return controller.get_operations()
