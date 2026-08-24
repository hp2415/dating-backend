"""Browse shelf builder — ported from ActivityBrowseShelfBuilder."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.modules.recommend.activity_scorer import (
    ScoredActivity,
    ScorerContext,
    has_available_spots,
    is_almost_full,
    is_past,
    ranked,
    score_activity,
)

MINIMUM_COUNT = 2
RAIL_LIMIT = 10
RANKED_LIMIT = 10

# layout hints for Android UI
LAYOUT_BY_ID = {
    "following": "rail",
    "filling": "rail",
    "nearby": "rail",
    "free": "rail",
    "soon": "rail",
    "tonight": "rail",
    "weekend": "rail",
    "forYou": "list",
    "ranked": "ranked",
    "more": "list",
}


@dataclass
class Shelf:
    id: str
    title: str
    layout: str
    items: list[ScoredActivity]
    subtitle: str = ""


def _layout_for(shelf_id: str) -> str:
    if shelf_id.startswith("interest."):
        return "rail"
    if shelf_id.startswith("category."):
        return "ranked"
    return LAYOUT_BY_ID.get(shelf_id, "list")


def build_shelves(activities: list[ScoredActivity], ctx: ScorerContext) -> list[Shelf]:
    now = ctx.now
    remaining = list(activities)
    claimed: set[str] = set()
    shelves: list[Shelf] = []

    def append(shelf: Shelf, claim: bool = True) -> None:
        if len(shelf.items) < MINIMUM_COUNT:
            return
        if claim:
            claimed.update(x.id for x in shelf.items)
        shelves.append(shelf)

    # 1 following
    append(
        Shelf(
            id="following",
            title="你参加的",
            layout=_layout_for("following"),
            items=[a for a in remaining if a.joined and not is_past(a, now)][:8],
        )
    )

    # 2 filling
    append(
        Shelf(
            id="filling",
            title="即将满员",
            layout=_layout_for("filling"),
            items=[
                a
                for a in remaining
                if is_almost_full(a) and has_available_spots(a) and not is_past(a, now)
            ][:RAIL_LIMIT],
        )
    )

    # 3 nearby
    nearby = [
        a for a in remaining if has_available_spots(a) and not is_past(a, now)
    ]
    nearby.sort(key=lambda a: a.distance_km if a.distance_km is not None else 1e9)
    append(Shelf(id="nearby", title="离你最近", layout=_layout_for("nearby"), items=nearby[:RAIL_LIMIT]))

    # 4 free (no fee field yet — keep as available pool sample)
    append(
        Shelf(
            id="free",
            title="免费活动",
            layout=_layout_for("free"),
            items=[a for a in remaining if has_available_spots(a) and not is_past(a, now)][:RAIL_LIMIT],
        )
    )

    # 5 soon
    soon_end = now + timedelta(hours=48)
    soon_items = []
    for a in remaining:
        if not has_available_spots(a) or is_past(a, now) or a.start_at is None:
            continue
        start = a.start_at if a.start_at.tzinfo else a.start_at.replace(tzinfo=timezone.utc)
        if now <= start < soon_end:
            soon_items.append(a)
    append(Shelf(id="soon", title="即将开始", layout=_layout_for("soon"), items=soon_items[:8]))

    # 6 tonight
    local_hour = now.astimezone().hour if now.tzinfo else now.hour
    tonight = []
    for a in remaining:
        if not has_available_spots(a) or is_past(a, now) or a.start_at is None:
            continue
        start = a.start_at if a.start_at.tzinfo else a.start_at.replace(tzinfo=timezone.utc)
        if start.date() == now.astimezone().date() and local_hour >= 17:
            tonight.append(a)
    append(Shelf(id="tonight", title="今晚可去", layout=_layout_for("tonight"), items=tonight[:RAIL_LIMIT]))

    # 7 weekend
    weekend = []
    for a in remaining:
        if not has_available_spots(a) or is_past(a, now) or a.start_at is None:
            continue
        start = a.start_at if a.start_at.tzinfo else a.start_at.replace(tzinfo=timezone.utc)
        if start.weekday() >= 5:
            weekend.append(a)
    append(Shelf(id="weekend", title="周末活动", layout=_layout_for("weekend"), items=weekend[:RAIL_LIMIT]))

    # 8 forYou
    append(
        Shelf(
            id="forYou",
            title="为你精选",
            layout=_layout_for("forYou"),
            items=ranked(
                [a for a in remaining if has_available_spots(a) and not is_past(a, now)],
                ctx,
                exclude_ids=claimed,
                limit=8,
            ),
        )
    )

    # 9 interest shelves
    for interest in list(dict.fromkeys(ctx.user_interests))[:5]:
        items = [
            a
            for a in remaining
            if has_available_spots(a)
            and not is_past(a, now)
            and (
                any(interest.lower() in t.lower() for t in a.tags)
                or interest.lower() in (a.title or "").lower()
            )
        ][:RAIL_LIMIT]
        append(
            Shelf(
                id=f"interest.{interest}",
                title=f"喜欢{interest}的人也去",
                layout=_layout_for(f"interest.{interest}"),
                items=items,
            )
        )

    # 10 category shelves
    cats = list(dict.fromkeys(a.category for a in remaining))[:5]
    for cat in cats:
        pool = [
            a
            for a in remaining
            if a.category == cat and has_available_spots(a) and not is_past(a, now)
        ]
        for a in pool:
            score_activity(a, ctx)
        pool.sort(key=lambda x: -x.score)
        append(
            Shelf(
                id=f"category.{cat}",
                title=cat,
                layout=_layout_for(f"category.{cat}"),
                items=pool[:RANKED_LIMIT],
            )
        )

    # 11 ranked (no claim)
    append(
        Shelf(
            id="ranked",
            title="本周推荐榜",
            layout=_layout_for("ranked"),
            items=ranked(
                [a for a in remaining if not is_past(a, now)],
                ctx,
                exclude_ids=claimed,
                limit=RANKED_LIMIT,
                include_full=True,
            ),
        ),
        claim=False,
    )

    # 12 more
    append(
        Shelf(
            id="more",
            title="还有这些局",
            layout=_layout_for("more"),
            items=ranked(
                [
                    a
                    for a in remaining
                    if has_available_spots(a) and not is_past(a, now) and a.id not in claimed
                ],
                ctx,
                exclude_ids=claimed,
                limit=12,
            ),
        )
    )

    return _reorder_for_engagement(shelves, ctx)


def _reorder_for_engagement(shelves: list[Shelf], ctx: ScorerContext) -> list[Shelf]:
    head = {"following", "editorial"}
    tail = {"ranked", "more"}
    pinned: list[Shelf] = []
    middle: list[Shelf] = []
    tails: list[Shelf] = []
    for s in shelves:
        if s.id in head:
            pinned.append(s)
        elif s.id in tail:
            tails.append(s)
        else:
            middle.append(s)

    def strength(s: Shelf) -> float:
        if not s.items:
            return 0.0
        mean = sum(score_activity(x, ctx) for x in s.items[:3]) / min(3, len(s.items))
        local_hour = ctx.now.astimezone().hour if ctx.now.tzinfo else ctx.now.hour
        weekday = ctx.now.astimezone().weekday() if ctx.now.tzinfo else ctx.now.weekday()
        bonus = 0.0
        if s.id == "tonight" and local_hour >= 17:
            bonus = 40.0
        elif s.id == "weekend" and weekday in (5, 6, 0):
            bonus = 30.0
        elif s.id == "filling":
            bonus = 14.0
        elif s.id == "soon":
            bonus = 10.0
        return mean + bonus

    middle.sort(key=strength, reverse=True)
    # keep original tail order ranked then more
    tails_sorted = [s for sid in ("ranked", "more") for s in tails if s.id == sid]
    return pinned + middle + tails_sorted


def pick_featured(activities: list[ScoredActivity], ctx: ScorerContext) -> ScoredActivity | None:
    pool = [a for a in activities if has_available_spots(a) and not is_past(a, ctx.now)]
    if not pool:
        pool = [a for a in activities if not is_past(a, ctx.now)]
    if not pool:
        return None
    ranked_list = ranked(pool, ctx, limit=5)
    if not ranked_list:
        return None
    top = ranked_list[0].score
    keep = [a for a in ranked_list if a.score >= top * 0.7]
    return keep[0] if keep else ranked_list[0]
