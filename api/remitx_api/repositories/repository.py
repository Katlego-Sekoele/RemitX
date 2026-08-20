from typing import Generic, TypeVar

from sqlalchemy import select

from remitx_api.extensions import db

T = TypeVar("T")
ID = TypeVar("ID")


class Repository(Generic[T, ID]):
    def __init__(self, model: type[T]) -> None:
        self._model = model

    def get_by_id(self, id: ID) -> T | None:
        return db.session.get(self._model, id)

    def list(self) -> list[T]:
        return db.session.scalars(select(self._model)).all()

    def save(self, entity: T) -> T:
        db.session.add(entity)
        db.session.commit()
        return entity

    def delete(self, id: ID) -> None:
        entity = self.get_by_id(id)
        if entity is not None:
            db.session.delete(entity)
            db.session.commit()
