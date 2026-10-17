from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class AnalyticsEventIn(BaseModel):
    event_id: UUID
    event_name: str = Field(min_length=3, max_length=64)
    anon_id: str = Field(min_length=1, max_length=64)
    session_id: str = Field(min_length=1, max_length=64)
    screen: str | None = Field(default=None, max_length=64)
    referrer_screen: str | None = Field(default=None, max_length=64)
    props: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime
    platform: str = Field(default="android", max_length=16)
    app_version: str | None = Field(default=None, max_length=32)
    build_type: str | None = Field(default=None, max_length=16)
    os_version: str | None = Field(default=None, max_length=32)
    device_model: str | None = Field(default=None, max_length=64)
    network_type: str | None = Field(default=None, max_length=16)
    # v2
    channel: str | None = Field(default=None, max_length=32)
    experiments: dict[str, str] | None = None
    object_type: str | None = Field(default=None, max_length=24)
    object_id: str | None = Field(default=None, max_length=64)
    duration_ms: int | None = Field(default=None, ge=0, le=86_400_000)
    seq: int | None = Field(default=None, ge=0)


class AnalyticsBatchIn(BaseModel):
    schema_version: int = Field(default=1, ge=1, le=99)
    sdk_version: str | None = Field(default=None, max_length=16)
    # Client wall clock at the moment the batch was sent; used to correct device clock skew.
    sent_at: datetime | None = None
    events: list[AnalyticsEventIn] = Field(min_length=1, max_length=100)
