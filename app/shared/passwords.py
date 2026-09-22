"""Password hashing for app accounts. Stdlib only (no extra image dependency)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re

_ALGO = "pbkdf2_sha256"
_ITERATIONS = 210_000
# Hashes written before the base64 format: salt is 32 hex chars used as UTF-8
# bytes, digest is 64 hex chars. Those rows still exist for the original admin.
_LEGACY_SALT = re.compile(r"^[0-9a-f]{32}$")
_LEGACY_DIGEST = re.compile(r"^[0-9a-f]{64}$")


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
        algo, iters, salt_part, hash_part = stored.split("$", 3)
        if algo != _ALGO:
            return False
        iterations = int(iters)
        if _LEGACY_SALT.fullmatch(salt_part) and _LEGACY_DIGEST.fullmatch(hash_part):
            digest_hex = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                salt_part.encode("utf-8"),
                iterations,
            ).hex()
            return hmac.compare_digest(digest_hex, hash_part)
        salt = base64.b64decode(salt_part)
        expected = base64.b64decode(hash_part)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(digest, expected)
    except Exception:
        return False
