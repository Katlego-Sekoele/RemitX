"""Errors raised by the KYC application lifecycle."""

from __future__ import annotations

from remitx_api.errors.base import ConflictError, NotFoundError


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
