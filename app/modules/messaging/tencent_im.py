"""Tencent Cloud IM provider — UserSig + optional REST account/group helpers."""

from __future__ import annotations

import logging
import random
from typing import Any
from uuid import UUID, uuid4

import httpx

from app.modules.messaging.provider import ImProvider
from app.modules.messaging.usersig import gen_user_sig
from app.shared.config import settings

logger = logging.getLogger(__name__)


def _im_user_id(user_id: UUID) -> str:
    """Stable IM identifier — UUID string is accepted by Tencent IM."""
    return str(user_id)


class TencentImProvider(ImProvider):
    """Requires TENCENT_IM_SDK_APP_ID + TENCENT_IM_SECRET_KEY; IM_PROVIDER=tencent."""

    def __init__(self) -> None:
        self.sdk_app_id = int(settings.tencent_im_sdk_app_id or 0)
        self.secret_key = (settings.tencent_im_secret_key or "").strip()
        self.admin_user = (settings.tencent_im_admin_user or "administrator").strip()
        self.expire = int(settings.tencent_im_usersig_expire_seconds or 604800)
        if self.sdk_app_id <= 0 or not self.secret_key:
            raise RuntimeError(
                "IM_PROVIDER=tencent but TENCENT_IM_SDK_APP_ID / TENCENT_IM_SECRET_KEY missing"
            )

    def _user_sig(self, user_id: str) -> str:
        return gen_user_sig(
            sdk_app_id=self.sdk_app_id,
            secret_key=self.secret_key,
            user_id=user_id,
            expire_seconds=self.expire,
        )

    async def _rest(self, service: str, command: str, body: dict[str, Any]) -> dict[str, Any]:
        """Call https://console.tim.qq.com/v4/{service}/{command}."""
        admin_sig = self._user_sig(self.admin_user)
        url = (
            f"https://console.tim.qq.com/v4/{service}/{command}"
            f"?sdkappid={self.sdk_app_id}"
            f"&identifier={self.admin_user}"
            f"&usersig={admin_sig}"
            f"&random={random.randint(0, 0xFFFFFFFF)}"
            f"&contenttype=json"
        )
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=body)
            resp.raise_for_status()
            data = resp.json()
        if int(data.get("ErrorCode", -1)) != 0:
            logger.warning("tencent im rest %s/%s failed: %s", service, command, data)
        return data

    async def ensure_user(self, user_id: UUID, nickname: str) -> str:
        im_uid = _im_user_id(user_id)
        try:
            await self._rest(
                "im_open_login_svc",
                "account_import",
                {"Identifier": im_uid, "Nick": (nickname or "user")[:64]},
            )
        except Exception:
            # Login can auto-create accounts depending on console settings; don't block token.
            logger.exception("tencent account_import failed for %s", im_uid)
        return im_uid

    async def issue_token(self, user_id: UUID, *, conversation_id: UUID | None = None) -> dict:
        im_uid = _im_user_id(user_id)
        token = self._user_sig(im_uid)
        return {
            "provider": "tencent",
            "token": token,
            "expires_in": self.expire,
            "ready": True,
            "sdk_app_id": self.sdk_app_id,
            "im_user_id": im_uid,
            "conversation_id": str(conversation_id) if conversation_id else None,
            "message": "ok",
        }

    async def open_direct(self, user_a: UUID, user_b: UUID) -> str | None:
        # C2C has no shared room id; client sends to peer user id.
        low, high = sorted([_im_user_id(user_a), _im_user_id(user_b)])
        return f"c2c:{low}:{high}"

    async def open_group(self, owner_id: UUID, member_ids: list[UUID], title: str) -> str | None:
        group_id = f"spark_{uuid4().hex[:16]}"
        members = [{"Member_Account": _im_user_id(m)} for m in member_ids if m != owner_id]
        body: dict[str, Any] = {
            "Type": "Public",
            "GroupId": group_id,
            "Name": (title or "群聊")[:30],
            "Owner_Account": _im_user_id(owner_id),
        }
        if members:
            body["MemberList"] = members[:100]
        try:
            data = await self._rest("group_open_http_svc", "create_group", body)
            if int(data.get("ErrorCode", -1)) == 0:
                return data.get("GroupId") or group_id
        except Exception:
            logger.exception("tencent create_group failed")
        # Fallback id so backend conversation still stores a stable key; client may create later.
        return group_id

    async def disable_user(self, user_id: UUID) -> None:
        im_uid = _im_user_id(user_id)
        try:
            await self._rest("im_open_login_svc", "account_delete", {"DeleteItem": [{"UserID": im_uid}]})
        except Exception:
            logger.exception("tencent account_delete failed for %s", im_uid)
