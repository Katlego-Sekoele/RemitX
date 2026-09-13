from pydantic import ConfigDict, Field

from remitx_api.models.schemas.base import Schema
from remitx_api.models.schemas.kyc import KycStandingRead


class MeAccessResponse(Schema):
    permissions: list[str]
    is_admin: bool = Field(
        description=(
            "True when the caller holds an active role with is_admin set in "
            "the catalogue. Gates staff portal access."
        )
    )


class MyPermissionResponse(Schema):
    permission: str
    description: str


class MyRoleResponse(Schema):
    name: str
    display_name: str
    description: str
    permissions: list[MyPermissionResponse]


# Same rule as the KYC contact step: a plus and 8 to 15 digits.
E164_PATTERN = r"^\+[1-9]\d{7,14}$"


class ProfileRead(Schema):
    """The caller's own profile. Unmasked: it is their own data. Name, avatar
    and security settings are Clerk's and are edited in Clerk's component."""

    email: str | None = Field(description="The account email, owned by Clerk.")
    mobile_number: str | None = Field(description="Contact mobile, E.164.")
    kyc: KycStandingRead


class ProfileUpdate(Schema):
    """Null clears the mobile."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    mobile_number: str | None = Field(
        pattern=E164_PATTERN,
        description="International format, for example +27821234567.",
    )
