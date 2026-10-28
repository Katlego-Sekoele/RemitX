import uuid

from remitx_api.models.orm.stokvel_cover import StokvelCover
from remitx_api.repositories.repository import Repository


class StokvelCoverRepository(Repository[StokvelCover, uuid.UUID]):
    """One cover row per stokvel, keyed by the stokvel id."""

    def __init__(self) -> None:
        super().__init__(StokvelCover)
