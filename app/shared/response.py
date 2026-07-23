from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: int = 0
    message: str = "ok"
    data: Optional[T] = None
    request_id: Optional[str] = None


def ok(data: Any = None, message: str = "ok", request_id: str | None = None) -> dict[str, Any]:
    return {
        "code": 0,
        "message": message,
        "data": data,
        "request_id": request_id,
    }


def fail(code: int, message: str, data: Any = None, request_id: str | None = None) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "data": data,
        "request_id": request_id,
    }


class ErrorCodes:
    AUTH_INVALID = 10001
    AUTH_CODE_INVALID = 10002
    AUTH_CODE_EXPIRED = 10003
    AUTH_RATE_LIMIT = 10004
    AUTH_UNAUTHORIZED = 10005
    AUTH_TOKEN_INVALID = 10006
    AUTH_BANNED = 10007

    USER_NOT_FOUND = 20001
    USER_PROFILE_INVALID = 20002
    USER_UNDERAGE = 20003
    USER_NOT_COMPLETED = 20004

    MATCH_INVALID = 30001
    MATCH_LIMIT = 30002
    MATCH_NOT_FOUND = 30003
    MATCH_ALREADY = 30004
    SWIPE_DUPLICATE = 30005

    MEDIA_INVALID = 40001
    MEDIA_FORBIDDEN = 40002
    CHAT_FORBIDDEN = 40003
    CHAT_NOT_READY = 40004

    REPORT_INVALID = 50001
    REPORT_DUPLICATE = 50002
    REPORT_NOT_FOUND = 50003
    BLOCK_INVALID = 50004
    BLOCK_NOT_FOUND = 50005
    USER_LIMITED = 50006

    MODERATION_INVALID = 60001
    MODERATION_NOT_FOUND = 60002

    COMMUNITY_INVALID = 70001
    COMMUNITY_NOT_FOUND = 70002
    COMMUNITY_FORBIDDEN = 70003
    COMMUNITY_ALREADY_LIKED = 70004

    ACTIVITY_INVALID = 71001
    ACTIVITY_NOT_FOUND = 71002
    ACTIVITY_FORBIDDEN = 71003
    ACTIVITY_FULL = 71004
    ACTIVITY_ALREADY_JOINED = 71005

    ADMIN_UNAUTHORIZED = 80001
    ADMIN_FORBIDDEN = 80002
    ADMIN_INVALID_CREDENTIALS = 80003
    ADMIN_DISABLED = 80004

    SYSTEM_ERROR = 90001
    VALIDATION_ERROR = 90002
