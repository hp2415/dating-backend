from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import AuditStatus, MediaAsset, User, UserPreference, UserProfile, UserStatus
from app.modules.auth.service import mask_phone
from app.shared.config import settings
from app.shared.errors import AppError
from app.shared.response import ErrorCodes


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


class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_me(self, user: User) -> dict:
        avatar_url = None
        if user.profile and user.profile.avatar_media_id:
            media = await self.db.get(MediaAsset, user.profile.avatar_media_id)
            if media and media.audit_status != AuditStatus.REJECTED.value:
                avatar_url = media.url

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
            "profile_completed": user.profile_completed,
            "discoverable": user.discoverable,
            "status": user.status,
            "profile": profile,
            "preference": preference,
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

        if payload.get("avatar_media_id"):
            media = await self.db.get(MediaAsset, payload["avatar_media_id"])
            if media is None or media.owner_id != user.id:
                raise AppError(ErrorCodes.MEDIA_FORBIDDEN, "头像资源无效")

        profile.completion_score = calc_completion(profile)

        # Mark profile completed when essential fields exist
        essential_ok = bool(
            profile.display_name and profile.birthday and profile.gender != "unknown"
        )
        age = calc_age(profile.birthday)
        underage = age is not None and age < settings.min_age
        user.profile_completed = essential_ok and not underage
        # Discoverable only when completed and avatar not rejected (pending allowed for MVP soft launch)
        user.discoverable = user.profile_completed and not underage
        user.updated_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(user)
        # reload relations
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
