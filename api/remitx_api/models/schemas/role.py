import uuid

from pydantic import BaseModel, ConfigDict, Field


class RoleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    role_id: uuid.UUID
    name: str
    display_name: str = Field(validation_alias="role_display_name")
    description: str
    is_admin: bool
    permissions: list[str]
