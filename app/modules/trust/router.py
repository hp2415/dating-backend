"""Client trust / verification / safety APIs."""

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.modules.trust.schemas import (
    PhotoVerificationSubmit,
    SafetyCheckinCreate,
    TrustEventReport,
)
from app.modules.trust.service import TrustService
from app.shared.deps import get_current_user, get_db, get_request_id
from app.shared.response import ok

router = APIRouter(tags=["trust"])


@router.get("/api/v1/me/trust")
async def me_trust(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await TrustService(db).get_me_trust(user)
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.get("/api/v1/users/{user_id}/trust")
async def public_trust(
    user_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _ = user
    data = await TrustService(db).get_public_trust(user_id)
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.post("/api/v1/trust/events")
async def report_trust_event(
    body: TrustEventReport,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await TrustService(db).report_client_event(user, body)
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.post("/api/v1/verifications/photo")
async def submit_photo_verification(
    body: PhotoVerificationSubmit,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await TrustService(db).submit_photo_verification(
        user, similarity=body.similarity, quality_score=body.quality_score
    )
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.post("/api/v1/safety/checkins")
async def create_safety_checkin(
    body: SafetyCheckinCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await TrustService(db).create_safety_checkin(
        user,
        subject_kind=body.subject_kind,
        subject_id=body.subject_id,
        result=body.result,
        note=body.note or "",
    )
    await db.commit()
    return ok(data, request_id=get_request_id(request))
