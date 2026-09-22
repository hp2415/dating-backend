from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class AnalyticsEventIn(BaseModel):
    event_id: UUID
    event_name: str = Field(min_length=1, max_length=64)
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


class AnalyticsBatchIn(BaseModel):
    events: list[AnalyticsEventIn] = Field(min_length=1, max_length=50)
