"""Staff view of cash-in volume and the settlement pipeline.

Gated by ``transaction:read_any``, which compliance, treasury, payout,
support and audit roles carry. Queue counts for KYC, deposits and bank
accounts stay on their own routers so a role without this permission still
sees the queues it can open.
"""

import uuid

from fastapi import APIRouter, Depends
from remitx_api.auth.dependencies import get_current_user
from remitx_api.auth.permissions import RequirePermission
from remitx_api.controllers.operations_controller import OperationsController
from remitx_api.controllers.settlement_recovery_controller import (
    SettlementRecoveryController,
)
from remitx_api.models.orm.permission import PermissionCode
from remitx_api.models.orm.user import User
from remitx_api.models.schemas.operations import OperationsRead
from remitx_api.models.schemas.settlement_recovery import (
    ReclaimPendingSettlementsRequest,
    ReclaimPendingSettlementsResponse,
    RetrySettlementEnqueueResponse,
    StuckSettlementRead,
)
from remitx_api.openapi import Tag, error_responses
from remitx_api.routes.routers import create_admin_router

router: APIRouter = create_admin_router(
    permission=PermissionCode.TRANSACTION_READ_ANY,
    prefix="/admin/operations",
    tags=[Tag.ADMIN_OPERATIONS],
)
controller = OperationsController()
recovery_controller = SettlementRecoveryController()


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


@router.get(
    "/settlements/stuck",
    response_model=list[StuckSettlementRead],
    summary="List non-terminal remittance settlements",
)
def list_stuck_settlements():
    """Remittances whose settlement leg is not ``confirmed``, with leg counts
    and a ``recovery_kind`` hint (`retry_enqueue` vs `manual_only`). Needs
    ``transaction:read_any``."""
    return recovery_controller.list_stuck()


@router.post(
    "/settlements/{quote_id}/retry-enqueue",
    response_model=RetrySettlementEnqueueResponse,
    dependencies=[Depends(RequirePermission(PermissionCode.SETTLEMENT_RETRY))],
    summary="Re-enqueue settlement for one quote",
    responses=error_responses(404, 409),
)
def retry_settlement_enqueue(
    quote_id: uuid.UUID,
    user: User = Depends(get_current_user),
):
    """Publishes ``settle_remittance`` when every leg is still ``pending``.
    Refuses ``processing`` or ``failed`` groups. Needs ``settlement:retry``."""
    return recovery_controller.retry_enqueue(user.id, quote_id)


@router.post(
    "/settlements/reclaim-pending",
    response_model=ReclaimPendingSettlementsResponse,
    dependencies=[Depends(RequirePermission(PermissionCode.SETTLEMENT_RETRY))],
    summary="Re-enqueue all fully pending settlements",
)
def reclaim_pending_settlements(
    payload: ReclaimPendingSettlementsRequest,
    user: User = Depends(get_current_user),
):
    """Same safe reclaim as the worker boot/beat job, on demand. Optional
    ``min_age_seconds`` skips very new groups. Needs ``settlement:retry``."""
    return recovery_controller.reclaim_pending(user.id, payload.min_age_seconds)
