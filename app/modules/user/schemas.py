from datetime import date
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ProfileUpdateRequest(BaseModel):
    display_name: Optional[str] = Field(default=None, max_length=64)
    birthday: Optional[date] = None
    gender: Optional[str] = Field(default=None, max_length=16)
    city: Optional[str] = Field(default=None, max_length=64)
    bio: Optional[str] = Field(default=None, max_length=500)
    tags: Optional[list[str]] = None
    avatar_media_id: Optional[UUID] = None


class PreferenceUpdateRequest(BaseModel):
    want_genders: Optional[list[str]] = None
    age_min: Optional[int] = Field(default=None, ge=18, le=80)
    age_max: Optional[int] = Field(default=None, ge=18, le=80)
    max_distance_km: Optional[int] = Field(default=None, ge=1, le=500)


class DeleteAccountRequest(BaseModel):
    confirm: bool = False
