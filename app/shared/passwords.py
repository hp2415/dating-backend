"""Password hashing for app accounts. Stdlib only (no extra image dependency)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os

_ALGO = "pbkdf2_sha256"
_ITERATIONS = 210_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return (
        f"{_ALGO}${_ITERATIONS}"
        f"${base64.b64encode(salt).decode('ascii')}"
        f"${base64.b64encode(digest).decode('ascii')}"
    )


def verify_password(password: str, stored: str | None) -> bool:
    if not password or not stored:
        return False
    try:
        algo, iters, salt_b64, hash_b64 = stored.split("$", 3)
        if algo != _ALGO:
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iters))
        return hmac.compare_digest(digest, expected)
    except Exception:
        return False
