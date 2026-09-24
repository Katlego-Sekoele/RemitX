"""Errors raised while reconciling a deposit."""

from __future__ import annotations

from remitx_api.errors.base import ConflictError, DomainError


class DepositNotPendingError(DomainError):
    """The deposit is missing, or it has already been confirmed."""

    def __init__(self) -> None:
        super().__init__("That deposit does not exist or is no longer pending.")


class UnknownDepositReferenceError(DomainError):
    """The reference doesn't resolve to a customer account."""

    def __init__(self) -> None:
        super().__init__("No RemitX account has that reference.")


class DepositCurrencyMismatchError(DomainError):
    """The reference names an account in another currency than the deposit."""

    def __init__(self, deposit_currency: str, account_currency: str) -> None:
        super().__init__(
            f"This deposit is in {deposit_currency}, but that reference is a "
            f"{account_currency} account. Use the customer's {deposit_currency} "
            "account reference."
        )


class PlatformBankAccountMissingError(ConflictError):
    """Reconciliation has nowhere to take the money from."""

    def __init__(self, currency: str) -> None:
        super().__init__(
            f"RemitX has no {currency} bank account, so {currency} deposits "
            "cannot be reconciled. Seed the platform accounts and try again."
        )
