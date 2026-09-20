#!/usr/bin/env python3
"""Cold-start content seed (INTEGRATION_PLAN P0-5 / W4-3).

Creates ~16 activities + 4 community posts (SMS host + admin approve),
then 1 hero + 2 rail discover shelves with manual items.

Idempotent by stable titles (SEED·…); safe to re-run.
Does NOT run on app lifespan — invoke manually:

  python scripts/seed_content.py --base http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SEED_PHONE = "13900008801"
ADMIN_USER = "admin"
ADMIN_PASS = "Admin@123456"
STATE_PATH = Path(__file__).resolve().parent / ".seed_content_state.json"

CATEGORIES = ["sport", "food", "travel", "game", "study", "outdoors", "other", "sport"]
CITIES = ["上海", "成都", "杭州", "深圳", "北京", "南京", "苏州", "广州"]
COVERS = [
    "https://images.unsplash.com/photo-1476480862126-209bfaa8edc8?w=640",
    "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?w=640",
    "https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?w=640",
    "https://images.unsplash.com/photo-1529626455594-4ff0802cfb7e?w=640",
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


def ensure_profile(base: str, token: str) -> None:
    _ok(
        _req(
            "PUT",
            f"{base}/api/v1/me/profile",
            token=token,
            body={
                "display_name": "SEED主办",
                "birthday": "1995-06-15",
                "gender": "female",
                "city": "上海",
                "bio": "内容冷启动账号（seed_content）",
                "tags": ["羽毛球", "骑行", "火锅局"],
            },
        )
    )


def list_admin_activities(base: str, admin: str) -> list[dict]:
    env = _req("GET", f"{base}/admin/v1/activities?limit=100&offset=0", token=admin)
    data = _ok(env) or {}
    return list(data.get("items") or [])


def list_admin_posts(base: str, admin: str) -> list[dict]:
    env = _req("GET", f"{base}/admin/v1/community/posts?limit=100&offset=0", token=admin)
    data = _ok(env) or {}
    return list(data.get("items") or [])


def list_shelves(base: str, admin: str) -> list[dict]:
    env = _req("GET", f"{base}/admin/v1/discover-shelves?limit=50&offset=0", token=admin)
    data = _ok(env) or {}
    return list(data.get("items") or [])


def activity_titles() -> list[str]:
    return [f"SEED·活动·{i:02d}" for i in range(1, 17)]


def post_titles() -> list[str]:
    # posts use content; we embed the seed key in content for idempotency
    return [f"SEED·帖子·{i:02d}" for i in range(1, 5)]


def ensure_activities(base: str, user: str, admin: str, dry_run: bool) -> list[str]:
    existing = {a.get("title"): a for a in list_admin_activities(base, admin)}
    ids: list[str] = []
    now = datetime.now(timezone.utc)
    for i, title in enumerate(activity_titles()):
        hit = existing.get(title)
        if hit and hit.get("id"):
            aid = str(hit["id"])
            if hit.get("status") != "published":
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
            else:
                print(f"  skip {title}")
            ids.append(aid)
            continue
        start = now + timedelta(days=2 + i, hours=10)
        body = {
            "title": title,
            "description": f"{title} · 冷启动活动，可删可重建。",
            "category": CATEGORIES[i % len(CATEGORIES)],
            "city": CITIES[i % len(CITIES)],
            "address": "市中心集合点",
            "capacity": 8 + (i % 6),
            "start_at": start.isoformat(),
            "media": [{"type": "image", "url": COVERS[i % len(COVERS)]}],
        }
        if dry_run:
            print(f"  dry-run create {title}")
            continue
        created = _ok(_req("POST", f"{base}/api/v1/activities", token=user, body=body))
        aid = str(created["id"])
        _ok(
            _req(
                "POST",
                f"{base}/admin/v1/activities/{aid}/review",
                token=admin,
                body={"action": "approve"},
            )
        )
        print(f"  created+approved {title} -> {aid}")
        ids.append(aid)
    return ids


def ensure_posts(base: str, user: str, admin: str, dry_run: bool) -> list[str]:
    existing_posts = list_admin_posts(base, admin)
    by_key = {}
    for p in existing_posts:
        content = p.get("content") or ""
        for key in post_titles():
            if key in content:
                by_key[key] = p
    ids: list[str] = []
    for i, key in enumerate(post_titles()):
        hit = by_key.get(key)
        if hit and hit.get("id"):
            pid = str(hit["id"])
            if hit.get("status") not in ("published", "approved", "active"):
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


def ensure_shelves(base: str, admin: str, activity_ids: list[str], dry_run: bool) -> None:
    if not activity_ids:
        print("  no activities for shelves; skip")
        return
    existing = {s.get("title"): s for s in list_shelves(base, admin)}
    specs = [
        ("SEED·Hero", "hero", "本周精选", activity_ids[:3]),
        ("SEED·周末精选", "rail", "周末好去处", activity_ids[3:9]),
        ("SEED·附近好玩", "rail", "同城热门", activity_ids[9:16]),
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
        # Replace items only when shelf is new or empty
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
    parser = argparse.ArgumentParser(description="Seed browse/community cold-start content")
    parser.add_argument("--base", default="http://127.0.0.1:8000", help="API root")
    parser.add_argument("--phone", default=SEED_PHONE, help="SMS host phone")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    base = args.base.rstrip("/")

    print(f"== seed_content base={base} phone={args.phone} ==")
    user = sms_login(base, args.phone)
    ensure_profile(base, user)
    admin = admin_login(base)

    print("== activities ==")
    activity_ids = ensure_activities(base, user, admin, args.dry_run)
    print("== posts ==")
    post_ids = ensure_posts(base, user, admin, args.dry_run)
    print("== shelves ==")
    ensure_shelves(base, admin, activity_ids, args.dry_run)

    state = {
        "base": base,
        "phone": args.phone,
        "activity_ids": activity_ids,
        "post_ids": post_ids,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if not args.dry_run:
        STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"== wrote {STATE_PATH.name} ==")
    print("SEED_CONTENT OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"SEED_CONTENT FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
