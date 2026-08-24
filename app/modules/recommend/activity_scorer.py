"""Activity recommendation scorer — ported from iOS/Android ActivityRecommender."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from hashlib import md5
from typing import Any


INTEREST_PER_TAG = 12
INTEREST_CATEGORY_BONUS = 8
INTEREST_CAP = 36.0
IMPLICIT_CAP = 22.0
DISTANCE_MAX = 25.0
MAX_KM = 12.0
NEARBY_KM = 3.0
NEARBY_BONUS = 4.0
TIME_CAP = 25.0
STARTING_SOON_HOURS = 48
URGENCY_ALMOST_FULL = 12.0
URGENCY_STARTING_SOON = 9.0
URGENCY_COMBO_BONUS = 7.0
URGENCY_CAP = 24.0
FRIEND_PER_PARTICIPANT = 15
FRIENDS_CAP = 30.0
QUALITY_CAP = 25.0
FRESHNESS_CAP = 20.0


@dataclass
class ScoredActivity:
    """Normalized activity dict used by scorer + shelf builder."""

    id: str
    title: str
    description: str
    category: str
    tags: list[str]
    capacity: int
    join_count: int
    media: list
    joined: bool
    start_at: datetime | None
    distance_km: float | None
    member_names: list[str]
    brief: dict[str, Any]
    catalog_index: int = 0
    score: float = 0.0


@dataclass
class ScorerContext:
    user_interests: list[str] = field(default_factory=list)
    current_user_name: str = ""
    friend_names: set[str] = field(default_factory=set)
    tag_weights: dict[str, float] = field(default_factory=dict)
    category_weights: dict[str, float] = field(default_factory=dict)
    now: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def has_available_spots(a: ScoredActivity) -> bool:
    return a.capacity == 0 or a.join_count < a.capacity


def is_almost_full(a: ScoredActivity) -> bool:
    return a.capacity > 0 and (a.join_count / a.capacity) >= 0.85


def is_past(a: ScoredActivity, now: datetime) -> bool:
    if a.start_at is None:
        return False
    start = a.start_at if a.start_at.tzinfo else a.start_at.replace(tzinfo=timezone.utc)
    ref = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    return start < ref


def interest_score(a: ScoredActivity, ctx: ScorerContext) -> float:
    score = 0.0
    lower_title = (a.title or "").lower()
    lower_desc = (a.description or "").lower()
    lower_cat = (a.category or "").lower()
    lower_tags = " ".join(a.tags).lower()
    for interest in ctx.user_interests:
        lower = interest.lower()
        if lower in lower_tags or lower in lower_title or lower in lower_desc:
            score += INTEREST_PER_TAG
    for interest in ctx.user_interests:
        li = interest.lower()
        if li in lower_cat or lower_cat in li:
            score += INTEREST_CATEGORY_BONUS
            break
    return min(score, INTEREST_CAP)


def implicit_score(a: ScoredActivity, ctx: ScorerContext) -> float:
    raw = 0.0
    for tag in a.tags:
        raw += float(ctx.tag_weights.get(tag, 0.0))
    raw += float(ctx.category_weights.get(a.category, 0.0)) * 0.5
    return min(raw, IMPLICIT_CAP)


def distance_score(a: ScoredActivity) -> float:
    dist = a.distance_km
    if dist is None:
        return 0.0
    if dist > MAX_KM:
        return 0.0
    score = (1.0 - dist / MAX_KM) * DISTANCE_MAX
    if dist <= NEARBY_KM:
        score += NEARBY_BONUS
    return min(score, DISTANCE_MAX)


def time_score(a: ScoredActivity, now: datetime) -> float:
    if a.start_at is None:
        return 4.0
    start = a.start_at if a.start_at.tzinfo else a.start_at.replace(tzinfo=timezone.utc)
    ref = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    hours_until = (start - ref).total_seconds() / 3600.0
    if hours_until < 24:
        score = 25.0
    elif hours_until < 48:
        score = 20.0
    elif hours_until < 24 * 7:
        score = 14.0
    elif hours_until < 24 * 14:
        score = 8.0
    else:
        score = 4.0
    if start.date() == ref.date():
        score += 3.0
    if start.weekday() >= 5:
        score += 2.0
    return min(score, TIME_CAP)


def urgency_score(a: ScoredActivity, now: datetime) -> float:
    if not has_available_spots(a) or a.start_at is None:
        return 0.0
    start = a.start_at if a.start_at.tzinfo else a.start_at.replace(tzinfo=timezone.utc)
    ref = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    hours_until = (start - ref).total_seconds() / 3600.0
    almost = is_almost_full(a)
    soon = 1 <= hours_until <= STARTING_SOON_HOURS
    score = 0.0
    if almost:
        score += URGENCY_ALMOST_FULL
    if soon:
        score += URGENCY_STARTING_SOON
    if almost and soon:
        score += URGENCY_COMBO_BONUS
    return min(score, URGENCY_CAP)


def friends_score(a: ScoredActivity, ctx: ScorerContext) -> float:
    matched = [n for n in a.member_names if n in ctx.friend_names and n != ctx.current_user_name]
    return min(len(matched) * FRIEND_PER_PARTICIPANT, FRIENDS_CAP)


def quality_score(a: ScoredActivity) -> float:
    score = 0.0
    fill = (a.join_count / a.capacity) if a.capacity > 0 else 0.0
    if fill >= 0.2:
        score += 6.0
    elif fill > 0:
        score += 3.0
    if a.media:
        score += 4.0
    if len(a.description or "") >= 24:
        score += 3.0
    if a.join_count >= 2:
        score += 2.0
    return min(score, QUALITY_CAP)


def freshness_score(a: ScoredActivity) -> float:
    idx = a.catalog_index
    score = {0: 20.0, 1: 15.0, 2: 10.0, 3: 5.0}.get(idx, 6.0)
    if a.joined:
        score -= 8.0
    return max(0.0, min(score, FRESHNESS_CAP))


def score_activity(a: ScoredActivity, ctx: ScorerContext) -> float:
    total = 0.0
    total += interest_score(a, ctx)
    total += implicit_score(a, ctx)
    total += distance_score(a)
    total += time_score(a, ctx.now)
    total += urgency_score(a, ctx.now)
    total += friends_score(a, ctx)
    total += quality_score(a)
    total += freshness_score(a)
    a.score = total
    return total


def daily_seed(activity_id: str, day: date | None = None) -> int:
    d = day or date.today()
    return int(md5(f"{activity_id}-{d.toordinal()}".encode()).hexdigest()[:8], 16)


def diversify(items: list[ScoredActivity]) -> list[ScoredActivity]:
    if len(items) <= 2:
        return items
    result = [items[0], items[1]]
    pool = list(items[2:])
    while pool:
        last2 = [x.category for x in result[-2:]]
        same = len(last2) == 2 and last2[0] == last2[1]
        if same:
            alt = next((x for x in pool if x.category != last2[0]), pool[0])
            pool.remove(alt)
            result.append(alt)
        else:
            result.append(pool.pop(0))
    return result


def ranked(
    activities: list[ScoredActivity],
    ctx: ScorerContext,
    *,
    exclude_ids: set[str] | None = None,
    limit: int = 10_000,
    include_full: bool = False,
) -> list[ScoredActivity]:
    exclude_ids = exclude_ids or set()
    candidates: list[ScoredActivity] = []
    for a in activities:
        if a.id in exclude_ids:
            continue
        if is_past(a, ctx.now):
            continue
        if not include_full and not has_available_spots(a):
            continue
        score_activity(a, ctx)
        candidates.append(a)
    candidates.sort(
        key=lambda x: (
            -x.score,
            daily_seed(x.id),
            x.distance_km if x.distance_km is not None else 1e9,
            x.start_at.timestamp() if x.start_at else 1e18,
        )
    )
    return diversify(candidates[:limit])
