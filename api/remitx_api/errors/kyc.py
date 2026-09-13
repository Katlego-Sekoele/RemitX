"""Errors raised by the KYC application lifecycle."""

from __future__ import annotations

from remitx_api.errors.base import (
    ConflictError,
    DomainError,
    ForbiddenError,
    NotFoundError,
)


class KycConflictError(ConflictError):
    """The request cannot be applied to the application as it stands now."""


class IllegalKycTransitionError(KycConflictError):
    """The state machine has no edge from the current status to the requested
    one — see models/orm/kyc_lifecycle.py."""


class KycVersionConflictError(KycConflictError):
    """Someone else changed the application since the caller last read it.

    The loser of two concurrent decisions gets this, rather than silently
    overwriting the winner's.
    """


class OpenApplicationExistsError(KycConflictError):
    """This user already has an application in flight."""


class UnknownKycApplicationError(NotFoundError):
    """Raised when an action targets an application id that doesn't exist."""


class InvalidKycDraftError(DomainError):
    """A field on a partial save is the wrong shape or format."""


class KycApplicationNotEditableError(KycConflictError):
    """The application is no longer a draft the applicant can change."""


class IncompleteKycDeclarationError(DomainError):
    """Submission refused: a declaration the risk rules score makes other
    fields mandatory, and they are missing — a PEP declaration without a source
    of wealth, say."""

    def __init__(self, missing_fields: list[str]) -> None:
        super().__init__(
            "This application cannot be submitted until these are provided: "
            + ", ".join(missing_fields)
        )
        self.missing_fields = missing_fields


class KycSeniorApprovalRequiredError(ForbiddenError):
    """Only a holder of `kyc:application:decide` may decide this application —
    it carries a PEP declaration, or its risk rating requires senior approval."""


class KycTierNotGrantableError(DomainError):
    """The tier requested on approval does not exist, is above what the
    application's risk rating allows, or needs a declaration it lacks."""


class KycRiskOverrideNotAllowedError(KycConflictError):
    """A risk rating can only be overridden while the application is awaiting a
    decision."""


class UnknownKycRiskRatingError(DomainError):
    """A rating named by a caller is not a row in `kyc_risk_ratings`."""

    def __init__(self, rating: str) -> None:
        super().__init__(f"Unknown risk rating: {rating}")
        self.rating = rating


class KycRiskRulesMisconfiguredError(RuntimeError):
    """The risk rule set in the database cannot be scored against — bands with a
    gap, an active signal with no detector.

    Deliberately not a `DomainError`: nothing the caller does fixes it, so it
    should surface as a 500 and an alert, not as a 4xx telling an applicant to
    try again.
    """


class KycIdentitySchemesMisconfiguredError(RuntimeError):
    """A `kyc_identity_schemes` row names a validator that does not exist.

    A 500 for the same reason as `KycRiskRulesMisconfiguredError`: no applicant
    input fixes it.
    """


class UnsupportedJurisdictionError(DomainError):
    """The applicant lives in a country RemitX does not operate in."""

    def __init__(self, country_name: str, operating_names: list[str]) -> None:
        served = (
            " and ".join(operating_names)
            if len(operating_names) <= 2
            else ", ".join(operating_names[:-1]) + " and " + operating_names[-1]
        )
        super().__init__(
            f"We don't operate in {country_name} yet. RemitX currently serves "
            f"residents of {served}."
        )
        self.country_name = country_name
