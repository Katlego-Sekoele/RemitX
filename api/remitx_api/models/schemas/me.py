from pydantic import Field

from remitx_api.models.schemas.base import Schema


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
