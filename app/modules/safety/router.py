from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.modules.safety.service import BlockCreate, ReportCreate, SafetyService
from app.shared.deps import get_current_user, get_db, get_request_id
from app.shared.pagination import page_offset
from app.shared.response import ok

router = APIRouter(prefix="/api/v1", tags=["safety"])


@router.post("/reports")
async def create_report(
    body: ReportCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await SafetyService(db).create_report(user, body)
    return ok(data, request_id=get_request_id(request))


@router.get("/me/reports")
async def my_reports(
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items, total = await SafetyService(db).list_my_reports(user, limit=limit, offset=offset)
    return ok(page_offset(items, total=total, limit=limit, offset=offset), request_id=get_request_id(request))


@router.post("/blocks")
async def create_block(
    body: BlockCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await SafetyService(db).create_block(user, body.target_user_id)
    return ok(data, request_id=get_request_id(request))


@router.delete("/blocks/{user_id}")
async def delete_block(
    user_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from uuid import UUID

    data = await SafetyService(db).delete_block(user, UUID(user_id))
    return ok(data, request_id=get_request_id(request))


@router.get("/blocks")
async def list_blocks(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await SafetyService(db).list_blocks(user)
    return ok({"items": data}, request_id=get_request_id(request))
