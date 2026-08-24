"""Buddy match scorer — ported from BuddyMatchScorer.kt / iOS."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

SHARED_HOBBY = 12
AVAILABLE_BONUS = 5
ONLINE_BONUS = 3


def shared_hobbies(profile_tags: list[str], my_interests: list[str]) -> list[str]:
    shared: list[str] = []
    for tag in profile_tags or []:
        for interest in my_interests or []:
            if interest.lower() in tag.lower() or tag.lower() in interest.lower():
                shared.append(tag)
                break
    return shared


def is_online(last_active_at: datetime | None, *, now: datetime | None = None) -> bool:
    if last_active_at is None:
        return False
    ref = now or datetime.now(timezone.utc)
    ts = last_active_at if last_active_at.tzinfo else last_active_at.replace(tzinfo=timezone.utc)
    ref = ref if ref.tzinfo else ref.replace(tzinfo=timezone.utc)
    return (ref - ts) <= timedelta(minutes=15)


def score_buddy(
    *,
    profile_tags: list[str],
    my_interests: list[str],
    distance_km: float | None,
    available: bool,
    online: bool,
) -> tuple[int, list[str], str]:
    shared = shared_hobbies(profile_tags, my_interests)
    score = float(len(shared) * SHARED_HOBBY)
    if available:
        score += AVAILABLE_BONUS
    if distance_km is not None:
        score += max(0.0, 15.0 - float(distance_km))
    if online:
        score += ONLINE_BONUS

    reasons: list[str] = []
    if shared:
        reasons.append(f"共同兴趣 {', '.join(shared[:3])}")
    if online:
        reasons.append("近期在线")
    if available:
        reasons.append("可约")
    if distance_km is not None and distance_km <= 5:
        reasons.append(f"约 {distance_km:.0f} km")
    reason = " · ".join(reasons) if reasons else "推荐认识"
    return int(score), shared, reason
