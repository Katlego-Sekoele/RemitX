"""Errors raised by the role and role-administration domain."""

from __future__ import annotations

from remitx_api.errors.base import ConflictError, DomainError, NotFoundError


class UnknownRoleError(NotFoundError):
    def __init__(self, role_name: str) -> None:
        super().__init__(f"Unknown role: {role_name}")
        self.role_name = role_name


class RoleNotGrantableError(DomainError):
    """The role exists but is never assigned through ``user_roles``."""

    def __init__(self, role_name: str) -> None:
        super().__init__(
            f"Role {role_name} is implicit for every user and cannot be granted."
        )
        self.role_name = role_name


class RoleNotHeldError(NotFoundError):
    def __init__(self, role_name: str) -> None:
        super().__init__(f"User does not hold role: {role_name}")
        self.role_name = role_name


class LastProtectedRoleHolderError(ConflictError):
    """Revoking this grant would leave the role with nobody holding it.

    ``roles.protect_last_holder`` marks the roles this applies to — today
    only ``iam_admin``, where an empty role means nobody can administer
    access and the way back is a psql session.
    """

    def __init__(self, role_name: str) -> None:
        super().__init__(
            f"This is the last active {role_name} grant, and {role_name} is "
            "protected against losing its last holder. Grant it to someone "
            "else before revoking this one."
        )
        self.role_name = role_name
