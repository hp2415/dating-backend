"""Cloud IM adapter — noop by default; set IM_PROVIDER=tencent for Tencent Cloud IM."""

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
            "sdk_app_id": 0,
            "im_user_id": f"noop_{user_id}",
            "conversation_id": str(conversation_id) if conversation_id else None,
            "message": "云 IM 未接入（noop stub）。设 IM_PROVIDER=tencent 并配置密钥后生效。",
        }

    async def open_direct(self, user_a: UUID, user_b: UUID) -> str | None:
        low, high = sorted([str(user_a), str(user_b)])
        return f"noop_dm_{low[:8]}_{high[:8]}"

    async def open_group(self, owner_id: UUID, member_ids: list[UUID], title: str) -> str | None:
        return f"noop_group_{owner_id.hex[:12]}"

    async def disable_user(self, user_id: UUID) -> None:
        return None


def get_im_provider() -> ImProvider:
    name = (settings.im_provider or "noop").strip().lower()
    if name == "tencent":
        from app.modules.messaging.tencent_im import TencentImProvider

        return TencentImProvider()
    return NoopImProvider()


def im_status() -> dict[str, Any]:
    ready = False
    message = "noop stub"
    if (settings.im_provider or "").strip().lower() == "tencent":
        ready = bool(settings.tencent_im_sdk_app_id and settings.tencent_im_secret_key)
        message = "tencent im" if ready else "tencent configured but keys missing"
    return {
        "provider": settings.im_provider,
        "ready": ready,
        "message": message,
    }
