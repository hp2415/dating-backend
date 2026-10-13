from datetime import date, datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

Occupation = Literal["学生", "上班", "自由职业", "其他"]
MeetRadius = Literal["同城见面", "可跨城", "仅线上先聊"]
Mbti = Literal[
    "INTJ", "INTP", "ENTJ", "ENTP",
    "INFJ", "INFP", "ENFJ", "ENFP",
    "ISTJ", "ISFJ", "ESTJ", "ESFJ",
    "ISTP", "ISFP", "ESTP", "ESFP",
]
Zodiac = Literal[
    "摩羯座", "水瓶座", "双鱼座", "白羊座", "金牛座", "双子座",
    "巨蟹座", "狮子座", "处女座", "天秤座", "天蝎座", "射手座",
]

# Explicit null clears these; legacy fields keep ignoring null.
PROFILE_EXTRA_KEYS = ("height_cm", "weight_kg", "occupation", "meet_radius", "mbti", "zodiac")


class ProfileUpdateRequest(BaseModel):
    display_name: Optional[str] = Field(default=None, max_length=64)
    birthday: Optional[date] = None
    gender: Optional[str] = Field(default=None, max_length=16)
    city: Optional[str] = Field(default=None, max_length=64)
    bio: Optional[str] = Field(default=None, max_length=500)
    tags: Optional[list[str]] = None
    avatar_media_id: Optional[UUID] = None
    height_cm: Optional[int] = Field(default=None, ge=100, le=250)
    weight_kg: Optional[int] = Field(default=None, ge=30, le=250)
    occupation: Optional[Occupation] = None
    meet_radius: Optional[MeetRadius] = None
    mbti: Optional[Mbti] = None
    zodiac: Optional[Zodiac] = None


class PreferenceUpdateRequest(BaseModel):
    want_genders: Optional[list[str]] = None
    age_min: Optional[int] = Field(default=None, ge=18, le=80)
    age_max: Optional[int] = Field(default=None, ge=18, le=80)
    max_distance_km: Optional[int] = Field(default=None, ge=1, le=500)


class SettingsUpdateRequest(BaseModel):
    show_distance: Optional[bool] = None
    show_online: Optional[bool] = None
    allow_invite: Optional[bool] = None
    notify_activity: Optional[bool] = None
    notify_buddy: Optional[bool] = None
    notify_message: Optional[bool] = None
    notify_community: Optional[bool] = None
    youth_mode: Optional[bool] = None
    guidelines_ack_at: Optional[datetime] = None
    legal_consent_at: Optional[datetime] = None


class DeleteAccountRequest(BaseModel):
    confirm: bool = False
