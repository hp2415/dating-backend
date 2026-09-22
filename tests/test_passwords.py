import hashlib

from app.shared.passwords import hash_password, verify_password


def _legacy_hash(password: str, salt_hex: str = "ab" * 16, iterations: int = 120_000) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt_hex.encode("utf-8"),
        iterations,
    ).hex()
    return f"pbkdf2_sha256${iterations}${salt_hex}${digest}"


def test_legacy_admin_hash_still_verifies():
    stored = _legacy_hash("Admin@123456")
    assert verify_password("Admin@123456", stored) is True
    assert verify_password("wrong-password", stored) is False


def test_current_hash_roundtrip():
    stored = hash_password("Admin@123456")
    assert stored.startswith("pbkdf2_sha256$210000$")
    assert verify_password("Admin@123456", stored) is True
    assert verify_password("Admin@123457", stored) is False
