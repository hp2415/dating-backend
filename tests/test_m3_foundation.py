from app.modules.admin.service import has_permission, permissions_for_role
from app.shared.pagination import legacy_admin_page, page_cursor, page_offset


def test_page_offset_shape():
    data = page_offset([{"id": 1}], total=5, limit=1, offset=0)
    assert data["page_info"]["total"] == 5
    assert data["page_info"]["has_more"] is True
    assert data["page_info"]["next_cursor"] is None


def test_page_cursor_shape():
    data = page_cursor([{"id": "a"}], limit=10, next_cursor="abc")
    assert data["page_info"]["next_cursor"] == "abc"
    assert data["page_info"]["has_more"] is True
    assert data["page_info"]["total"] is None


def test_legacy_admin_page_keeps_flat_fields():
    data = legacy_admin_page([1, 2], total=2, limit=20, offset=0)
    assert data["total"] == 2
    assert data["limit"] == 20
    assert data["offset"] == 0
    assert data["page_info"]["total"] == 2
    assert data["page_info"]["has_more"] is False


def test_superadmin_has_all_permissions():
    assert has_permission("superadmin", "order:refund", "config:write")
    assert "*" in permissions_for_role("superadmin")


def test_readonly_cannot_write_reports():
    assert has_permission("readonly", "report:read")
    assert not has_permission("readonly", "report:write")
    assert not has_permission("readonly", "activity:review")


def test_auditor_can_review_activity():
    assert has_permission("auditor", "activity:review", "media:review")
    assert not has_permission("auditor", "config:write")


def test_operator_can_enqueue_ops_events():
    assert has_permission("operator", "config:write", "dashboard:read")


def test_finance_role_can_refund():
    assert has_permission("finance", "order:refund", "order:read")
    assert not has_permission("readonly", "order:refund")


def test_order_kind_and_pay_method_enums():
    from app.models import OrderKind, PayMethod, OrderStatus

    assert OrderKind.WALLET_TOPUP.value == "wallet_topup"
    assert PayMethod.WECHAT.value == "wechat"
    assert OrderStatus.PENDING_PAYMENT.value == "pending_payment"


def test_stub_pay_methods_list():
    from app.modules.commerce.providers import list_pay_methods

    methods = {m["method"] for m in list_pay_methods()}
    assert methods == {"wallet", "wechat", "alipay", "apple_pay"}
    stubs = [m for m in list_pay_methods() if m["stub"]]
    assert len(stubs) == 3
