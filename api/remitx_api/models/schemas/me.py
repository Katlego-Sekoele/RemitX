from pydantic import BaseModel, Field


class MeAccessResponse(BaseModel):
    permissions: list[str]
    is_admin: bool = Field(
        description=(
            "True when the caller holds an active role with is_admin set in "
            "the catalogue. Gates staff portal access."
        )
    )


class MyPermissionResponse(BaseModel):
    permission: str
    description: str


class MyRoleResponse(BaseModel):
    name: str
    display_name: str
    description: str
    permissions: list[MyPermissionResponse]
