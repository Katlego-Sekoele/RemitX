"""SQLAlchemy ORM models. Import models here so metadata is registered."""

from remitx_api.extensions import Base
from remitx_api.models.orm.account import Account
from remitx_api.models.orm.deposit import Deposit
from remitx_api.models.orm.integration_message import IntegrationMessage
from remitx_api.models.orm.kyc_application import KycApplication
from remitx_api.models.orm.kyc_decision import KycDecision
from remitx_api.models.orm.kyc_document import KycDocument
from remitx_api.models.orm.kyc_lifecycle import KycStatus
from remitx_api.models.orm.permission import Permission, PermissionCode
from remitx_api.models.orm.role import Role
from remitx_api.models.orm.role_permission import RolePermission
from remitx_api.models.orm.toxic_combination import ToxicCombination
from remitx_api.models.orm.transaction import Transaction
from remitx_api.models.orm.user import User
from remitx_api.models.orm.user_role import UserRole

__all__ = [
    "Account",
    "Base",
    "Deposit",
    "IntegrationMessage",
    "KycApplication",
    "KycDecision",
    "KycDocument",
    "KycStatus",
    "Permission",
    "PermissionCode",
    "Role",
    "RolePermission",
    "ToxicCombination",
    "Transaction",
    "User",
    "UserRole",
]
