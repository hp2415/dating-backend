"""Idempotency-Key helpers for write endpoints (orders / pay / refund)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from fastapi import Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import IdempotencyRecord
from app.shared.config import settings
from app.shared.errors import AppError
from app.shared.response import ErrorCodes


def _hash_request(method: str, path: str, body: bytes | None) -> str:
    digest = hashlib.sha256()
    digest.update(method.upper().encode())
    digest.update(b"|")
    digest.update(path.encode())
    digest.update(b"|")
    digest.update(body or b"")
    return digest.hexdigest()


class IdempotencyService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def lookup(
        self,
        *,
        scope: str,
        key: str,
        user_id: UUID | None = None,
    ) -> IdempotencyRecord | None:
        result = await self.db.execute(
            select(IdempotencyRecord).where(
                IdempotencyRecord.scope == scope,
                IdempotencyRecord.key == key,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        if user_id is not None and row.user_id is not None and row.user_id != user_id:
            raise AppError(
                ErrorCodes.IDEMPOTENCY_CONFLICT,
                "Idempotency-Key 不属于当前用户",
                status_code=409,
            )
        if row.expires_at <= datetime.now(timezone.utc):
            await self.db.delete(row)
            await self.db.flush()
            return None
        return row

    async def begin(
        self,
        *,
        scope: str,
        key: str,
        user_id: UUID | None,
        request_hash: str,
    ) -> IdempotencyRecord | dict[str, Any]:
        """Return cached response dict if replay; otherwise create a pending row."""
        existing = await self.lookup(scope=scope, key=key, user_id=user_id)
        if existing is not None:
            if existing.request_hash and existing.request_hash != request_hash:
                raise AppError(
                    ErrorCodes.IDEMPOTENCY_CONFLICT,
                    "Idempotency-Key 已用于不同请求",
                    status_code=409,
                )
            if existing.status == "completed" and existing.response_snapshot is not None:
                return existing.response_snapshot
            if existing.status == "pending":
                raise AppError(
                    ErrorCodes.IDEMPOTENCY_IN_PROGRESS,
                    "相同请求正在处理中",
                    status_code=409,
                )

        row = IdempotencyRecord(
            id=uuid4(),
            scope=scope,
            key=key,
            user_id=user_id,
            request_hash=request_hash,
            status="pending",
            response_snapshot=None,
            expires_at=datetime.now(timezone.utc)
            + timedelta(seconds=settings.idempotency_ttl_seconds),
        )
        self.db.add(row)
        await self.db.flush()
        return row

    async def complete(self, row: IdempotencyRecord, response: dict[str, Any]) -> None:
        row.status = "completed"
        row.response_snapshot = response
        await self.db.flush()

    async def fail(self, row: IdempotencyRecord) -> None:
        await self.db.delete(row)
        await self.db.flush()


async def require_idempotency_key(
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> str:
    if not idempotency_key or not idempotency_key.strip():
        raise AppError(
            ErrorCodes.IDEMPOTENCY_REQUIRED,
            "缺少 Idempotency-Key",
            status_code=400,
        )
    if len(idempotency_key) > 128:
        raise AppError(ErrorCodes.IDEMPOTENCY_REQUIRED, "Idempotency-Key 过长", status_code=400)
    return idempotency_key.strip()


def request_body_hash(request: Request, body: bytes | None = None) -> str:
    return _hash_request(request.method, request.url.path, body)


def snapshot_ok(data: Any, message: str = "ok", request_id: str | None = None) -> dict[str, Any]:
    """Build a JSON-serializable success envelope for storage."""
    return {
        "code": 0,
        "message": message,
        "data": json.loads(json.dumps(data, default=str)),
        "request_id": request_id,
    }
