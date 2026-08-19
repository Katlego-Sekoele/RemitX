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
            .order_by(IntegrationMessage.created_at.desc())
            .limit(limit)
        )
        return list(db.session.scalars(statement))
