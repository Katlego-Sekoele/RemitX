"""Baseline RBAC catalogue for migrations and tests.

Deterministic UUIDs keep seed rows stable across environments so migrations
can reference them without round-trips.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from remitx_api.models.orm.permission import PermissionCode

# Fixed namespace for uuid5 so seed rows get the same primary keys in every
# environment. Lets migrations precompute IDs without querying the database.
RBAC_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


def precompute_permission_id_given_permission_code(
    code: PermissionCode | str,
) -> uuid.UUID:
    value = code.value if isinstance(code, PermissionCode) else code
    return uuid.uuid5(RBAC_NAMESPACE, f"permission:{value}")


def precompute_role_id_given_role_name(name: str) -> uuid.UUID:
    return uuid.uuid5(RBAC_NAMESPACE, f"role:{name}")


def precompute_role_permission_id_given_role_and_permission(
    role_name: str,
    permission: PermissionCode | str,
) -> uuid.UUID:
    value = permission.value if isinstance(permission, PermissionCode) else permission
    return uuid.uuid5(RBAC_NAMESPACE, f"role_permission:{role_name}:{value}")


def precompute_toxic_combination_id_given_permissions(
    first: PermissionCode | str,
    second: PermissionCode | str,
) -> uuid.UUID:
    values = sorted(
        code.value if isinstance(code, PermissionCode) else code
        for code in (first, second)
    )
    return uuid.uuid5(RBAC_NAMESPACE, f"toxic_combination:{values[0]}:{values[1]}")


@dataclass(frozen=True, slots=True)
class PermissionSeed:
    code: PermissionCode
    description: str


PERMISSION_SEEDS: tuple[PermissionSeed, ...] = (
    PermissionSeed(
        PermissionCode.KYC_APPLICATION_READ,
        "View KYC application metadata (status, timestamps) without PII.",
    ),
    PermissionSeed(
        PermissionCode.KYC_APPLICATION_READ_PII,
        "View sensitive KYC applicant fields (ID number, address, etc.).",
    ),
    PermissionSeed(
        PermissionCode.KYC_DOCUMENT_READ,
        "View uploaded identity and supporting documents.",
    ),
    PermissionSeed(
        PermissionCode.KYC_APPLICATION_DECIDE,
        "Approve or reject a completed KYC application.",
    ),
    PermissionSeed(
        PermissionCode.KYC_APPLICATION_REQUEST_INFO,
        "Ask the applicant for missing or corrected information.",
    ),
    PermissionSeed(
        PermissionCode.KYC_RISK_WRITE,
        "Set or update customer risk rating and tier.",
    ),
    PermissionSeed(
        PermissionCode.USER_READ,
        "View non-sensitive user profile and account metadata.",
    ),
    PermissionSeed(
        PermissionCode.USER_READ_PII,
        "View sensitive user profile fields (PII).",
    ),
    PermissionSeed(
        PermissionCode.USER_SUSPEND,
        "Suspend or re-enable a customer account.",
    ),
    PermissionSeed(
        PermissionCode.ROLE_READ,
        "View roles and their permission assignments.",
    ),
    PermissionSeed(
        PermissionCode.ROLE_GRANT,
        "Grant an operational role to a user.",
    ),
    PermissionSeed(
        PermissionCode.ROLE_REVOKE,
        "Revoke an operational role from a user.",
    ),
    PermissionSeed(
        PermissionCode.CASHIN_READ,
        "View pending and historical ZAR cash-in records.",
    ),
    PermissionSeed(
        PermissionCode.CASHIN_CONFIRM,
        "Confirm simulated ZAR cash-in received.",
    ),
    PermissionSeed(
        PermissionCode.CASHIN_CANCEL,
        "Cancel a pending cash-in before settlement starts.",
    ),
    PermissionSeed(
        PermissionCode.CASHOUT_READ,
        "View payout queue items and their status.",
    ),
    PermissionSeed(
        PermissionCode.CASHOUT_APPROVE,
        "Approve a payout for processing.",
    ),
    PermissionSeed(
        PermissionCode.CASHOUT_COMPLETE,
        "Mark a payout as successfully completed.",
    ),
    PermissionSeed(
        PermissionCode.CASHOUT_FAIL,
        "Mark a payout as failed and record the reason.",
    ),
    PermissionSeed(
        PermissionCode.TRANSACTION_READ_ANY,
        "Read any customer's transfer history (cross-user).",
    ),
    PermissionSeed(
        PermissionCode.PLATFORM_ACCOUNT_READ,
        "View RemitX's own account balances: bank, fee revenue and treasury.",
    ),
    PermissionSeed(
        PermissionCode.CONFIG_FEES_WRITE,
        "Change fee schedules and pricing rules.",
    ),
    PermissionSeed(
        PermissionCode.CONFIG_LIMITS_WRITE,
        "Change per-user and global transfer limits.",
    ),
    PermissionSeed(
        PermissionCode.CONFIG_FX_WRITE,
        "Change FX margins and rate configuration.",
    ),
    PermissionSeed(
        PermissionCode.AUDIT_READ,
        "Read the immutable activity and change log.",
    ),
)


@dataclass(frozen=True, slots=True)
class RoleSeed:
    name: str
    display_name: str
    description: str
    permissions: tuple[PermissionCode, ...]
    is_admin: bool = False
    # Mirrors ``roles.is_grantable`` / ``roles.protect_last_holder`` — see
    # models/orm/role.py for what each one buys.
    is_grantable: bool = True
    protect_last_holder: bool = False


ROLE_SEEDS: tuple[RoleSeed, ...] = (
    RoleSeed(
        name="customer",
        display_name="Customer",
        description="Every provisioned user. Not a granted role.",
        permissions=(),
        is_grantable=False,
    ),
    RoleSeed(
        name="compliance_analyst",
        display_name="Compliance Analyst",
        description=("Prepares applications and chases missing info. Cannot decide."),
        is_admin=True,
        permissions=(
            PermissionCode.KYC_APPLICATION_READ,
            PermissionCode.KYC_APPLICATION_READ_PII,
            PermissionCode.KYC_DOCUMENT_READ,
            PermissionCode.KYC_APPLICATION_REQUEST_INFO,
        ),
    ),
    RoleSeed(
        name="compliance_officer",
        display_name="Compliance Officer",
        description="Approves or rejects applications and sets risk rating and tier.",
        is_admin=True,
        permissions=(
            PermissionCode.KYC_APPLICATION_READ,
            PermissionCode.KYC_APPLICATION_READ_PII,
            PermissionCode.KYC_DOCUMENT_READ,
            PermissionCode.KYC_APPLICATION_REQUEST_INFO,
            PermissionCode.KYC_APPLICATION_DECIDE,
            PermissionCode.KYC_RISK_WRITE,
            PermissionCode.USER_READ,
            PermissionCode.TRANSACTION_READ_ANY,
            PermissionCode.AUDIT_READ,
        ),
    ),
    RoleSeed(
        name="treasury_operator",
        display_name="Treasury Operator",
        description="Confirms the simulated ZAR cash-in.",
        is_admin=True,
        permissions=(
            PermissionCode.CASHIN_READ,
            PermissionCode.CASHIN_CONFIRM,
            PermissionCode.CASHIN_CANCEL,
            PermissionCode.TRANSACTION_READ_ANY,
            PermissionCode.PLATFORM_ACCOUNT_READ,
        ),
    ),
    RoleSeed(
        name="payout_operator",
        display_name="Payout Operator",
        description="Works the cash-out queue.",
        is_admin=True,
        permissions=(
            PermissionCode.CASHOUT_READ,
            PermissionCode.CASHOUT_APPROVE,
            PermissionCode.CASHOUT_COMPLETE,
            PermissionCode.CASHOUT_FAIL,
            PermissionCode.TRANSACTION_READ_ANY,
        ),
    ),
    RoleSeed(
        name="support_agent",
        display_name="Support Agent",
        description=("Answers status questions without seeing PII or moving money."),
        is_admin=True,
        permissions=(
            PermissionCode.USER_READ,
            PermissionCode.TRANSACTION_READ_ANY,
            PermissionCode.KYC_APPLICATION_READ,
        ),
    ),
    RoleSeed(
        name="iam_admin",
        display_name="IAM Admin",
        description="Administers access. Holds no domain permissions.",
        is_admin=True,
        protect_last_holder=True,
        permissions=(
            PermissionCode.ROLE_READ,
            PermissionCode.ROLE_GRANT,
            PermissionCode.ROLE_REVOKE,
            PermissionCode.USER_READ,
            PermissionCode.USER_SUSPEND,
            PermissionCode.AUDIT_READ,
        ),
    ),
    RoleSeed(
        name="config_admin",
        display_name="Config Admin",
        description=("Changes fees, margins, and limits. Kept separate from IAM."),
        is_admin=True,
        permissions=(
            PermissionCode.CONFIG_FEES_WRITE,
            PermissionCode.CONFIG_LIMITS_WRITE,
            PermissionCode.CONFIG_FX_WRITE,
            PermissionCode.AUDIT_READ,
        ),
    ),
    RoleSeed(
        name="auditor",
        display_name="Auditor",
        description="Read-only oversight with no PII and no mutations.",
        is_admin=True,
        permissions=(
            PermissionCode.AUDIT_READ,
            PermissionCode.USER_READ,
            PermissionCode.TRANSACTION_READ_ANY,
        ),
    ),
)


@dataclass(frozen=True, slots=True)
class ToxicCombinationSeed:
    permissions: tuple[PermissionCode, PermissionCode]
    explanation: str


# The baseline separation-of-duties rules. Seeded, not hardcoded: after the
# migration these are rows an operator can change without a redeploy, and the
# API reads them from the table on every grant.
TOXIC_COMBINATION_SEEDS: tuple[ToxicCombinationSeed, ...] = (
    ToxicCombinationSeed(
        permissions=(PermissionCode.CASHIN_CONFIRM, PermissionCode.CASHOUT_COMPLETE),
        explanation=(
            "One person could confirm money in and pay money out, so no second "
            "pair of eyes ever sees a transfer end to end."
        ),
    ),
    ToxicCombinationSeed(
        permissions=(PermissionCode.KYC_APPLICATION_DECIDE, PermissionCode.ROLE_GRANT),
        explanation=(
            "One person could approve a customer and hand out the access that "
            "reviews that decision."
        ),
    ),
)

if {seed.code for seed in PERMISSION_SEEDS} != set(PermissionCode):
    raise RuntimeError("PERMISSION_SEEDS must cover every PermissionCode member")
