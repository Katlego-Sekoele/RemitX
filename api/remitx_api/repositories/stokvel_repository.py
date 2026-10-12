import uuid

from remitx_api.models.orm.stokvel import Stokvel
from remitx_api.repositories.repository import Repository


class StokvelRepository(Repository[Stokvel, uuid.UUID]):
    """Repository for stokvels. Queries here run under row-level security on
    Postgres; SQLite (tests) does not filter, so callers scope by user."""

    def __init__(self) -> None:
        super().__init__(Stokvel)
