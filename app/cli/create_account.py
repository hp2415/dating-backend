"""Create or reset an app login (phone + password).

Inside the API container (after image rebuild):

    docker exec dating-api python -m app.cli.create_account \\
        --phone 13800001111 --password 'YourPassword8+'

Reset:

    docker exec dating-api python -m app.cli.create_account \\
        --phone 13800001111 --password 'NewPassword8+' --reset
"""

from __future__ import annotations

import argparse
import asyncio
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import User, UserPreference, UserProfile, UserStatus
from app.modules.auth.service import normalize_phone
from app.shared.db import SessionLocal, engine
from app.shared.passwords import hash_password


def _parse() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create or reset an app phone/password account")
    parser.add_argument("--phone", required=True, help="11-digit phone, used as the login account")
    parser.add_argument("--password", required=True, help="At least 8 characters")
    parser.add_argument("--display-name", default="", help="Optional display name")
    parser.add_argument("--reset", action="store_true", help="Overwrite password if the phone already exists")
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> None:
    phone = normalize_phone(args.phone)
    password = args.password
    if len(phone) != 11:
        raise SystemExit("手机号必须是 11 位数字")
    if len(password) < 8 or len(password) > 72:
        raise SystemExit("密码长度需在 8–72 之间")

    async with SessionLocal() as db:
        result = await db.execute(select(User).where(User.phone == phone).options(selectinload(User.profile)))
        user = result.scalar_one_or_none()
        if user is None:
            user = User(
                id=uuid4(),
                phone=phone,
                password_hash=hash_password(password),
                status=UserStatus.ACTIVE.value,
            )
            db.add(user)
            await db.flush()
            name = args.display_name.strip() or None
            db.add(UserProfile(user_id=user.id, display_name=name, tags=[]))
            db.add(UserPreference(user_id=user.id, want_genders=[]))
            action = "created"
        elif args.reset:
            user.password_hash = hash_password(password)
            if user.status == UserStatus.DELETED.value:
                user.status = UserStatus.ACTIVE.value
            if args.display_name.strip() and user.profile is not None:
                user.profile.display_name = args.display_name.strip()
            action = "reset"
        else:
            raise SystemExit(f"手机号 {phone} 已存在。要改密码请加 --reset")
        await db.commit()
        print(f"{action} account phone={phone} user_id={user.id}")

    await engine.dispose()


def main() -> None:
    asyncio.run(_run(_parse()))


if __name__ == "__main__":
    main()
