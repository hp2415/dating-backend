"""Profile extras + follow contract unit asserts (no DB)."""

import pytest
from pydantic import ValidationError

from app.models import UserFollow, UserProfile
from app.modules.user.schemas import PROFILE_EXTRA_KEYS, ProfileUpdateRequest


def test_legacy_profile_payload_has_no_extras():
    body = ProfileUpdateRequest(display_name="A", city="上海")
    data = body.model_dump(exclude_unset=True)
    assert data == {"display_name": "A", "city": "上海"}
    assert not any(key in data for key in PROFILE_EXTRA_KEYS)


def test_explicit_null_extra_is_kept_for_clearing():
    data = ProfileUpdateRequest.model_validate({"mbti": None}).model_dump(exclude_unset=True)
    assert data == {"mbti": None}


def test_extras_accept_ios_raw_values():
    body = ProfileUpdateRequest(
        height_cm=170,
        weight_kg=60,
        occupation="自由职业",
        meet_radius="仅线上先聊",
        mbti="INTJ",
        zodiac="射手座",
    )
    assert body.zodiac == "射手座"


@pytest.mark.parametrize(
    "payload",
    [{"mbti": "XXXX"}, {"zodiac": "龙"}, {"occupation": "老板"}, {"height_cm": 20}, {"weight_kg": 999}],
)
def test_extras_reject_unknown_values(payload):
    with pytest.raises(ValidationError):
        ProfileUpdateRequest.model_validate(payload)


def test_profile_model_has_extra_columns():
    columns = set(UserProfile.__table__.columns.keys())
    assert set(PROFILE_EXTRA_KEYS) <= columns


def test_follow_pair_unique():
    names = {c.name for c in UserFollow.__table__.constraints}
    assert "uq_user_follows_pair" in names
