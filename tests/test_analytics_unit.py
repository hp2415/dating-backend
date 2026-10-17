from datetime import datetime, timedelta, timezone

from app.modules.admin.analytics import mask_event_row, pseudonym
from app.modules.analytics.aggregate import funnel_sql
from app.modules.analytics.service import correct_time, sanitize_props
from app.modules.analytics.taxonomy import EVENT_NAME_RE, EVENTS, FUNNELS, OBJECT_TYPES, PROP_KEY_RE


def test_catalogue_is_consistent():
    for name, d in EVENTS.items():
        assert EVENT_NAME_RE.match(name), name
        for key in d.props:
            assert PROP_KEY_RE.match(key), (name, key)
        if d.object_type:
            assert d.object_type in OBJECT_TYPES
    for key, (_, steps) in FUNNELS.items():
        for s in steps:
            assert s.event in EVENTS, (key, s.event)


def test_sanitize_props_drops_pii_and_scrubs_values():
    clean, dropped = sanitize_props(
        {"phone": "13800138000", "reason": "call me 13800138000 or a@b.com", "n": 3, "nested": {"a": 1}, "Bad-Key": 1,
         "query": "骑行", "token": "x", "ok": True}
    )
    assert "phone" not in clean and "token" not in clean and "nested" not in clean and "Bad-Key" not in clean
    assert clean["reason"] == "call me [phone] or [email]"
    assert clean["n"] == 3 and clean["ok"] is True and clean["query"] == "骑行"
    assert dropped == 4


def test_correct_time_handles_wrong_device_clock():
    now = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)
    # device clock is 1h behind: it thinks "now" is 11:00 and the event happened 5s earlier
    sent = now - timedelta(hours=1)
    corrected, skew, bad = correct_time(sent - timedelta(seconds=5), sent_at=sent, now=now)
    assert bad is None and corrected == now - timedelta(seconds=5) and skew == 3_600_000
    # no sent_at: raw timestamp, too old is rejected
    _, _, bad = correct_time(now - timedelta(days=30), sent_at=None, now=now)
    assert bad == "too_old"
    # far future is clamped to now
    corrected, _, bad = correct_time(now + timedelta(days=2), sent_at=None, now=now)
    assert bad is None and corrected == now


def test_funnel_sql_shape():
    sql, params = funnel_sql(FUNNELS["activity_join"][1])
    assert sql.count("JOIN s") == 5 and params["o0"] == "activity" and "ORDER BY idx" in sql


def test_masking():
    row = {"user_id": "8f7c1b0e-0000-4000-8000-000000000001", "anon_id": "abcdef", "ip_hash": "h", "event_name": "x"}
    masked = mask_event_row(row, unmasked=False)
    assert masked["user_id"] == pseudonym(row["user_id"], "u") and masked["user_id"].startswith("u_")
    assert masked["anon_id"].startswith("d_") and "ip_hash" not in masked
    assert mask_event_row(row, unmasked=True) == row
