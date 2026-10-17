"""Interest clubs (俱乐部) and companion guilds (陪玩工会)."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Club,
    ClubMember,
    ClubMemberRole,
    ClubMemberStatus,
    ClubStatus,
    CompanionBooking,
    CompanionProfile,
    Conversation,
    ConversationKind,
    ConversationMember,
    ConversationStatus,
    Guild,
    GuildFollow,
    GuildStatus,
    MemberRole,
    MemberStatus,
    User,
    UserProfile,
    UserStatus,
)
from app.modules.messaging.provider import get_im_provider
from app.modules.safety.content_safety import guard_text
from app.modules.safety.service import is_blocked_either
from app.modules.trust.service import TrustService
from app.shared.errors import AppError
from app.shared.response import ErrorCodes

CLUB_TOPICS = ["骑行", "户外", "运动", "美食", "玩乐", "娱乐", "咖啡", "徒步", "摄影", "羽毛球"]
CLUB_TOPIC_IMAGES = {
    "骑行": "bicycle", "户外": "figure.hiking", "运动": "figure.run", "美食": "fork.knife", "玩乐": "bag",
    "娱乐": "gamecontroller", "咖啡": "cup.and.saucer", "徒步": "figure.hiking", "摄影": "camera",
    "羽毛球": "figure.badminton",
}
MIN_NAME, MAX_NAME, MIN_SUMMARY, MAX_SUMMARY = 2, 20, 8, 300
MAX_CREATED_PER_USER = 5
MAX_TAGS = 6
SORTS = {"active", "members", "newest"}


def _clean_tags(tags: list[str] | None) -> list[str]:
    seen: list[str] = []
    for t in tags or []:
        v = re.sub(r"\s+", "", str(t))[:10]
        if v and v not in seen:
            seen.append(v)
    return seen[:MAX_TAGS]


class ClubService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.im = get_im_provider()

    # ── helpers ────────────────────────────────────────────

    async def _name(self, user_id: UUID | None) -> str:
        if user_id is None:
            return ""
        profile = await self.db.get(UserProfile, user_id)
        return (profile.display_name if profile and profile.display_name else "") or "用户"

    async def _membership(self, club_id: UUID, user_id: UUID) -> ClubMember | None:
        return (
            await self.db.execute(
                select(ClubMember).where(ClubMember.club_id == club_id, ClubMember.user_id == user_id)
            )
        ).scalar_one_or_none()

    async def brief(self, club: Club, *, viewer_id: UUID | None) -> dict:
        member = await self._membership(club.id, viewer_id) if viewer_id else None
        joined = bool(member and member.status == ClubMemberStatus.ACTIVE.value)
        return {
            "id": str(club.id),
            "name": club.name,
            "topic": club.topic,
            "city": club.city,
            "summary": club.summary,
            "tags": list(club.tags or []),
            "system_image": club.system_image,
            "member_count": club.member_count,
            "weekly_active": club.weekly_active,
            "is_official": club.is_official,
            "is_joined": joined,
            "is_creator": bool(viewer_id and club.creator_id == viewer_id),
            "my_role": member.role if joined and member else None,
            "creator_name": await self._name(club.creator_id),
            "conversation_id": str(club.conversation_id) if club.conversation_id and joined else None,
            "status": club.status,
            "created_at": club.created_at.isoformat() if club.created_at else None,
        }

    async def _get(self, club_id: UUID, *, allow_hidden_for: UUID | None = None) -> Club:
        club = await self.db.get(Club, club_id)
        if club is None or club.status == ClubStatus.DISSOLVED.value:
            raise AppError(ErrorCodes.CLUB_NOT_FOUND, "俱乐部不存在或已解散", status_code=404)
        if club.status == ClubStatus.HIDDEN.value and club.creator_id != allow_hidden_for:
            raise AppError(ErrorCodes.CLUB_NOT_FOUND, "俱乐部不存在或已下架", status_code=404)
        return club

    # ── queries ────────────────────────────────────────────

    async def list_clubs(
        self,
        viewer: User,
        *,
        q: str | None,
        topic: str | None,
        city: str | None,
        sort: str,
        scope: str,
        limit: int,
        offset: int,
    ) -> tuple[list[dict], int]:
        filters = [Club.status == ClubStatus.ACTIVE.value]
        if scope == "created":
            filters = [Club.creator_id == viewer.id, Club.status.in_([ClubStatus.ACTIVE.value, ClubStatus.HIDDEN.value])]
        elif scope == "joined":
            joined_ids = select(ClubMember.club_id).where(
                ClubMember.user_id == viewer.id, ClubMember.status == ClubMemberStatus.ACTIVE.value
            )
            filters.append(Club.id.in_(joined_ids))
        if topic:
            filters.append(Club.topic == topic)
        if city:
            filters.append(Club.city.ilike(f"{city.strip()}%"))
        if q and q.strip():
            like = f"%{q.strip()}%"
            filters.append(or_(Club.name.ilike(like), Club.summary.ilike(like), cast(Club.tags, String).ilike(like)))
        order = {
            "members": [Club.member_count.desc(), Club.created_at.desc()],
            "newest": [Club.created_at.desc()],
        }.get(sort, [Club.weekly_active.desc(), Club.member_count.desc(), Club.created_at.desc()])
        total = int(await self.db.scalar(select(func.count()).select_from(Club).where(*filters)) or 0)
        rows = (await self.db.execute(select(Club).where(*filters).order_by(*order).limit(limit).offset(offset))).scalars().all()
        return [await self.brief(c, viewer_id=viewer.id) for c in rows], total

    async def get(self, viewer: User, club_id: UUID) -> dict:
        club = await self._get(club_id, allow_hidden_for=viewer.id)
        return await self.brief(club, viewer_id=viewer.id)

    # ── commands ───────────────────────────────────────────

    async def create(
        self, user: User, *, name: str, topic: str, city: str, summary: str, tags: list[str] | None,
        club_id: UUID | None = None,
    ) -> dict:
        if user.status != UserStatus.ACTIVE.value:
            raise AppError(ErrorCodes.USER_LIMITED, "账号受限，暂不能创建俱乐部", status_code=403)
        if club_id is not None:
            prior = await self.db.get(Club, club_id)
            if prior is not None:  # idempotent retry of the same create
                if prior.creator_id != user.id:
                    raise AppError(ErrorCodes.CLUB_INVALID, "ID 已被占用", status_code=409)
                return await self.brief(prior, viewer_id=user.id)
        name = name.strip()
        summary = summary.strip()
        if not (MIN_NAME <= len(name) <= MAX_NAME):
            raise AppError(ErrorCodes.CLUB_INVALID, f"俱乐部名称需 {MIN_NAME}-{MAX_NAME} 个字")
        if len(summary) < MIN_SUMMARY:
            raise AppError(ErrorCodes.CLUB_INVALID, f"简介至少 {MIN_SUMMARY} 个字")
        if len(summary) > MAX_SUMMARY:
            raise AppError(ErrorCodes.CLUB_INVALID, f"简介不超过 {MAX_SUMMARY} 个字")
        if topic not in CLUB_TOPICS:
            raise AppError(ErrorCodes.CLUB_INVALID, "请选择有效的主题")
        clean_tags = _clean_tags(tags)
        mine = int(
            await self.db.scalar(
                select(func.count()).select_from(Club).where(
                    Club.creator_id == user.id, Club.status.in_([ClubStatus.ACTIVE.value, ClubStatus.HIDDEN.value])
                )
            )
            or 0
        )
        if mine >= MAX_CREATED_PER_USER:
            raise AppError(ErrorCodes.CLUB_INVALID, f"最多创建 {MAX_CREATED_PER_USER} 个俱乐部", status_code=409)
        dup = await self.db.scalar(
            select(Club.id).where(func.lower(Club.name) == name.lower(), Club.status != ClubStatus.DISSOLVED.value)
        )
        if dup is not None:
            raise AppError(ErrorCodes.CLUB_INVALID, "已有同名俱乐部", status_code=409)

        verdict = await guard_text(self.db, name, summary, " ".join(clean_tags), scene="club")
        club = Club(
            id=club_id or uuid4(),
            name=name,
            topic=topic,
            city=city.strip()[:48],
            summary=summary,
            tags=clean_tags,
            system_image=CLUB_TOPIC_IMAGES.get(topic, "person.3"),
            creator_id=user.id,
            is_official=False,
            status=ClubStatus.ACTIVE.value,
            member_count=1,
            weekly_active=1,
        )
        self.db.add(club)
        await self.db.flush()
        self.db.add(
            ClubMember(
                id=uuid4(),
                club_id=club.id,
                user_id=user.id,
                role=ClubMemberRole.OWNER.value,
                status=ClubMemberStatus.ACTIVE.value,
                last_active_at=datetime.now(timezone.utc),
            )
        )
        await self._ensure_conversation(club, user.id)
        if verdict.needs_review:
            await TrustService(self.db).enqueue_moderation_task(
                target_kind="club",
                target_id=club.id,
                machine_label="review",
                machine_result={"hits": verdict.hits, "scene": "club"},
                payload={"name": club.name},
            )
        await self.db.flush()
        return await self.brief(club, viewer_id=user.id)

    async def _ensure_conversation(self, club: Club, user_id: UUID) -> Conversation:
        conv = await self.db.get(Conversation, club.conversation_id) if club.conversation_id else None
        if conv is None:
            owner_id = club.creator_id or user_id
            im_id = await self.im.open_group(owner_id, [owner_id, user_id], club.name)
            conv = Conversation(
                id=uuid4(),
                kind=ConversationKind.CIRCLE.value,
                im_conversation_id=im_id,
                title=club.name,
                owner_id=club.creator_id,
                related_circle_id=club.id,
                status=ConversationStatus.ACTIVE.value,
            )
            self.db.add(conv)
            await self.db.flush()
            club.conversation_id = conv.id
        elif conv.status != ConversationStatus.ACTIVE.value:
            conv.status = ConversationStatus.ACTIVE.value
        existing = (
            await self.db.execute(
                select(ConversationMember).where(
                    ConversationMember.conversation_id == conv.id, ConversationMember.user_id == user_id
                )
            )
        ).scalar_one_or_none()
        is_owner = club.creator_id == user_id
        if existing is None:
            self.db.add(
                ConversationMember(
                    id=uuid4(),
                    conversation_id=conv.id,
                    user_id=user_id,
                    role=MemberRole.OWNER.value if is_owner else MemberRole.MEMBER.value,
                    status=MemberStatus.ACTIVE.value,
                )
            )
        else:
            existing.status = MemberStatus.ACTIVE.value
        await self.db.flush()
        return conv

    async def join(self, user: User, club_id: UUID) -> dict:
        club = await self._get(club_id)
        if user.status == UserStatus.BANNED.value:
            raise AppError(ErrorCodes.USER_LIMITED, "账号受限", status_code=403)
        member = await self._membership(club.id, user.id)
        if member and member.status == ClubMemberStatus.ACTIVE.value:
            return await self.brief(club, viewer_id=user.id)
        if member and member.status == ClubMemberStatus.KICKED.value:
            raise AppError(ErrorCodes.CLUB_FORBIDDEN, "你已被移出该俱乐部", status_code=403)
        if club.creator_id and await is_blocked_either(self.db, user.id, club.creator_id):
            raise AppError(ErrorCodes.CLUB_FORBIDDEN, "暂时无法加入该俱乐部", status_code=403)
        if member is None:
            member = ClubMember(id=uuid4(), club_id=club.id, user_id=user.id)
            self.db.add(member)
        member.role = ClubMemberRole.MEMBER.value
        member.status = ClubMemberStatus.ACTIVE.value
        member.joined_at = datetime.now(timezone.utc)
        member.last_active_at = member.joined_at
        club.member_count = (club.member_count or 0) + 1
        club.weekly_active = (club.weekly_active or 0) + 1
        await self.db.flush()
        await self._ensure_conversation(club, user.id)
        return await self.brief(club, viewer_id=user.id)

    async def leave(self, user: User, club_id: UUID) -> dict:
        club = await self._get(club_id, allow_hidden_for=user.id)
        member = await self._membership(club.id, user.id)
        if member is None or member.status != ClubMemberStatus.ACTIVE.value:
            return await self.brief(club, viewer_id=user.id)
        if member.role == ClubMemberRole.OWNER.value and club.creator_id == user.id:
            raise AppError(ErrorCodes.CLUB_FORBIDDEN, "创建者不能退出，请解散俱乐部", status_code=409)
        member.status = ClubMemberStatus.LEFT.value
        club.member_count = max(0, (club.member_count or 0) - 1)
        await self._drop_conversation_member(club, user.id)
        await self.db.flush()
        return await self.brief(club, viewer_id=user.id)

    async def _drop_conversation_member(self, club: Club, user_id: UUID, status: str = MemberStatus.LEFT.value) -> None:
        if club.conversation_id is None:
            return
        row = (
            await self.db.execute(
                select(ConversationMember).where(
                    ConversationMember.conversation_id == club.conversation_id,
                    ConversationMember.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if row is not None:
            row.status = status

    async def dissolve(self, user: User, club_id: UUID) -> dict:
        club = await self._get(club_id, allow_hidden_for=user.id)
        if club.is_official or club.creator_id != user.id:
            raise AppError(ErrorCodes.CLUB_FORBIDDEN, "仅创建者可解散俱乐部", status_code=403)
        await self._dissolve(club)
        return {"dissolved": True, "id": str(club.id)}

    async def _dissolve(self, club: Club) -> None:
        club.status = ClubStatus.DISSOLVED.value
        club.dissolved_at = datetime.now(timezone.utc)
        members = (
            await self.db.execute(
                select(ClubMember).where(ClubMember.club_id == club.id, ClubMember.status == ClubMemberStatus.ACTIVE.value)
            )
        ).scalars().all()
        for m in members:
            m.status = ClubMemberStatus.LEFT.value
        if club.conversation_id:
            conv = await self.db.get(Conversation, club.conversation_id)
            if conv is not None:
                conv.status = ConversationStatus.DISSOLVED.value
            cms = (
                await self.db.execute(
                    select(ConversationMember).where(ConversationMember.conversation_id == club.conversation_id)
                )
            ).scalars().all()
            for cm in cms:
                cm.status = MemberStatus.LEFT.value
        club.member_count = 0
        await self.db.flush()

    async def members(self, user: User, club_id: UUID, *, limit: int, offset: int) -> tuple[list[dict], int]:
        club = await self._get(club_id, allow_hidden_for=user.id)
        me = await self._membership(club.id, user.id)
        if me is None or me.status != ClubMemberStatus.ACTIVE.value:
            raise AppError(ErrorCodes.CLUB_FORBIDDEN, "加入俱乐部后可查看成员", status_code=403)
        base = (ClubMember.club_id == club.id, ClubMember.status == ClubMemberStatus.ACTIVE.value)
        total = int(await self.db.scalar(select(func.count()).select_from(ClubMember).where(*base)) or 0)
        rows = (
            await self.db.execute(
                select(ClubMember).where(*base).order_by(ClubMember.role.desc(), ClubMember.joined_at.asc()).limit(limit).offset(offset)
            )
        ).scalars().all()
        items = [
            {
                "user_id": str(m.user_id),
                "display_name": m.nickname or await self._name(m.user_id),
                "role": m.role,
                "joined_at": m.joined_at.isoformat() if m.joined_at else None,
            }
            for m in rows
        ]
        return items, total

    async def kick(self, user: User, club_id: UUID, target_user_id: UUID) -> dict:
        club = await self._get(club_id, allow_hidden_for=user.id)
        me = await self._membership(club.id, user.id)
        if me is None or me.status != ClubMemberStatus.ACTIVE.value or me.role not in {
            ClubMemberRole.OWNER.value, ClubMemberRole.ADMIN.value
        }:
            raise AppError(ErrorCodes.CLUB_FORBIDDEN, "无权移除成员", status_code=403)
        victim = await self._membership(club.id, target_user_id)
        if victim is None or victim.status != ClubMemberStatus.ACTIVE.value:
            raise AppError(ErrorCodes.CLUB_NOT_FOUND, "成员不存在", status_code=404)
        if victim.role == ClubMemberRole.OWNER.value:
            raise AppError(ErrorCodes.CLUB_FORBIDDEN, "不能移除创建者", status_code=403)
        victim.status = ClubMemberStatus.KICKED.value
        club.member_count = max(0, (club.member_count or 0) - 1)
        await self._drop_conversation_member(club, target_user_id, MemberStatus.KICKED.value)
        await self.db.flush()
        return {"removed": True}

    async def chat(self, user: User, club_id: UUID) -> dict:
        """俱乐部群聊会话（成员专属）。"""
        club = await self._get(club_id, allow_hidden_for=user.id)
        me = await self._membership(club.id, user.id)
        if me is None or me.status != ClubMemberStatus.ACTIVE.value:
            raise AppError(ErrorCodes.CLUB_FORBIDDEN, "加入俱乐部后可进群聊", status_code=403)
        conv = await self._ensure_conversation(club, user.id)
        from app.modules.messaging.service import MessagingService

        return await MessagingService(self.db).conversation_brief(conv, viewer_id=user.id)

    # ── admin ──────────────────────────────────────────────

    async def admin_list(
        self, *, q: str | None, status: str | None, topic: str | None, limit: int, offset: int
    ) -> tuple[list[dict], int]:
        filters = []
        if status and status != "all":
            filters.append(Club.status == status)
        if topic:
            filters.append(Club.topic == topic)
        if q and q.strip():
            like = f"%{q.strip()}%"
            filters.append(or_(Club.name.ilike(like), Club.city.ilike(like)))
        total = int(await self.db.scalar(select(func.count()).select_from(Club).where(*filters)) or 0)
        rows = (
            await self.db.execute(select(Club).where(*filters).order_by(Club.created_at.desc()).limit(limit).offset(offset))
        ).scalars().all()
        items = [await self.brief(c, viewer_id=None) | {"creator_id": str(c.creator_id) if c.creator_id else None, "admin_note": c.admin_note} for c in rows]
        return items, total

    async def admin_set_status(self, club_id: UUID, *, action: str, note: str | None) -> dict:
        club = await self.db.get(Club, club_id)
        if club is None:
            raise AppError(ErrorCodes.CLUB_NOT_FOUND, "俱乐部不存在", status_code=404)
        if action == "hide":
            club.status = ClubStatus.HIDDEN.value
        elif action == "unhide":
            if club.status == ClubStatus.DISSOLVED.value:
                raise AppError(ErrorCodes.CLUB_INVALID, "已解散的俱乐部不能恢复")
            club.status = ClubStatus.ACTIVE.value
        elif action == "dissolve":
            await self._dissolve(club)
        else:
            raise AppError(ErrorCodes.CLUB_INVALID, "无效操作")
        if note is not None:
            club.admin_note = note[:500] or None
        await self.db.flush()
        return await self.brief(club, viewer_id=None) | {"admin_note": club.admin_note}


class GuildService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _counts(self, guild: Guild) -> tuple[int, int]:
        companions = int(
            await self.db.scalar(select(func.count()).select_from(CompanionProfile).where(CompanionProfile.guild_id == guild.id))
            or 0
        )
        since = datetime.now(timezone.utc) - timedelta(days=7)
        orders = int(
            await self.db.scalar(
                select(func.count())
                .select_from(CompanionBooking)
                .join(CompanionProfile, CompanionProfile.user_id == CompanionBooking.companion_id)
                .where(CompanionProfile.guild_id == guild.id, CompanionBooking.created_at >= since)
            )
            or 0
        )
        return companions, orders

    async def brief(self, guild: Guild, *, viewer_id: UUID | None) -> dict:
        companions, orders = await self._counts(guild)
        followed = False
        if viewer_id:
            followed = (
                await self.db.scalar(
                    select(GuildFollow.id).where(GuildFollow.guild_id == guild.id, GuildFollow.user_id == viewer_id)
                )
            ) is not None
        return {
            "id": str(guild.id),
            "name": guild.name,
            "specialty": guild.specialty,
            "city": guild.city,
            "summary": guild.summary,
            "tags": list(guild.tags or []),
            "system_image": guild.system_image,
            "companion_count": companions,
            "weekly_orders": orders,
            "price_from": guild.price_from_cents // 100,
            "price_from_cents": guild.price_from_cents,
            "is_followed": followed,
            "status": guild.status,
        }

    async def list_guilds(self, viewer: User, *, city: str | None, q: str | None, limit: int, offset: int) -> tuple[list[dict], int]:
        filters = [Guild.status == GuildStatus.ACTIVE.value]
        if city:
            filters.append(Guild.city.ilike(f"{city.strip()}%"))
        if q and q.strip():
            like = f"%{q.strip()}%"
            filters.append(or_(Guild.name.ilike(like), Guild.specialty.ilike(like), Guild.summary.ilike(like)))
        total = int(await self.db.scalar(select(func.count()).select_from(Guild).where(*filters)) or 0)
        rows = (await self.db.execute(select(Guild).where(*filters).order_by(Guild.created_at.asc()).limit(limit).offset(offset))).scalars().all()
        return [await self.brief(g, viewer_id=viewer.id) for g in rows], total

    async def _get(self, guild_id: UUID) -> Guild:
        g = await self.db.get(Guild, guild_id)
        if g is None or g.status != GuildStatus.ACTIVE.value:
            raise AppError(ErrorCodes.GUILD_NOT_FOUND, "工会不存在", status_code=404)
        return g

    async def get(self, viewer: User, guild_id: UUID) -> dict:
        return await self.brief(await self._get(guild_id), viewer_id=viewer.id)

    async def follow(self, user: User, guild_id: UUID, *, follow: bool) -> dict:
        g = await self._get(guild_id)
        row = (
            await self.db.execute(select(GuildFollow).where(GuildFollow.guild_id == g.id, GuildFollow.user_id == user.id))
        ).scalar_one_or_none()
        if follow and row is None:
            self.db.add(GuildFollow(id=uuid4(), guild_id=g.id, user_id=user.id))
        elif not follow and row is not None:
            await self.db.delete(row)
        await self.db.flush()
        return await self.brief(g, viewer_id=user.id)

    async def chat(self, user: User, guild_id: UUID) -> dict:
        """工会咨询会话：用户 ↔ 工会负责人（无负责人时仅用户一侧，待运营接入客服）。"""
        g = await self._get(guild_id)
        convs = (
            await self.db.execute(
                select(Conversation)
                .join(ConversationMember, ConversationMember.conversation_id == Conversation.id)
                .where(
                    Conversation.kind == ConversationKind.GROUP.value,
                    Conversation.status == ConversationStatus.ACTIVE.value,
                    ConversationMember.user_id == user.id,
                    ConversationMember.status == MemberStatus.ACTIVE.value,
                )
            )
        ).scalars().all()
        conv = next((c for c in convs if (c.meta or {}).get("guild_id") == str(g.id)), None)
        from app.modules.messaging.service import MessagingService

        svc = MessagingService(self.db)
        if conv is None:
            participants = [user.id] + ([g.owner_user_id] if g.owner_user_id and g.owner_user_id != user.id else [])
            im_id = await get_im_provider().open_group(user.id, participants, g.name)
            conv = Conversation(
                id=uuid4(),
                kind=ConversationKind.GROUP.value,
                im_conversation_id=im_id,
                title=f"{g.name} · 咨询",
                owner_id=g.owner_user_id or user.id,
                status=ConversationStatus.ACTIVE.value,
                meta={"guild_id": str(g.id)},
            )
            self.db.add(conv)
            await self.db.flush()
            await svc._add_member(conv.id, user.id, MemberRole.MEMBER.value)
            if g.owner_user_id and g.owner_user_id != user.id:
                await svc._add_member(conv.id, g.owner_user_id, MemberRole.OWNER.value)
            await self.db.flush()
        return await svc.conversation_brief(conv, viewer_id=user.id)

    # ── admin ──────────────────────────────────────────────

    async def admin_list(self, *, q: str | None, status: str | None, limit: int, offset: int) -> tuple[list[dict], int]:
        filters = []
        if status and status != "all":
            filters.append(Guild.status == status)
        if q and q.strip():
            like = f"%{q.strip()}%"
            filters.append(or_(Guild.name.ilike(like), Guild.city.ilike(like)))
        total = int(await self.db.scalar(select(func.count()).select_from(Guild).where(*filters)) or 0)
        rows = (await self.db.execute(select(Guild).where(*filters).order_by(Guild.created_at.desc()).limit(limit).offset(offset))).scalars().all()
        out = []
        for g in rows:
            b = await self.brief(g, viewer_id=None)
            b["owner_user_id"] = str(g.owner_user_id) if g.owner_user_id else None
            out.append(b)
        return out, total

    async def admin_upsert(self, guild_id: UUID | None, data: dict) -> dict:
        if guild_id is None:
            g = Guild(id=uuid4())
            self.db.add(g)
        else:
            g = await self.db.get(Guild, guild_id)
            if g is None:
                raise AppError(ErrorCodes.GUILD_NOT_FOUND, "工会不存在", status_code=404)
        for key in ("name", "specialty", "city", "summary", "system_image"):
            if data.get(key) is not None:
                setattr(g, key, str(data[key]).strip())
        if not (g.name or "").strip():
            raise AppError(ErrorCodes.CLUB_INVALID, "工会名称不能为空")
        if data.get("tags") is not None:
            g.tags = _clean_tags(data["tags"])
        if data.get("price_from_cents") is not None:
            g.price_from_cents = max(0, int(data["price_from_cents"]))
        if "owner_user_id" in data:
            g.owner_user_id = data["owner_user_id"]
        if data.get("status") in {GuildStatus.ACTIVE.value, GuildStatus.HIDDEN.value}:
            g.status = data["status"]
        if g.tags is None:
            g.tags = []
        await self.db.flush()
        return await self.brief(g, viewer_id=None) | {"owner_user_id": str(g.owner_user_id) if g.owner_user_id else None}

    async def admin_assign_companion(self, guild_id: UUID, companion_user_id: UUID, *, assign: bool) -> dict:
        g = await self.db.get(Guild, guild_id)
        if g is None:
            raise AppError(ErrorCodes.GUILD_NOT_FOUND, "工会不存在", status_code=404)
        profile = await self.db.get(CompanionProfile, companion_user_id)
        if profile is None:
            raise AppError(ErrorCodes.COMPANION_NOT_FOUND, "陪玩不存在", status_code=404)
        profile.guild_id = g.id if assign else (None if profile.guild_id == g.id else profile.guild_id)
        await self.db.flush()
        return await self.brief(g, viewer_id=None)
