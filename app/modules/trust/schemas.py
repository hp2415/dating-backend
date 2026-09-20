"""M7 trust / governance API schemas."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class TrustEventReport(BaseModel):
    name: str = Field(max_length=48)
    domain: str = Field(max_length=24)
    value: Optional[float] = Field(default=None, ge=-100, le=100)
    note: Optional[str] = Field(default=None, max_length=200)
    subject_user_id: Optional[UUID] = None
    dedup_key: Optional[str] = Field(default=None, max_length=128)


class PhotoVerificationSubmit(BaseModel):
    similarity: float = Field(ge=0, le=1)
    quality_score: float = Field(ge=0, le=1)


class SafetyCheckinCreate(BaseModel):
    subject_kind: str = Field(max_length=24)
    subject_id: UUID
    result: str = Field(description="ok | issue")
    note: Optional[str] = Field(default=None, max_length=200)


class AdminVerificationReview(BaseModel):
    action: str = Field(description="approve | reject")
    reason: Optional[str] = Field(default=None, max_length=200)


class AdminSanctionCreate(BaseModel):
    user_id: UUID
    kind: str = Field(max_length=24)
    reason: str = Field(max_length=200)
    scope: Optional[str] = Field(default="global", max_length=64)
    expires_at: Optional[datetime] = None


class AdminSanctionRevoke(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=200)


class AdminModerationReview(BaseModel):
    action: str = Field(description="approve | reject")
    reason_code: Optional[str] = Field(default=None, max_length=32)
    admin_note: Optional[str] = Field(default=None, max_length=500)


class AdminTrustAdjust(BaseModel):
    user_id: UUID
    value: float = Field(ge=-100, le=100)
    note: str = Field(max_length=200)
    domain: str = Field(default="moderation", max_length=24)


class SensitiveWordUpsert(BaseModel):
    word: str = Field(max_length=64)
    category: str = Field(default="general", max_length=32)
    action: str = Field(default="review", max_length=16)
    enabled: bool = True
