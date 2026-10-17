"""DB-free asserts for clubs / reports / waitlist contracts."""

from app.main import app
from app.models import ActivityParticipant, Club, ClubMember, ConversationMember, Report
from app.modules.activity.service import _JOURNEY_FEEDBACK_KEYS, _JOURNEY_STEP_KEYS, _pick
from app.modules.clubs.service import CLUB_TOPICS, _clean_tags
from app.modules.safety.content_safety import TextVerdict
from app.modules.safety.service import ALLOWED_REASONS, REASON_ALIASES, TARGET_KINDS


def _paths() -> set[tuple[str, str]]:
    return {(m, r.path) for r in app.routes if hasattr(r, "methods") for m in r.methods}


def test_new_routes_registered():
    paths = _paths()
    for item in [
        ("GET", "/api/v1/clubs"),
        ("POST", "/api/v1/clubs"),
        ("DELETE", "/api/v1/clubs/{club_id}"),
        ("POST", "/api/v1/clubs/{club_id}/join"),
        ("POST", "/api/v1/clubs/{club_id}/leave"),
        ("GET", "/api/v1/clubs/{club_id}/members"),
        ("POST", "/api/v1/clubs/{club_id}/report"),
        ("GET", "/api/v1/guilds"),
        ("POST", "/api/v1/guilds/{guild_id}/chat"),
        ("GET", "/api/v1/me/reports"),
        ("POST", "/api/v1/conversations/{conversation_id}/clear"),
        ("POST", "/api/v1/conversations/{conversation_id}/dissolve"),
        ("POST", "/api/v1/conversations/{conversation_id}/messages/recall"),
        ("POST", "/api/v1/conversations/{conversation_id}/messages/edit"),
        ("POST", "/api/v1/activities/{activity_id}/waitlist"),
        ("GET", "/api/v1/activities/{activity_id}/my-status"),
        ("PUT", "/api/v1/activities/{activity_id}/journey"),
        ("GET", "/admin/v1/clubs"),
        ("POST", "/admin/v1/guilds"),
    ]:
        assert item in paths, item


def test_activity_mine_route_precedes_dynamic_id():
    order = [r.path for r in app.routes if getattr(r, "path", "").startswith("/api/v1/activities")]
    assert order.index("/api/v1/activities/mine") < order.index("/api/v1/activities/{activity_id}")


def test_report_aliases_map_to_valid_reasons():
    assert set(REASON_ALIASES.values()) <= ALLOWED_REASONS
    assert {"user", "post", "club", "guild", "conversation", "activity"} <= TARGET_KINDS


def test_report_target_user_nullable():
    assert Report.__table__.c.target_user_id.nullable
    assert "target_kind" in Report.__table__.c and "snapshot" in Report.__table__.c


def test_unique_membership_constraints():
    assert any(c.name == "uq_club_member" for c in ClubMember.__table__.constraints)
    assert "cleared_at" in ConversationMember.__table__.c
    assert {"note", "waitlisted_at"} <= set(ActivityParticipant.__table__.c.keys())
    assert Club.__table__.c.status.index


def test_club_tags_are_cleaned():
    assert _clean_tags([" 夜 骑 ", "夜骑", "", "a" * 30]) == ["夜骑", "a" * 10]
    assert len(_clean_tags([str(i) for i in range(20)])) == 6


def test_club_topics_match_android_enum():
    assert set(CLUB_TOPICS) == {"骑行", "户外", "运动", "美食", "玩乐", "娱乐", "咖啡", "徒步", "摄影", "羽毛球"}


def test_journey_payload_whitelist():
    steps = _pick({"marked_arrived": 1, "arrived_at": "1760000000000", "x": 1}, _JOURNEY_STEP_KEYS)
    assert steps == {"marked_arrived": True, "arrived_at": 1760000000000}
    fb = _pick({"feedback_highlight": "x" * 500, "recap_skipped": True}, _JOURNEY_FEEDBACK_KEYS)
    assert len(fb["feedback_highlight"]) == 200 and fb["recap_skipped"] is True


def test_text_verdict_flags():
    assert TextVerdict(action="block").blocked
    assert TextVerdict(action="review").needs_review
    assert not TextVerdict().blocked
