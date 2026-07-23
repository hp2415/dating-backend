import logging
import random
import string
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Device, RefreshToken, User, UserPreference, UserProfile, UserStatus
from app.shared.config import settings
from app.shared.errors import AppError
from app.shared.redis_client import get_redis
from app.shared.response import ErrorCodes
from app.shared.security import create_access_token, create_refresh_token, decode_token

logger = logging.getLogger(__name__)


def mask_phone(phone: str) -> str:
    if len(phone) < 7:
        return phone
    return phone[:3] + "****" + phone[-4:]


def normalize_phone(phone: str) -> str:
    digits = "".join(ch for ch in phone if ch.isdigit())
    if digits.startswith("86") and len(digits) == 13:
        digits = digits[2:]
    return digits


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.redis = get_redis()

    async def send_sms(self, phone: str) -> dict:
        phone = normalize_phone(phone)
        if len(phone) < 11:
            raise AppError(ErrorCodes.AUTH_INVALID, "手机号格式不正确")

        interval_key = f"sms:interval:{phone}"
        if await self.redis.exists(interval_key):
            raise AppError(ErrorCodes.AUTH_RATE_LIMIT, "发送过于频繁，请稍后再试", status_code=429)

        daily_key = f"sms:daily:{phone}:{datetime.now(timezone.utc).strftime('%Y%m%d')}"
        daily_count = int(await self.redis.get(daily_key) or 0)
        if daily_count >= settings.sms_daily_limit:
            raise AppError(ErrorCodes.AUTH_RATE_LIMIT, "今日短信次数已达上限", status_code=429)

        code = settings.sms_dev_code if settings.app_env == "development" else "".join(
            random.choices(string.digits, k=6)
        )
        await self.redis.setex(f"sms:code:{phone}", settings.sms_code_ttl_seconds, code)
        await self.redis.setex(interval_key, settings.sms_send_interval_seconds, "1")
        await self.redis.incr(daily_key)
        await self.redis.expire(daily_key, 86400)

        # Development: log code. Production: call SMS provider.
        logger.info("SMS code for %s => %s", mask_phone(phone), code)
        payload = {"phone_masked": mask_phone(phone), "expires_in": settings.sms_code_ttl_seconds}
        if settings.app_env == "development":
            payload["dev_code"] = code
        return payload

    async def login(self, phone: str, code: str, device_id: str, platform: str) -> dict:
        phone = normalize_phone(phone)
        stored = await self.redis.get(f"sms:code:{phone}")
        if stored is None:
            raise AppError(ErrorCodes.AUTH_CODE_EXPIRED, "验证码已过期，请重新获取")
        if stored != code and not (
            settings.app_env == "development" and code == settings.sms_dev_code
        ):
            raise AppError(ErrorCodes.AUTH_CODE_INVALID, "验证码错误")

        await self.redis.delete(f"sms:code:{phone}")

        result = await self.db.execute(
            select(User)
            .where(User.phone == phone)
            .options(selectinload(User.profile), selectinload(User.preference))
        )
        user = result.scalar_one_or_none()
        created = False
        if user is None:
            user = User(id=uuid4(), phone=phone, status=UserStatus.ACTIVE.value)
            self.db.add(user)
            await self.db.flush()
            self.db.add(UserProfile(user_id=user.id, tags=[]))
            self.db.add(UserPreference(user_id=user.id, want_genders=[]))
            created = True
        elif user.status == UserStatus.BANNED.value:
            raise AppError(ErrorCodes.AUTH_BANNED, "账号已被封禁", status_code=403)
        elif user.status == UserStatus.DELETED.value:
            raise AppError(ErrorCodes.AUTH_UNAUTHORIZED, "账号已注销", status_code=401)

        user.last_active_at = datetime.now(timezone.utc)
        await self._upsert_device(user.id, device_id, platform)
        tokens = await self._issue_tokens(user.id)
        await self.db.commit()

        return {
            "tokens": tokens,
            "user": {
                "id": user.id,
                "phone_masked": mask_phone(user.phone),
                "profile_completed": user.profile_completed,
                "discoverable": user.discoverable,
                "status": user.status,
            },
            "created": created,
        }

    async def refresh(self, refresh_token: str) -> dict:
        try:
            payload = decode_token(refresh_token)
        except Exception as exc:  # noqa: BLE001
            raise AppError(ErrorCodes.AUTH_TOKEN_INVALID, "刷新令牌无效", status_code=401) from exc
        if payload.get("type") != "refresh":
            raise AppError(ErrorCodes.AUTH_TOKEN_INVALID, "刷新令牌类型错误", status_code=401)

        jti = payload.get("jti")
        user_id = payload.get("sub")
        row = await self.db.execute(select(RefreshToken).where(RefreshToken.jti == jti))
        token_row = row.scalar_one_or_none()
        if token_row is None or token_row.revoked:
            raise AppError(ErrorCodes.AUTH_TOKEN_INVALID, "刷新令牌已失效", status_code=401)
        if token_row.expires_at < datetime.now(timezone.utc):
            raise AppError(ErrorCodes.AUTH_TOKEN_INVALID, "刷新令牌已过期", status_code=401)

        token_row.revoked = True
        tokens = await self._issue_tokens(UUID(user_id))
        await self.db.commit()
        return tokens

    async def logout(self, refresh_token: str | None) -> None:
        if not refresh_token:
            return
        try:
            payload = decode_token(refresh_token)
            jti = payload.get("jti")
            if jti:
                row = await self.db.execute(select(RefreshToken).where(RefreshToken.jti == jti))
                token_row = row.scalar_one_or_none()
                if token_row:
                    token_row.revoked = True
                    await self.db.commit()
        except Exception:  # noqa: BLE001
            return

    async def _issue_tokens(self, user_id: UUID) -> dict:
        access = create_access_token(user_id=str(user_id))
        refresh, jti = create_refresh_token(user_id=str(user_id))
        self.db.add(
            RefreshToken(
                id=uuid4(),
                user_id=user_id,
                jti=jti,
                expires_at=datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_ttl_days),
            )
        )
        return {
            "access_token": access,
            "refresh_token": refresh,
            "token_type": "Bearer",
            "expires_in": settings.jwt_access_ttl_minutes * 60,
        }

    async def _upsert_device(self, user_id: UUID, device_id: str, platform: str) -> None:
        result = await self.db.execute(
            select(Device).where(Device.user_id == user_id, Device.device_id == device_id)
        )
        device = result.scalar_one_or_none()
        now = datetime.now(timezone.utc)
        if device is None:
            self.db.add(
                Device(
                    id=uuid4(),
                    user_id=user_id,
                    device_id=device_id,
                    platform=platform,
                    last_seen_at=now,
                )
            )
        else:
            device.platform = platform
            device.last_seen_at = now
