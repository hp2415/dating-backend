"""End-to-end flows for clubs / guilds / reports / waitlist / chat housekeeping (real Postgres)."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest


async def _publish_activity(host_id: str, capacity: int = 2) -> str:
    from app.models import Activity, ActivityParticipant
    from app.shared.db import SessionLocal

    aid = uuid4()
    async with SessionLocal() as db:
        db.add(Activity(id=aid, host_id=host_id, title="周末骑行", status="published", capacity=capacity,
                        join_count=1, start_at=datetime.now(timezone.utc) + timedelta(days=2)))
        await db.flush()
        db.add(ActivityParticipant(id=uuid4(), activity_id=aid, user_id=host_id, role="host", status="joined"))
        await db.commit()
    return str(aid)


async def test_club_lifecycle(client, make_user, admin_headers):
    cname = f"测试骑行社{uuid4().hex[:5]}"
    owner, bob = await make_user("社长"), await make_user("Bob")

    r = await client.post("/api/v1/clubs", headers=owner["h"],
                          json={"name": cname, "topic": "骑行", "city": "上海 · 黄浦", "summary": "每周三夜骑，欢迎新手", "tags": ["夜骑", "新手"]})
    assert r.status_code == 200, r.text
    club = r.json()["data"]
    assert club["is_creator"] and club["is_joined"] and club["member_count"] == 1
    cid = club["id"]
    # idempotent create with client id
    cl = str(uuid4())
    body = {"id": cl, "name": f"幂等社{uuid4().hex[:5]}", "topic": "咖啡", "summary": "咖啡爱好者每周交流分享", "city": "上海"}
    a1 = (await client.post("/api/v1/clubs", headers=owner["h"], json=body)).json()["data"]
    a2 = (await client.post("/api/v1/clubs", headers=owner["h"], json=body)).json()["data"]
    assert a1["id"] == a2["id"] == cl

    # validation + duplicate
    bad = await client.post("/api/v1/clubs", headers=owner["h"], json={"name": cname, "topic": "骑行", "summary": "每周三夜骑，欢迎新手"})
    assert bad.status_code == 409
    bad = await client.post("/api/v1/clubs", headers=owner["h"], json={"name": "短", "topic": "不存在", "summary": "x"})
    assert bad.status_code == 400

    # official seed present and listable / searchable
    r = await client.get("/api/v1/clubs", headers=bob["h"], params={"q": "夜骑"})
    names = [c["name"] for c in r.json()["data"]["items"]]
    assert cname in names and "黄浦夜骑群" in names

    # join / members / leave
    r = await client.post(f"/api/v1/clubs/{cid}/join", headers=bob["h"])
    assert r.json()["data"]["is_joined"] and r.json()["data"]["member_count"] == 2
    r = await client.get(f"/api/v1/clubs/{cid}/members", headers=bob["h"])
    assert r.json()["data"]["page_info"]["total"] == 2
    r = await client.post(f"/api/v1/clubs/{cid}/chat", headers=bob["h"])
    assert r.json()["data"]["kind"] == "circle"
    conv_id = r.json()["data"]["id"]
    r = await client.get("/api/v1/clubs", headers=bob["h"], params={"scope": "joined"})
    assert cid in [c["id"] for c in r.json()["data"]["items"]]
    r = await client.post(f"/api/v1/clubs/{cid}/leave", headers=bob["h"])
    assert not r.json()["data"]["is_joined"] and r.json()["data"]["member_count"] == 1
    r = await client.get(f"/api/v1/clubs/{cid}/members", headers=bob["h"])
    assert r.status_code == 403
    # creator cannot leave
    r = await client.post(f"/api/v1/clubs/{cid}/leave", headers=owner["h"])
    assert r.status_code == 409

    # report → ops queue (+ my reports)
    r = await client.post(f"/api/v1/clubs/{cid}/report", headers=bob["h"], json={"reason": "欺诈广告", "detail": "疑似拉人头"})
    assert r.status_code == 200, r.text
    dup = await client.post(f"/api/v1/clubs/{cid}/report", headers=bob["h"], json={"reason": "spam"})
    assert dup.status_code == 409
    mine = (await client.get("/api/v1/me/reports", headers=bob["h"])).json()["data"]["items"]
    assert mine[0]["target_kind"] == "club" and mine[0]["reason"] == "spam" and mine[0]["status"] == "pending"
    q = (await client.get("/admin/v1/reports", headers=admin_headers)).json()["data"]["items"]
    rep = next(i for i in q if i["target_id"] == cid)
    assert rep["target_title"] == cname
    r = await client.post(f"/admin/v1/reports/{rep['id']}/resolve", headers=admin_headers, json={"resolution": "takedown", "admin_note": "下架"})
    assert r.status_code == 200, r.text
    r = await client.get(f"/api/v1/clubs/{cid}", headers=bob["h"])
    assert r.status_code == 404  # hidden for others
    r = await client.get(f"/api/v1/clubs/{cid}", headers=owner["h"])
    assert r.json()["data"]["status"] == "hidden"

    # admin unhide then creator dissolves
    r = await client.post(f"/admin/v1/clubs/{cid}/action", headers=admin_headers, json={"action": "unhide"})
    assert r.json()["data"]["status"] == "active"
    r = await client.delete(f"/api/v1/clubs/{cid}", headers=bob["h"])
    assert r.status_code == 403
    r = await client.delete(f"/api/v1/clubs/{cid}", headers=owner["h"])
    assert r.json()["data"]["dissolved"]
    assert (await client.get(f"/api/v1/clubs/{cid}", headers=owner["h"])).status_code == 404
    _ = conv_id


async def test_activity_waitlist_note_and_journey(client, make_user):
    host, a, b = await make_user("发起人"), await make_user("甲"), await make_user("乙")
    aid = await _publish_activity(host["id"], capacity=2)

    # a joins with a note → friend request to host
    r = await client.post(f"/api/v1/activities/{aid}/join", headers=a["h"], json={"note": "你好，我是新手"})
    assert r.json()["data"]["joined"] and r.json()["data"]["friend_request_sent"]
    reqs = (await client.get("/api/v1/friend-requests", headers=host["h"], params={"direction": "received"})).json()["data"]["items"]
    assert any(x["from_user_id"] == a["id"] and x["source"] == "activity" for x in reqs)

    # full → plain join 409, waitlist works
    r = await client.post(f"/api/v1/activities/{aid}/join", headers=b["h"])
    assert r.status_code == 409
    r = await client.post(f"/api/v1/activities/{aid}/waitlist", headers=b["h"])
    assert r.json()["data"] == {"waitlisted": True, "position": 1, "join_count": 2}
    st = (await client.get(f"/api/v1/activities/{aid}/my-status", headers=b["h"])).json()["data"]
    assert st["status"] == "waitlisted" and st["waitlist_position"] == 1
    mine = (await client.get("/api/v1/activities/mine", headers=b["h"], params={"status": "waitlisted"})).json()["data"]["items"]
    assert [i["id"] for i in mine] == [aid]

    # journey is participants-only
    assert (await client.get(f"/api/v1/activities/{aid}/journey", headers=b["h"])).status_code == 403
    r = await client.put(f"/api/v1/activities/{aid}/journey", headers=a["h"],
                         json={"steps": {"marked_arrived": True, "arrived_at": 1760000000000, "evil": 1}, "feedback": {"feedback_highlight": "好玩"}})
    d = r.json()["data"]
    assert d["steps"] == {"marked_arrived": True, "arrived_at": 1760000000000} and d["feedback"]["feedback_highlight"] == "好玩"

    # a quits → b is promoted automatically, a leaves the activity group
    r = await client.delete(f"/api/v1/activities/{aid}/join", headers=a["h"])
    assert r.json()["data"]["join_count"] == 2
    st = (await client.get(f"/api/v1/activities/{aid}/my-status", headers=b["h"])).json()["data"]
    assert st["status"] == "joined"
    st = (await client.get(f"/api/v1/activities/{aid}/my-status", headers=a["h"])).json()["data"]
    assert st["status"] == "quit"


async def test_waitlist_leave_and_capacity_increase(client, make_user):
    host, a, b = await make_user("H"), await make_user("A"), await make_user("B")
    aid = await _publish_activity(host["id"], capacity=2)
    await client.post(f"/api/v1/activities/{aid}/join", headers=a["h"])
    await client.post(f"/api/v1/activities/{aid}/waitlist", headers=b["h"])
    r = await client.delete(f"/api/v1/activities/{aid}/waitlist", headers=b["h"])
    assert r.json()["data"]["waitlisted"] is False
    await client.post(f"/api/v1/activities/{aid}/waitlist", headers=b["h"])
    r = await client.put(f"/api/v1/activities/{aid}", headers=host["h"], json={"capacity": 5})
    assert r.status_code == 200
    st = (await client.get(f"/api/v1/activities/{aid}/my-status", headers=b["h"])).json()["data"]
    assert st["status"] == "joined"


async def test_chat_housekeeping(client, make_user):
    owner, m1, m2 = await make_user("群主"), await make_user("成员1"), await make_user("成员2")
    r = await client.post("/api/v1/conversations/group", headers=owner["h"],
                          json={"title": "测试群", "member_ids": [m1["id"], m2["id"]]})
    cid = r.json()["data"]["id"]

    r = await client.post(f"/api/v1/conversations/{cid}/clear", headers=m1["h"])
    assert r.json()["data"]["cleared_at"]
    assert (await client.get(f"/api/v1/conversations/{cid}", headers=m1["h"])).json()["data"]["cleared_at"]
    assert (await client.get(f"/api/v1/conversations/{cid}", headers=m2["h"])).json()["data"]["cleared_at"] is None

    now = datetime.now(timezone.utc)
    r = await client.post(f"/api/v1/conversations/{cid}/messages/recall", headers=m1["h"],
                          json={"message_id": "m-1", "sent_at": (now - timedelta(seconds=30)).isoformat()})
    assert r.status_code == 200
    r = await client.post(f"/api/v1/conversations/{cid}/messages/recall", headers=m1["h"],
                          json={"message_id": "m-2", "sent_at": (now - timedelta(minutes=10)).isoformat()})
    assert r.status_code == 400
    r = await client.post(f"/api/v1/conversations/{cid}/messages/edit", headers=m1["h"],
                          json={"message_id": "m-3", "body": "改好了", "sent_at": (now - timedelta(minutes=5)).isoformat()})
    assert r.status_code == 200

    # non-owner cannot dissolve; owner leaving transfers ownership; last owner leaving closes group
    assert (await client.post(f"/api/v1/conversations/{cid}/dissolve", headers=m1["h"])).status_code == 403
    await client.delete(f"/api/v1/conversations/{cid}/members/me", headers=owner["h"])
    brief = (await client.get(f"/api/v1/conversations/{cid}", headers=m1["h"])).json()["data"]
    assert brief["owner_id"] in {m1["id"], m2["id"]}
    new_owner = m1 if brief["owner_id"] == m1["id"] else m2
    r = await client.post(f"/api/v1/conversations/{cid}/dissolve", headers=new_owner["h"])
    assert r.json()["data"]["dissolved"]
    assert (await client.get(f"/api/v1/conversations/{cid}", headers=m1["h"])).status_code == 404


async def test_guilds_and_generic_reports(client, make_user, admin_headers):
    u = await make_user("用户")
    items = (await client.get("/api/v1/guilds", headers=u["h"], params={"city": "上海"})).json()["data"]["items"]
    assert len(items) >= 5
    gid = items[0]["id"]
    r = await client.post(f"/api/v1/guilds/{gid}/follow", headers=u["h"])
    assert r.json()["data"]["is_followed"]
    r = await client.delete(f"/api/v1/guilds/{gid}/follow", headers=u["h"])
    assert not r.json()["data"]["is_followed"]
    r = await client.post(f"/api/v1/guilds/{gid}/chat", headers=u["h"])
    conv = r.json()["data"]
    again = (await client.post(f"/api/v1/guilds/{gid}/chat", headers=u["h"])).json()["data"]
    assert conv["id"] == again["id"]

    # generic reports: unknown/local targets are still recorded, bad kind rejected
    r = await client.post("/api/v1/reports", headers=u["h"],
                          json={"target_kind": "post", "target_id": str(uuid4()), "title": "某动态", "reason": "色情低俗"})
    assert r.status_code == 200 and r.json()["data"]["reason"] == "inappropriate"
    rid = str(uuid4())
    body = {"id": rid, "target_kind": "conversation", "target_id": str(uuid4()), "title": "某会话", "reason": "骚扰辱骂"}
    r1 = await client.post("/api/v1/reports", headers=u["h"], json=body)
    r2 = await client.post("/api/v1/reports", headers=u["h"], json=body)
    assert r1.json()["data"]["id"] == r2.json()["data"]["id"] == rid
    mine = (await client.get("/api/v1/me/reports", headers=u["h"])).json()["data"]["items"]
    assert rid in [m["id"] for m in mine]
    r = await client.post("/api/v1/reports", headers=u["h"], json={"target_kind": "bogus", "target_id": "x", "reason": "spam"})
    assert r.status_code == 400
    r = await client.post("/api/v1/reports", headers=u["h"], json={"target_user_id": u["id"], "reason": "spam"})
    assert r.status_code == 400  # cannot report self

    # admin guild CRUD
    r = await client.post("/admin/v1/guilds", headers=admin_headers, json={"name": "新工会", "specialty": "测试", "city": "上海 · 黄浦", "price_from_cents": 9900})
    assert r.status_code == 200, r.text
    new_id = r.json()["data"]["id"]
    r = await client.put(f"/admin/v1/guilds/{new_id}", headers=admin_headers, json={"status": "hidden"})
    assert r.json()["data"]["status"] == "hidden"
    assert (await client.get(f"/api/v1/guilds/{new_id}", headers=u["h"])).status_code == 404
