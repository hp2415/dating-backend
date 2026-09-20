"""Unit tests for local media storage + SMS provider (no DB)."""

import pytest

from app.modules.auth.sms_provider import LogSmsProvider, get_sms_provider, sms_status
from app.modules.media.storage import LocalStorageDriver, safe_object_key, sniff_content_type, validate_upload_bytes


def test_safe_object_key_rejects_traversal():
    with pytest.raises(ValueError):
        safe_object_key("../etc/passwd")
    with pytest.raises(ValueError):
        safe_object_key("/abs/path")
    assert safe_object_key("avatar/u1/a.jpg") == "avatar/u1/a.jpg"


def test_sniff_jpeg_png_webp():
    assert sniff_content_type(b"\xff\xd8\xff\xe0rest") == "image/jpeg"
    assert sniff_content_type(b"\x89PNG\r\n\x1a\nrest") == "image/png"
    assert sniff_content_type(b"RIFF....WEBP....") == "image/webp"
    assert sniff_content_type(b"not-an-image") is None


def test_validate_upload_bytes_ok_and_mismatch():
    jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 20
    validate_upload_bytes(jpeg, "image/jpeg")
    with pytest.raises(ValueError, match="mismatch"):
        validate_upload_bytes(jpeg, "image/png")
    with pytest.raises(ValueError, match="empty"):
        validate_upload_bytes(b"", "image/jpeg")


def test_local_storage_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIA_LOCAL_ROOT", str(tmp_path))
    # Settings already loaded — construct driver with explicit root
    driver = LocalStorageDriver(root=str(tmp_path))
    key = "avatar/user1/test.jpg"
    data = b"\xff\xd8\xff\xe0" + b"\x00" * 32
    assert driver.exists(key) is False
    driver.save(key, data)
    assert driver.exists(key) is True
    assert (tmp_path / "avatar" / "user1" / "test.jpg").read_bytes() == data
    url = driver.public_url(key, public_base="http://example.com")
    assert url == "http://example.com/media/avatar/user1/test.jpg"
    driver.delete(key)
    assert driver.exists(key) is False


@pytest.mark.asyncio
async def test_log_sms_provider():
    provider = LogSmsProvider()
    result = await provider.send_code("13800138000", "123456")
    assert result["status"] == "sent"
    assert result["provider"] == "log"
    assert result["provider_msg_id"]


def test_get_sms_provider_default():
    p = get_sms_provider()
    assert p.name == "log"
    status = sms_status()
    assert "provider" in status
    assert "allow_dev_code" in status
