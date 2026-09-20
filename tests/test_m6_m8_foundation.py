"""M6–M8 foundation enum / seed unit asserts (no DB)."""

from app.models import BookingStatus, TaxonomyKind, TrustLevel
from app.modules.ops.seed import default_taxonomy_seed_codes
from app.shared.response import ErrorCodes


def test_booking_status_values():
    assert BookingStatus.PENDING_CONFIRM.value == "pending_confirm"
    assert BookingStatus.AWAITING_PAYMENT.value == "awaiting_payment"
    assert BookingStatus.PAID.value == "paid"
    assert BookingStatus.IN_PROGRESS.value == "in_progress"
    assert BookingStatus.COMPLETED.value == "completed"
    assert BookingStatus.CANCELLED.value == "cancelled"
    assert BookingStatus.REFUNDED.value == "refunded"


def test_trust_level_values():
    assert TrustLevel.GUEST.value == "guest"
    assert TrustLevel.NEWCOMER.value == "newcomer"
    assert TrustLevel.TRUSTED.value == "trusted"
    assert TrustLevel.RELIABLE_HOST.value == "reliable_host"
    assert TrustLevel.RESTRICTED.value == "restricted"


def test_taxonomy_kind_values():
    assert TaxonomyKind.ACTIVITY_CATEGORY.value == "activity_category"
    assert TaxonomyKind.INTEREST.value == "interest"
    assert TaxonomyKind.CITY.value == "city"
    assert TaxonomyKind.COMPANION_SPECIALTY.value == "companion_specialty"


def test_default_taxonomy_seed_codes():
    codes = default_taxonomy_seed_codes()
    assert "hiking" in codes
    assert "camping" in codes
    assert "sports" in codes
    assert "food" in codes
    assert "other" in codes
    assert "outdoors" in codes
    assert "shanghai" in codes
    assert len(codes) >= 10


def test_m6_m8_error_codes_exist():
    assert ErrorCodes.BOOKING_NOT_FOUND == 73006
    assert ErrorCodes.TRUST_INVALID == 74001
    assert ErrorCodes.OPS_NOT_FOUND == 75002
    assert ErrorCodes.TAXONOMY_INVALID == 75003
    assert ErrorCodes.NOTIFICATION_NOT_FOUND == 75004
