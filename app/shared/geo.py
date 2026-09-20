"""PostGIS helpers. Extension enabled in migration 0007; columns added per-domain later."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession


async def ensure_postgis(conn: AsyncConnection) -> bool:
    """Return True if postgis is available after CREATE EXTENSION attempt."""
    try:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        return True
    except Exception:  # noqa: BLE001
        return False


async def postgis_ready(db: AsyncSession) -> bool:
    result = await db.execute(
        text("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'postgis')")
    )
    return bool(result.scalar())


def point_wkt(lng: float, lat: float) -> str:
    """WGS84 point as EWKT for geography inserts."""
    return f"SRID=4326;POINT({lng} {lat})"


async def nearby_ids(
    db: AsyncSession,
    *,
    table: str,
    lng: float,
    lat: float,
    radius_km: float,
    limit: int = 50,
) -> list[Any]:
    """Requires a ``location geography(Point,4326)`` column on ``table``.

    Table name is allowlisted by the caller — never pass user input.
    """
    allowed = {"user_profiles", "activities", "companion_profiles"}
    if table not in allowed:
        raise ValueError(f"table not allowlisted for geo query: {table}")
    origin = point_wkt(lng, lat)
    if table == "user_profiles":
        sql = text(
            """
            SELECT user_id AS id
            FROM user_profiles
            WHERE location IS NOT NULL
              AND ST_DWithin(location, ST_GeogFromText(:origin), :radius_m)
            ORDER BY location <-> ST_GeogFromText(:origin)
            LIMIT :limit
            """
        )
    else:
        sql = text(
            f"""
            SELECT id
            FROM {table}
            WHERE location IS NOT NULL
              AND ST_DWithin(location, ST_GeogFromText(:origin), :radius_m)
            ORDER BY location <-> ST_GeogFromText(:origin)
            LIMIT :limit
            """
        )
    result = await db.execute(
        sql,
        {"origin": origin, "radius_m": radius_km * 1000.0, "limit": limit},
    )
    return [row[0] for row in result.fetchall()]
