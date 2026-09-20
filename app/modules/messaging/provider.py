"""Cloud IM adapter — noop stub by default; swap without changing route contracts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any
from uuid import UUID

from app.shared.config import settings


class ImProvider(ABC):
    @abstractmethod
    async def ensure_user(self, user_id: UUID, nickname: str) -> str: ...

    @abstractmethod
    async def issue_token(self, user_id: UUID, *, conversation_id: UUID | None = None) -> dict: ...

    @abstractmethod
    async def open_direct(self, user_a: UUID, user_b: UUID) -> str | None: ...

    @abstractmethod
    async def open_group(self, owner_id: UUID, member_ids: list[UUID], title: str) -> str | None: ...

    @abstractmethod
    async def disable_user(self, user_id: UUID) -> None: ...


class NoopImProvider(ImProvider):
    """Demo provider: messages stay local-metadata only until a real SDK is wired."""

    async def ensure_user(self, user_id: UUID, nickname: str) -> str:
        return f"noop_{user_id}"

    async def issue_token(self, user_id: UUID, *, conversation_id: UUID | None = None) -> dict:
        return {
            "provider": "noop",
            "token": f"noop-token-{user_id}",
            "expires_in": 3600,
            "ready": False,
            "conversation_id": str(conversation_id) if conversation_id else None,
            "im_user_id": f"noop_{user_id}",
            "message": "云 IM 未接入（noop stub）。接融云/网易/腾讯 IM 时只替换 ImProvider。",
        }

    async def open_direct(self, user_a: UUID, user_b: UUID) -> str | None:
        low, high = sorted([str(user_a), str(user_b)])
        return f"noop_dm_{low[:8]}_{high[:8]}"

    async def open_group(self, owner_id: UUID, member_ids: list[UUID], title: str) -> str | None:
        return f"noop_group_{owner_id.hex[:12]}"

    async def disable_user(self, user_id: UUID) -> None:
        return None


def get_im_provider() -> ImProvider:
    # Reserved: settings.im_provider in {rongcloud, netease, tencent}
    if settings.im_provider != "noop":
        pass
    return NoopImProvider()


def im_status() -> dict[str, Any]:
    return {
        "provider": settings.im_provider,
        "ready": settings.im_provider != "noop",
        "message": "noop stub" if settings.im_provider == "noop" else "cloud im",
    }
