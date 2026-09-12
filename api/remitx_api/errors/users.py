"""Errors raised by the user domain."""

from __future__ import annotations

import uuid

from remitx_api.errors.base import NotFoundError


class UnknownUserError(NotFoundError):
    def __init__(self, user_id: uuid.UUID | str) -> None:
        super().__init__("User not found")
        self.user_id = str(user_id)
