import uuid

from remitx_api.models.orm.stokvel_member import StokvelMember
from remitx_api.repositories.repository import Repository


class StokvelMemberRepository(Repository[StokvelMember, uuid.UUID]):
    """Repository for stokvel memberships. Queries here run under row-level security on
    Postgres; SQLite (tests) does not filter, so callers scope by user."""

    def __init__(self) -> None:
        super().__init__(StokvelMember)
