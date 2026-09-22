#!/usr/bin/env python3
"""Page-level demo seed. Complements scripts/seed_content.py (prefix SEED·).

This script uses prefix DEMO· and phones 13900007701–13900007710.
It downloads cover images, uploads them through /api/v1/media, then fills:

  - activities in every category (food/sport/travel/game/study/outdoors/other)
  - plaza posts with pictures, comments, likes and bookmarks
  - companions with services, slots, one paid booking and a review
  - joins, favorites, buddy intents, friend requests, wallet orders

Idempotent by stable DEMO· titles. Safe to re-run.
Does not run on app startup.

  python scripts/seed_pages.py --base http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PHONES = [f"139000077{i:02d}" for i in range(1, 11)]
ADMIN_USER = "admin"
ADMIN_PASS = "Admin@123456"
SMS_CODE = "123456"
MARKER = "DEMO·评"

# picsum ids are fetched by the script at runtime (JPEG after redirect).
PHOTO_IDS = [1015, 1016, 1025, 1036, 1040, 106, 133, 146, 164, 180, 201, 237, 250, 292, 318, 342]

PROFILES: list[dict[str, Any]] = [
    {"display_name": "DEMO·林夏", "birthday": "1996-04-12", "gender": "female", "city": "上海", "bio": "爱探店，周末固定组局。", "tags": ["美食", "探店", "摄影"]},
    {"display_name": "DEMO·周予", "birthday": "1993-08-02", "gender": "male", "city": "成都", "bio": "羽毛球和夜骑都可以约。", "tags": ["羽毛球", "骑行", "健身"]},
    {"display_name": "DEMO·苏晚", "birthday": "1998-01-19", "gender": "female", "city": "杭州", "bio": "短途旅行，喜欢博物馆。", "tags": ["旅行", "博物馆", "咖啡"]},
    {"display_name": "DEMO·陈柯", "birthday": "1994-11-30", "gender": "male", "city": "深圳", "bio": "剧本杀常驻，也能带新手。", "tags": ["剧本杀", "桌游", "电影"]},
    {"display_name": "DEMO·江禾", "birthday": "1997-06-08", "gender": "female", "city": "北京", "bio": "自习和语言交换。", "tags": ["自习", "英语", "读书"]},
    {"display_name": "DEMO·赵北", "birthday": "1992-02-14", "gender": "male", "city": "南京", "bio": "徒步向导，周末出城。", "tags": ["徒步", "露营", "摄影"]},
    {"display_name": "DEMO·许安", "birthday": "1999-09-21", "gender": "female", "city": "广州", "bio": "电竞观赛和开黑。", "tags": ["游戏", "电竞", "奶茶"]},
    {"display_name": "DEMO·韩澈", "birthday": "1995-12-03", "gender": "male", "city": "苏州", "bio": "城市漫步陪逛。", "tags": ["漫步", "咖啡", "展览"]},
    {"display_name": "DEMO·唐果", "birthday": "1991-07-27", "gender": "female", "city": "上海", "bio": "火锅局组织者。", "tags": ["火锅", "美食", "聊天"]},
    {"display_name": "DEMO·梁川", "birthday": "1990-03-16", "gender": "male", "city": "成都", "bio": "篮球和飞盘。", "tags": ["篮球", "飞盘", "运动"]},
]

# host is an index into PHONES. pending items stay unapproved for the moderation queue.
ACTIVITIES: list[dict[str, Any]] = [
    {"key": "DEMO·活动·美食·火锅局", "category": "food", "city": "上海", "address": "静安嘉里中心", "fee_type": "free", "fee_cents": 0, "host": 8, "capacity": 6, "summary": "六人火锅，人均自理，先到先坐。"},
    {"key": "DEMO·活动·美食·早茶", "category": "food", "city": "广州", "address": "上下九", "fee_type": "online_pay", "fee_cents": 6800, "host": 6, "capacity": 8, "summary": "周日早茶，费用含茶位。"},
    {"key": "DEMO·活动·美食·待审探店", "category": "food", "city": "成都", "address": "玉林路", "fee_type": "free", "fee_cents": 0, "host": 0, "capacity": 4, "summary": "待运营审核的探店局。", "pending": True},
    {"key": "DEMO·活动·运动·羽毛球", "category": "sport", "city": "成都", "address": "高新体育馆", "fee_type": "aa_offline", "fee_cents": 4000, "fee_note": "场地费 AA", "host": 1, "capacity": 8, "summary": "进阶局，自带拍。"},
    {"key": "DEMO·活动·运动·夜骑", "category": "sport", "city": "杭州", "address": "钱塘江岸", "fee_type": "free", "fee_cents": 0, "host": 9, "capacity": 12, "summary": "20 公里休闲骑，有头盔更好。"},
    {"key": "DEMO·活动·运动·篮球三对三", "category": "sport", "city": "成都", "address": "东郊记忆球场", "fee_type": "free", "fee_cents": 0, "host": 9, "capacity": 6, "summary": "半场三对三，输的人请饮料。"},
    {"key": "DEMO·活动·旅行·西湖半日", "category": "travel", "city": "杭州", "address": "断桥", "fee_type": "free", "fee_cents": 0, "host": 2, "capacity": 8, "summary": "步行+拍照，不赶景点。"},
    {"key": "DEMO·活动·旅行·博物馆", "category": "travel", "city": "上海", "address": "上海博物馆", "fee_type": "free", "fee_cents": 0, "host": 0, "capacity": 6, "summary": "东馆预约后集合。"},
    {"key": "DEMO·活动·旅行·南京城墙", "category": "travel", "city": "南京", "address": "中华门", "fee_type": "online_pay", "fee_cents": 3000, "host": 5, "capacity": 10, "summary": "门票自理，集合后一起走。"},
    {"key": "DEMO·活动·游戏·剧本杀", "category": "game", "city": "深圳", "address": "海岸城店", "fee_type": "online_pay", "fee_cents": 12800, "host": 3, "capacity": 6, "summary": "情感本，6 人满员开。"},
    {"key": "DEMO·活动·游戏·桌游夜", "category": "game", "city": "北京", "address": "五道口", "fee_type": "free", "fee_cents": 0, "host": 3, "capacity": 8, "summary": "阿瓦隆和卡坦，新手可来。"},
    {"key": "DEMO·活动·游戏·开黑", "category": "game", "city": "广州", "address": "线上", "fee_type": "free", "fee_cents": 0, "host": 6, "capacity": 5, "summary": "语音开黑，段位不限。"},
    {"key": "DEMO·活动·学习·自习室", "category": "study", "city": "北京", "address": "国图附近", "fee_type": "free", "fee_cents": 0, "host": 4, "capacity": 6, "summary": "静音自习三小时。"},
    {"key": "DEMO·活动·学习·英语角", "category": "study", "city": "上海", "address": "徐汇滨江", "fee_type": "free", "fee_cents": 0, "host": 4, "capacity": 10, "summary": "中英夹杂聊天，不考试。"},
    {"key": "DEMO·活动·学习·读书会", "category": "study", "city": "苏州", "address": "诚品书店", "fee_type": "free", "fee_cents": 0, "host": 7, "capacity": 8, "summary": "每人带一本正在读的书。"},
    {"key": "DEMO·活动·户外·徒步", "category": "outdoors", "city": "杭州", "address": "九溪", "fee_type": "free", "fee_cents": 0, "host": 5, "capacity": 10, "summary": "轻徒步，穿防滑鞋。"},
    {"key": "DEMO·活动·户外·露营", "category": "outdoors", "city": "成都", "address": "三圣乡", "fee_type": "aa_offline", "fee_cents": 8000, "fee_note": "营地费 AA", "host": 5, "capacity": 8, "summary": "过夜露营，公共装备我带。"},
    {"key": "DEMO·活动·户外·待审飞盘", "category": "outdoors", "city": "上海", "address": "世纪公园", "fee_type": "free", "fee_cents": 0, "host": 9, "capacity": 14, "summary": "待审核的飞盘局。", "pending": True},
    {"key": "DEMO·活动·其他·城市漫步", "category": "other", "city": "苏州", "address": "平江路", "fee_type": "free", "fee_cents": 0, "host": 7, "capacity": 6, "summary": "慢走拍照，随时可撤。"},
    {"key": "DEMO·活动·其他·看展", "category": "other", "city": "上海", "address": "西岸美术馆", "fee_type": "online_pay", "fee_cents": 5000, "host": 2, "capacity": 6, "summary": "门票各自买，一起看。"},
    {"key": "DEMO·活动·其他·咖啡办公", "category": "other", "city": "深圳", "address": "华侨城", "fee_type": "free", "fee_cents": 0, "host": 7, "capacity": 4, "summary": "带电脑坐一下午。"},
]

POSTS: list[dict[str, Any]] = [
    {"key": "DEMO·帖子·火锅复盘", "author": 8, "content": "DEMO·帖子·火锅复盘\n静安那家锅底偏辣，六个人刚好。下周还想约清汤。"},
    {"key": "DEMO·帖子·夜骑", "author": 9, "content": "DEMO·帖子·夜骑\n钱塘江风很大，头盔比车灯重要。"},
    {"key": "DEMO·帖子·西湖", "author": 2, "content": "DEMO·帖子·西湖\n断桥人少的时候拍照最好看，建议上午。"},
    {"key": "DEMO·帖子·剧本杀", "author": 3, "content": "DEMO·帖子·剧本杀\n这本适合第一次玩的人，别选硬推理。"},
    {"key": "DEMO·帖子·自习", "author": 4, "content": "DEMO·帖子·自习\n国图附近的位置要早到，插座不多。"},
    {"key": "DEMO·帖子·徒步", "author": 5, "content": "DEMO·帖子·徒步\n九溪石阶湿，穿旧鞋就行。"},
    {"key": "DEMO·帖子·早茶", "author": 6, "content": "DEMO·帖子·早茶\n虾饺先点，凤爪要等。"},
    {"key": "DEMO·帖子·看展", "author": 0, "content": "DEMO·帖子·看展\n西岸这周的展不需要预约，周一闭馆。"},
    {"key": "DEMO·帖子·篮球", "author": 9, "content": "DEMO·帖子·篮球\n东郊记忆傍晚有灯，适合下班后来。"},
    {"key": "DEMO·帖子·咖啡", "author": 7, "content": "DEMO·帖子·咖啡\n平江路靠河那家可以坐很久，插座在窗边。"},
    {"key": "DEMO·帖子·待审飞盘", "author": 1, "content": "DEMO·帖子·待审飞盘\n世纪公园新手局，等审核通过再约时间。", "pending": True},
    {"key": "DEMO·帖子·待审露营", "author": 5, "content": "DEMO·帖子·待审露营\n装备清单还在整理，先发出来等审核。", "pending": True},
]

COMPANION_INDEXES = (1, 5, 7)  # 周予 / 赵北 / 韩澈


def _idem_key(prefix: str, *parts: str, limit: int = 64) -> str:
    """Stable key that fits companion_bookings.idempotency_key (varchar 64)."""
    raw = "-".join(part.replace("-", "") for part in parts)
    key = f"{prefix}-{raw}"
    if len(key) <= limit:
        return key
    room = limit - len(prefix) - 1
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"{prefix}-{digest[:room]}"


def _sniff(data: bytes) -> tuple[str, str]:
    if data.startswith(b"\xff\xd8"):
        return "image/jpeg", "jpg"
    if data.startswith(b"\x89PNG"):
        return "image/png", "png"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp", "webp"
    if data.startswith(b"GIF8"):
        return "image/gif", "gif"
    raise RuntimeError("下载到的文件不是受支持的图片")


def _download(url: str) -> tuple[bytes, str, str]:
    request = Request(url, headers={"User-Agent": "spark-seed-pages/1.0", "Accept": "image/*"})
    try:
        with urlopen(request, timeout=40) as resp:
            data = resp.read()
    except (HTTPError, URLError) as exc:
        raise RuntimeError(f"下载图片失败 {url}: {exc}") from exc
    if len(data) < 32:
        raise RuntimeError(f"图片过小 {url}")
    content_type, ext = _sniff(data)
    return data, content_type, ext


def _req(
    method: str,
    url: str,
    *,
    token: str | None = None,
    body: dict | None = None,
    raw: bytes | None = None,
    content_type: str | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    extra = dict(headers or {})
    data: bytes | None = None
    if raw is not None:
        data = raw
        extra.setdefault("Content-Type", content_type or "application/octet-stream")
    elif body is not None:
        data = json.dumps(body).encode("utf-8")
        extra["Content-Type"] = "application/json"
    extra.setdefault("Accept", "application/json")
    if token:
        extra["Authorization"] = f"Bearer {token}"
    request = Request(url, data=data, headers=extra, method=method)
    try:
        with urlopen(request, timeout=40) as resp:
            text = resp.read().decode("utf-8")
            return json.loads(text) if text else {}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} -> {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"{method} {url} failed: {exc}") from exc


def _ok(env: dict) -> Any:
    if env.get("code", 0) != 0:
        raise RuntimeError(env.get("message") or str(env))
    return env.get("data")


def _soft(label: str, fn) -> Any:
    try:
        return fn()
    except RuntimeError as exc:
        print(f"  skip {label}: {exc}")
        return None


def _optional(base: str, path: str, token: str) -> Any:
    """GET that treats a missing resource as empty."""
    try:
        return _ok(_req("GET", f"{base}{path}", token=token))
    except RuntimeError as exc:
        text = str(exc)
        if "-> 404:" in text or "尚未" in text:
            return None
        raise


def sms_login(base: str, phone: str) -> str:
    try:
        _req("POST", f"{base}/api/v1/auth/sms/send", body={"phone": phone})
    except RuntimeError:
        pass
    data = _ok(
        _req(
            "POST",
            f"{base}/api/v1/auth/sms/login",
            body={"phone": phone, "code": SMS_CODE, "device_id": "seed-pages", "platform": "android"},
        )
    )
    return data["tokens"]["access_token"]


def admin_login(base: str) -> str:
    data = _ok(
        _req(
            "POST",
            f"{base}/admin/v1/auth/login",
            body={"username": ADMIN_USER, "password": ADMIN_PASS},
        )
    )
    return data["access_token"]


class ImageCache:
    def __init__(self) -> None:
        self._blobs: dict[int, tuple[bytes, str, str]] = {}

    def blob(self, slot: int) -> tuple[bytes, str, str]:
        start = slot % len(PHOTO_IDS)
        last: Exception | None = None
        for step in range(len(PHOTO_IDS)):
            photo_id = PHOTO_IDS[(start + step) % len(PHOTO_IDS)]
            cached = self._blobs.get(photo_id)
            if cached is not None:
                return cached
            url = f"https://picsum.photos/id/{photo_id}/960/640.jpg"
            print(f"  download {url}")
            try:
                blob = _download(url)
            except RuntimeError as exc:
                last = exc
                print(f"  next photo: {exc}")
                continue
            self._blobs[photo_id] = blob
            return blob
        raise RuntimeError(f"没有可用的封面图: {last}")


def upload_image(
    base: str,
    token: str,
    images: ImageCache,
    slot: int,
    media_type: str,
    *,
    avatar: bool = False,
) -> str:
    data, content_type, ext = images.blob(slot)
    sts = _ok(
        _req(
            "POST",
            f"{base}/api/v1/media/sts",
            token=token,
            body={"media_type": media_type, "content_type": content_type, "ext": ext},
        )
    )
    upload_url = str(sts["upload_url"])
    if upload_url.startswith("/"):
        upload_url = base + upload_url
    _ok(_req("PUT", upload_url, raw=data, content_type=content_type))
    done = _ok(
        _req(
            "POST",
            f"{base}/api/v1/media/complete",
            token=token,
            body={
                "object_key": sts["object_key"],
                "media_type": media_type,
                "set_as_avatar": avatar,
                "width": 960,
                "height": 640,
            },
        )
    )
    return str(done["id"])


def list_admin(base: str, admin: str, path: str, *, status: str | None = None) -> list[dict]:
    items: list[dict] = []
    offset = 0
    while True:
        query = f"limit=100&offset={offset}"
        if status:
            query += f"&status={status}"
        data = _ok(_req("GET", f"{base}{path}?{query}", token=admin)) or {}
        batch = list(data.get("items") or [])
        items.extend(batch)
        total = int(data.get("total") or 0)
        offset += 100
        if not batch or offset >= total:
            break
    return items


def ensure_users(base: str, images: ImageCache, dry_run: bool) -> list[dict[str, Any]]:
    users: list[dict[str, Any]] = []
    for i, phone in enumerate(PHONES):
        profile = PROFILES[i]
        if dry_run:
            print(f"  dry-run user {phone} {profile['display_name']}")
            users.append({"phone": phone, "token": "", "user_id": "", "index": i})
            continue
        token = sms_login(base, phone)
        _ok(_req("PUT", f"{base}/api/v1/me/profile", token=token, body=profile))
        me = _ok(_req("GET", f"{base}/api/v1/me", token=token)) or {}
        uid = str(me.get("id") or "")
        profile_body = me.get("profile") or {}
        avatar = profile_body.get("avatar_url") or ""
        if not avatar:
            upload_image(base, token, images, i, "avatar", avatar=True)
            print(f"  avatar {phone}")
        print(f"  user {phone} {profile['display_name']} -> {uid}")
        users.append({"phone": phone, "token": token, "user_id": uid, "index": i})
    return users


def ensure_balance(base: str, users: list[dict], admin: str, dry_run: bool) -> None:
    if dry_run:
        print("  dry-run wallet grant")
        return
    for user in users:
        brief = _ok(_req("GET", f"{base}/api/v1/me/wallet", token=user["token"])) or {}
        balance = int(brief.get("balance_cents") or 0)
        if balance >= 30_000:
            print(f"  wallet {user['phone']} already {balance}")
            continue
        _ok(
            _req(
                "POST",
                f"{base}/admin/v1/wallet/grant",
                token=admin,
                body={
                    "user_id": user["user_id"],
                    "amount_cents": 80_000,
                    "title": "DEMO·页面演示余额",
                },
            )
        )
        print(f"  granted ¥800 to {user['phone']}")


def ensure_activities(
    base: str,
    users: list[dict],
    admin: str,
    images: ImageCache,
    dry_run: bool,
) -> list[dict[str, Any]]:
    existing = {a.get("title"): a for a in list_admin(base, admin, "/admin/v1/activities", status="all")}
    out: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)
    for i, spec in enumerate(ACTIVITIES):
        title = spec["key"]
        hit = existing.get(title)
        if dry_run:
            print(f"  dry-run activity {title}")
            continue
        if hit and hit.get("id"):
            aid = str(hit["id"])
            status = hit.get("status")
            print(f"  skip activity {title} ({status})")
        else:
            host = users[spec["host"]]
            media_id = upload_image(base, host["token"], images, i + 3, "activity_image")
            start = now + timedelta(days=2 + (i % 10), hours=10)
            created = _ok(
                _req(
                    "POST",
                    f"{base}/api/v1/activities",
                    token=host["token"],
                    body={
                        "title": title,
                        "description": spec["summary"],
                        "category": spec["category"],
                        "city": spec["city"],
                        "address": spec["address"],
                        "capacity": spec["capacity"],
                        "start_at": start.isoformat(),
                        "end_at": (start + timedelta(hours=3)).isoformat(),
                        "fee_type": spec["fee_type"],
                        "fee_cents": spec["fee_cents"],
                        "fee_note": spec.get("fee_note"),
                        "media": [{"type": "image", "media_id": media_id}],
                    },
                )
            )
            aid = str(created["id"])
            _ok(
                _req(
                    "PUT",
                    f"{base}/api/v1/activities/{aid}/details",
                    token=host["token"],
                    body={
                        "timeline": [{"time": "14:00", "title": "集合", "note": spec["address"]}],
                        "prep_notes": ["提前 10 分钟到", "下雨改期会在通知里说"],
                        "host_note": spec["summary"],
                        "fee_included": ["组织与集合"],
                        "fee_excluded": ["个人餐饮与交通"],
                    },
                )
            )
            print(f"  created {title} -> {aid}")
            status = created.get("status") or "pending"
        if spec.get("pending"):
            print(f"  leave pending {title}")
        elif status != "published":
            _ok(
                _req(
                    "POST",
                    f"{base}/admin/v1/activities/{aid}/review",
                    token=admin,
                    body={"action": "approve"},
                )
            )
            print(f"  approved {title}")
            status = "published"
        out.append({**spec, "id": aid, "status": status})
    return out


def ensure_posts(
    base: str,
    users: list[dict],
    admin: str,
    images: ImageCache,
    dry_run: bool,
) -> list[dict[str, Any]]:
    existing = list_admin(base, admin, "/admin/v1/community/posts", status="all")
    by_key: dict[str, dict] = {}
    for post in existing:
        content = post.get("content") or ""
        for spec in POSTS:
            if spec["key"] in content:
                by_key[spec["key"]] = post
    out: list[dict[str, Any]] = []
    for i, spec in enumerate(POSTS):
        key = spec["key"]
        if dry_run:
            print(f"  dry-run post {key}")
            continue
        hit = by_key.get(key)
        if hit and hit.get("id"):
            pid = str(hit["id"])
            status = hit.get("status")
            print(f"  skip post {key} ({status})")
        else:
            author = users[spec["author"]]
            media_id = upload_image(base, author["token"], images, i + 1, "post_image")
            created = _ok(
                _req(
                    "POST",
                    f"{base}/api/v1/community/posts",
                    token=author["token"],
                    body={
                        "content": spec["content"],
                        "media": [{"type": "image", "media_id": media_id}],
                    },
                )
            )
            pid = str(created["id"])
            status = created.get("status") or "pending"
            print(f"  created post {key} -> {pid}")
        if spec.get("pending"):
            print(f"  leave pending {key}")
        elif status not in ("published", "approved", "active"):
            _ok(
                _req(
                    "POST",
                    f"{base}/admin/v1/community/posts/{pid}/review",
                    token=admin,
                    body={"action": "approve"},
                )
            )
            print(f"  approved {key}")
            status = "published"
        out.append({**spec, "id": pid, "status": status})
    return out


def _has_comment(base: str, token: str, path: str, marker: str) -> bool:
    data = _ok(_req("GET", f"{base}{path}", token=token)) or {}
    for item in data.get("items") or []:
        if marker in (item.get("content") or ""):
            return True
    return False


def simulate_usage(base: str, users: list[dict], activities: list[dict], posts: list[dict], dry_run: bool) -> None:
    if dry_run:
        print("  dry-run joins / comments / likes")
        return
    published = [a for a in activities if a.get("status") == "published" and a.get("id")]
    for activity in published:
        host_index = activity["host"]
        guests = [u for u in users if u["index"] != host_index][:3]
        for guest in guests[:2]:
            _soft(
                f"join {activity['key']}",
                lambda g=guest, aid=activity["id"]: _ok(
                    _req("POST", f"{base}/api/v1/activities/{aid}/join", token=g["token"])
                ),
            )
        commenter = guests[0]
        marker = f"{MARKER}·{activity['key']}"
        if not _has_comment(base, commenter["token"], f"/api/v1/activities/{activity['id']}/comments", marker):
            _soft(
                f"comment {activity['key']}",
                lambda c=commenter, aid=activity["id"], text=marker: _ok(
                    _req(
                        "POST",
                        f"{base}/api/v1/activities/{aid}/comments",
                        token=c["token"],
                        body={"content": f"{text}\n我可以到，大概提前十分钟。"},
                    )
                ),
            )
        for guest in guests:
            _soft(
                "like",
                lambda g=guest, aid=activity["id"]: _ok(
                    _req("POST", f"{base}/api/v1/activities/{aid}/like", token=g["token"])
                ),
            )
        _soft(
            "favorite",
            lambda g=guests[-1], aid=activity["id"]: _ok(
                _req("POST", f"{base}/api/v1/activities/{aid}/favorite", token=g["token"])
            ),
        )
    print(f"  usage on {len(published)} activities")

    for post in posts:
        if post.get("status") != "published" or not post.get("id"):
            continue
        others = [u for u in users if u["index"] != post["author"]][:2]
        for user in others:
            _soft(
                "post like",
                lambda u=user, pid=post["id"]: _ok(
                    _req("POST", f"{base}/api/v1/community/posts/{pid}/like", token=u["token"])
                ),
            )
        _soft(
            "bookmark",
            lambda u=others[0], pid=post["id"]: _ok(
                _req("POST", f"{base}/api/v1/community/posts/{pid}/bookmark", token=u["token"])
            ),
        )
        marker = f"{MARKER}·{post['key']}"
        if not _has_comment(base, others[0]["token"], f"/api/v1/community/posts/{post['id']}/comments", marker):
            _soft(
                "post comment",
                lambda u=others[0], pid=post["id"], text=marker: _ok(
                    _req(
                        "POST",
                        f"{base}/api/v1/community/posts/{pid}/comments",
                        token=u["token"],
                        body={"content": f"{text}\n看起来不错，算我一个。"},
                    )
                ),
            )
    print(f"  usage on posts")


def ensure_orders(base: str, users: list[dict], activities: list[dict], dry_run: bool) -> None:
    paid = next((a for a in activities if a.get("status") == "published" and a.get("fee_cents", 0) > 0), None)
    if paid is None or dry_run:
        print("  skip activity order")
        return
    buyer = next(u for u in users if u["index"] != paid["host"])
    key = f"demo-order-{paid['id']}-{buyer['user_id']}"
    order = _soft(
        "create activity order",
        lambda: _ok(
            _req(
                "POST",
                f"{base}/api/v1/orders",
                token=buyer["token"],
                headers={"Idempotency-Key": key},
                body={
                    "kind": "activity",
                    "subject_id": paid["id"],
                    "subject_title": paid["key"],
                    "amount_cents": paid["fee_cents"],
                },
            )
        ),
    )
    if not order:
        return
    if order.get("status") != "paid":
        _soft(
            "pay activity order",
            lambda: _ok(
                _req(
                    "POST",
                    f"{base}/api/v1/orders/{order['id']}/pay",
                    token=buyer["token"],
                    body={"method": "wallet"},
                )
            ),
        )
    print(f"  order for {paid['key']}")


def ensure_companions(base: str, users: list[dict], admin: str, dry_run: bool) -> None:
    now = datetime.now(timezone.utc)
    specialties = ["羽毛球陪练", "徒步向导", "城市漫步"]
    for n, index in enumerate(COMPANION_INDEXES):
        user = users[index]
        if dry_run:
            print(f"  dry-run companion {user['phone']}")
            continue
        profile = _optional(base, f"/api/v1/me/companion-profile", user["token"])
        status = (profile or {}).get("status") if isinstance(profile, dict) else None
        if status != "active":
            if status != "pending":
                _ok(
                    _req(
                        "POST",
                        f"{base}/api/v1/companions/apply",
                        token=user["token"],
                        body={
                            "service_type": "offline",
                            "specialty": specialties[n],
                            "intro": f"{PROFILES[index]['display_name']} · 页面演示陪玩，可预约近 7 天。",
                            "city": PROFILES[index]["city"],
                            "response_time_minutes": 20 + n * 10,
                        },
                    )
                )
            _ok(
                _req(
                    "POST",
                    f"{base}/admin/v1/companions/{user['user_id']}/review",
                    token=admin,
                    body={"action": "approve"},
                )
            )
            print(f"  approved companion {user['phone']}")
        profile = _ok(_req("GET", f"{base}/api/v1/me/companion-profile", token=user["token"])) or {}
        services = list(profile.get("services") or [])
        if not services:
            _ok(
                _req(
                    "POST",
                    f"{base}/api/v1/me/companion-profile/services",
                    token=user["token"],
                    body={
                        "title": f"DEMO·服务·{specialties[n]}",
                        "pricing_unit": "hour",
                        "price_cents": 8800 + n * 2000,
                        "min_units": 1,
                        "description": "两小时起，含集合与简单指导。",
                        "sort_order": 0,
                        "active": True,
                    },
                )
            )
            profile = _ok(_req("GET", f"{base}/api/v1/me/companion-profile", token=user["token"])) or {}
            services = list(profile.get("services") or [])
        slots = _ok(_req("GET", f"{base}/api/v1/companions/{user['user_id']}/slots", token=user["token"]))
        slot_items = list((slots or {}).get("items") or [])
        open_days = {(s.get("start_at") or "")[:10] for s in slot_items if s.get("status") == "open"}
        for day in range(7):
            start = (now + timedelta(days=1 + day)).replace(hour=15, minute=0, second=0, microsecond=0)
            if start.date().isoformat() in open_days:
                continue
            _ok(
                _req(
                    "POST",
                    f"{base}/api/v1/me/companion-profile/slots",
                    token=user["token"],
                    body={"start_at": start.isoformat(), "end_at": (start + timedelta(hours=2)).isoformat()},
                )
            )
        print(f"  companion ready {user['phone']}")
        if n == 0 and services:
            _complete_one_booking(base, users, user, services[0])


def _complete_one_booking(base: str, users: list[dict], companion: dict, service: dict) -> None:
    buyer = users[0]
    if buyer["user_id"] == companion["user_id"]:
        buyer = users[2]
    existing = _ok(_req("GET", f"{base}/api/v1/me/bookings", token=buyer["token"])) or {}
    for row in existing.get("items") or []:
        if str(row.get("companion_id") or "") == companion["user_id"]:
            status = row.get("status")
            if status == "completed":
                _review_and_checkin(base, buyer, companion, str(row["id"]))
                print("  skip booking (already completed)")
                return
            if status in ("cancelled", "refunded"):
                continue
            _advance_booking(base, buyer, companion, row)
            print(f"  resumed booking {row.get('id')}")
            return
    slots = _ok(
        _req("GET", f"{base}/api/v1/companions/{companion['user_id']}/slots", token=buyer["token"])
    ) or {}
    open_slot = next((s for s in (slots.get("items") or []) if s.get("status") == "open"), None)
    if open_slot is None:
        print("  skip booking (no open slot)")
        return
    service_id = str(service.get("id") or "")
    booking = _ok(
        _req(
            "POST",
            f"{base}/api/v1/bookings",
            token=buyer["token"],
            headers={
                "Idempotency-Key": _idem_key("demo-bk", companion["user_id"], buyer["user_id"]),
            },
            body={
                "companion_id": companion["user_id"],
                "service_id": service_id,
                "slot_id": open_slot["id"],
                "units": 1,
            },
        )
    )
    _advance_booking(base, buyer, companion, booking)
    print(f"  completed booking {booking.get('id')}")


def _advance_booking(base: str, buyer: dict, companion: dict, booking: dict) -> None:
    bid = str(booking["id"])
    status = booking.get("status")
    order_id = booking.get("order_id")
    if status == "awaiting_payment" and order_id:
        _ok(
            _req(
                "POST",
                f"{base}/api/v1/orders/{order_id}/pay",
                token=buyer["token"],
                body={"method": "wallet"},
            )
        )
        status = "paid"
    if status in ("paid", "pending_confirm"):
        _ok(_req("POST", f"{base}/api/v1/bookings/{bid}/start", token=companion["token"]))
        status = "in_progress"
    if status == "in_progress":
        _ok(_req("POST", f"{base}/api/v1/bookings/{bid}/complete", token=buyer["token"]))
    _review_and_checkin(base, buyer, companion, bid)


def _review_and_checkin(base: str, buyer: dict, companion: dict, booking_id: str) -> None:
    _soft(
        "review",
        lambda: _ok(
            _req(
                "POST",
                f"{base}/api/v1/companions/{companion['user_id']}/reviews?booking_id={booking_id}",
                token=buyer["token"],
                body={"rating": 5, "content": "DEMO·评·陪玩体验顺利，时间准，沟通清楚。"},
            )
        ),
    )
    _soft(
        "checkin",
        lambda: _ok(
            _req(
                "POST",
                f"{base}/api/v1/safety/checkins",
                token=buyer["token"],
                body={
                    "subject_kind": "booking",
                    "subject_id": booking_id,
                    "result": "ok",
                    "note": "DEMO·顺利",
                },
            )
        ),
    )


def ensure_social(base: str, users: list[dict], activities: list[dict], dry_run: bool) -> None:
    if dry_run or len(users) < 4:
        print("  dry-run social")
        return
    pairs = [(0, 1), (2, 3), (4, 5)]
    for a, b in pairs:
        left, right = users[a], users[b]
        friends = _ok(_req("GET", f"{base}/api/v1/friends", token=left["token"])) or {}
        ids = {str(item.get("user_id") or item.get("friend_user_id") or "") for item in (friends.get("items") or [])}
        if right["user_id"] not in ids:
            created = _soft(
                "friend request",
                lambda l=left, r=right: _ok(
                    _req(
                        "POST",
                        f"{base}/api/v1/friend-requests",
                        token=l["token"],
                        body={"to_user_id": r["user_id"], "message": "DEMO·周末一起玩吗", "source": "demo"},
                    )
                ),
            )
            if created and created.get("id"):
                _soft(
                    "accept friend",
                    lambda r=right, rid=created["id"]: _ok(
                        _req(
                            "POST",
                            f"{base}/api/v1/friend-requests/{rid}/respond",
                            token=r["token"],
                            body={"action": "accept"},
                        )
                    ),
                )
        _soft(
            "direct",
            lambda l=left, r=right: _ok(
                _req(
                    "POST",
                    f"{base}/api/v1/conversations/direct",
                    token=l["token"],
                    body={"peer_user_id": r["user_id"], "preview": "DEMO·明天下午见？"},
                )
            ),
        )
    for user in users[:6]:
        _soft(
            "intent",
            lambda u=user: _ok(
                _req(
                    "PUT",
                    f"{base}/api/v1/me/buddy-intent",
                    token=u["token"],
                    body={
                        "text": f"DEMO·{PROFILES[u['index']]['display_name']} 这周末想找人一起玩",
                        "tags": PROFILES[u["index"]]["tags"],
                        "city": PROFILES[u["index"]]["city"],
                        "active": True,
                    },
                )
            ),
        )
    published = next((a for a in activities if a.get("status") == "published"), None)
    if published:
        host = users[published["host"]]
        guest = next(u for u in users if u["index"] != published["host"])
        _soft(
            "greet",
            lambda: _ok(
                _req(
                    "POST",
                    f"{base}/api/v1/buddies/{host['user_id']}/greet",
                    token=guest["token"],
                    body={"text": "DEMO·你好，看到你的活动了"},
                )
            ),
        )
        sent = _ok(
            _req("GET", f"{base}/api/v1/me/buddy-invites?direction=sent", token=host["token"])
        ) or {}
        already = any(
            str(item.get("activity_id") or "") == published["id"]
            and str(item.get("to_user_id") or "") == guest["user_id"]
            for item in (sent.get("items") or [])
        )
        if not already:
            _soft(
                "invite",
                lambda: _ok(
                    _req(
                        "POST",
                        f"{base}/api/v1/buddies/invites",
                        token=host["token"],
                        body={
                            "to_user_id": guest["user_id"],
                            "activity_id": published["id"],
                            "message": "DEMO·一起来吗",
                        },
                    )
                ),
            )
    print("  social graph ready")


def ensure_shelves(base: str, admin: str, activities: list[dict], dry_run: bool) -> None:
    published = [a for a in activities if a.get("status") == "published" and a.get("id")]
    if not published:
        print("  no activities for shelves")
        return
    existing = {s.get("title"): s for s in list_admin(base, admin, "/admin/v1/discover-shelves")}
    groups: list[tuple[str, str, list[str]]] = [
        ("DEMO·本周精选", "hero", [a["id"] for a in published[:4]]),
    ]
    for category in ("food", "sport", "travel", "game", "study", "outdoors", "other"):
        ids = [a["id"] for a in published if a["category"] == category]
        if ids:
            groups.append((f"DEMO·{category}", "rail", ids))
    for title, layout, ids in groups:
        if dry_run:
            print(f"  dry-run shelf {title}")
            continue
        shelf = existing.get(title)
        if shelf and shelf.get("id"):
            shelf_id = str(shelf["id"])
            print(f"  skip shelf {title}")
        else:
            created = _ok(
                _req(
                    "POST",
                    f"{base}/admin/v1/discover-shelves",
                    token=admin,
                    body={
                        "title": title,
                        "subtitle": "页面演示",
                        "layout": layout,
                        "rule_type": "manual",
                        "rule": {},
                        "city_scope": [],
                        "sort_order": 5 if layout == "hero" else 30,
                        "enabled": True,
                    },
                )
            )
            shelf_id = str(created["id"])
            print(f"  shelf {title}")
        items = _ok(_req("GET", f"{base}/admin/v1/discover-shelves/{shelf_id}/items", token=admin)) or {}
        if items.get("items"):
            continue
        for idx, sid in enumerate(ids):
            _ok(
                _req(
                    "POST",
                    f"{base}/admin/v1/discover-shelves/{shelf_id}/items",
                    token=admin,
                    body={
                        "subject_kind": "activity",
                        "subject_id": sid,
                        "sort_order": idx,
                        "pinned": idx == 0 and layout == "hero",
                    },
                )
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed page-level demo content (DEMO·)")
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    base = args.base.rstrip("/")
    images = ImageCache()
    print(f"seed_pages -> {base}")
    admin = "" if args.dry_run else admin_login(base)
    print("== users ==")
    users = ensure_users(base, images, args.dry_run)
    print("== wallet ==")
    if not args.dry_run:
        ensure_balance(base, users, admin, args.dry_run)
    print("== activities ==")
    activities = ensure_activities(base, users, admin, images, args.dry_run)
    print("== posts ==")
    posts = ensure_posts(base, users, admin, images, args.dry_run)
    print("== usage ==")
    simulate_usage(base, users, activities, posts, args.dry_run)
    print("== orders ==")
    ensure_orders(base, users, activities, args.dry_run)
    print("== companions ==")
    ensure_companions(base, users, admin, args.dry_run)
    print("== social ==")
    ensure_social(base, users, activities, args.dry_run)
    print("== shelves ==")
    ensure_shelves(base, admin, activities, args.dry_run)
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
