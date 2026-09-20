from app.modules.admin.service import has_permission, permissions_for_role
from app.modules.messaging.provider import NoopImProvider, get_im_provider, im_status
from app.modules.messaging.uid import derive_public_uid
from uuid import uuid4


def test_im_provider_is_noop_by_default():
    provider = get_im_provider()
    assert isinstance(provider, NoopImProvider)
    status = im_status()
    assert status["provider"] == "noop"
    assert status["ready"] is False


def test_public_uid_is_nine_digits():
    uid = derive_public_uid(uuid4())
    assert len(uid) == 9
    assert uid.isdigit()


def test_support_has_chat_read():
    assert has_permission("support", "chat:read")
    assert has_permission("readonly", "chat:read")
    assert not has_permission("finance", "chat:read")
    assert "*" in permissions_for_role("superadmin")


def test_conversation_kind_enums():
    from app.models import ConversationKind, FriendRequestStatus, ChatTransferStatus, CallStatus

    assert ConversationKind.DIRECT.value == "direct"
    assert ConversationKind.ACTIVITY.value == "activity"
    assert FriendRequestStatus.PENDING.value == "pending"
    assert ChatTransferStatus.PENDING.value == "pending"
    assert CallStatus.RINGING.value == "ringing"
