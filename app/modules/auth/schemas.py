from datetime import date
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class SmsSendRequest(BaseModel):
    phone: str = Field(min_length=11, max_length=20)


class SmsLoginRequest(BaseModel):
    phone: str = Field(min_length=11, max_length=20)
    code: str = Field(min_length=4, max_length=8)
    device_id: str = Field(default="unknown", max_length=128)
    platform: str = Field(default="android", max_length=32)


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int


class UserBrief(BaseModel):
    id: UUID
    phone_masked: str
    profile_completed: bool
    discoverable: bool
    status: str


class LoginData(BaseModel):
    tokens: TokenPair
    user: UserBrief


class ProfileOut(BaseModel):
    display_name: Optional[str] = None
    birthday: Optional[date] = None
    gender: str = "unknown"
    city: Optional[str] = None
    bio: Optional[str] = None
    tags: list[str] = []
    avatar_url: Optional[str] = None
    completion_score: int = 0


class PreferenceOut(BaseModel):
    want_genders: list[str] = []
    age_min: int = 18
    age_max: int = 50
    max_distance_km: Optional[int] = None


class MeOut(BaseModel):
    id: UUID
    phone_masked: str
    profile_completed: bool
    discoverable: bool
    status: str
    profile: Optional[ProfileOut] = None
    preference: Optional[PreferenceOut] = None
