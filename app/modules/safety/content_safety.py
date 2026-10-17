"""Content-safety provider abstraction (text).

* ``local``  — built-in sensitive-word list managed in 运营后台 (default, no external SDK)
* ``aliyun`` / ``tencent`` — placeholders: wire the vendor SDK in ``_CloudStubProvider.check_text``;
  until credentials exist the provider logs and falls back to the local word list.

Callers use :func:`guard_text`; the provider is selected by ``CONTENT_SAFETY_PROVIDER``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Protocol

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SensitiveWord
from app.shared.config import settings
from app.shared.errors import AppError
from app.shared.response import ErrorCodes

logger = logging.getLogger("dating.content_safety")


@dataclass
class TextVerdict:
    action: str = "pass"  # pass | warn | review | block
    hits: list[str] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return self.action == "block"

    @property
    def needs_review(self) -> bool:
        return self.action == "review"


_RANK = {"pass": 0, "warn": 1, "review": 2, "block": 3}


class ContentSafetyProvider(Protocol):
    name: str

    async def check_text(self, db: AsyncSession, text: str, *, scene: str) -> TextVerdict: ...


class LocalWordListProvider:
    name = "local"

    async def check_text(self, db: AsyncSession, text: str, *, scene: str) -> TextVerdict:
        content = (text or "").strip().lower()
        if not content:
            return TextVerdict()
        rows = (
            await db.execute(select(SensitiveWord.id, SensitiveWord.word, SensitiveWord.action).where(SensitiveWord.enabled.is_(True)))
        ).all()
        verdict = TextVerdict()
        hit_ids = []
        for wid, word, action in rows:
            if word and word.lower() in content:
                verdict.hits.append(word)
                hit_ids.append(wid)
                if _RANK.get(action, 2) > _RANK[verdict.action]:
                    verdict.action = action if action in _RANK else "review"
        if hit_ids:
            await db.execute(
                update(SensitiveWord).where(SensitiveWord.id.in_(hit_ids)).values(hit_count=SensitiveWord.hit_count + 1)
            )
        return verdict


class _CloudStubProvider(LocalWordListProvider):
    """Placeholder for a vendor text-moderation API (Aliyun Green / Tencent TMS)."""

    def __init__(self, name: str):
        self.name = name

    async def check_text(self, db: AsyncSession, text: str, *, scene: str) -> TextVerdict:
        logger.warning("content safety provider %s not configured, using local word list", self.name)
        return await super().check_text(db, text, scene=scene)


def get_provider() -> ContentSafetyProvider:
    name = (settings.content_safety_provider or "local").lower()
    if name in {"aliyun", "tencent"}:
        return _CloudStubProvider(name)
    return LocalWordListProvider()


async def guard_text(db: AsyncSession, *texts: str | None, scene: str, raise_on_block: bool = True) -> TextVerdict:
    """Check user-authored text. ``block`` raises COMMUNITY_INVALID-style 400, others are returned."""
    joined = "\n".join(t for t in texts if t)
    verdict = await get_provider().check_text(db, joined, scene=scene)
    if verdict.blocked and raise_on_block:
        raise AppError(ErrorCodes.VALIDATION_ERROR, "内容包含不适宜的表述，请修改后再试")
    return verdict


def content_safety_status() -> dict:
    name = (settings.content_safety_provider or "local").strip().lower()
    return {"provider": name, "ready": True, "real": False, "message": "cloud adapters fall back to local word list"}
