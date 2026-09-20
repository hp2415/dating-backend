"""Unified list pagination helpers.

Client feeds prefer cursor; admin tables use limit/offset + total.
All list payloads should converge on::

    { "items": [...], "page_info": { ... } }
"""

from typing import Any, Generic, Optional, Sequence, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PageInfo(BaseModel):
    next_cursor: Optional[str] = None
    has_more: bool = False
    total: Optional[int] = None
    limit: Optional[int] = None
    offset: Optional[int] = None


class Paginated(BaseModel, Generic[T]):
    items: list[T] = Field(default_factory=list)
    page_info: PageInfo = Field(default_factory=PageInfo)


def page_offset(
    items: Sequence[Any],
    *,
    total: int,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    """Admin-style offset pagination."""
    return {
        "items": list(items),
        "page_info": {
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + len(items) < total,
            "next_cursor": None,
        },
    }


def page_cursor(
    items: Sequence[Any],
    *,
    limit: int,
    next_cursor: str | None = None,
    has_more: bool | None = None,
) -> dict[str, Any]:
    """Feed-style cursor pagination."""
    more = has_more if has_more is not None else (next_cursor is not None)
    return {
        "items": list(items),
        "page_info": {
            "next_cursor": next_cursor,
            "has_more": more,
            "total": None,
            "limit": limit,
            "offset": None,
        },
    }


def legacy_admin_page(
    items: Sequence[Any],
    *,
    total: int,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    """Backward-compatible admin shape during migration.

    Existing web clients expect ``{items, total, limit, offset}``.
    Also embed ``page_info`` so new clients can adopt the unified contract.
    """
    unified = page_offset(items, total=total, limit=limit, offset=offset)
    return {
        "items": unified["items"],
        "total": total,
        "limit": limit,
        "offset": offset,
        "page_info": unified["page_info"],
    }
