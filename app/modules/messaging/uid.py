"""Public UID helpers (9-digit add-friend code)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


def derive_public_uid(user_id: UUID) -> str:
    """Deterministic 9-digit code from UUID (demo; collisions rare at our scale)."""
    n = int(user_id.hex[:12], 16) % 1_000_000_000
    return f"{n:09d}"


async def ensure_public_uid(db: AsyncSession, user: User) -> str:
    if user.public_uid:
        return user.public_uid
    candidate = derive_public_uid(user.id)
    # Resolve rare collision
    for i in range(20):
        uid = candidate if i == 0 else f"{(int(candidate) + i) % 1_000_000_000:09d}"
        hit = await db.execute(select(User.id).where(User.public_uid == uid, User.id != user.id))
        if hit.scalar_one_or_none() is None:
            user.public_uid = uid
            await db.flush()
            return uid
    user.public_uid = user.id.hex[:9]
    await db.flush()
    return user.public_uid
