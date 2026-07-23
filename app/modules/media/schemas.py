from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class StsRequest(BaseModel):
    media_type: str = Field(
        default="avatar",
        pattern="^(avatar|album|chat|post_image|post_video|activity_image|activity_video)$",
    )
    content_type: str = Field(default="image/jpeg", max_length=64)
    ext: str = Field(default="jpg", max_length=8)


class StsResponse(BaseModel):
    upload_url: str
    object_key: str
    public_url: str
    method: str = "PUT"
    headers: dict[str, str] = {}
    expires_in: int = 600


class MediaCompleteRequest(BaseModel):
    object_key: str
    media_type: str = Field(
        default="avatar",
        pattern="^(avatar|album|chat|post_image|post_video|activity_image|activity_video)$",
    )
    set_as_avatar: bool = False
    width: Optional[int] = None
    height: Optional[int] = None


class MediaOut(BaseModel):
    id: UUID
    url: str
    media_type: str
    audit_status: str
    object_key: str
