import uuid

from remitx_api.models.orm.quote import Quote
from remitx_api.repositories.repository import Repository


class QuoteRepository(Repository[Quote, uuid.UUID]):
    def __init__(self) -> None:
        super().__init__(Quote)
