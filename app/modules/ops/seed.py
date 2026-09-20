"""Seed default taxonomies for discover / activities."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Taxonomy, TaxonomyKind


DEFAULT_ACTIVITY_CATEGORIES = [
    ("hiking", "徒步", 1),
    ("camping", "露营", 2),
    ("sports", "运动", 3),
    ("food", "美食", 4),
    ("other", "其他", 5),
]

DEFAULT_INTERESTS = [
    ("outdoors", "户外", 1),
    ("photography", "摄影", 2),
    ("music", "音乐", 3),
    ("boardgames", "桌游", 4),
    ("fitness", "健身", 5),
]

DEFAULT_CITIES = [
    ("shanghai", "上海", 1),
    ("beijing", "北京", 2),
    ("guangzhou", "广州", 3),
    ("shenzhen", "深圳", 4),
]


def default_taxonomy_seed_codes() -> list[str]:
    """Flat list of seeded taxonomy codes (for unit tests)."""
    return (
        [c for c, _, _ in DEFAULT_ACTIVITY_CATEGORIES]
        + [c for c, _, _ in DEFAULT_INTERESTS]
        + [c for c, _, _ in DEFAULT_CITIES]
    )


async def _ensure_kind(
    session: AsyncSession,
    *,
    kind: str,
    rows: list[tuple[str, str, int]],
) -> None:
    for code, name, sort_order in rows:
        existing = await session.execute(
            select(Taxonomy).where(Taxonomy.kind == kind, Taxonomy.code == code)
        )
        if existing.scalar_one_or_none() is not None:
            continue
        session.add(
            Taxonomy(
                id=uuid4(),
                kind=kind,
                code=code,
                name=name,
                sort_order=sort_order,
                enabled=True,
                meta={},
            )
        )


async def ensure_default_taxonomies(session: AsyncSession) -> None:
    await _ensure_kind(
        session,
        kind=TaxonomyKind.ACTIVITY_CATEGORY.value,
        rows=DEFAULT_ACTIVITY_CATEGORIES,
    )
    await _ensure_kind(
        session,
        kind=TaxonomyKind.INTEREST.value,
        rows=DEFAULT_INTERESTS,
    )
    city_count = int(
        (
            await session.execute(
                select(func.count())
                .select_from(Taxonomy)
                .where(Taxonomy.kind == TaxonomyKind.CITY.value)
            )
        ).scalar_one()
    )
    if city_count == 0:
        await _ensure_kind(
            session,
            kind=TaxonomyKind.CITY.value,
            rows=DEFAULT_CITIES,
        )
    await session.commit()
