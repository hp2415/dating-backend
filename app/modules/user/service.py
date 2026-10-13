from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    AuditStatus,
    MediaAsset,
    User,
    UserFollow,
    UserPreference,
    UserProfile,
    UserSettings,
    UserStatus,
)
from app.modules.auth.service import mask_phone
from app.modules.media.storage import normalize_stored_media_url
from app.modules.user.schemas import PROFILE_EXTRA_KEYS
from app.shared.config import settings
from app.shared.errors import AppError
from app.shared.pagination import page_offset
from app.shared.response import ErrorCodes


def _profile_extras(profile: UserProfile) -> dict:
    return {key: getattr(profile, key, None) for key in PROFILE_EXTRA_KEYS}


def calc_age(birthday: date | None) -> int | None:
    if birthday is None:
        return None
    today = date.today()
    return today.year - birthday.year - ((today.month, today.day) < (birthday.month, birthday.day))


def calc_completion(profile: UserProfile) -> int:
    score = 0
    if profile.display_name:
        score += 25
    if profile.birthday:
        score += 20
    if profile.gender and profile.gender != "unknown":
        score += 15
    if profile.city:
        score += 10
    if profile.bio:
        score += 15
    if profile.tags:
        score += 10
    if profile.avatar_media_id:
        score += 5
    return min(score, 100)


_SETTINGS_BOOL_KEYS = (
    "show_distance",
    "show_online",
    "allow_invite",
    "notify_activity",
    "notify_buddy",
    "notify_message",
    "notify_community",
    "youth_mode",
)
_SETTINGS_DT_KEYS = ("guidelines_ack_at", "legal_consent_at")


class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_me(self, user: User) -> dict:
        avatar_url = None
        if user.profile and user.profile.avatar_media_id:
            media = await self.db.get(MediaAsset, user.profile.avatar_media_id)
            if media and media.audit_status != AuditStatus.REJECTED.value and media.deleted_at is None:
                avatar_url = normalize_stored_media_url(media.url)

        profile = None
        if user.profile:
            profile = {
                "display_name": user.profile.display_name,
                "birthday": user.profile.birthday,
                "gender": user.profile.gender,
                "city": user.profile.city,
                "bio": user.profile.bio,
                "tags": user.profile.tags or [],
                "avatar_url": avatar_url,
                "completion_score": user.profile.completion_score,
                **_profile_extras(user.profile),
            }
        preference = None
        if user.preference:
            preference = {
                "want_genders": user.preference.want_genders or [],
                "age_min": user.preference.age_min,
                "age_max": user.preference.age_max,
                "max_distance_km": user.preference.max_distance_km,
            }
        return {
            "id": user.id,
            "phone_masked": mask_phone(user.phone),
            "public_uid": user.public_uid,
            "profile_completed": user.profile_completed,
            "discoverable": user.discoverable,
            "status": user.status,
            "profile": profile,
            "preference": preference,
        }

    async def get_public_profile(self, viewer: User, user_id: UUID) -> dict:
        result = await self.db.execute(
            select(User).where(User.id == user_id).options(selectinload(User.profile))
        )
        user = result.scalar_one_or_none()
        if user is None or user.status == UserStatus.DELETED.value:
            raise AppError(ErrorCodes.USER_NOT_FOUND, "用户不存在", status_code=404)

        avatar_url = None
        display_name = None
        city = None
        bio = None
        tags: list[str] = []
        if user.profile:
            display_name = user.profile.display_name
            city = user.profile.city
            bio = user.profile.bio
            tags = user.profile.tags or []
            if user.profile.avatar_media_id:
                media = await self.db.get(MediaAsset, user.profile.avatar_media_id)
                if (
                    media
                    and media.audit_status == AuditStatus.APPROVED.value
                    and media.deleted_at is None
                ):
                    avatar_url = normalize_stored_media_url(media.url)

        from app.modules.trust.service import TrustService

        trust = await TrustService(self.db).get_public_trust(user_id)
        extras = _profile_extras(user.profile) if user.profile else dict.fromkeys(PROFILE_EXTRA_KEYS)
        return {
            "id": user.id,
            "public_uid": user.public_uid,
            "display_name": display_name or "用户",
            "city": city,
            "bio": bio,
            "tags": tags,
            "avatar_url": avatar_url,
            "trust": trust,
            **extras,
            **await self._follow_stats(viewer.id, user.id),
        }

    async def _follow_stats(self, viewer_id: UUID, target_id: UUID) -> dict:
        following = await self.db.scalar(
            select(func.count()).select_from(UserFollow).where(UserFollow.follower_id == target_id)
        )
        followers = await self.db.scalar(
            select(func.count()).select_from(UserFollow).where(UserFollow.followee_id == target_id)
        )
        is_following = False
        if viewer_id != target_id:
            is_following = (
                await self.db.scalar(
                    select(UserFollow.id).where(
                        UserFollow.follower_id == viewer_id, UserFollow.followee_id == target_id
                    )
                )
            ) is not None
        return {
            "following_count": int(following or 0),
            "followers_count": int(followers or 0),
            "is_following": is_following,
        }

    async def follow(self, viewer: User, target_id: UUID) -> dict:
        if viewer.id == target_id:
            raise AppError(ErrorCodes.USER_PROFILE_INVALID, "不能关注自己")
        target = await self.db.get(User, target_id)
        if target is None or target.status == UserStatus.DELETED.value:
            raise AppError(ErrorCodes.USER_NOT_FOUND, "用户不存在", status_code=404)
        exists = await self.db.scalar(
            select(UserFollow.id).where(
                UserFollow.follower_id == viewer.id, UserFollow.followee_id == target_id
            )
        )
        if exists is None:
            self.db.add(UserFollow(follower_id=viewer.id, followee_id=target_id))
            try:
                await self.db.commit()
            except IntegrityError:
                await self.db.rollback()
        return {"user_id": target_id, **await self._follow_stats(viewer.id, target_id)}

    async def unfollow(self, viewer: User, target_id: UUID) -> dict:
        await self.db.execute(
            delete(UserFollow).where(
                UserFollow.follower_id == viewer.id, UserFollow.followee_id == target_id
            )
        )
        await self.db.commit()
        return {"user_id": target_id, **await self._follow_stats(viewer.id, target_id)}

    async def list_follows(self, viewer: User, direction: str, limit: int, offset: int) -> dict:
        if direction == "following":
            own_col, peer_col = UserFollow.follower_id, UserFollow.followee_id
        else:
            own_col, peer_col = UserFollow.followee_id, UserFollow.follower_id

        live = (User.id == peer_col) & (User.status != UserStatus.DELETED.value)
        total = await self.db.scalar(
            select(func.count()).select_from(UserFollow).join(User, live).where(own_col == viewer.id)
        )
        rows = (
            await self.db.execute(
                select(User, UserFollow.created_at)
                .join(UserFollow, live)
                .where(own_col == viewer.id)
                .options(selectinload(User.profile))
                .order_by(UserFollow.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()

        peer_ids = [u.id for u, _ in rows]
        mutual: set[UUID] = set()
        if peer_ids:
            if direction == "following":
                back = select(UserFollow.follower_id).where(
                    UserFollow.followee_id == viewer.id, UserFollow.follower_id.in_(peer_ids)
                )
            else:
                back = select(UserFollow.followee_id).where(
                    UserFollow.follower_id == viewer.id, UserFollow.followee_id.in_(peer_ids)
                )
            mutual = set((await self.db.execute(back)).scalars().all())

        items = []
        for peer, followed_at in rows:
            items.append(
                {
                    "id": peer.id,
                    "public_uid": peer.public_uid,
                    "display_name": (peer.profile.display_name if peer.profile else None) or "用户",
                    "avatar_url": await self._approved_avatar(peer),
                    "bio": peer.profile.bio if peer.profile else None,
                    "is_mutual": peer.id in mutual,
                    "followed_at": followed_at.isoformat() if followed_at else None,
                }
            )
        return page_offset(items, total=int(total or 0), limit=limit, offset=offset)

    async def _approved_avatar(self, user: User) -> str | None:
        if not user.profile or not user.profile.avatar_media_id:
            return None
        media = await self.db.get(MediaAsset, user.profile.avatar_media_id)
        if media and media.audit_status == AuditStatus.APPROVED.value and media.deleted_at is None:
            return normalize_stored_media_url(media.url)
        return None

    async def get_settings(self, user: User) -> dict:
        row = await self._ensure_settings(user.id)
        return self._settings_brief(row)

    async def update_settings(self, user: User, payload: dict) -> dict:
        row = await self._ensure_settings(user.id)
        for key in _SETTINGS_BOOL_KEYS:
            if key in payload and payload[key] is not None:
                setattr(row, key, bool(payload[key]))
        for key in _SETTINGS_DT_KEYS:
            if key in payload and payload[key] is not None:
                setattr(row, key, payload[key])
        row.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(row)
        return self._settings_brief(row)

    async def _ensure_settings(self, user_id: UUID) -> UserSettings:
        row = await self.db.get(UserSettings, user_id)
        if row is None:
            row = UserSettings(user_id=user_id)
            self.db.add(row)
            await self.db.flush()
        return row

    def _settings_brief(self, row: UserSettings) -> dict:
        return {
            "show_distance": row.show_distance,
            "show_online": row.show_online,
            "allow_invite": row.allow_invite,
            "notify_activity": row.notify_activity,
            "notify_buddy": row.notify_buddy,
            "notify_message": row.notify_message,
            "notify_community": row.notify_community,
            "youth_mode": row.youth_mode,
            "guidelines_ack_at": row.guidelines_ack_at.isoformat() if row.guidelines_ack_at else None,
            "legal_consent_at": row.legal_consent_at.isoformat() if row.legal_consent_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    async def update_profile(self, user: User, payload: dict) -> dict:
        result = await self.db.execute(
            select(UserProfile).where(UserProfile.user_id == user.id)
        )
        profile = result.scalar_one_or_none()
        if profile is None:
            profile = UserProfile(user_id=user.id, tags=[])
            self.db.add(profile)

        if "birthday" in payload and payload["birthday"] is not None:
            age = calc_age(payload["birthday"])
            if age is not None and age < settings.min_age:
                raise AppError(ErrorCodes.USER_UNDERAGE, f"未满{settings.min_age}岁无法使用匹配功能")

        for key in ("display_name", "birthday", "gender", "city", "bio", "tags", "avatar_media_id"):
            if key in payload and payload[key] is not None:
                setattr(profile, key, payload[key])
        for key in PROFILE_EXTRA_KEYS:
            if key in payload:
                setattr(profile, key, payload[key])

        if payload.get("avatar_media_id"):
            media = await self.db.get(MediaAsset, payload["avatar_media_id"])
            if media is None or media.owner_id != user.id:
                raise AppError(ErrorCodes.MEDIA_FORBIDDEN, "头像资源无效")

        profile.completion_score = calc_completion(profile)

        essential_ok = bool(
            profile.display_name and profile.birthday and profile.gender != "unknown"
        )
        age = calc_age(profile.birthday)
        underage = age is not None and age < settings.min_age
        user.profile_completed = essential_ok and not underage
        user.discoverable = user.profile_completed and not underage
        user.updated_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(user)
        result = await self.db.execute(
            select(User)
            .where(User.id == user.id)
            .options(selectinload(User.profile), selectinload(User.preference))
        )
        user = result.scalar_one()
        return await self.get_me(user)

    async def update_preference(self, user: User, payload: dict) -> dict:
        result = await self.db.execute(
            select(UserPreference).where(UserPreference.user_id == user.id)
        )
        pref = result.scalar_one_or_none()
        if pref is None:
            pref = UserPreference(user_id=user.id, want_genders=[])
            self.db.add(pref)

        age_min = payload.get("age_min", pref.age_min)
        age_max = payload.get("age_max", pref.age_max)
        if age_min > age_max:
            raise AppError(ErrorCodes.USER_PROFILE_INVALID, "年龄范围不合法")

        for key in ("want_genders", "age_min", "age_max", "max_distance_km"):
            if key in payload and payload[key] is not None:
                setattr(pref, key, payload[key])

        await self.db.commit()
        result = await self.db.execute(
            select(User)
            .where(User.id == user.id)
            .options(selectinload(User.profile), selectinload(User.preference))
        )
        user = result.scalar_one()
        return await self.get_me(user)

    async def delete_account(self, user: User, confirm: bool) -> dict:
        if not confirm:
            raise AppError(ErrorCodes.USER_PROFILE_INVALID, "请确认注销账号")
        user.status = UserStatus.DELETED.value
        user.discoverable = False
        user.profile_completed = False
        await self.db.commit()
        return {"deleted": True}
