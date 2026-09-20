"""M6 companion / buddy API schemas."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class BuddyIntentUpsert(BaseModel):
    text: str = Field(max_length=280)
    tags: list[str] = Field(default_factory=list)
    city: Optional[str] = Field(default=None, max_length=64)
    active: bool = True
    expires_at: Optional[datetime] = None


class BuddyGreetRequest(BaseModel):
    text: str = Field(default="你好，交个朋友吧", max_length=200)


class BuddyInviteCreate(BaseModel):
    to_user_id: UUID
    activity_id: UUID
    message: str = Field(default="一起去玩吧", max_length=200)


class BuddyInviteRespond(BaseModel):
    action: str = Field(description="accept | decline")


class CompanionApplyRequest(BaseModel):
    service_type: str = Field(default="offline")
    specialty: str = Field(max_length=80)
    intro: str = Field(default="", max_length=2000)
    city: Optional[str] = Field(default=None, max_length=64)
    response_time_minutes: int = Field(default=30, ge=5, le=1440)


class CompanionProfileUpdate(BaseModel):
    specialty: Optional[str] = Field(default=None, max_length=80)
    intro: Optional[str] = Field(default=None, max_length=2000)
    city: Optional[str] = Field(default=None, max_length=64)
    service_type: Optional[str] = None
    response_time_minutes: Optional[int] = Field(default=None, ge=5, le=1440)
    status: Optional[str] = Field(default=None, description="active|paused — self only")


class CompanionServiceUpsert(BaseModel):
    title: str = Field(max_length=80)
    pricing_unit: str = Field(default="hour")
    price_cents: int = Field(ge=100)
    min_units: int = Field(default=1, ge=1)
    description: str = Field(default="", max_length=2000)
    sort_order: int = 0
    active: bool = True


class CompanionSlotCreate(BaseModel):
    start_at: datetime
    end_at: datetime


class BookingCreateRequest(BaseModel):
    companion_id: UUID
    service_id: UUID
    slot_id: UUID
    units: int = Field(default=1, ge=1)


class BookingActionRequest(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=200)
    scheduled_at: Optional[datetime] = None


class CompanionReviewCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    content: str = Field(default="", max_length=500)


class AdminCompanionReview(BaseModel):
    action: str = Field(description="approve | reject")
    reason: Optional[str] = Field(default=None, max_length=200)
