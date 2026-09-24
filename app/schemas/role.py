from uuid import UUID

from pydantic import BaseModel


class PermissionResponse(BaseModel):
    id: UUID
    name: str
    description: str | None = None

    model_config = {"from_attributes": True}


class RoleCreate(BaseModel):
    name: str
    description: str | None = None
    permission_ids: list[UUID] = []


class RoleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    permission_ids: list[UUID] | None = None


class RoleResponse(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    permissions: list[PermissionResponse] = []

    model_config = {"from_attributes": True}


class AssignRolesRequest(BaseModel):
    role_ids: list[UUID]
