"""Request/response schemas for the role catalogue and role administration."""

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_serializer

# A reason is mandatory on every grant and revoke, and long enough to be a
# sentence rather than a keystroke. It costs the granter five seconds and
# turns the history from a list of mutations into something a person can
# review six months later.
MIN_REASON_LENGTH = 10
MAX_REASON_LENGTH = 500


def _as_utc(value: datetime | None) -> str | None:
    # See models/schemas/integration_message.py: SQLite drops the tz offset
    # Postgres preserves.
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


class RoleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    role_id: uuid.UUID
    name: str
    display_name: str = Field(validation_alias="role_display_name")
    description: str
    is_admin: bool
    is_grantable: bool
    permissions: list[str]


class ToxicCombinationRead(BaseModel):
    """A pair of permissions the access page warns about before a grant."""

    permissions: list[str]
    explanation: str


class RoleGrantRequest(BaseModel):
    role: str = Field(description="Machine name of the role, e.g. iam_admin.")
    reason: str = Field(
        min_length=MIN_REASON_LENGTH,
        max_length=MAX_REASON_LENGTH,
        description="Why this person needs this role. Recorded against the grant.",
    )
    toxic_combination_acknowledged: bool = Field(
        default=False,
        description=(
            "Set when the granter was shown a separation-of-duties warning and "
            "went ahead anyway. Recorded, never enforced — the server warns "
            "rather than blocks."
        ),
    )


class RoleRevokeRequest(BaseModel):
    reason: str = Field(
        min_length=MIN_REASON_LENGTH,
        max_length=MAX_REASON_LENGTH,
        description="Why this role is being taken away. Recorded against the row.",
    )


class UserRoleRead(BaseModel):
    """One row of the append-only grant history, live or revoked."""

    user_role_id: uuid.UUID
    role: str
    display_name: str
    granted_at: datetime
    granted_by: uuid.UUID | None
    grant_reason: str | None
    self_granted: bool
    toxic_combination_acknowledged: bool
    revoked_at: datetime | None
    revoked_by: uuid.UUID | None
    revoke_reason: str | None

    @computed_field
    @property
    def active(self) -> bool:
        return self.revoked_at is None

    @field_serializer("granted_at", "revoked_at")
    def _serialize_timestamps(self, value: datetime | None) -> str | None:
        return _as_utc(value)


class UserAccessRead(BaseModel):
    """Everything the access page shows about one person's access."""

    user_id: uuid.UUID
    email: str | None
    base_reference: str
    permissions: list[str]
    roles: list[UserRoleRead]


class RoleGrantResult(BaseModel):
    grant: UserRoleRead
    created: bool = Field(
        description=(
            "False when the user already held the role and the existing grant "
            "was returned unchanged, rather than a duplicate row inserted."
        )
    )
    toxic_combinations: list[ToxicCombinationRead] = Field(
        default_factory=list,
        description="Separation-of-duties warnings this grant leaves in place.",
    )


class AdminRoleRead(BaseModel):
    role: str
    display_name: str
    granted_at: datetime
    self_granted: bool

    @field_serializer("granted_at")
    def _serialize_granted_at(self, value: datetime) -> str | None:
        return _as_utc(value)


class AdminMemberRead(BaseModel):
    """One row of the admin list: a person and the roles they hold now."""

    user_id: uuid.UUID
    email: str | None
    base_reference: str
    roles: list[AdminRoleRead]
    last_granted_at: datetime
    has_self_grant: bool

    @field_serializer("last_granted_at")
    def _serialize_last_granted_at(self, value: datetime) -> str | None:
        return _as_utc(value)


class UserSearchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID = Field(validation_alias="id")
    email: str | None
    base_reference: str
