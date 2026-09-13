"""The caller's own profile: contact mobile plus where they stand on KYC.

Clerk owns name, email and security, edited in its own component. Verified
identity lives on the approved KYC application and changes only through a new
application.
"""

import uuid
from dataclasses import dataclass

from remitx_api.db.transaction import db_transaction
from remitx_api.models.schemas.me import ProfileUpdate
from remitx_api.repositories.kyc_application_repository import (
    KycApplicationRepository,
    KycStanding,
)
from remitx_api.repositories.user_repository import UserRepository


@dataclass(frozen=True)
class ProfileView:
    email: str | None
    mobile_number: str | None
    kyc: KycStanding


class ProfileController:
    def __init__(self) -> None:
        self._users = UserRepository()
        self._applications = KycApplicationRepository()

    def get(self, user_id: uuid.UUID) -> ProfileView:
        user = self._users.require_by_id(user_id)
        return ProfileView(
            email=user.email,
            mobile_number=user.mobile_number,
            # The same derivation the send flow's limit check reads, so the
            # limits shown here cannot disagree with the ones enforced.
            kyc=self._applications.get_standing(user_id),
        )

    def update(self, user_id: uuid.UUID, changes: ProfileUpdate) -> ProfileView:
        self._apply(user_id, changes)
        return self.get(user_id)

    @db_transaction
    def _apply(self, user_id: uuid.UUID, changes: ProfileUpdate) -> None:
        self._users.require_by_id(user_id).mobile_number = changes.mobile_number
