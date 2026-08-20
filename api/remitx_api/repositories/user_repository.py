import uuid

from sqlalchemy import select

from remitx_api.extensions import db
from remitx_api.models.orm.user import User
from remitx_api.repositories.repository import Repository


class UserRepository(Repository[User, uuid.UUID]):
    def __init__(self) -> None:
        super().__init__(User)

    def get_by_clerk_id(self, clerk_user_id: str) -> User | None:
        return db.session.scalars(
            select(User).where(User.clerk_user_id == clerk_user_id)
        ).first()
