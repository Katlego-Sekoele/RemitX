from sqlalchemy import select

from remitx_api.extensions import db
from remitx_api.models.orm.integration_message import IntegrationMessage
from remitx_api.repositories.repository import Repository


class IntegrationMessageRepository(Repository[IntegrationMessage, str]):
    def __init__(self) -> None:
        super().__init__(IntegrationMessage)

    def list_recent(self, limit: int) -> list:
        statement = (
            select(IntegrationMessage)
            # id breaks ties: created_at alone leaves rows written in the same
            # clock tick in arbitrary order, which makes ordering flaky on
            # coarse-clock platforms and unstable for future pagination.
            .order_by(
                IntegrationMessage.created_at.desc(), IntegrationMessage.id.desc()
            )
            .limit(limit)
        )
        return list(db.session.scalars(statement))
