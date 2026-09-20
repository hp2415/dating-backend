"""M8 ops / config API schemas."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class TaxonomyUpsert(BaseModel):
    kind: str = Field(max_length=32)
    code: str = Field(max_length=64)
    name: str = Field(max_length=80)
    parent_code: Optional[str] = Field(default=None, max_length=64)
    icon: Optional[str] = Field(default=None, max_length=64)
    sort_order: int = 0
    enabled: bool = True
    meta: dict = Field(default_factory=dict)


class ShelfUpsert(BaseModel):
    title: str = Field(max_length=80)
    subtitle: str = Field(default="", max_length=160)
    layout: str = Field(default="rail", max_length=16)
    rule_type: str = Field(default="manual", max_length=16)
    rule: dict = Field(default_factory=dict)
    city_scope: list[str] = Field(default_factory=list)
    sort_order: int = 0
    enabled: bool = True
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None


class ShelfItemUpsert(BaseModel):
    subject_kind: str = Field(max_length=24)
    subject_id: UUID
    sort_order: int = 0
    pinned: bool = False


class PushTokenRegister(BaseModel):
    device_id: str = Field(max_length=128)
    platform: str = Field(max_length=16)
    token: str = Field(max_length=512)
    provider: str = Field(default="fcm", max_length=16)


class NotificationRead(BaseModel):
    ids: Optional[list[UUID]] = None
    all: bool = False


class FeedbackCreate(BaseModel):
    category: str = Field(default="general", max_length=32)
    content: str = Field(min_length=1, max_length=4000)
    contact: Optional[str] = Field(default=None, max_length=64)


class AnnouncementCreate(BaseModel):
    title: str = Field(max_length=120)
    body: str = Field(default="", max_length=20000)
    pinned: bool = False
    audience: str = Field(default="all", max_length=32)
    publish_at: Optional[datetime] = None
    expire_at: Optional[datetime] = None


class CampaignCreate(BaseModel):
    title: str = Field(max_length=120)
    body: str = Field(default="", max_length=500)
    deep_link: Optional[str] = Field(default=None, max_length=240)
    audience: dict = Field(default_factory=dict)
    scheduled_at: Optional[datetime] = None


class CampaignSend(BaseModel):
    """Optional override audience for one-shot send; empty = use campaign.audience."""

    audience: Optional[dict] = None


class FeedbackReply(BaseModel):
    reply: str = Field(min_length=1, max_length=4000)
