import uuid

from remitx_api.models.orm.stokvel_invitation import StokvelInvitation
from remitx_api.repositories.repository import Repository


class StokvelInvitationRepository(Repository[StokvelInvitation, uuid.UUID]):
    """Repository for stokvel invitations. Queries here run under row-level security on
    Postgres; SQLite (tests) does not filter, so callers scope by user."""

    def __init__(self) -> None:
        super().__init__(StokvelInvitation)
