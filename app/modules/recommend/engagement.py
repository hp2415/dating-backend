"""Redis-backed implicit activity engagement (tag/category weights + daily decay)."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from uuid import UUID

from app.shared.redis_client import get_redis

VIEWED = 1.0
FAVORITED = 3.0
JOINED = 7.0
EVENT_WEIGHTS = {"view": VIEWED, "favorite": FAVORITED, "join": JOINED}

MAX_WEIGHT = 60.0
DECAY_RATE = 0.9
DROP_BELOW = 0.4


class EngagementStore:
    def __init__(self, user_id: UUID):
        self.user_id = user_id
        self.redis = get_redis()
        self._key = f"eng:act:{user_id}"

    async def _load_raw(self) -> dict:
        raw = await self.redis.get(self._key)
        if not raw:
            return {"tags": {}, "categories": {}, "last_decay": date.today().isoformat()}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {"tags": {}, "categories": {}, "last_decay": date.today().isoformat()}
        data.setdefault("tags", {})
        data.setdefault("categories", {})
        data.setdefault("last_decay", date.today().isoformat())
        return data

    async def _save(self, data: dict) -> None:
        await self.redis.set(self._key, json.dumps(data), ex=60 * 60 * 24 * 180)

    def _apply_decay(self, data: dict) -> dict:
        try:
            last = date.fromisoformat(data.get("last_decay") or date.today().isoformat())
        except ValueError:
            last = date.today()
        today = date.today()
        days = (today - last).days
        if days <= 0:
            return data
        factor = DECAY_RATE**days

        def decay_map(m: dict) -> dict:
            out = {}
            for k, v in m.items():
                try:
                    nv = float(v) * factor
                except (TypeError, ValueError):
                    continue
                if nv > DROP_BELOW:
                    out[k] = nv
            return out

        data["tags"] = decay_map(data.get("tags") or {})
        data["categories"] = decay_map(data.get("categories") or {})
        data["last_decay"] = today.isoformat()
        return data

    async def record(self, event: str, *, category: str, tags: list[str]) -> None:
        weight = EVENT_WEIGHTS.get(event)
        if weight is None:
            return
        data = self._apply_decay(await self._load_raw())
        tags_map = dict(data.get("tags") or {})
        cats_map = dict(data.get("categories") or {})
        for tag in tags:
            if not tag:
                continue
            tags_map[tag] = min(MAX_WEIGHT, float(tags_map.get(tag, 0.0)) + weight)
        if category:
            cats_map[category] = min(MAX_WEIGHT, float(cats_map.get(category, 0.0)) + weight)
        data["tags"] = tags_map
        data["categories"] = cats_map
        await self._save(data)

    async def weights(self) -> tuple[dict[str, float], dict[str, float]]:
        data = self._apply_decay(await self._load_raw())
        await self._save(data)
        tags = {k: float(v) for k, v in (data.get("tags") or {}).items()}
        cats = {k: float(v) for k, v in (data.get("categories") or {}).items()}
        return tags, cats

    def implicit_score(
        self,
        *,
        category: str,
        tags: list[str],
        tag_weights: dict[str, float],
        category_weights: dict[str, float],
    ) -> float:
        raw = 0.0
        for tag in tags:
            raw += float(tag_weights.get(tag, 0.0))
        raw += float(category_weights.get(category, 0.0)) * 0.5
        return raw


def derive_tags(title: str, description: str, category: str) -> list[str]:
    """Activities have no tags column — derive lightweight tags for interest/engagement."""
    out: list[str] = []
    if category:
        out.append(category)
    for token in (title or "").replace("，", " ").replace(",", " ").split():
        t = token.strip()
        if len(t) >= 2:
            out.append(t)
    # keep short unique list
    seen: set[str] = set()
    uniq: list[str] = []
    for t in out:
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(t)
    return uniq[:12]
