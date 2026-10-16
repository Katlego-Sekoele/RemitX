"""Errors raised by the stokvel domain.

Each ``detail`` is written for the customer to read as is.
"""

from __future__ import annotations

from remitx_api.errors.base import DomainError, ForbiddenError


class KycNotApprovedToCreateStokvelError(ForbiddenError):
    """Creating a stokvel is for verified customers only: its members
    receive cross-border payouts, so the bar is the same as sending."""

    def __init__(self) -> None:
        super().__init__(
            "Only verified customers can create a stokvel. Finish verification "
            "to continue."
        )


class StokvelCurrencyAccountMissingError(DomainError):
    """The Organiser pays contributions from their own fiat account in the
    Stokvel currency (D7), and they don't hold one. Never opened on their
    behalf: they open it themselves first. A plain 400, as for the
    beneficiaries' `PayoutAccountMissingError`."""

    def __init__(self, currency: str) -> None:
        super().__init__(
            f"Open a {currency} account first. Your contributions are paid from it."
        )
        self.currency = currency
