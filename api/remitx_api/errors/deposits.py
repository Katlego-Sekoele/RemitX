"""Errors raised while reconciling a ZAR deposit."""

from __future__ import annotations

from remitx_api.errors.base import DomainError


class DepositNotPendingError(DomainError):
    """The deposit is missing, or it has already been confirmed."""

    def __init__(self) -> None:
        super().__init__("That deposit does not exist or is no longer pending.")


class UnknownDepositReferenceError(DomainError):
    """The reference doesn't resolve to a customer account."""

    def __init__(self) -> None:
        super().__init__("No RemitX account has that reference.")
