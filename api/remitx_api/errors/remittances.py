"""Errors raised by the remittance domain."""

from __future__ import annotations

import uuid

from remitx_api.errors.base import NotFoundError


class UnknownRemittanceError(NotFoundError):
    """No such remittance, or the caller is neither its sender nor its
    recipient — one answer for both, so an id can't be probed for."""

    def __init__(self, remittance_id: uuid.UUID | str) -> None:
        super().__init__("Transfer not found")
        self.remittance_id = str(remittance_id)
