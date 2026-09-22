"""Tencent Cloud IM UserSig (TLSSigAPIv2) — mirrors official sample, no extra package."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import zlib


def gen_user_sig(*, sdk_app_id: int, secret_key: str, user_id: str, expire_seconds: int) -> str:
    if sdk_app_id <= 0 or not secret_key or not user_id:
        raise ValueError("sdk_app_id / secret_key / user_id required for UserSig")

    curr_time = int(time.time())
    raw_to_sign = (
        f"TLS.identifier:{user_id}\n"
        f"TLS.sdkappid:{sdk_app_id}\n"
        f"TLS.time:{curr_time}\n"
        f"TLS.expire:{expire_seconds}\n"
    )
    sig = base64.b64encode(
        hmac.new(secret_key.encode("utf-8"), raw_to_sign.encode("utf-8"), hashlib.sha256).digest()
    ).decode("utf-8")

    payload = {
        "TLS.ver": "2.0",
        "TLS.identifier": str(user_id),
        "TLS.sdkappid": int(sdk_app_id),
        "TLS.expire": int(expire_seconds),
        "TLS.time": int(curr_time),
        "TLS.sig": sig,
    }
    compressed = zlib.compress(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    return (
        base64.b64encode(compressed)
        .decode("utf-8")
        .replace("+", "*")
        .replace("/", "-")
        .replace("=", "_")
    )
