"""RBAC permission catalogue.

Each row is one atomic capability checked at request time, with a human-readable
``description`` for admin UI. Roles receive permissions through
``role_permissions``; end users receive roles through ``user_roles``. The
``customer`` role is implicit and never granted.
"""

import uuid
from enum import StrEnum

from sqlalchemy import CheckConstraint, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from remitx_api.extensions import Base


class PermissionCode(StrEnum):
    KYC_APPLICATION_READ = "kyc:application:read"
    KYC_APPLICATION_READ_PII = "kyc:application:read_pii"
    KYC_DOCUMENT_READ = "kyc:document:read"
    KYC_APPLICATION_DECIDE = "kyc:application:decide"
    KYC_APPLICATION_REQUEST_INFO = "kyc:application:request_info"
    KYC_RISK_WRITE = "kyc:risk:write"
    USER_READ = "user:read"
    USER_READ_PII = "user:read_pii"
    USER_SUSPEND = "user:suspend"
    ROLE_READ = "role:read"
    ROLE_GRANT = "role:grant"
    ROLE_REVOKE = "role:revoke"
    CASHIN_READ = "cashin:read"
    CASHIN_CONFIRM = "cashin:confirm"
    CASHIN_CANCEL = "cashin:cancel"
    CASHOUT_READ = "cashout:read"
    CASHOUT_APPROVE = "cashout:approve"
    CASHOUT_COMPLETE = "cashout:complete"
    CASHOUT_FAIL = "cashout:fail"
    TRANSACTION_READ_ANY = "transaction:read_any"
    PLATFORM_ACCOUNT_READ = "platform_account:read"
    CONFIG_FEES_WRITE = "config:fees:write"
    CONFIG_LIMITS_WRITE = "config:limits:write"
    CONFIG_FX_WRITE = "config:fx:write"
    AUDIT_READ = "audit:read"


_PERMISSION_CHECK_VALUES = ", ".join(f"'{code.value}'" for code in PermissionCode)


class Permission(Base):
    __tablename__ = "permissions"
    __table_args__ = (
        CheckConstraint(
            f"permission IN ({_PERMISSION_CHECK_VALUES})",
            name="permissions_permission_valid",
        ),
    )

    permission_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    permission: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
