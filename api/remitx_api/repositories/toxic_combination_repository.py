import uuid

from sqlalchemy import select
from sqlalchemy.orm import aliased

from remitx_api.extensions import db
from remitx_api.models.orm.permission import Permission
from remitx_api.models.orm.toxic_combination import ToxicCombination
from remitx_api.repositories.repository import Repository


class ToxicCombinationRepository(Repository[ToxicCombination, uuid.UUID]):
    def __init__(self) -> None:
        super().__init__(ToxicCombination)

    def list_pairs(self) -> list[tuple[str, str, str]]:
        """Every rule as ``(permission, permission, explanation)``.

        Resolved to permission codes here so nothing downstream has to carry
        permission ids around just to compare a rule against what someone
        holds.
        """
        first = aliased(Permission)
        second = aliased(Permission)
        return [
            (row[0], row[1], row[2])
            for row in db.session.execute(
                select(
                    first.permission, second.permission, ToxicCombination.explanation
                )
                .join(first, first.permission_id == ToxicCombination.permission_a_id)
                .join(second, second.permission_id == ToxicCombination.permission_b_id)
                .order_by(first.permission, second.permission)
            ).all()
        ]
