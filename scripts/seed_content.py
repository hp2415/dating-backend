#!/usr/bin/env python3
"""Cold-start / demo content seed (INTEGRATION_PLAN P0-5 / DEMO_PLAN B-07).

Creates 8 SMS demo users, 2 approved companions (+ services/slots),
20 activities (17 published + 3 pending), 12 posts (10 published + 2 pending),
friendship + direct conversation preview, wallet grants when balance is 0,
and discover shelves pointing at published activities.

Idempotent by stable titles (SEED·…); safe to re-run.
Does NOT run on app lifespan — invoke manually:

  python scripts/seed_content.py --base http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SEED_PHONES = [f"1390000880{i}" for i in range(1, 9)]  # 13900008801 .. 13900008808
SEED_PHONE = SEED_PHONES[0]
ADMIN_USER = "admin"
ADMIN_PASS = os.environ.get("ADMIN_DEFAULT_PASSWORD", "Admin@123456")
STATE_PATH = Path(__file__).resolve().parent / ".seed_content_state.json"

WALLET_GRANT_CENTS = 50_000
PENDING_ACTIVITY_NS = {18, 19, 20}
PENDING_POST_NS = {11, 12}
COMPANION_PHONE_INDEXES = (1, 2)  # users 2 and 3 (0-based: phones[1], phones[2])

CATEGORIES = ["sport", "food", "travel", "game", "study", "outdoors", "other", "sport"]
CITIES = ["上海", "成都", "杭州", "深圳", "北京", "南京", "苏州", "广州"]
COVERS = [
    "https://images.unsplash.com/photo-1476480862126-209bfaa8edc8?w=640",
    "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?w=640",
    "https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?w=640",
    "https://images.unsplash.com/photo-1529626455594-4ff0802cfb7e?w=640",
]

# Distinct profiles for the 8 demo phones (index 0 = SEED主办 host).
DEMO_PROFILES: list[dict[str, Any]] = [
    {
        "display_name": "SEED主办",
        "birthday": "1995-06-15",
        "gender": "female",
        "city": "上海",
        "bio": "内容冷启动账号（seed_content）",
        "tags": ["羽毛球", "骑行", "火锅局"],
    },
    {
        "display_name": "SEED陪玩·阿程",
        "birthday": "1993-03-22",
        "gender": "male",
        "city": "成都",
        "bio": "线下陪玩演示账号",
        "tags": ["剧本杀", "桌游", "咖啡"],
    },
    {
        "display_name": "SEED陪玩·小鹿",
        "birthday": "1997-11-08",
        "gender": "female",
        "city": "杭州",
        "bio": "户外与摄影陪玩演示",
        "tags": ["徒步", "摄影", "露营"],
    },
    {
        "display_name": "SEED吃货小林",
        "birthday": "1998-01-30",
        "gender": "female",
        "city": "深圳",
        "bio": "探店与美食局",
        "tags": ["火锅", "探店", "奶茶"],
    },
    {
        "display_name": "SEED球友老周",
        "birthday": "1992-09-12",
        "gender": "male",
        "city": "北京",
        "bio": "球类活动常驻",
        "tags": ["篮球", "网球", "健身"],
    },
    {
        "display_name": "SEED旅人阿南",
        "birthday": "1996-05-04",
        "gender": "male",
        "city": "南京",
        "bio": "周末短途旅行",
        "tags": ["旅行", "博物馆", "摄影"],
    },
    {
        "display_name": "SEED学霸小美",
        "birthday": "1999-07-19",
        "gender": "female",
        "city": "苏州",
        "bio": "自习与语言交换",
        "tags": ["自习", "英语", "读书"],
    },
    {
        "display_name": "SEED电竞阿凯",
        "birthday": "1994-12-01",
        "gender": "male",
        "city": "广州",
        "bio": "线上开黑与电竞观赛",
        "tags": ["游戏", "电竞", "桌游"],
    },
]


def _req(
    method: str,
    url: str,
    *,
    token: str | None = None,
    body: dict | None = None,
) -> Any:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} -> {e.code}: {detail}") from e
    except URLError as e:
        raise RuntimeError(f"{method} {url} failed: {e}") from e


def _ok(env: dict) -> Any:
    if env.get("code", 0) != 0:
        raise RuntimeError(env.get("message") or str(env))
    return env.get("data")


def sms_login(base: str, phone: str) -> str:
    try:
        _req("POST", f"{base}/api/v1/auth/sms/send", body={"phone": phone})
    except RuntimeError:
        pass
    env = _req(
        "POST",
        f"{base}/api/v1/auth/sms/login",
        body={
            "phone": phone,
            "code": "123456",
            "device_id": "seed-content",
            "platform": "android",
        },
    )
    data = _ok(env)
    return data["tokens"]["access_token"]


def admin_login(base: str) -> str:
    env = _req(
        "POST",
        f"{base}/admin/v1/auth/login",
        body={"username": ADMIN_USER, "password": ADMIN_PASS},
    )
    data = _ok(env)
    return data["access_token"]


def get_me(base: str, token: str) -> dict:
    return _ok(_req("GET", f"{base}/api/v1/me", token=token)) or {}


def ensure_profile(base: str, token: str, profile: dict[str, Any]) -> None:
    _ok(_req("PUT", f"{base}/api/v1/me/profile", token=token, body=profile))


def list_admin_activities(base: str, admin: str) -> list[dict]:
    items: list[dict] = []
    offset = 0
    limit = 100
    while True:
        env = _req(
            "GET",
            f"{base}/admin/v1/activities?limit={limit}&offset={offset}",
            token=admin,
        )
        data = _ok(env) or {}
        batch = list(data.get("items") or [])
        items.extend(batch)
        total = int(data.get("total") or 0)
        offset += limit
        if not batch or offset >= total:
            break
    return items


def list_admin_posts(base: str, admin: str) -> list[dict]:
    items: list[dict] = []
    offset = 0
    limit = 100
    while True:
        env = _req(
            "GET",
            f"{base}/admin/v1/community/posts?limit={limit}&offset={offset}",
            token=admin,
        )
        data = _ok(env) or {}
        batch = list(data.get("items") or [])
        items.extend(batch)
        total = int(data.get("total") or 0)
        offset += limit
        if not batch or offset >= total:
            break
    return items


def list_shelves(base: str, admin: str) -> list[dict]:
    env = _req("GET", f"{base}/admin/v1/discover-shelves?limit=50&offset=0", token=admin)
    data = _ok(env) or {}
    return list(data.get("items") or [])


def activity_titles() -> list[str]:
    return [f"SEED·活动·{i:02d}" for i in range(1, 21)]


def post_titles() -> list[str]:
    return [f"SEED·帖子·{i:02d}" for i in range(1, 13)]


def _activity_n(title: str) -> int | None:
    # SEED·活动·18 → 18
    if not title.startswith("SEED·活动·"):
        return None
    try:
        return int(title.rsplit("·", 1)[-1])
    except ValueError:
        return None


def _should_leave_pending_activity(title: str) -> bool:
    n = _activity_n(title)
    return n in PENDING_ACTIVITY_NS


def _should_leave_pending_post(key: str) -> bool:
    try:
        n = int(key.rsplit("·", 1)[-1])
    except ValueError:
        return False
    return n in PENDING_POST_NS


def ensure_demo_users(base: str, dry_run: bool) -> list[dict[str, Any]]:
    """Login 8 phones, set distinct profiles; return [{phone, token, user_id}, ...]."""
    users: list[dict[str, Any]] = []
    for i, phone in enumerate(SEED_PHONES):
        profile = DEMO_PROFILES[i]
        if dry_run:
            print(f"  dry-run user {phone} {profile['display_name']}")
            users.append({"phone": phone, "token": "", "user_id": ""})
            continue
        token = sms_login(base, phone)
        ensure_profile(base, token, profile)
        me = get_me(base, token)
        uid = str(me.get("id") or "")
        print(f"  user {phone} {profile['display_name']} -> {uid}")
        users.append({"phone": phone, "token": token, "user_id": uid})
    return users


def ensure_companions(base: str, users: list[dict], admin: str, dry_run: bool) -> None:
    now = datetime.now(timezone.utc)
    for idx in COMPANION_PHONE_INDEXES:
        u = users[idx]
        token = u["token"]
        phone = u["phone"]
        city = DEMO_PROFILES[idx]["city"]
        specialty = "线下陪玩·桌游" if idx == 1 else "户外摄影陪拍"
        if dry_run:
            print(f"  dry-run companion {phone}")
            continue
        existing = _ok(_req("GET", f"{base}/api/v1/me/companion-profile", token=token))
        status = (existing or {}).get("status") if existing else None
        if status != "active":
            if status != "pending":
                _ok(
                    _req(
                        "POST",
                        f"{base}/api/v1/companions/apply",
                        token=token,
                        body={
                            "service_type": "offline",
                            "specialty": specialty,
                            "intro": f"{DEMO_PROFILES[idx]['display_name']} · seed 陪玩入驻",
                            "city": city,
                            "response_time_minutes": 30,
                        },
                    )
                )
                print(f"  applied companion {phone}")
            _ok(
                _req(
                    "POST",
                    f"{base}/admin/v1/companions/{u['user_id']}/review",
                    token=admin,
                    body={"action": "approve"},
                )
            )
            print(f"  approved companion {phone}")
        else:
            print(f"  skip companion approve {phone}")

        profile = _ok(_req("GET", f"{base}/api/v1/me/companion-profile", token=token)) or {}
        services = list(profile.get("services") or [])
        if not services:
            _ok(
                _req(
                    "POST",
                    f"{base}/api/v1/me/companion-profile/services",
                    token=token,
                    body={
                        "title": f"SEED·服务·{phone[-2:]}",
                        "pricing_unit": "hour",
                        "price_cents": 9800 if idx == 1 else 12800,
                        "min_units": 1,
                        "description": "演示档服务，可删可重建。",
                        "sort_order": 0,
                        "active": True,
                    },
                )
            )
            print(f"  created service for {phone}")
        else:
            print(f"  skip service {phone} ({len(services)} existing)")

        slots = _ok(
            _req("GET", f"{base}/api/v1/companions/{u['user_id']}/slots", token=token)
        )
        slot_items = list((slots or {}).get("items") or [])
        open_future = [
            s
            for s in slot_items
            if s.get("status") == "open" and (s.get("start_at") or "") > now.isoformat()
        ]
        if len(open_future) >= 7:
            print(f"  skip slots {phone} ({len(open_future)} open)")
            continue
        for day in range(7):
            start = (now + timedelta(days=1 + day)).replace(
                hour=14, minute=0, second=0, microsecond=0
            )
            end = start + timedelta(hours=2)
            # Skip if an open slot already starts near this day
            day_key = start.date().isoformat()
            if any((s.get("start_at") or "")[:10] == day_key for s in open_future):
                continue
            _ok(
                _req(
                    "POST",
                    f"{base}/api/v1/me/companion-profile/slots",
                    token=token,
                    body={"start_at": start.isoformat(), "end_at": end.isoformat()},
                )
            )
        print(f"  ensured slots covering next 7 days for {phone}")


def ensure_activities(
    base: str, user: str, admin: str, dry_run: bool
) -> tuple[list[str], list[str]]:
    """Return (all_ids, published_ids). Activities 18–20 stay pending."""
    existing = {a.get("title"): a for a in list_admin_activities(base, admin)}
    ids: list[str] = []
    published_ids: list[str] = []
    now = datetime.now(timezone.utc)
    for i, title in enumerate(activity_titles()):
        n = i + 1
        leave_pending = _should_leave_pending_activity(title)
        hit = existing.get(title)
        if hit and hit.get("id"):
            aid = str(hit["id"])
            status = hit.get("status")
            if leave_pending:
                print(f"  leave pending {title} (status={status})")
            elif status != "published":
                if not dry_run:
                    _ok(
                        _req(
                            "POST",
                            f"{base}/admin/v1/activities/{aid}/review",
                            token=admin,
                            body={"action": "approve"},
                        )
                    )
                print(f"  approve existing {title}")
                status = "published"
            else:
                print(f"  skip {title}")
            ids.append(aid)
            if not leave_pending and status == "published":
                published_ids.append(aid)
            continue

        # Mix free / paid: odd → free, even → online_pay
        if n % 2 == 0:
            fee_type, fee_cents, fee_note = "online_pay", 2900 + (n * 100), "含场地"
        else:
            fee_type, fee_cents, fee_note = "free", 0, None
        start = now + timedelta(days=2 + (i % 14), hours=10)
        body: dict[str, Any] = {
            "title": title,
            "description": f"{title} · 冷启动活动，可删可重建。",
            "category": CATEGORIES[i % len(CATEGORIES)],
            "city": CITIES[i % len(CITIES)],
            "address": "市中心集合点",
            "capacity": 8 + (i % 6),
            "start_at": start.isoformat(),
            "media": [{"type": "image", "url": COVERS[i % len(COVERS)]}],
            "fee_type": fee_type,
            "fee_cents": fee_cents,
        }
        if fee_note:
            body["fee_note"] = fee_note
        if dry_run:
            print(f"  dry-run create {title} fee={fee_type}/{fee_cents}")
            continue
        created = _ok(_req("POST", f"{base}/api/v1/activities", token=user, body=body))
        aid = str(created["id"])
        if leave_pending:
            print(f"  created pending {title} -> {aid}")
        else:
            _ok(
                _req(
                    "POST",
                    f"{base}/admin/v1/activities/{aid}/review",
                    token=admin,
                    body={"action": "approve"},
                )
            )
            print(f"  created+approved {title} -> {aid}")
            published_ids.append(aid)
        ids.append(aid)
    # Reconcile published list from admin list for shelf safety
    if not dry_run:
        published_ids = []
        by_title = {a.get("title"): a for a in list_admin_activities(base, admin)}
        for title in activity_titles():
            hit = by_title.get(title)
            if not hit or not hit.get("id"):
                continue
            if _should_leave_pending_activity(title):
                continue
            if hit.get("status") == "published":
                published_ids.append(str(hit["id"]))
    return ids, published_ids


def ensure_posts(base: str, user: str, admin: str, dry_run: bool) -> list[str]:
    existing_posts = list_admin_posts(base, admin)
    by_key: dict[str, dict] = {}
    for p in existing_posts:
        content = p.get("content") or ""
        for key in post_titles():
            if key in content:
                by_key[key] = p
    ids: list[str] = []
    for i, key in enumerate(post_titles()):
        leave_pending = _should_leave_pending_post(key)
        hit = by_key.get(key)
        if hit and hit.get("id"):
            pid = str(hit["id"])
            status = hit.get("status")
            if leave_pending:
                print(f"  leave pending {key} (status={status})")
            elif status not in ("published", "approved", "active"):
                if not dry_run:
                    _ok(
                        _req(
                            "POST",
                            f"{base}/admin/v1/community/posts/{pid}/review",
                            token=admin,
                            body={"action": "approve"},
                        )
                    )
                print(f"  approve existing {key}")
            else:
                print(f"  skip {key}")
            ids.append(pid)
            continue
        body = {
            "content": f"{key} 周末约局分享，欢迎评论。",
            "media": [{"type": "image", "url": COVERS[(i + 1) % len(COVERS)]}],
        }
        if dry_run:
            print(f"  dry-run create {key}")
            continue
        created = _ok(_req("POST", f"{base}/api/v1/community/posts", token=user, body=body))
        pid = str(created["id"])
        if leave_pending:
            print(f"  created pending {key} -> {pid}")
        else:
            _ok(
                _req(
                    "POST",
                    f"{base}/admin/v1/community/posts/{pid}/review",
                    token=admin,
                    body={"action": "approve"},
                )
            )
            print(f"  created+approved {key} -> {pid}")
        ids.append(pid)
    return ids


def ensure_friendship_and_chat(base: str, users: list[dict], dry_run: bool) -> None:
    """User1 → friend-request → user2 accepts; open direct with preview (no message body API)."""
    if len(users) < 2 or dry_run:
        if dry_run:
            print("  dry-run friendship + direct conversation")
        return
    u1, u2 = users[0], users[1]
    friends = _ok(_req("GET", f"{base}/api/v1/friends", token=u1["token"])) or {}
    friend_ids = {str(f.get("user_id") or f.get("friend_user_id") or f.get("id") or "") for f in (friends.get("items") or [])}
    if u2["user_id"] in friend_ids:
        print("  skip friendship (already friends)")
    else:
        # Pending incoming on u2?
        incoming = _ok(
            _req("GET", f"{base}/api/v1/friend-requests?direction=incoming", token=u2["token"])
        ) or {}
        pending = None
        for req in incoming.get("items") or []:
            if str(req.get("from_user_id") or "") == u1["user_id"] and req.get("status") == "pending":
                pending = req
                break
        if pending is None:
            created = _ok(
                _req(
                    "POST",
                    f"{base}/api/v1/friend-requests",
                    token=u1["token"],
                    body={
                        "to_user_id": u2["user_id"],
                        "message": "SEED·你好，交个朋友",
                        "source": "seed",
                    },
                )
            )
            req_id = str((created or {}).get("id") or "")
            print(f"  friend-request {u1['phone']} → {u2['phone']} ({req_id})")
        else:
            req_id = str(pending.get("id") or "")
            print(f"  reuse pending friend-request {req_id}")
        if req_id:
            _ok(
                _req(
                    "POST",
                    f"{base}/api/v1/friend-requests/{req_id}/respond",
                    token=u2["token"],
                    body={"action": "accept"},
                )
            )
            print("  friend-request accepted")

    # Messaging API has no client "send text" — open_direct with preview leaves a short line.
    _ok(
        _req(
            "POST",
            f"{base}/api/v1/conversations/direct",
            token=u1["token"],
            body={
                "peer_user_id": u2["user_id"],
                "preview": "SEED·周末一起打球吗？",
            },
        )
    )
    print("  direct conversation + preview message")


def ensure_wallet_grants(base: str, users: list[dict], admin: str, dry_run: bool) -> None:
    """POST /admin/v1/wallet/grant only when current balance is 0."""
    for u in users:
        if dry_run:
            print(f"  dry-run wallet grant {u['phone']}")
            continue
        brief = _ok(_req("GET", f"{base}/api/v1/me/wallet", token=u["token"])) or {}
        balance = int(brief.get("balance_cents") or 0)
        if balance > 0:
            print(f"  skip wallet {u['phone']} balance={balance}")
            continue
        _ok(
            _req(
                "POST",
                f"{base}/admin/v1/wallet/grant",
                token=admin,
                body={
                    "user_id": u["user_id"],
                    "amount_cents": WALLET_GRANT_CENTS,
                    "title": "SEED·演示余额",
                },
            )
        )
        print(f"  granted {WALLET_GRANT_CENTS} cents to {u['phone']}")


def ensure_shelves(base: str, admin: str, published_ids: list[str], dry_run: bool) -> None:
    if not published_ids:
        print("  no published activities for shelves; skip")
        return
    existing = {s.get("title"): s for s in list_shelves(base, admin)}
    specs = [
        ("SEED·Hero", "hero", "本周精选", published_ids[:3]),
        ("SEED·周末精选", "rail", "周末好去处", published_ids[3:9]),
        ("SEED·附近好玩", "rail", "同城热门", published_ids[9:17]),
    ]
    for title, layout, subtitle, subject_ids in specs:
        shelf = existing.get(title)
        if shelf and shelf.get("id"):
            shelf_id = str(shelf["id"])
            print(f"  skip shelf {title}")
        else:
            body = {
                "title": title,
                "subtitle": subtitle,
                "layout": layout,
                "rule_type": "manual",
                "rule": {},
                "city_scope": [],
                "sort_order": 10 if layout == "hero" else 20,
                "enabled": True,
            }
            if dry_run:
                print(f"  dry-run shelf {title}")
                continue
            created = _ok(
                _req("POST", f"{base}/admin/v1/discover-shelves", token=admin, body=body)
            )
            shelf_id = str(created["id"])
            print(f"  created shelf {title} -> {shelf_id}")
        if dry_run:
            continue
        items_env = _ok(
            _req("GET", f"{base}/admin/v1/discover-shelves/{shelf_id}/items", token=admin)
        )
        items = list((items_env or {}).get("items") or [])
        if items:
            print(f"  shelf {title} already has {len(items)} items")
            continue
        for idx, sid in enumerate(subject_ids):
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
        print(f"  filled {title} with {len(subject_ids)} items")


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed browse/community demo content")
    parser.add_argument("--base", default="http://127.0.0.1:8000", help="API root")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    base = args.base.rstrip("/")

    print(f"== seed_content base={base} ==")
    print("== demo users ==")
    users = ensure_demo_users(base, args.dry_run)
    admin = "" if args.dry_run else admin_login(base)
    host_token = users[0]["token"] if users else ""

    print("== companions ==")
    ensure_companions(base, users, admin, args.dry_run)
    print("== activities ==")
    activity_ids, published_ids = ensure_activities(base, host_token, admin, args.dry_run)
    print("== posts ==")
    post_ids = ensure_posts(base, host_token, admin, args.dry_run)
    print("== friendship / chat ==")
    ensure_friendship_and_chat(base, users, args.dry_run)
    print("== wallet grants ==")
    ensure_wallet_grants(base, users, admin, args.dry_run)
    print("== shelves ==")
    ensure_shelves(base, admin, published_ids, args.dry_run)

    state = {
        "base": base,
        "phones": SEED_PHONES,
        "activity_ids": activity_ids,
        "published_activity_ids": published_ids,
        "post_ids": post_ids,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if not args.dry_run:
        STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"== wrote {STATE_PATH.name} ==")
    print(
        "SEED_CONTENT OK "
        f"users={len(users)} activities={len(activity_ids)} "
        f"published={len(published_ids)} posts={len(post_ids)}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"SEED_CONTENT FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
