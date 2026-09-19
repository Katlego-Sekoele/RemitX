"""SQLAlchemy ORM models. Import models here so metadata is registered."""

from remitx_api.extensions import Base
from remitx_api.models.orm.account import Account
from remitx_api.models.orm.audit_log import AuditAction, AuditLog, AuditSubject
from remitx_api.models.orm.beneficiary import Beneficiary
from remitx_api.models.orm.country import Country
from remitx_api.models.orm.deposit import Deposit
from remitx_api.models.orm.exchange_rate import ExchangeRate
from remitx_api.models.orm.integration_message import IntegrationMessage
from remitx_api.models.orm.kyc_application import KycApplication
from remitx_api.models.orm.kyc_application_history import KycApplicationHistory
from remitx_api.models.orm.kyc_application_risk_view import kyc_application_risk
from remitx_api.models.orm.kyc_application_status import KycApplicationStatusRecord
from remitx_api.models.orm.kyc_assessment_audit import KycAssessmentAudit
from remitx_api.models.orm.kyc_assessment_audit_signal import KycAssessmentAuditSignal
from remitx_api.models.orm.kyc_decision import KycDecision
from remitx_api.models.orm.kyc_decision_history import KycDecisionHistory
from remitx_api.models.orm.kyc_document import KycDocument
from remitx_api.models.orm.kyc_identity_scheme import KycIdentityScheme
from remitx_api.models.orm.kyc_lifecycle import KycStatus
from remitx_api.models.orm.kyc_onboarding_editable_status import (
    KycOnboardingEditableStatus,
)
from remitx_api.models.orm.kyc_onboarding_requirement import (
    KycOnboardingRequirement,
)
from remitx_api.models.orm.kyc_onboarding_step import KycOnboardingStep
from remitx_api.models.orm.kyc_pep_relationship import KycPepRelationshipRecord
from remitx_api.models.orm.kyc_reason_code import KycReasonCodeRecord
from remitx_api.models.orm.kyc_risk_rating import KycRiskRatingRecord
from remitx_api.models.orm.kyc_risk_signal import KycRiskSignalRecord
from remitx_api.models.orm.kyc_status_progression import KycApplicationStatusProgression
from remitx_api.models.orm.kyc_tier import KycTier
from remitx_api.models.orm.permission import Permission, PermissionCode
from remitx_api.models.orm.quote import Quote
from remitx_api.models.orm.role import Role
from remitx_api.models.orm.role_permission import RolePermission
from remitx_api.models.orm.toxic_combination import ToxicCombination
from remitx_api.models.orm.transaction import Transaction
from remitx_api.models.orm.user import User
from remitx_api.models.orm.user_role import UserRole

__all__ = [
    "Account",
    "AuditAction",
    "AuditLog",
    "AuditSubject",
    "Base",
    "Beneficiary",
    "Country",
    "Deposit",
    "ExchangeRate",
    "IntegrationMessage",
    "KycApplication",
    "KycApplicationHistory",
    "KycApplicationStatusRecord",
    "KycAssessmentAudit",
    "KycAssessmentAuditSignal",
    "KycDecision",
    "KycApplicationStatusProgression",
    "KycReasonCodeRecord",
    "KycRiskRatingRecord",
    "KycRiskSignalRecord",
    "KycDecisionHistory",
    "KycDocument",
    "KycIdentityScheme",
    "KycOnboardingEditableStatus",
    "KycOnboardingRequirement",
    "KycOnboardingStep",
    "KycPepRelationshipRecord",
    "KycStatus",
    "KycTier",
    "Permission",
    "PermissionCode",
    "Quote",
    "Role",
    "RolePermission",
    "ToxicCombination",
    "Transaction",
    "User",
    "UserRole",
    "kyc_application_risk",
]
