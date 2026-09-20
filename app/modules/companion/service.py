"""Buddy free path + companion booking marketplace."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Activity,
    ActivityStatus,
    BookingStatus,
    BuddyGreeting,
    BuddyGreetingStatus,
    BuddyIntent,
    BuddyInvite,
    BuddyInviteStatus,
    CompanionBooking,
    CompanionLeaderboard,
    CompanionProfile,
    CompanionProfileStatus,
    CompanionReview,
    CompanionService,
    CompanionServiceType,
    CompanionSlot,
    LeaderboardPeriod,
    OrderKind,
    PricingUnit,
    SlotStatus,
    User,
    UserProfile,
)
from app.modules.commerce.service import CommerceService
from app.modules.events.service import DomainEventName, DomainEventService
from app.modules.safety.service import is_blocked_either
from app.shared.errors import AppError
from app.shared.response import ErrorCodes


class CompanionServiceLayer:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.events = DomainEventService(db)
        self.commerce = CommerceService(db)

    # ── free buddy path ────────────────────────────────────

    async def get_my_intent(self, user_id: UUID) -> dict | None:
        row = await self._intent_of(user_id)
        return self.intent_brief(row) if row else None

    async def upsert_intent(self, user: User, *, text: str, tags: list[str], city: str | None, active: bool, expires_at: datetime | None) -> dict:
        row = await self._intent_of(user.id)
        if row is None:
            row = BuddyIntent(id=uuid4(), user_id=user.id)
            self.db.add(row)
        row.text = (text or "").strip()[:280]
        row.tags = [t.strip()[:32] for t in tags if t.strip()][:12]
        row.city = city
        row.active = active
        row.expires_at = expires_at
        await self.db.flush()
        return self.intent_brief(row)

    async def buddy_feed(
        self, user: User, *, sort: str, city: str | None, limit: int, offset: int
    ) -> tuple[list[dict], int]:
        now = datetime.now(timezone.utc)
        filters = [
            BuddyIntent.active.is_(True),
            BuddyIntent.user_id != user.id,
            or_(BuddyIntent.expires_at.is_(None), BuddyIntent.expires_at > now),
        ]
        if city:
            filters.append(BuddyIntent.city == city)
        count_q = select(func.count()).select_from(BuddyIntent).where(*filters)
        total = int((await self.db.execute(count_q)).scalar_one())
        stmt = select(BuddyIntent).where(*filters)
        if sort == "active":
            stmt = stmt.order_by(BuddyIntent.updated_at.desc())
        else:
            stmt = stmt.order_by(BuddyIntent.created_at.desc())
        rows = list((await self.db.execute(stmt.limit(limit).offset(offset))).scalars().all())
        items = []
        for intent in rows:
            items.append(
                {
                    **self.intent_brief(intent),
                    "display_name": await self._display_name(intent.user_id),
                    "user_id": str(intent.user_id),
                }
            )
        return items, total

    async def greet(self, user: User, to_user_id: UUID, text: str) -> dict:
        if to_user_id == user.id:
            raise AppError(ErrorCodes.BUDDY_INVALID, "不能向自己打招呼")
        peer = await self.db.get(User, to_user_id)
        if peer is None:
            raise AppError(ErrorCodes.USER_NOT_FOUND, "用户不存在", status_code=404)
        if await is_blocked_either(self.db, user.id, to_user_id):
            raise AppError(ErrorCodes.CHAT_FORBIDDEN, "已拉黑", status_code=403)
        existing = await self.db.execute(
            select(BuddyGreeting).where(
                BuddyGreeting.from_user_id == user.id,
                BuddyGreeting.to_user_id == to_user_id,
                BuddyGreeting.status == BuddyGreetingStatus.SENT.value,
            )
        )
        hit = existing.scalar_one_or_none()
        if hit:
            return self.greeting_brief(hit)
        row = BuddyGreeting(
            id=uuid4(),
            from_user_id=user.id,
            to_user_id=to_user_id,
            text=(text or "")[:200],
            status=BuddyGreetingStatus.SENT.value,
        )
        self.db.add(row)
        await self.db.flush()
        await self.events.enqueue(
            name=DomainEventName.BUDDY_GREETING_SENT,
            aggregate_kind="buddy_greeting",
            aggregate_id=row.id,
            payload={"from": str(user.id), "to": str(to_user_id)},
        )
        return self.greeting_brief(row)

    async def create_invite(self, user: User, *, to_user_id: UUID, activity_id: UUID, message: str) -> dict:
        if to_user_id == user.id:
            raise AppError(ErrorCodes.BUDDY_INVALID, "不能邀约自己")
        activity = await self.db.get(Activity, activity_id)
        if activity is None or activity.status == ActivityStatus.CANCELLED.value:
            raise AppError(ErrorCodes.ACTIVITY_NOT_FOUND, "活动不存在", status_code=404)
        row = BuddyInvite(
            id=uuid4(),
            from_user_id=user.id,
            to_user_id=to_user_id,
            activity_id=activity_id,
            message=(message or "")[:200],
            status=BuddyInviteStatus.PENDING.value,
        )
        self.db.add(row)
        await self.db.flush()
        await self.events.enqueue(
            name=DomainEventName.BUDDY_INVITE_SENT,
            aggregate_kind="buddy_invite",
            aggregate_id=row.id,
            payload={"from": str(user.id), "to": str(to_user_id), "activity_id": str(activity_id)},
        )
        return self.invite_brief(row)

    async def list_invites(self, user_id: UUID, *, direction: str) -> list[dict]:
        if direction == "sent":
            stmt = select(BuddyInvite).where(BuddyInvite.from_user_id == user_id)
        else:
            stmt = select(BuddyInvite).where(BuddyInvite.to_user_id == user_id)
        rows = list((await self.db.execute(stmt.order_by(BuddyInvite.created_at.desc()))).scalars().all())
        return [self.invite_brief(r) for r in rows]

    async def respond_invite(self, user: User, invite_id: UUID, *, accept: bool) -> dict:
        row = await self.db.get(BuddyInvite, invite_id)
        if row is None or row.to_user_id != user.id:
            raise AppError(ErrorCodes.BUDDY_NOT_FOUND, "邀约不存在", status_code=404)
        if row.status != BuddyInviteStatus.PENDING.value:
            raise AppError(ErrorCodes.BUDDY_INVALID, "邀约已处理", status_code=409)
        row.status = BuddyInviteStatus.ACCEPTED.value if accept else BuddyInviteStatus.DECLINED.value
        row.responded_at = datetime.now(timezone.utc)
        await self.db.flush()
        return self.invite_brief(row)

    # ── companion profile ──────────────────────────────────

    async def apply(self, user: User, body) -> dict:
        existing = await self.db.get(CompanionProfile, user.id)
        if existing and existing.status == CompanionProfileStatus.ACTIVE.value:
            raise AppError(ErrorCodes.COMPANION_INVALID, "已是陪玩师", status_code=409)
        profile = existing or CompanionProfile(user_id=user.id)
        if existing is None:
            self.db.add(profile)
        st = body.service_type if body.service_type in {e.value for e in CompanionServiceType} else CompanionServiceType.OFFLINE.value
        profile.service_type = st
        profile.specialty = body.specialty.strip()[:80]
        profile.intro = (body.intro or "")[:2000]
        profile.city = body.city
        profile.response_time_minutes = body.response_time_minutes
        profile.status = CompanionProfileStatus.PENDING.value
        profile.reject_reason = None
        await self.db.flush()
        await self.events.enqueue(
            name=DomainEventName.COMPANION_APPLIED,
            aggregate_kind="companion",
            aggregate_id=user.id,
            payload={"user_id": str(user.id)},
        )
        return await self.profile_brief(profile, include_private=True)

    async def get_my_profile(self, user_id: UUID) -> dict | None:
        profile = await self.db.get(CompanionProfile, user_id)
        if profile is None:
            return None
        return await self.profile_brief(profile, include_private=True, include_services=True)

    async def update_my_profile(self, user: User, body) -> dict:
        profile = await self.db.get(CompanionProfile, user.id)
        if profile is None:
            raise AppError(ErrorCodes.COMPANION_NOT_FOUND, "尚未申请陪玩", status_code=404)
        if body.specialty is not None:
            profile.specialty = body.specialty.strip()[:80]
        if body.intro is not None:
            profile.intro = body.intro[:2000]
        if body.city is not None:
            profile.city = body.city
        if body.service_type is not None and body.service_type in {e.value for e in CompanionServiceType}:
            profile.service_type = body.service_type
        if body.response_time_minutes is not None:
            profile.response_time_minutes = body.response_time_minutes
        if body.status in (CompanionProfileStatus.ACTIVE.value, CompanionProfileStatus.PAUSED.value):
            if profile.status not in {
                CompanionProfileStatus.ACTIVE.value,
                CompanionProfileStatus.PAUSED.value,
            }:
                raise AppError(ErrorCodes.COMPANION_FORBIDDEN, "资料未通过审核，无法改状态", status_code=403)
            profile.status = body.status
        await self.db.flush()
        return await self.profile_brief(profile, include_private=True, include_services=True)

    async def upsert_service(self, user: User, body, service_id: UUID | None = None) -> dict:
        profile = await self._require_own_companion(user.id)
        unit = body.pricing_unit if body.pricing_unit in {e.value for e in PricingUnit} else PricingUnit.HOUR.value
        if service_id:
            svc = await self.db.get(CompanionService, service_id)
            if svc is None or svc.companion_id != user.id:
                raise AppError(ErrorCodes.COMPANION_NOT_FOUND, "服务不存在", status_code=404)
        else:
            svc = CompanionService(id=uuid4(), companion_id=profile.user_id)
            self.db.add(svc)
        svc.title = body.title.strip()[:80]
        svc.pricing_unit = unit
        svc.price_cents = body.price_cents
        svc.min_units = body.min_units
        svc.description = (body.description or "")[:2000]
        svc.sort_order = body.sort_order
        svc.active = body.active
        await self.db.flush()
        return self.service_brief(svc)

    async def create_slot(self, user: User, *, start_at: datetime, end_at: datetime) -> dict:
        await self._require_own_companion(user.id)
        if end_at <= start_at:
            raise AppError(ErrorCodes.COMPANION_INVALID, "档期时间无效")
        slot = CompanionSlot(
            id=uuid4(),
            companion_id=user.id,
            start_at=start_at,
            end_at=end_at,
            status=SlotStatus.OPEN.value,
        )
        self.db.add(slot)
        await self.db.flush()
        return self.slot_brief(slot)

    async def list_companions(
        self,
        *,
        service_type: str | None,
        city: str | None,
        sort: str,
        available_only: bool,
        limit: int,
        offset: int,
    ) -> tuple[list[dict], int]:
        filters = [CompanionProfile.status == CompanionProfileStatus.ACTIVE.value]
        if service_type:
            filters.append(CompanionProfile.service_type == service_type)
        if city:
            filters.append(CompanionProfile.city == city)
        count_q = select(func.count()).select_from(CompanionProfile).where(*filters)
        total = int((await self.db.execute(count_q)).scalar_one())
        stmt = select(CompanionProfile).where(*filters)
        if sort == "price":
            # approximate via min active service price subquery omitted; order by rating then
            stmt = stmt.order_by(CompanionProfile.rating_avg.desc(), CompanionProfile.order_count.desc())
        elif sort == "earliest":
            stmt = stmt.order_by(CompanionProfile.response_time_minutes.asc())
        else:
            stmt = stmt.order_by(CompanionProfile.order_count.desc(), CompanionProfile.rating_avg.desc())
        rows = list((await self.db.execute(stmt.limit(limit).offset(offset))).scalars().all())
        items = []
        for p in rows:
            if available_only:
                open_slot = await self.db.execute(
                    select(CompanionSlot.id)
                    .where(
                        CompanionSlot.companion_id == p.user_id,
                        CompanionSlot.status == SlotStatus.OPEN.value,
                        CompanionSlot.start_at > datetime.now(timezone.utc),
                    )
                    .limit(1)
                )
                if open_slot.scalar_one_or_none() is None:
                    continue
            items.append(await self.profile_brief(p))
        return items, total if not available_only else len(items)

    async def get_companion(self, companion_id: UUID) -> dict:
        profile = await self.db.get(CompanionProfile, companion_id)
        if profile is None or profile.status not in {
            CompanionProfileStatus.ACTIVE.value,
            CompanionProfileStatus.PAUSED.value,
        }:
            raise AppError(ErrorCodes.COMPANION_NOT_FOUND, "陪玩师不存在", status_code=404)
        data = await self.profile_brief(profile, include_services=True)
        reviews, _ = await self.list_reviews(companion_id, limit=10, offset=0)
        data["reviews"] = reviews
        return data

    async def list_slots(self, companion_id: UUID) -> list[dict]:
        now = datetime.now(timezone.utc)
        # release expired holds
        held = await self.db.execute(
            select(CompanionSlot).where(
                CompanionSlot.companion_id == companion_id,
                CompanionSlot.status == SlotStatus.HELD.value,
                CompanionSlot.hold_expires_at < now,
            )
        )
        for s in held.scalars().all():
            s.status = SlotStatus.OPEN.value
            s.hold_expires_at = None
        result = await self.db.execute(
            select(CompanionSlot)
            .where(
                CompanionSlot.companion_id == companion_id,
                CompanionSlot.end_at > now,
                CompanionSlot.status.in_([SlotStatus.OPEN.value, SlotStatus.HELD.value]),
            )
            .order_by(CompanionSlot.start_at.asc())
        )
        return [self.slot_brief(s) for s in result.scalars().all()]

    async def leaderboard(self, *, period: str, limit: int = 50) -> list[dict]:
        p = period if period in {e.value for e in LeaderboardPeriod} else LeaderboardPeriod.WEEK.value
        key = self._period_key(p)
        result = await self.db.execute(
            select(CompanionLeaderboard)
            .where(CompanionLeaderboard.period == p, CompanionLeaderboard.period_key == key)
            .order_by(CompanionLeaderboard.rank.asc())
            .limit(limit)
        )
        rows = list(result.scalars().all())
        if not rows:
            # fallback: live rank by order_count
            live = await self.db.execute(
                select(CompanionProfile)
                .where(CompanionProfile.status == CompanionProfileStatus.ACTIVE.value)
                .order_by(CompanionProfile.order_count.desc(), CompanionProfile.rating_avg.desc())
                .limit(limit)
            )
            out = []
            for i, c in enumerate(live.scalars().all(), start=1):
                brief = await self.profile_brief(c)
                brief["rank"] = i
                brief["score"] = float(c.order_count)
                out.append(brief)
            return out
        out = []
        for r in rows:
            profile = await self.db.get(CompanionProfile, r.companion_id)
            if profile is None:
                continue
            brief = await self.profile_brief(profile)
            brief["rank"] = r.rank
            brief["score"] = float(r.score)
            out.append(brief)
        return out

    # ── bookings ───────────────────────────────────────────

    async def create_booking(
        self, user: User, *, companion_id: UUID, service_id: UUID, slot_id: UUID, units: int, idempotency_key: str | None
    ) -> dict:
        if companion_id == user.id:
            raise AppError(ErrorCodes.BOOKING_INVALID, "不能预约自己")
        if idempotency_key:
            hit = await self.db.execute(
                select(CompanionBooking).where(
                    CompanionBooking.buyer_id == user.id,
                    CompanionBooking.idempotency_key == idempotency_key,
                )
            )
            existing = hit.scalar_one_or_none()
            if existing:
                return await self.booking_brief(existing)

        profile = await self.db.get(CompanionProfile, companion_id)
        if profile is None or profile.status != CompanionProfileStatus.ACTIVE.value:
            raise AppError(ErrorCodes.COMPANION_UNAVAILABLE, "陪玩师不可约", status_code=409)
        svc = await self.db.get(CompanionService, service_id)
        if svc is None or svc.companion_id != companion_id or not svc.active:
            raise AppError(ErrorCodes.COMPANION_NOT_FOUND, "服务不存在", status_code=404)
        if units < svc.min_units:
            raise AppError(ErrorCodes.BOOKING_INVALID, f"最少购买 {svc.min_units} 份")
        slot = await self.db.get(CompanionSlot, slot_id)
        if slot is None or slot.companion_id != companion_id:
            raise AppError(ErrorCodes.COMPANION_NOT_FOUND, "档期不存在", status_code=404)
        now = datetime.now(timezone.utc)
        if slot.status == SlotStatus.HELD.value and slot.hold_expires_at and slot.hold_expires_at < now:
            slot.status = SlotStatus.OPEN.value
        if slot.status != SlotStatus.OPEN.value:
            raise AppError(ErrorCodes.BOOKING_CONFLICT, "档期已被占用", status_code=409)

        amount = svc.price_cents * units
        booking = CompanionBooking(
            id=uuid4(),
            companion_id=companion_id,
            buyer_id=user.id,
            service_id=service_id,
            slot_id=slot_id,
            units=units,
            amount_cents=amount,
            status=BookingStatus.PENDING_CONFIRM.value,
            scheduled_at=slot.start_at,
            idempotency_key=idempotency_key,
        )
        self.db.add(booking)
        slot.status = SlotStatus.HELD.value
        slot.hold_expires_at = now + timedelta(minutes=15)
        await self.db.flush()

        order = await self.commerce.create_order(
            user,
            kind=OrderKind.COMPANION_BOOKING.value,
            subject_id=booking.id,
            amount_cents=amount,
            subject_title=f"{svc.title} · 陪玩预约",
            meta={"booking_id": str(booking.id), "companion_id": str(companion_id)},
            idempotency_key=f"booking:{idempotency_key}" if idempotency_key else None,
        )
        booking.order_id = order.id
        booking.status = BookingStatus.AWAITING_PAYMENT.value
        await self.db.flush()
        await self.events.enqueue(
            name=DomainEventName.BOOKING_CREATED,
            aggregate_kind="booking",
            aggregate_id=booking.id,
            payload={"buyer_id": str(user.id), "companion_id": str(companion_id), "order_id": str(order.id)},
        )
        data = await self.booking_brief(booking)
        data["order"] = self.commerce.order_brief(order)
        return data

    async def mark_booking_paid(self, booking_id: UUID) -> None:
        booking = await self.db.get(CompanionBooking, booking_id)
        if booking is None:
            return
        if booking.status not in {
            BookingStatus.AWAITING_PAYMENT.value,
            BookingStatus.PENDING_CONFIRM.value,
        }:
            return
        now = datetime.now(timezone.utc)
        booking.status = BookingStatus.PAID.value
        booking.paid_at = now
        booking.confirmed_at = booking.confirmed_at or now
        if booking.slot_id:
            slot = await self.db.get(CompanionSlot, booking.slot_id)
            if slot:
                slot.status = SlotStatus.BOOKED.value
                slot.hold_expires_at = None
        profile = await self.db.get(CompanionProfile, booking.companion_id)
        if profile:
            profile.order_count = int(profile.order_count or 0) + 1
        await self.events.enqueue(
            name=DomainEventName.BOOKING_PAID,
            aggregate_kind="booking",
            aggregate_id=booking.id,
            payload={"companion_id": str(booking.companion_id), "buyer_id": str(booking.buyer_id)},
        )

    async def list_my_bookings(self, user_id: UUID, *, as_companion: bool, limit: int, offset: int) -> tuple[list[dict], int]:
        if as_companion:
            filters = [CompanionBooking.companion_id == user_id]
        else:
            filters = [CompanionBooking.buyer_id == user_id]
        count_q = select(func.count()).select_from(CompanionBooking).where(*filters)
        total = int((await self.db.execute(count_q)).scalar_one())
        rows = list(
            (
                await self.db.execute(
                    select(CompanionBooking)
                    .where(*filters)
                    .order_by(CompanionBooking.created_at.desc())
                    .limit(limit)
                    .offset(offset)
                )
            )
            .scalars()
            .all()
        )
        return [await self.booking_brief(b) for b in rows], total

    async def get_booking(self, user: User, booking_id: UUID) -> dict:
        booking = await self._get_booking_for(user, booking_id)
        return await self.booking_brief(booking)

    async def transition(
        self, user: User, booking_id: UUID, *, action: str, reason: str | None = None, scheduled_at: datetime | None = None
    ) -> dict:
        booking = await self._get_booking_for(user, booking_id)
        now = datetime.now(timezone.utc)
        is_companion = booking.companion_id == user.id
        is_buyer = booking.buyer_id == user.id

        if action == "confirm":
            if not is_companion:
                raise AppError(ErrorCodes.COMPANION_FORBIDDEN, "仅陪玩师可确认", status_code=403)
            if booking.status != BookingStatus.PAID.value:
                raise AppError(ErrorCodes.BOOKING_INVALID, "当前状态不可确认", status_code=409)
            booking.confirmed_at = now
        elif action == "decline":
            if not is_companion:
                raise AppError(ErrorCodes.COMPANION_FORBIDDEN, "仅陪玩师可拒绝", status_code=403)
            if booking.status not in {BookingStatus.PENDING_CONFIRM.value, BookingStatus.PAID.value, BookingStatus.AWAITING_PAYMENT.value}:
                raise AppError(ErrorCodes.BOOKING_INVALID, "当前状态不可拒绝", status_code=409)
            booking.status = BookingStatus.CANCELLED.value
            booking.cancelled_at = now
            booking.cancel_reason = reason or "陪玩师拒绝"
            await self._release_slot(booking)
        elif action == "start":
            if not is_companion:
                raise AppError(ErrorCodes.COMPANION_FORBIDDEN, "仅陪玩师可开始", status_code=403)
            if booking.status != BookingStatus.PAID.value:
                raise AppError(ErrorCodes.BOOKING_INVALID, "当前状态不可开始", status_code=409)
            booking.status = BookingStatus.IN_PROGRESS.value
            booking.started_at = now
        elif action == "complete":
            if not (is_companion or is_buyer):
                raise AppError(ErrorCodes.COMPANION_FORBIDDEN, "无权操作", status_code=403)
            if booking.status != BookingStatus.IN_PROGRESS.value:
                raise AppError(ErrorCodes.BOOKING_INVALID, "当前状态不可完成", status_code=409)
            booking.status = BookingStatus.COMPLETED.value
            booking.completed_at = now
            await self.events.enqueue(
                name=DomainEventName.BOOKING_COMPLETED,
                aggregate_kind="booking",
                aggregate_id=booking.id,
                payload={"companion_id": str(booking.companion_id), "buyer_id": str(booking.buyer_id)},
            )
        elif action == "cancel":
            if booking.status in {BookingStatus.COMPLETED.value, BookingStatus.CANCELLED.value, BookingStatus.REFUNDED.value}:
                raise AppError(ErrorCodes.BOOKING_INVALID, "当前状态不可取消", status_code=409)
            booking.status = BookingStatus.CANCELLED.value
            booking.cancelled_at = now
            booking.cancel_reason = reason or "用户取消"
            await self._release_slot(booking)
            await self.events.enqueue(
                name=DomainEventName.BOOKING_CANCELLED,
                aggregate_kind="booking",
                aggregate_id=booking.id,
                payload={"by": str(user.id)},
            )
        elif action == "reschedule":
            if not is_companion:
                raise AppError(ErrorCodes.COMPANION_FORBIDDEN, "仅陪玩师可改期", status_code=403)
            if scheduled_at is None:
                raise AppError(ErrorCodes.BOOKING_INVALID, "缺少 scheduled_at")
            booking.scheduled_at = scheduled_at
        else:
            raise AppError(ErrorCodes.BOOKING_INVALID, f"未知动作 {action}")
        await self.db.flush()
        return await self.booking_brief(booking)

    async def add_review(self, user: User, companion_id: UUID, *, booking_id: UUID, rating: int, content: str) -> dict:
        booking = await self.db.get(CompanionBooking, booking_id)
        if booking is None or booking.buyer_id != user.id or booking.companion_id != companion_id:
            raise AppError(ErrorCodes.BOOKING_NOT_FOUND, "预约不存在", status_code=404)
        if booking.status != BookingStatus.COMPLETED.value:
            raise AppError(ErrorCodes.BOOKING_INVALID, "仅已完成预约可评价", status_code=409)
        existing = await self.db.execute(select(CompanionReview).where(CompanionReview.booking_id == booking_id))
        if existing.scalar_one_or_none():
            raise AppError(ErrorCodes.BOOKING_INVALID, "已评价", status_code=409)
        review = CompanionReview(
            id=uuid4(),
            booking_id=booking_id,
            companion_id=companion_id,
            buyer_id=user.id,
            rating=rating,
            content=(content or "")[:500],
        )
        self.db.add(review)
        profile = await self.db.get(CompanionProfile, companion_id)
        if profile:
            n = int(profile.rating_count or 0)
            avg = Decimal(str(profile.rating_avg or 0))
            new_avg = ((avg * n) + Decimal(rating)) / Decimal(n + 1) if n else Decimal(rating)
            profile.rating_avg = new_avg.quantize(Decimal("0.01"))
            profile.rating_count = n + 1
        await self.db.flush()
        return {
            "id": str(review.id),
            "rating": review.rating,
            "content": review.content,
            "created_at": review.created_at.isoformat() if review.created_at else None,
        }

    async def list_reviews(self, companion_id: UUID, *, limit: int, offset: int) -> tuple[list[dict], int]:
        filters = [CompanionReview.companion_id == companion_id]
        total = int((await self.db.execute(select(func.count()).select_from(CompanionReview).where(*filters))).scalar_one())
        rows = list(
            (
                await self.db.execute(
                    select(CompanionReview)
                    .where(*filters)
                    .order_by(CompanionReview.created_at.desc())
                    .limit(limit)
                    .offset(offset)
                )
            )
            .scalars()
            .all()
        )
        return [
            {
                "id": str(r.id),
                "buyer_id": str(r.buyer_id),
                "rating": r.rating,
                "content": r.content,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ], total

    # ── admin ──────────────────────────────────────────────

    async def admin_review_companion(self, admin_id: UUID, companion_id: UUID, *, approve: bool, reason: str | None) -> dict:
        profile = await self.db.get(CompanionProfile, companion_id)
        if profile is None:
            raise AppError(ErrorCodes.COMPANION_NOT_FOUND, "陪玩师不存在", status_code=404)
        profile.reviewed_by = admin_id
        profile.reviewed_at = datetime.now(timezone.utc)
        if approve:
            profile.status = CompanionProfileStatus.ACTIVE.value
            profile.reject_reason = None
        else:
            profile.status = CompanionProfileStatus.REJECTED.value
            profile.reject_reason = reason or "资料不符合规范"
        await self.db.flush()
        await self.events.enqueue(
            name=DomainEventName.COMPANION_REVIEWED,
            aggregate_kind="companion",
            aggregate_id=companion_id,
            payload={"approved": approve, "admin_id": str(admin_id)},
        )
        return await self.profile_brief(profile, include_private=True)

    # ── briefs / helpers ───────────────────────────────────

    def intent_brief(self, row: BuddyIntent) -> dict:
        return {
            "id": str(row.id),
            "text": row.text,
            "tags": row.tags or [],
            "city": row.city,
            "active": row.active,
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    def greeting_brief(self, row: BuddyGreeting) -> dict:
        return {
            "id": str(row.id),
            "from_user_id": str(row.from_user_id),
            "to_user_id": str(row.to_user_id),
            "text": row.text,
            "status": row.status,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    def invite_brief(self, row: BuddyInvite) -> dict:
        return {
            "id": str(row.id),
            "from_user_id": str(row.from_user_id),
            "to_user_id": str(row.to_user_id),
            "activity_id": str(row.activity_id),
            "message": row.message,
            "status": row.status,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "responded_at": row.responded_at.isoformat() if row.responded_at else None,
        }

    async def profile_brief(
        self, profile: CompanionProfile, *, include_private: bool = False, include_services: bool = False
    ) -> dict:
        data = {
            "user_id": str(profile.user_id),
            "display_name": await self._display_name(profile.user_id),
            "service_type": profile.service_type,
            "specialty": profile.specialty,
            "intro": profile.intro,
            "city": profile.city,
            "response_time_minutes": profile.response_time_minutes,
            "order_count": profile.order_count,
            "rating_avg": float(profile.rating_avg or 0),
            "rating_count": profile.rating_count,
            "verified": profile.verified,
            "status": profile.status,
        }
        if include_private:
            data["reject_reason"] = profile.reject_reason
            data["reviewed_at"] = profile.reviewed_at.isoformat() if profile.reviewed_at else None
        if include_services:
            svcs = await self.db.execute(
                select(CompanionService)
                .where(CompanionService.companion_id == profile.user_id)
                .order_by(CompanionService.sort_order.asc())
            )
            data["services"] = [self.service_brief(s) for s in svcs.scalars().all()]
        return data

    def service_brief(self, s: CompanionService) -> dict:
        return {
            "id": str(s.id),
            "title": s.title,
            "pricing_unit": s.pricing_unit,
            "price_cents": s.price_cents,
            "price_display": f"¥{s.price_cents/100:.2f}",
            "min_units": s.min_units,
            "description": s.description,
            "sort_order": s.sort_order,
            "active": s.active,
        }

    def slot_brief(self, s: CompanionSlot) -> dict:
        return {
            "id": str(s.id),
            "start_at": s.start_at.isoformat(),
            "end_at": s.end_at.isoformat(),
            "status": s.status,
            "hold_expires_at": s.hold_expires_at.isoformat() if s.hold_expires_at else None,
        }

    async def booking_brief(self, b: CompanionBooking) -> dict:
        return {
            "id": str(b.id),
            "companion_id": str(b.companion_id),
            "buyer_id": str(b.buyer_id),
            "service_id": str(b.service_id) if b.service_id else None,
            "slot_id": str(b.slot_id) if b.slot_id else None,
            "order_id": str(b.order_id) if b.order_id else None,
            "units": b.units,
            "amount_cents": b.amount_cents,
            "amount_display": f"¥{b.amount_cents/100:.2f}",
            "status": b.status,
            "scheduled_at": b.scheduled_at.isoformat() if b.scheduled_at else None,
            "confirmed_at": b.confirmed_at.isoformat() if b.confirmed_at else None,
            "paid_at": b.paid_at.isoformat() if b.paid_at else None,
            "started_at": b.started_at.isoformat() if b.started_at else None,
            "completed_at": b.completed_at.isoformat() if b.completed_at else None,
            "cancelled_at": b.cancelled_at.isoformat() if b.cancelled_at else None,
            "cancel_reason": b.cancel_reason,
            "created_at": b.created_at.isoformat() if b.created_at else None,
        }

    async def _intent_of(self, user_id: UUID) -> BuddyIntent | None:
        result = await self.db.execute(select(BuddyIntent).where(BuddyIntent.user_id == user_id))
        return result.scalar_one_or_none()

    async def _require_own_companion(self, user_id: UUID) -> CompanionProfile:
        profile = await self.db.get(CompanionProfile, user_id)
        if profile is None:
            raise AppError(ErrorCodes.COMPANION_NOT_FOUND, "尚未申请陪玩", status_code=404)
        return profile

    async def _get_booking_for(self, user: User, booking_id: UUID) -> CompanionBooking:
        booking = await self.db.get(CompanionBooking, booking_id)
        if booking is None or (booking.buyer_id != user.id and booking.companion_id != user.id):
            raise AppError(ErrorCodes.BOOKING_NOT_FOUND, "预约不存在", status_code=404)
        return booking

    async def _release_slot(self, booking: CompanionBooking) -> None:
        if not booking.slot_id:
            return
        slot = await self.db.get(CompanionSlot, booking.slot_id)
        if slot and slot.status in {SlotStatus.HELD.value, SlotStatus.BOOKED.value}:
            slot.status = SlotStatus.OPEN.value
            slot.hold_expires_at = None

    async def _display_name(self, user_id: UUID) -> str:
        profile = await self.db.get(UserProfile, user_id)
        if profile and profile.display_name:
            return profile.display_name
        return "用户"

    def _period_key(self, period: str) -> str:
        now = datetime.now(timezone.utc)
        if period == LeaderboardPeriod.DAY.value:
            return now.strftime("%Y%m%d")
        if period == LeaderboardPeriod.MONTH.value:
            return now.strftime("%Y%m")
        return f"{now.isocalendar().year}W{now.isocalendar().week:02d}"
