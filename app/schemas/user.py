from pydantic import BaseModel, EmailStr
from uuid import UUID
from datetime import datetime


class UserDetail(BaseModel):
    id: UUID
    email: str
    is_active: bool
    oauth_provider: str | None = None
    created_at: datetime
    updated_at: datetime
    roles: list[str] = []

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    is_active: bool | None = None
