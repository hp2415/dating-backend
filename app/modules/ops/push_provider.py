"""Push provider abstraction.

``PUSH_PROVIDER=log`` (default): the in-app Notification row is the only delivery; nothing leaves the box.
Vendor adapters (fcm / hms / mipush / oppo / vivo / apns) are placeholders that refuse to run until
credentials exist and the vendor SDK is wired in ``VendorPushProvider.send``. Delivery is best-effort:
a push failure must never break the business transaction that created the notification.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PushToken
from app.shared.config import settings

logger = logging.getLogger("dating.push")


@dataclass
class PushMessage:
    title: str
    body: str = ""
    deep_link: str | None = None
    data: dict | None = None


class PushProvider(ABC):
    name: str

    @abstractmethod
    async def send(self, tokens: list[PushToken], message: PushMessage) -> dict:
        """Return {sent, failed, invalid_tokens: [token,...]}."""


class LogPushProvider(PushProvider):
    name = "log"

    async def send(self, tokens: list[PushToken], message: PushMessage) -> dict:
        logger.info("push[log] devices=%d title=%s", len(tokens), message.title)
        return {"sent": 0, "failed": 0, "invalid_tokens": [], "stub": True}


class VendorPushProvider(PushProvider):
    """Placeholder for FCM / HMS / MiPush / OPPO / vivo / APNs."""

    def __init__(self, name: str):
        self.name = name

    def configured(self) -> bool:
        if self.name == "apns":
            return bool(settings.push_apns_key_id and settings.push_apns_team_id and settings.push_apns_key_path)
        if self.name == "fcm":
            return bool(settings.push_fcm_credentials_json)
        return bool(settings.push_vendor_app_id and settings.push_vendor_app_secret)

    async def send(self, tokens: list[PushToken], message: PushMessage) -> dict:
        if not self.configured():
            raise RuntimeError(f"push provider {self.name} credentials not configured")
        # Wire the vendor SDK / HTTP API here. Refuse silent no-op so ops notice.
        raise NotImplementedError(f"push provider {self.name} SDK not wired yet")


def get_push_provider() -> PushProvider:
    name = (settings.push_provider or "log").strip().lower()
    if name in {"fcm", "hms", "mipush", "oppo", "vivo", "apns"}:
        return VendorPushProvider(name)
    return LogPushProvider()


def push_status() -> dict:
    name = (settings.push_provider or "log").strip().lower()
    provider = get_push_provider()
    ready = name == "log" or (isinstance(provider, VendorPushProvider) and provider.configured())
    return {"provider": name, "ready": ready, "real": name != "log"}


async def push_to_users(
    db: AsyncSession, user_ids: list[UUID], message: PushMessage
) -> dict:
    """Best-effort fan-out to the users' active device tokens. Never raises."""
    if not user_ids or (settings.push_provider or "log").strip().lower() == "log":
        return {"sent": 0, "failed": 0, "skipped": True}
    try:
        tokens = list(
            (
                await db.execute(
                    select(PushToken).where(PushToken.user_id.in_(user_ids), PushToken.active.is_(True))
                )
            ).scalars()
        )
        if not tokens:
            return {"sent": 0, "failed": 0}
        result = await get_push_provider().send(tokens, message)
        bad = set(result.get("invalid_tokens") or [])
        for t in tokens:
            if t.token in bad:
                t.active = False
        return result
    except Exception:  # noqa: BLE001
        logger.exception("push delivery failed (ignored)")
        return {"sent": 0, "failed": len(user_ids), "error": True}
