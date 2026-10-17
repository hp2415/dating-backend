"""Real-name / face verification provider abstraction.

``IDENTITY_PROVIDER=manual`` (default): face-photo verification goes to the admin review queue
(``/admin/v1/verifications``); real-name checks only validate the ID-number format locally and are
marked ``verified=False`` (never trusted as proof of identity).
``aliyun`` / ``tencent`` / ``wechat``: placeholders until credentials exist.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from app.shared.config import settings

_W = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
_C = "10X98765432"


def id_number_format_ok(id_no: str) -> bool:
    """GB 11643 checksum for the 18-digit mainland ID — format only, not an identity proof."""
    v = (id_no or "").strip().upper()
    if not re.fullmatch(r"\d{17}[\dX]", v):
        return False
    return _C[sum(int(c) * w for c, w in zip(v[:17], _W)) % 11] == v[17]


@dataclass
class IdentityResult:
    verified: bool
    reason: str = ""
    stub: bool = False


class IdentityProvider(Protocol):
    name: str

    async def verify_real_name(self, *, real_name: str, id_number: str) -> IdentityResult: ...

    async def compare_face(self, *, image_url: str, reference_url: str) -> float:
        """Similarity 0..1."""


class ManualIdentityProvider:
    name = "manual"

    async def verify_real_name(self, *, real_name: str, id_number: str) -> IdentityResult:
        if not real_name.strip() or not id_number_format_ok(id_number):
            return IdentityResult(False, "证件号格式不正确", stub=True)
        return IdentityResult(False, "未接入实名核验服务，仅格式校验通过", stub=True)

    async def compare_face(self, *, image_url: str, reference_url: str) -> float:
        raise NotImplementedError("人脸比对未接入，请走人工审核队列")


class VendorIdentityProvider(ManualIdentityProvider):
    def __init__(self, name: str):
        self.name = name

    def configured(self) -> bool:
        return bool(settings.identity_access_key_id and settings.identity_access_key_secret)

    async def verify_real_name(self, *, real_name: str, id_number: str) -> IdentityResult:
        if not self.configured():
            raise RuntimeError(f"identity provider {self.name} credentials not configured")
        raise NotImplementedError(f"identity provider {self.name} SDK not wired yet")

    async def compare_face(self, *, image_url: str, reference_url: str) -> float:
        if not self.configured():
            raise RuntimeError(f"identity provider {self.name} credentials not configured")
        raise NotImplementedError(f"identity provider {self.name} SDK not wired yet")


def get_identity_provider() -> IdentityProvider:
    name = (settings.identity_provider or "manual").strip().lower()
    if name in {"aliyun", "tencent", "wechat"}:
        return VendorIdentityProvider(name)
    return ManualIdentityProvider()


def identity_status() -> dict:
    name = (settings.identity_provider or "manual").strip().lower()
    p = get_identity_provider()
    ready = name == "manual" or (isinstance(p, VendorIdentityProvider) and p.configured())
    return {"provider": name, "ready": ready, "real": name != "manual"}
