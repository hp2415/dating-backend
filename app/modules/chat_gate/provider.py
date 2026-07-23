from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from app.shared.config import settings


class ImProvider(ABC):
    """Third-party IM adapter. M2 uses Noop; swap to RongCloud/NetEase later."""

    @abstractmethod
    async def ensure_user(self, user_id: UUID, nickname: str) -> str:
        """Register/sync user on IM cloud; return vendor user id."""

    @abstractmethod
    async def issue_token(self, user_id: UUID) -> dict:
        """Issue short-lived IM token for client SDK."""

    @abstractmethod
    async def open_conversation(self, user_a: UUID, user_b: UUID) -> str | None:
        """Create or fetch 1v1 conversation id; None if provider is noop."""

    @abstractmethod
    async def disable_user(self, user_id: UUID) -> None:
        """Ban/disable IM account when user is banned."""


class NoopImProvider(ImProvider):
    async def ensure_user(self, user_id: UUID, nickname: str) -> str:
        return f"noop_{user_id}"

    async def issue_token(self, user_id: UUID) -> dict:
        return {
            "provider": "noop",
            "token": f"noop-token-{user_id}",
            "expires_in": 3600,
            "ready": False,
            "message": "IM SDK not configured; reserved for M3",
        }

    async def open_conversation(self, user_a: UUID, user_b: UUID) -> str | None:
        return None

    async def disable_user(self, user_id: UUID) -> None:
        return None


def get_im_provider() -> ImProvider:
    # M2/M3: swap by settings.im_provider when SDK is wired (rongcloud / netease / ...)
    if settings.im_provider != "noop":
        # Reserved: return vendor provider when implemented
        pass
    return NoopImProvider()
