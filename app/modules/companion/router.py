"""Client companion / buddy APIs."""

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.modules.companion.schemas import (
    BookingActionRequest,
    BookingCreateRequest,
    BuddyGreetRequest,
    BuddyIntentUpsert,
    BuddyInviteCreate,
    BuddyInviteRespond,
    CompanionApplyRequest,
    CompanionProfileUpdate,
    CompanionReviewCreate,
    CompanionServiceUpsert,
    CompanionSlotCreate,
)
from app.modules.companion.service import CompanionServiceLayer
from app.shared.deps import get_current_user, get_db, get_request_id
from app.shared.errors import AppError
from app.shared.pagination import page_offset
from app.shared.response import ErrorCodes, ok

router = APIRouter(tags=["companion"])


@router.get("/api/v1/buddies/feed")
async def buddy_feed(
    request: Request,
    sort: str = Query(default="recommended"),
    city: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items, total = await CompanionServiceLayer(db).buddy_feed(
        user, sort=sort, city=city, limit=limit, offset=offset
    )
    return ok(page_offset(items, total=total, limit=limit, offset=offset), request_id=get_request_id(request))


@router.get("/api/v1/me/buddy-intent")
async def get_buddy_intent(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await CompanionServiceLayer(db).get_my_intent(user.id)
    return ok(data, request_id=get_request_id(request))


@router.put("/api/v1/me/buddy-intent")
async def put_buddy_intent(
    body: BuddyIntentUpsert,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await CompanionServiceLayer(db).upsert_intent(
        user,
        text=body.text,
        tags=body.tags,
        city=body.city,
        active=body.active,
        expires_at=body.expires_at,
    )
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.post("/api/v1/buddies/{user_id}/greet")
async def greet_buddy(
    user_id: UUID,
    body: BuddyGreetRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await CompanionServiceLayer(db).greet(user, user_id, body.text)
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.post("/api/v1/buddies/invites")
async def create_invite(
    body: BuddyInviteCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await CompanionServiceLayer(db).create_invite(
        user, to_user_id=body.to_user_id, activity_id=body.activity_id, message=body.message
    )
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.get("/api/v1/me/buddy-invites")
async def list_invites(
    request: Request,
    direction: str = Query(default="incoming"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items = await CompanionServiceLayer(db).list_invites(user.id, direction=direction)
    return ok({"items": items}, request_id=get_request_id(request))


@router.post("/api/v1/buddy-invites/{invite_id}/respond")
async def respond_invite(
    invite_id: UUID,
    body: BuddyInviteRespond,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.action not in ("accept", "decline"):
        raise AppError(ErrorCodes.BUDDY_INVALID, "action 须为 accept|decline")
    data = await CompanionServiceLayer(db).respond_invite(user, invite_id, accept=body.action == "accept")
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.get("/api/v1/companions")
async def list_companions(
    request: Request,
    service_type: str | None = Query(default=None),
    city: str | None = Query(default=None),
    sort: str = Query(default="recommended"),
    available_only: bool = Query(default=False),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _ = user
    items, total = await CompanionServiceLayer(db).list_companions(
        service_type=service_type,
        city=city,
        sort=sort,
        available_only=available_only,
        limit=limit,
        offset=offset,
    )
    await db.commit()
    return ok(page_offset(items, total=total, limit=limit, offset=offset), request_id=get_request_id(request))


@router.get("/api/v1/companions/leaderboard")
async def companion_leaderboard(
    request: Request,
    period: str = Query(default="week"),
    limit: int = Query(default=50, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _ = user
    items = await CompanionServiceLayer(db).leaderboard(period=period, limit=limit)
    return ok({"items": items, "period": period}, request_id=get_request_id(request))


@router.post("/api/v1/companions/apply")
async def apply_companion(
    body: CompanionApplyRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await CompanionServiceLayer(db).apply(user, body)
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.get("/api/v1/companions/{companion_id}")
async def get_companion(
    companion_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _ = user
    data = await CompanionServiceLayer(db).get_companion(companion_id)
    return ok(data, request_id=get_request_id(request))


@router.get("/api/v1/companions/{companion_id}/slots")
async def companion_slots(
    companion_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _ = user
    items = await CompanionServiceLayer(db).list_slots(companion_id)
    await db.commit()
    return ok({"items": items}, request_id=get_request_id(request))


@router.get("/api/v1/companions/{companion_id}/reviews")
async def companion_reviews(
    companion_id: UUID,
    request: Request,
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _ = user
    items, total = await CompanionServiceLayer(db).list_reviews(companion_id, limit=limit, offset=offset)
    return ok(page_offset(items, total=total, limit=limit, offset=offset), request_id=get_request_id(request))


@router.post("/api/v1/companions/{companion_id}/reviews")
async def post_review(
    companion_id: UUID,
    body: CompanionReviewCreate,
    request: Request,
    booking_id: UUID = Query(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await CompanionServiceLayer(db).add_review(
        user, companion_id, booking_id=booking_id, rating=body.rating, content=body.content
    )
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.get("/api/v1/me/companion-profile")
async def my_companion_profile(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await CompanionServiceLayer(db).get_my_profile(user.id)
    return ok(data, request_id=get_request_id(request))


@router.put("/api/v1/me/companion-profile")
async def update_companion_profile(
    body: CompanionProfileUpdate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await CompanionServiceLayer(db).update_my_profile(user, body)
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.post("/api/v1/me/companion-profile/services")
async def add_service(
    body: CompanionServiceUpsert,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await CompanionServiceLayer(db).upsert_service(user, body)
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.put("/api/v1/me/companion-profile/services/{service_id}")
async def update_service(
    service_id: UUID,
    body: CompanionServiceUpsert,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await CompanionServiceLayer(db).upsert_service(user, body, service_id=service_id)
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.post("/api/v1/me/companion-profile/slots")
async def add_slot(
    body: CompanionSlotCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await CompanionServiceLayer(db).create_slot(user, start_at=body.start_at, end_at=body.end_at)
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.post("/api/v1/bookings")
async def create_booking(
    body: BookingCreateRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    if not idempotency_key:
        raise AppError(ErrorCodes.IDEMPOTENCY_REQUIRED, "预约须带 Idempotency-Key", status_code=400)
    if len(idempotency_key) > 64:
        raise AppError(ErrorCodes.IDEMPOTENCY_REQUIRED, "Idempotency-Key 最长 64 个字符", status_code=400)
    data = await CompanionServiceLayer(db).create_booking(
        user,
        companion_id=body.companion_id,
        service_id=body.service_id,
        slot_id=body.slot_id,
        units=body.units,
        idempotency_key=idempotency_key,
    )
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.get("/api/v1/me/bookings")
async def my_bookings(
    request: Request,
    as_companion: bool = Query(default=False),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items, total = await CompanionServiceLayer(db).list_my_bookings(
        user.id, as_companion=as_companion, limit=limit, offset=offset
    )
    return ok(page_offset(items, total=total, limit=limit, offset=offset), request_id=get_request_id(request))


@router.get("/api/v1/bookings/{booking_id}")
async def get_booking(
    booking_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await CompanionServiceLayer(db).get_booking(user, booking_id)
    return ok(data, request_id=get_request_id(request))


@router.post("/api/v1/bookings/{booking_id}/confirm")
async def booking_confirm(
    booking_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await CompanionServiceLayer(db).transition(user, booking_id, action="confirm")
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.post("/api/v1/bookings/{booking_id}/decline")
async def booking_decline(
    booking_id: UUID,
    request: Request,
    body: BookingActionRequest = BookingActionRequest(),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await CompanionServiceLayer(db).transition(user, booking_id, action="decline", reason=body.reason)
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.post("/api/v1/bookings/{booking_id}/start")
async def booking_start(
    booking_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await CompanionServiceLayer(db).transition(user, booking_id, action="start")
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.post("/api/v1/bookings/{booking_id}/complete")
async def booking_complete(
    booking_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await CompanionServiceLayer(db).transition(user, booking_id, action="complete")
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.post("/api/v1/bookings/{booking_id}/cancel")
async def booking_cancel(
    booking_id: UUID,
    request: Request,
    body: BookingActionRequest = BookingActionRequest(),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await CompanionServiceLayer(db).transition(user, booking_id, action="cancel", reason=body.reason)
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.post("/api/v1/bookings/{booking_id}/reschedule")
async def booking_reschedule(
    booking_id: UUID,
    body: BookingActionRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await CompanionServiceLayer(db).transition(
        user, booking_id, action="reschedule", reason=body.reason, scheduled_at=body.scheduled_at
    )
    await db.commit()
    return ok(data, request_id=get_request_id(request))
