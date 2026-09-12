import uuid

from sqlalchemy import select

from remitx_api.extensions import db
from remitx_api.models.orm.kyc_status_progression import KycApplicationStatusProgression
from remitx_api.repositories.repository import Repository


class KycApplicationStatusProgressionRepository(
    Repository[KycApplicationStatusProgression, uuid.UUID]
):
    def __init__(self) -> None:
        super().__init__(KycApplicationStatusProgression)

    def is_allowed(self, from_status: str, to_status: str) -> bool:
        return (
            db.session.scalar(
                select(
                    select(KycApplicationStatusProgression)
                    .where(KycApplicationStatusProgression.from_status == from_status)
                    .where(KycApplicationStatusProgression.to_status == to_status)
                    .exists()
                )
            )
            is True
        )
