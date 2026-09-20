"""M7 trust score, verification, sanctions, moderation queue."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AdminUser,
    ModerationMachineLabel,
    ModerationTask,
    ModerationTaskStatus,
    SafetyCheckin,
    SafetyCheckinResult,
    Sanction,
    SanctionKind,
    SensitiveWord,
    SensitiveWordAction,
    TrustBadge,
    TrustBadgeKind,
    TrustDomain,
    TrustEvent,
    TrustLevel,
    TrustScore,
    User,
    UserStatus,
    Verification,
    VerificationKind,
    VerificationStatus,
)
from app.modules.events.service import DomainEventName, DomainEventService
from app.shared.errors import AppError
from app.shared.response import ErrorCodes

EMA_ALPHA = Decimal("0.85")
_DOMAIN_VALUES = {e.value for e in TrustDomain}
_SANCTION_VALUES = {e.value for e in SanctionKind}
_SENSITIVE_ACTIONS = {e.value for e in SensitiveWordAction}
_AXIS_BY_DOMAIN = {
    TrustDomain.ACCOUNT.value: "identity",
    TrustDomain.ORG.value: "identity",
    TrustDomain.ACTIVITY.value: "reliability",
    TrustDomain.BOOKING.value: "reliability",
    TrustDomain.BUDDY.value: "communication",
    TrustDomain.SOCIAL.value: "communication",
    TrustDomain.COMMUNITY.value: "communication",
    TrustDomain.WALLET.value: "safety",
    TrustDomain.MODERATION.value: "safety",
}


def _dec(v: float | Decimal | int) -> Decimal:
    return Decimal(str(v)).quantize(Decimal("0.01"))


def _clamp(v: Decimal, lo: Decimal = Decimal("0"), hi: Decimal = Decimal("100")) -> Decimal:
    return max(lo, min(hi, v))


def _level_for(score: Decimal, sample_size: int) -> str:
    if sample_size <= 0:
        return TrustLevel.GUEST.value
    s = float(score)
    if s < 30:
        return TrustLevel.RESTRICTED.value
    if s < 50:
        return TrustLevel.NEWCOMER.value
    if s < 70:
        return TrustLevel.TRUSTED.value
    return TrustLevel.RELIABLE_HOST.value


class TrustService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.events = DomainEventService(db)

    # ── score read models ──────────────────────────────────

    async def ensure_score(self, user_id: UUID) -> TrustScore:
        row = await self.db.get(TrustScore, user_id)
        if row is not None:
            return row
        row = TrustScore(
            user_id=user_id,
            score=Decimal("50"),
            level=TrustLevel.GUEST.value,
            identity=Decimal("50"),
            reliability=Decimal("50"),
            communication=Decimal("50"),
            safety=Decimal("50"),
            facts={},
            sample_size=0,
            confidence_low=True,
            computed_at=datetime.now(timezone.utc),
        )
        self.db.add(row)
        await self.db.flush()
        return row

    async def get_me_trust(self, user: User) -> dict:
        score = await self.ensure_score(user.id)
        badges = await self._active_badges(user.id)
        tips = self._tips_for(score, badges)
        return {
            "user_id": str(user.id),
            "score": float(score.score),
            "level": score.level,
            "axes": {
                "identity": float(score.identity),
                "reliability": float(score.reliability),
                "communication": float(score.communication),
                "safety": float(score.safety),
            },
            "facts": score.facts or {},
            "confidence_low": bool(score.confidence_low),
            "sample_size": score.sample_size,
            "badges": [self.badge_brief(b) for b in badges],
            "tips": tips,
            "computed_at": score.computed_at.isoformat() if score.computed_at else None,
        }

    async def get_public_trust(self, user_id: UUID) -> dict:
        user = await self.db.get(User, user_id)
        if user is None:
            raise AppError(ErrorCodes.USER_NOT_FOUND, "用户不存在", status_code=404)
        score = await self.ensure_score(user_id)
        badges = await self._active_badges(user_id)
        return {
            "user_id": str(user_id),
            "badges": [self.badge_brief(b) for b in badges],
            "facts": score.facts or {},
        }

    # ── events / scoring ───────────────────────────────────

    async def record_event(
        self,
        *,
        name: str,
        domain: str,
        value: float | Decimal = 0,
        note: str = "",
        source: str = "server",
        actor_user_id: UUID | None = None,
        subject_user_id: UUID | None = None,
        dedup_key: str | None = None,
        meta: dict | None = None,
    ) -> dict:
        domain = (domain or "").strip()
        if domain not in _DOMAIN_VALUES:
            raise AppError(ErrorCodes.TRUST_INVALID, f"无效 domain: {domain}")
        name = (name or "").strip()[:48]
        if not name:
            raise AppError(ErrorCodes.TRUST_INVALID, "缺少 name")

        if dedup_key:
            existing = await self.db.execute(select(TrustEvent).where(TrustEvent.dedup_key == dedup_key))
            hit = existing.scalar_one_or_none()
            if hit:
                return self.event_brief(hit)

        event = TrustEvent(
            id=uuid4(),
            actor_user_id=actor_user_id,
            subject_user_id=subject_user_id,
            domain=domain,
            name=name,
            value=_dec(value),
            note=(note or "")[:200],
            source=source,
            dedup_key=dedup_key,
            meta=meta or {},
        )
        self.db.add(event)
        await self.db.flush()

        if subject_user_id is not None:
            await self._apply_ema(subject_user_id, domain=domain, value=event.value, name=name)

        await self.events.enqueue(
            name=DomainEventName.TRUST_EVENT_RECORDED,
            aggregate_kind="trust_event",
            aggregate_id=event.id,
            payload={
                "name": name,
                "domain": domain,
                "subject_user_id": str(subject_user_id) if subject_user_id else None,
                "value": float(event.value),
                "source": source,
            },
        )
        return self.event_brief(event)

    async def report_client_event(self, user: User, body) -> dict:
        raw = body.value if body.value is not None else 0
        capped = max(-5.0, min(5.0, float(raw)))
        subject = body.subject_user_id or user.id
        return await self.record_event(
            name=body.name,
            domain=body.domain,
            value=capped,
            note=body.note or "",
            source="client",
            actor_user_id=user.id,
            subject_user_id=subject,
            dedup_key=body.dedup_key,
            meta={"client_reported": True},
        )

    async def admin_adjust(self, admin: AdminUser, body) -> dict:
        user = await self.db.get(User, body.user_id)
        if user is None:
            raise AppError(ErrorCodes.USER_NOT_FOUND, "用户不存在", status_code=404)
        domain = body.domain if body.domain in _DOMAIN_VALUES else TrustDomain.MODERATION.value
        return await self.record_event(
            name="admin_adjust",
            domain=domain,
            value=body.value,
            note=body.note,
            source="admin",
            actor_user_id=None,
            subject_user_id=body.user_id,
            meta={"admin_id": str(admin.id)},
        )

    async def _apply_ema(self, user_id: UUID, *, domain: str, value: Decimal, name: str) -> TrustScore:
        score = await self.ensure_score(user_id)
        observation = _clamp(_dec(score.score) + _dec(value))
        new_score = _clamp(EMA_ALPHA * _dec(score.score) + (Decimal("1") - EMA_ALPHA) * observation)
        score.score = new_score

        axis = _AXIS_BY_DOMAIN.get(domain, "reliability")
        cur = _dec(getattr(score, axis))
        axis_obs = _clamp(cur + _dec(value))
        setattr(score, axis, _clamp(EMA_ALPHA * cur + (Decimal("1") - EMA_ALPHA) * axis_obs))

        score.sample_size = int(score.sample_size or 0) + 1
        score.confidence_low = score.sample_size < 5
        score.level = _level_for(score.score, score.sample_size)
        score.computed_at = datetime.now(timezone.utc)

        facts = dict(score.facts or {})
        facts["last_event"] = name
        facts["last_domain"] = domain
        facts["event_count"] = int(facts.get("event_count") or 0) + 1
        if name.startswith("safety_checkin"):
            key = "checkins_ok" if "ok" in name else "checkins_issue"
            facts[key] = int(facts.get(key) or 0) + 1
        score.facts = facts
        await self.db.flush()
        return score

    # ── verification ───────────────────────────────────────

    async def submit_photo_verification(self, user: User, *, similarity: float, quality_score: float) -> dict:
        pending = await self.db.execute(
            select(Verification).where(
                Verification.user_id == user.id,
                Verification.kind == VerificationKind.PHOTO.value,
                Verification.status == VerificationStatus.PENDING.value,
            )
        )
        row = pending.scalar_one_or_none()
        if row is None:
            row = Verification(
                id=uuid4(),
                user_id=user.id,
                kind=VerificationKind.PHOTO.value,
                status=VerificationStatus.PENDING.value,
            )
            self.db.add(row)
        row.similarity = Decimal(str(round(similarity, 3)))
        row.quality_score = Decimal(str(round(quality_score, 3)))
        row.reject_reason = None
        await self.db.flush()
        await self.events.enqueue(
            name=DomainEventName.VERIFICATION_SUBMITTED,
            aggregate_kind="verification",
            aggregate_id=row.id,
            payload={"user_id": str(user.id), "kind": row.kind, "similarity": float(row.similarity or 0)},
        )
        return self.verification_brief(row)

    async def admin_review_verification(
        self, admin: AdminUser, verification_id: UUID, *, approve: bool, reason: str | None
    ) -> dict:
        row = await self.db.get(Verification, verification_id)
        if row is None:
            raise AppError(ErrorCodes.VERIFICATION_NOT_FOUND, "认证不存在", status_code=404)
        if row.status != VerificationStatus.PENDING.value:
            raise AppError(ErrorCodes.VERIFICATION_INVALID, "认证已处理", status_code=409)
        now = datetime.now(timezone.utc)
        row.reviewed_by = admin.id
        row.reviewed_at = now
        if approve:
            row.status = VerificationStatus.APPROVED.value
            row.reject_reason = None
            await self._grant_badge(row.user_id, TrustBadgeKind.PHOTO_VERIFIED.value, source="admin")
            score = await self.ensure_score(row.user_id)
            facts = dict(score.facts or {})
            facts["photo_verified"] = True
            score.facts = facts
            await self.record_event(
                name="photo_verified",
                domain=TrustDomain.ACCOUNT.value,
                value=8,
                note="真人认证通过",
                source="admin",
                subject_user_id=row.user_id,
                meta={"verification_id": str(row.id), "admin_id": str(admin.id)},
            )
        else:
            row.status = VerificationStatus.REJECTED.value
            row.reject_reason = (reason or "认证未通过")[:200]
        await self.db.flush()
        await self.events.enqueue(
            name=DomainEventName.VERIFICATION_REVIEWED,
            aggregate_kind="verification",
            aggregate_id=row.id,
            payload={"approved": approve, "admin_id": str(admin.id), "user_id": str(row.user_id)},
        )
        return self.verification_brief(row)

    async def list_verifications(
        self, *, status: str | None, kind: str | None, limit: int, offset: int
    ) -> tuple[list[dict], int]:
        filters = []
        if status:
            filters.append(Verification.status == status)
        if kind:
            filters.append(Verification.kind == kind)
        count_q = select(func.count()).select_from(Verification)
        list_q = select(Verification).order_by(Verification.created_at.desc())
        for f in filters:
            count_q = count_q.where(f)
            list_q = list_q.where(f)
        total = int((await self.db.execute(count_q)).scalar_one())
        rows = list((await self.db.execute(list_q.limit(limit).offset(offset))).scalars().all())
        return [self.verification_brief(r) for r in rows], total

    # ── safety checkin ─────────────────────────────────────

    async def create_safety_checkin(
        self, user: User, *, subject_kind: str, subject_id: UUID, result: str, note: str = ""
    ) -> dict:
        if result not in {SafetyCheckinResult.OK.value, SafetyCheckinResult.ISSUE.value}:
            raise AppError(ErrorCodes.TRUST_INVALID, "result 须为 ok|issue")
        row = SafetyCheckin(
            id=uuid4(),
            user_id=user.id,
            subject_kind=(subject_kind or "")[:24],
            subject_id=subject_id,
            result=result,
            note=(note or "")[:200],
        )
        self.db.add(row)
        await self.db.flush()
        value = 3 if result == SafetyCheckinResult.OK.value else -8
        await self.record_event(
            name=f"safety_checkin_{result}",
            domain=TrustDomain.ACTIVITY.value,
            value=value,
            note=note or "",
            source="client",
            actor_user_id=user.id,
            subject_user_id=user.id,
            meta={"checkin_id": str(row.id), "subject_kind": subject_kind, "subject_id": str(subject_id)},
        )
        return self.checkin_brief(row)

    # ── sanctions ──────────────────────────────────────────

    async def admin_apply_sanction(self, admin: AdminUser, body) -> dict:
        if body.kind not in _SANCTION_VALUES:
            raise AppError(ErrorCodes.SANCTION_INVALID, f"无效 kind: {body.kind}")
        user = await self.db.get(User, body.user_id)
        if user is None:
            raise AppError(ErrorCodes.USER_NOT_FOUND, "用户不存在", status_code=404)
        row = Sanction(
            id=uuid4(),
            user_id=body.user_id,
            kind=body.kind,
            reason=(body.reason or "")[:200],
            scope=(body.scope or "global")[:64],
            expires_at=body.expires_at,
            admin_id=admin.id,
        )
        self.db.add(row)
        if body.kind == SanctionKind.BAN.value:
            user.status = UserStatus.BANNED.value
        elif body.kind in {SanctionKind.MUTE.value, SanctionKind.LIMIT_PUBLISH.value, SanctionKind.LIMIT_TRADE.value}:
            if user.status == UserStatus.ACTIVE.value:
                user.status = UserStatus.LIMITED.value
        await self.db.flush()
        await self.record_event(
            name=f"sanction_{body.kind}",
            domain=TrustDomain.MODERATION.value,
            value=-25 if body.kind == SanctionKind.BAN.value else -10,
            note=body.reason,
            source="admin",
            subject_user_id=body.user_id,
            meta={"sanction_id": str(row.id), "admin_id": str(admin.id)},
        )
        await self.events.enqueue(
            name=DomainEventName.SANCTION_APPLIED,
            aggregate_kind="sanction",
            aggregate_id=row.id,
            payload={"user_id": str(body.user_id), "kind": body.kind, "admin_id": str(admin.id)},
        )
        return self.sanction_brief(row)

    async def admin_revoke_sanction(self, admin: AdminUser, sanction_id: UUID, *, reason: str | None) -> dict:
        row = await self.db.get(Sanction, sanction_id)
        if row is None:
            raise AppError(ErrorCodes.SANCTION_NOT_FOUND, "处置不存在", status_code=404)
        if row.revoked_at is not None:
            raise AppError(ErrorCodes.SANCTION_INVALID, "已撤销", status_code=409)
        row.revoked_at = datetime.now(timezone.utc)
        row.revoke_reason = (reason or "运营撤销")[:200]
        user = await self.db.get(User, row.user_id)
        if user and user.status in {UserStatus.BANNED.value, UserStatus.LIMITED.value}:
            active = await self.db.execute(
                select(Sanction).where(
                    Sanction.user_id == row.user_id,
                    Sanction.id != row.id,
                    Sanction.revoked_at.is_(None),
                )
            )
            remaining = list(active.scalars().all())
            now = datetime.now(timezone.utc)
            still = [
                s
                for s in remaining
                if s.expires_at is None or s.expires_at > now
            ]
            if not still:
                user.status = UserStatus.ACTIVE.value
            elif any(s.kind == SanctionKind.BAN.value for s in still):
                user.status = UserStatus.BANNED.value
            else:
                user.status = UserStatus.LIMITED.value
        await self.db.flush()
        _ = admin
        return self.sanction_brief(row)

    async def list_sanctions(
        self, *, user_id: UUID | None, kind: str | None, active_only: bool, limit: int, offset: int
    ) -> tuple[list[dict], int]:
        filters = []
        if user_id:
            filters.append(Sanction.user_id == user_id)
        if kind:
            filters.append(Sanction.kind == kind)
        if active_only:
            filters.append(Sanction.revoked_at.is_(None))
        count_q = select(func.count()).select_from(Sanction)
        list_q = select(Sanction).order_by(Sanction.created_at.desc())
        for f in filters:
            count_q = count_q.where(f)
            list_q = list_q.where(f)
        total = int((await self.db.execute(count_q)).scalar_one())
        rows = list((await self.db.execute(list_q.limit(limit).offset(offset))).scalars().all())
        return [self.sanction_brief(r) for r in rows], total

    # ── moderation tasks ───────────────────────────────────

    async def enqueue_moderation_task(
        self,
        *,
        target_kind: str,
        target_id: UUID,
        machine_label: str = ModerationMachineLabel.REVIEW.value,
        machine_result: dict | None = None,
        payload: dict | None = None,
        priority: int = 0,
        auto_pass: bool = False,
    ) -> ModerationTask:
        status = (
            ModerationTaskStatus.AUTO_PASSED.value
            if auto_pass or machine_label == ModerationMachineLabel.PASS.value
            else ModerationTaskStatus.PENDING.value
        )
        row = ModerationTask(
            id=uuid4(),
            target_kind=target_kind[:24],
            target_id=target_id,
            machine_result=machine_result or {},
            machine_label=machine_label,
            status=status,
            priority=priority,
            payload=payload or {},
        )
        self.db.add(row)
        await self.db.flush()
        return row

    async def list_moderation_tasks(
        self,
        *,
        status: str | None,
        target_kind: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[dict], int]:
        filters = []
        if status:
            filters.append(ModerationTask.status == status)
        if target_kind:
            filters.append(ModerationTask.target_kind == target_kind)
        count_q = select(func.count()).select_from(ModerationTask)
        list_q = select(ModerationTask).order_by(
            ModerationTask.priority.desc(), ModerationTask.submitted_at.asc()
        )
        for f in filters:
            count_q = count_q.where(f)
            list_q = list_q.where(f)
        total = int((await self.db.execute(count_q)).scalar_one())
        rows = list((await self.db.execute(list_q.limit(limit).offset(offset))).scalars().all())
        return [self.moderation_brief(r) for r in rows], total

    async def claim_moderation_task(self, admin: AdminUser, task_id: UUID) -> dict:
        row = await self.db.get(ModerationTask, task_id)
        if row is None:
            raise AppError(ErrorCodes.TRUST_NOT_FOUND, "审核任务不存在", status_code=404)
        if row.status not in {
            ModerationTaskStatus.PENDING.value,
            ModerationTaskStatus.REVIEWING.value,
        }:
            raise AppError(ErrorCodes.TRUST_INVALID, "任务不可认领", status_code=409)
        if (
            row.status == ModerationTaskStatus.REVIEWING.value
            and row.assignee_admin_id
            and row.assignee_admin_id != admin.id
        ):
            raise AppError(ErrorCodes.TRUST_INVALID, "已被其他管理员认领", status_code=409)
        row.status = ModerationTaskStatus.REVIEWING.value
        row.assignee_admin_id = admin.id
        await self.db.flush()
        return self.moderation_brief(row)

    async def review_moderation_task(
        self,
        admin: AdminUser,
        task_id: UUID,
        *,
        approve: bool,
        reason_code: str | None,
        admin_note: str | None,
    ) -> dict:
        row = await self.db.get(ModerationTask, task_id)
        if row is None:
            raise AppError(ErrorCodes.TRUST_NOT_FOUND, "审核任务不存在", status_code=404)
        if row.status in {
            ModerationTaskStatus.APPROVED.value,
            ModerationTaskStatus.REJECTED.value,
            ModerationTaskStatus.AUTO_PASSED.value,
        }:
            raise AppError(ErrorCodes.TRUST_INVALID, "任务已审结", status_code=409)
        row.status = ModerationTaskStatus.APPROVED.value if approve else ModerationTaskStatus.REJECTED.value
        row.reviewed_by = admin.id
        row.reviewed_at = datetime.now(timezone.utc)
        row.assignee_admin_id = row.assignee_admin_id or admin.id
        row.reason_code = reason_code
        row.admin_note = (admin_note or "")[:500] or None
        await self.db.flush()
        return self.moderation_brief(row)

    # ── sensitive words ────────────────────────────────────

    async def list_sensitive_words(
        self, *, enabled: bool | None, limit: int, offset: int
    ) -> tuple[list[dict], int]:
        filters = []
        if enabled is not None:
            filters.append(SensitiveWord.enabled.is_(enabled))
        count_q = select(func.count()).select_from(SensitiveWord)
        list_q = select(SensitiveWord).order_by(SensitiveWord.created_at.desc())
        for f in filters:
            count_q = count_q.where(f)
            list_q = list_q.where(f)
        total = int((await self.db.execute(count_q)).scalar_one())
        rows = list((await self.db.execute(list_q.limit(limit).offset(offset))).scalars().all())
        return [self.sensitive_word_brief(r) for r in rows], total

    async def upsert_sensitive_word(
        self, *, word: str, category: str, action: str, enabled: bool
    ) -> dict:
        w = (word or "").strip()[:64]
        if not w:
            raise AppError(ErrorCodes.TRUST_INVALID, "词不能为空")
        act = action if action in _SENSITIVE_ACTIONS else SensitiveWordAction.REVIEW.value
        existing = await self.db.execute(select(SensitiveWord).where(SensitiveWord.word == w))
        row = existing.scalar_one_or_none()
        if row is None:
            row = SensitiveWord(id=uuid4(), word=w)
            self.db.add(row)
        row.category = (category or "general")[:32]
        row.action = act
        row.enabled = enabled
        await self.db.flush()
        return self.sensitive_word_brief(row)

    # ── admin lists ────────────────────────────────────────

    async def list_scores(self, *, level: str | None, limit: int, offset: int) -> tuple[list[dict], int]:
        filters = []
        if level:
            filters.append(TrustScore.level == level)
        count_q = select(func.count()).select_from(TrustScore)
        list_q = select(TrustScore).order_by(TrustScore.score.desc())
        for f in filters:
            count_q = count_q.where(f)
            list_q = list_q.where(f)
        total = int((await self.db.execute(count_q)).scalar_one())
        rows = list((await self.db.execute(list_q.limit(limit).offset(offset))).scalars().all())
        return [self.score_brief(r) for r in rows], total

    async def list_events(
        self,
        *,
        subject_user_id: UUID | None,
        domain: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[dict], int]:
        filters = []
        if subject_user_id:
            filters.append(TrustEvent.subject_user_id == subject_user_id)
        if domain:
            filters.append(TrustEvent.domain == domain)
        count_q = select(func.count()).select_from(TrustEvent)
        list_q = select(TrustEvent).order_by(TrustEvent.created_at.desc())
        for f in filters:
            count_q = count_q.where(f)
            list_q = list_q.where(f)
        total = int((await self.db.execute(count_q)).scalar_one())
        rows = list((await self.db.execute(list_q.limit(limit).offset(offset))).scalars().all())
        return [self.event_brief(r) for r in rows], total

    # ── briefs / helpers ───────────────────────────────────

    def score_brief(self, s: TrustScore) -> dict:
        return {
            "user_id": str(s.user_id),
            "score": float(s.score),
            "level": s.level,
            "identity": float(s.identity),
            "reliability": float(s.reliability),
            "communication": float(s.communication),
            "safety": float(s.safety),
            "facts": s.facts or {},
            "sample_size": s.sample_size,
            "confidence_low": bool(s.confidence_low),
            "computed_at": s.computed_at.isoformat() if s.computed_at else None,
        }

    def event_brief(self, e: TrustEvent) -> dict:
        return {
            "id": str(e.id),
            "created_at": e.created_at.isoformat() if e.created_at else None,
            "actor_user_id": str(e.actor_user_id) if e.actor_user_id else None,
            "subject_user_id": str(e.subject_user_id) if e.subject_user_id else None,
            "domain": e.domain,
            "name": e.name,
            "value": float(e.value),
            "note": e.note,
            "source": e.source,
            "dedup_key": e.dedup_key,
            "meta": e.meta or {},
        }

    def badge_brief(self, b: TrustBadge) -> dict:
        return {
            "id": str(b.id),
            "kind": b.kind,
            "granted_at": b.granted_at.isoformat() if b.granted_at else None,
            "source": b.source,
        }

    def verification_brief(self, v: Verification) -> dict:
        return {
            "id": str(v.id),
            "user_id": str(v.user_id),
            "kind": v.kind,
            "status": v.status,
            "similarity": float(v.similarity) if v.similarity is not None else None,
            "quality_score": float(v.quality_score) if v.quality_score is not None else None,
            "reject_reason": v.reject_reason,
            "reviewed_at": v.reviewed_at.isoformat() if v.reviewed_at else None,
            "created_at": v.created_at.isoformat() if v.created_at else None,
        }

    def checkin_brief(self, c: SafetyCheckin) -> dict:
        return {
            "id": str(c.id),
            "user_id": str(c.user_id),
            "subject_kind": c.subject_kind,
            "subject_id": str(c.subject_id),
            "result": c.result,
            "note": c.note,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }

    def sanction_brief(self, s: Sanction) -> dict:
        return {
            "id": str(s.id),
            "user_id": str(s.user_id),
            "kind": s.kind,
            "reason": s.reason,
            "scope": s.scope,
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "expires_at": s.expires_at.isoformat() if s.expires_at else None,
            "admin_id": str(s.admin_id) if s.admin_id else None,
            "revoked_at": s.revoked_at.isoformat() if s.revoked_at else None,
            "revoke_reason": s.revoke_reason,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }

    def moderation_brief(self, t: ModerationTask) -> dict:
        return {
            "id": str(t.id),
            "target_kind": t.target_kind,
            "target_id": str(t.target_id),
            "submitted_at": t.submitted_at.isoformat() if t.submitted_at else None,
            "machine_label": t.machine_label,
            "machine_result": t.machine_result or {},
            "status": t.status,
            "assignee_admin_id": str(t.assignee_admin_id) if t.assignee_admin_id else None,
            "reviewed_by": str(t.reviewed_by) if t.reviewed_by else None,
            "reviewed_at": t.reviewed_at.isoformat() if t.reviewed_at else None,
            "reason_code": t.reason_code,
            "admin_note": t.admin_note,
            "priority": t.priority,
            "payload": t.payload or {},
        }

    def sensitive_word_brief(self, w: SensitiveWord) -> dict:
        return {
            "id": str(w.id),
            "word": w.word,
            "category": w.category,
            "action": w.action,
            "enabled": w.enabled,
            "hit_count": w.hit_count,
            "created_at": w.created_at.isoformat() if w.created_at else None,
        }

    async def _active_badges(self, user_id: UUID) -> list[TrustBadge]:
        result = await self.db.execute(
            select(TrustBadge)
            .where(TrustBadge.user_id == user_id, TrustBadge.revoked_at.is_(None))
            .order_by(TrustBadge.granted_at.desc())
        )
        return list(result.scalars().all())

    async def _grant_badge(self, user_id: UUID, kind: str, *, source: str = "system") -> TrustBadge:
        result = await self.db.execute(
            select(TrustBadge).where(TrustBadge.user_id == user_id, TrustBadge.kind == kind)
        )
        badge = result.scalar_one_or_none()
        if badge is None:
            badge = TrustBadge(id=uuid4(), user_id=user_id, kind=kind, source=source)
            self.db.add(badge)
        else:
            badge.revoked_at = None
            badge.source = source
            badge.granted_at = datetime.now(timezone.utc)
        await self.db.flush()
        return badge

    def _tips_for(self, score: TrustScore, badges: list[TrustBadge]) -> list[str]:
        tips: list[str] = []
        kinds = {b.kind for b in badges}
        if TrustBadgeKind.PHOTO_VERIFIED.value not in kinds:
            tips.append("完成真人认证，提升身份可信度")
        if score.confidence_low:
            tips.append("多参与活动与互动，积累可解释的信任样本")
        if float(score.reliability) < 55:
            tips.append("按时履约、认真对待邀约，可提升靠谱度")
        if float(score.communication) < 55:
            tips.append("友好回应打招呼与消息，有助沟通分")
        if float(score.safety) < 55:
            tips.append("遵守社区规范，避免违规举报")
        if not tips:
            tips.append("保持良好履约与互动，巩固信任等级")
        return tips[:4]
