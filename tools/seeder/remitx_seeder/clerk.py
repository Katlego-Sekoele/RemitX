"""Synthetic people as Clerk users.

Every seeded person is a real user in the target's Clerk development instance
when the target has a Clerk key, signing in with a `+clerk_test` email and the
fixed code 424242 (Clerk's test mode). Development instances are capped at 100
users, so the engine asks for at most `capacity()` of them and makes everyone
else database-only.

Each seeded Clerk user carries `private_metadata.remitx_seed = true`, which is
how Reset finds exactly the users the seeder made and leaves your testers' own
accounts alone.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

SEED_METADATA_KEY = "remitx_seed"
DATABASE_ONLY_PREFIX = "seed_"
TEST_OTP_CODE = "424242"


def database_only_id() -> str:
    """A `users.clerk_user_id` for someone with no Clerk account. Clerk's own
    ids start `user_`, so these can never collide with one."""
    return f"{DATABASE_ONLY_PREFIX}{uuid.uuid4().hex}"


def test_email(local_part: str, domain: str) -> str:
    """Clerk treats any `+clerk_test` address as a test address: no email is
    sent, and the verification code is always 424242."""
    return f"{local_part}+clerk_test@{domain}"


class ClerkGateway(Protocol):
    def user_count(self) -> int: ...

    def find_by_email(self, email: str) -> tuple[str, bool] | None:
        """(clerk user id, made by the seeder) for an existing address."""

    def create_user(
        self,
        *,
        email: str,
        first_name: str,
        last_name: str,
        created_at: datetime,
        run_id: str,
    ) -> str: ...

    def seeded_user_ids(self) -> list[str]: ...

    def delete_user(self, clerk_user_id: str) -> None: ...

    def session_token(self, clerk_user_id: str) -> str: ...


class SdkClerkGateway:
    """The real Clerk Backend API, through the SDK the API already uses."""

    def __init__(self, secret_key: str) -> None:
        from clerk_backend_api import Clerk

        self._sdk = Clerk(bearer_auth=secret_key)

    def user_count(self) -> int:
        return int(self._sdk.users.count().total_count)

    def find_by_email(self, email: str) -> tuple[str, bool] | None:
        users = self._sdk.users.list(request={"email_address": [email], "limit": 1})
        if not users:
            return None
        user = users[0]
        seeded = bool((user.private_metadata or {}).get(SEED_METADATA_KEY))
        return user.id, seeded

    def create_user(
        self,
        *,
        email: str,
        first_name: str,
        last_name: str,
        created_at: datetime,
        run_id: str,
    ) -> str:
        user = self._sdk.users.create(
            email_address=[email],
            first_name=first_name,
            last_name=last_name,
            skip_password_requirement=True,
            skip_legal_checks=True,
            # Clerk's own sign-up date matches the replayed one in RemitX.
            created_at=created_at.isoformat().replace("+00:00", "Z"),
            private_metadata={SEED_METADATA_KEY: True, "seed_run": run_id},
        )
        return user.id

    def seeded_user_ids(self) -> list[str]:
        ids: list[str] = []
        offset = 0
        while True:
            page = self._sdk.users.list(request={"limit": 100, "offset": offset})
            if not page:
                return ids
            ids.extend(
                user.id
                for user in page
                if (user.private_metadata or {}).get(SEED_METADATA_KEY)
            )
            offset += len(page)

    def delete_user(self, clerk_user_id: str) -> None:
        self._sdk.users.delete(user_id=clerk_user_id)

    def session_token(self, clerk_user_id: str) -> str:
        session = self._sdk.sessions.create(request={"user_id": clerk_user_id})
        return self._sdk.sessions.create_token(session_id=session.id).jwt


@dataclass
class FakeClerkGateway:
    """An in-memory Clerk for tests and for database-only runs."""

    existing_users: int = 0
    users: dict[str, dict] = field(default_factory=dict)

    def user_count(self) -> int:
        return self.existing_users + len(self.users)

    def find_by_email(self, email: str) -> tuple[str, bool] | None:
        for clerk_id, user in self.users.items():
            if user["email"] == email:
                return clerk_id, True
        return None

    def create_user(self, *, email, first_name, last_name, created_at, run_id) -> str:
        clerk_id = f"user_fake{uuid.uuid4().hex[:20]}"
        self.users[clerk_id] = {
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "created_at": created_at,
            "run_id": run_id,
        }
        return clerk_id

    def seeded_user_ids(self) -> list[str]:
        return list(self.users)

    def delete_user(self, clerk_user_id: str) -> None:
        self.users.pop(clerk_user_id, None)

    def session_token(self, clerk_user_id: str) -> str:
        return f"fake-token-for-{clerk_user_id}"
