"""Errors raised when a customer opens a currency account."""

from __future__ import annotations

from remitx_api.errors.base import ConflictError, ForbiddenError


class AccountAlreadyHeldError(ConflictError):
    """The caller already has an account in this currency."""

    def __init__(self, currency: str) -> None:
        super().__init__(f"You already have a {currency} account.")
        self.currency = currency


class KycNotApprovedToOpenAccountError(ForbiddenError):
    """Opening a payout account is for verified customers only."""

    def __init__(self) -> None:
        super().__init__(
            "Only verified customers can open a currency account. Finish "
            "verification to continue."
        )
