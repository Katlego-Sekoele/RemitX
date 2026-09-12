"""Domain errors, shared base first and then one module per domain.

Import from the domain module (``remitx_api.errors.users``) rather than from
here when the caller belongs to one domain; this package exists so the shared
contract has a home and so ``app.py`` can register a single handler.
"""

from remitx_api.errors.base import ConflictError, DomainError, NotFoundError
from remitx_api.errors.users import UnknownUserError

__all__ = [
    "ConflictError",
    "DomainError",
    "NotFoundError",
    "UnknownUserError",
]
