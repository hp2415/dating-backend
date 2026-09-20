"""SMS provider abstraction — log stub by default; swap without changing auth routes."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any
from uuid import uuid4

from app.shared.config import settings

logger = logging.getLogger(__name__)


class SmsProvider(ABC):
    name: str

    @abstractmethod
    async def send_code(self, phone: str, code: str, *, scene: str = "login") -> dict[str, Any]:
        """Send verification code. Returns provider metadata for sms_send_logs."""


class LogSmsProvider(SmsProvider):
    """Default. Structured log only — no external send."""

    name = "log"

    async def send_code(self, phone: str, code: str, *, scene: str = "login") -> dict[str, Any]:
        masked = phone[:3] + "****" + phone[-4:] if len(phone) >= 7 else phone
        logger.info("SMS[%s] provider=log phone=%s code=%s", scene, masked, code)
        return {
            "provider": self.name,
            "provider_msg_id": f"log-{uuid4().hex[:12]}",
            "status": "sent",
            "error_code": None,
            "error_message": None,
        }


class AliyunSmsProvider(SmsProvider):
    """Reserved. Requires SMS_ACCESS_KEY_* + SMS_SIGN_NAME + SMS_TEMPLATE_CODE."""

    name = "aliyun"

    async def send_code(self, phone: str, code: str, *, scene: str = "login") -> dict[str, Any]:
        if not (settings.sms_access_key_id and settings.sms_access_key_secret and settings.sms_sign_name and settings.sms_template_code):
            raise RuntimeError("Aliyun SMS credentials not configured")
        # Wire SDK later — refuse silent no-op.
        raise NotImplementedError("Aliyun SMS SDK not wired yet")


class TencentSmsProvider(SmsProvider):
    name = "tencent"

    async def send_code(self, phone: str, code: str, *, scene: str = "login") -> dict[str, Any]:
        if not (settings.sms_access_key_id and settings.sms_access_key_secret and settings.sms_sign_name and settings.sms_template_code):
            raise RuntimeError("Tencent SMS credentials not configured")
        raise NotImplementedError("Tencent SMS SDK not wired yet")


def get_sms_provider() -> SmsProvider:
    name = (settings.sms_provider or "log").lower()
    if name == "aliyun":
        return AliyunSmsProvider()
    if name == "tencent":
        return TencentSmsProvider()
    return LogSmsProvider()


def sms_status() -> dict[str, Any]:
    return {
        "provider": settings.sms_provider,
        "allow_dev_code": settings.sms_allow_dev_code,
        "ready": settings.sms_provider == "log" or bool(settings.sms_access_key_id),
        "sign_name_set": bool(settings.sms_sign_name),
        "template_set": bool(settings.sms_template_code),
    }
