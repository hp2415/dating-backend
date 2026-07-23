from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class AdminLoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)


class AdminOut(BaseModel):
    id: UUID
    username: str
    display_name: str
    role: str
    is_active: bool


class AdminLoginData(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    admin: AdminOut


class AdminMeOut(BaseModel):
    id: UUID
    username: str
    display_name: str
    role: str
    permissions: list[str]
    last_login_at: Optional[str] = None
