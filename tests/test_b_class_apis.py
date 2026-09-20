"""B-class API unit asserts (no DB)."""

from app.models import FeeType
from app.modules.activity.service import FEE_TYPES, _normalize_fee
from app.modules.user.schemas import SettingsUpdateRequest


def test_fee_type_values():
    assert FeeType.FREE.value == "free"
    assert FeeType.ONLINE_PAY.value == "online_pay"
    assert FeeType.AA_OFFLINE.value == "aa_offline"
    assert FEE_TYPES == {"free", "online_pay", "aa_offline"}


def test_normalize_fee_free_zeros_cents():
    ft, cents, note = _normalize_fee("free", 12000, "ignored")
    assert ft == "free"
    assert cents == 0
    assert note == "ignored"


def test_normalize_fee_invalid_falls_back():
    ft, cents, note = _normalize_fee("weird", 500, None)
    assert ft == "free"
    assert cents == 0
    assert note is None


def test_normalize_fee_online_pay():
    ft, cents, note = _normalize_fee("online_pay", 9900, "含保险")
    assert ft == "online_pay"
    assert cents == 9900
    assert note == "含保险"


def test_settings_update_schema_fields():
    body = SettingsUpdateRequest(youth_mode=True, notify_message=False)
    data = body.model_dump(exclude_unset=True)
    assert data["youth_mode"] is True
    assert data["notify_message"] is False
    assert "show_distance" not in data
