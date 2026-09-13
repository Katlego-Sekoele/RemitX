"""Data access for KYC document rows. No bytes pass through here."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select

from remitx_api.extensions import db
from remitx_api.models.orm.kyc_document import KycDocument
from remitx_api.models.orm.kyc_lifecycle import KycDocumentStatus
from remitx_api.repositories.repository import Repository


class KycDocumentRepository(Repository[KycDocument, uuid.UUID]):
    def __init__(self) -> None:
        super().__init__(KycDocument)

    def list_for_application(
        self,
        application_id: uuid.UUID,
        *,
        stored_only: bool = False,
    ) -> list[KycDocument]:
        query = select(KycDocument).where(KycDocument.application_id == application_id)
        if stored_only:
            query = query.where(KycDocument.status == KycDocumentStatus.STORED.value)
        return list(db.session.scalars(query.order_by(KycDocument.uploaded_at)).all())

    def count_for_application(self, application_id: uuid.UUID) -> int:
        """Stored documents only.

        A client cannot create a `pending` row on demand — one exists only
        where the API's own write to the bucket failed — so counting them
        would spend an applicant's allowance on our outage.
        """
        return db.session.scalar(
            select(func.count())
            .select_from(KycDocument)
            .where(KycDocument.application_id == application_id)
            .where(KycDocument.status == KycDocumentStatus.STORED.value)
        )

    def find_stored_by_digest(
        self,
        application_id: uuid.UUID,
        sha256: str,
    ) -> KycDocument | None:
        """Only `stored` rows hold a digest, so this is the dedup check."""
        return db.session.scalars(
            select(KycDocument)
            .where(KycDocument.application_id == application_id)
            .where(KycDocument.sha256 == sha256)
        ).first()
