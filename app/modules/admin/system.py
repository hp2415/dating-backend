"""Admin: provider status + launch readiness checks (read-only)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.models import AdminUser
from app.modules.admin.deps import require_perm
from app.modules.auth.sms_provider import sms_status
from app.modules.media.storage import get_storage
from app.modules.messaging.provider import im_status
from app.modules.ops.push_provider import push_status
from app.modules.safety.content_safety import content_safety_status
from app.modules.trust.identity_provider import identity_status
from app.shared.config import settings
from app.shared.deps import get_request_id
from app.shared.geo_provider import geo_status
from app.shared.response import ok

router = APIRouter(prefix="/admin/v1/system", tags=["admin-system"])

_DEFAULT_JWT = "change-me-in-production-use-long-random-string"
_DEFAULT_ADMIN_JWT = "change-me-admin-jwt-secret"


def launch_checks() -> list[dict]:
    prod = settings.app_env == "production"
    items: list[dict] = []

    def add(key: str, level: str, ok_: bool, message: str) -> None:
        items.append({"key": key, "level": "ok" if ok_ else level, "message": message})

    add("env", "critical", prod, f"APP_ENV={settings.app_env}（上线应为 production）")
    add("jwt_secret", "critical", settings.jwt_secret != _DEFAULT_JWT, "JWT_SECRET 仍是默认值")
    add("admin_jwt_secret", "critical", settings.admin_jwt_secret != _DEFAULT_ADMIN_JWT, "ADMIN_JWT_SECRET 仍是默认值")
    add("admin_password", "critical", settings.admin_default_password != "Admin@123456", "管理员默认密码未修改")
    add("sms_dev_code", "critical", settings.sms_provider != "log" and not (prod and settings.sms_allow_dev_code),
        "短信仍为 log 通道，或生产环境仍允许固定验证码")
    add("payment", "critical", settings.payment_provider != "stub", "支付为演示 stub，订单不会真实收款")
    add("im", "warn", settings.im_provider != "noop", "云 IM 未接入（noop），聊天消息只在本机")
    add("push", "warn", settings.push_provider != "log", "厂商推送未接入，仅站内信")
    add("storage", "warn", settings.storage_driver == "oss", "媒体存放本机磁盘（建议 OSS + CDN）")
    add("cdn", "warn", bool(settings.cdn_base_url), "未配置 CDN_BASE_URL")
    add("identity", "warn", settings.identity_provider != "manual", "实名/人脸核验为人工审核")
    add("content_safety", "warn", settings.content_safety_provider != "local", "内容安全仅本地敏感词库")
    add("map", "warn", settings.map_provider != "none", "服务端地图/地理编码未接入")
    add("https", "critical", (settings.public_base_url or "").startswith("https://"), "PUBLIC_BASE_URL 非 https")
    add("icp", "critical", bool(settings.icp_record_no), "ICP 备案号未填写（ICP_RECORD_NO）")
    add("privacy", "critical", bool(settings.privacy_policy_url and settings.terms_url), "隐私政策 / 用户协议链接未配置")
    add("demo_seed", "warn", not (settings.seed_demo_users and prod), "生产环境仍开启演示用户种子（SEED_DEMO_USERS）")
    add("media_auto_approve", "warn", not settings.media_auto_approve, "媒体自动通过审核（MEDIA_AUTO_APPROVE=true）")
    return items


@router.get("/providers")
async def providers(request: Request, admin: AdminUser = Depends(require_perm("config:read"))):
    _ = admin
    storage = get_storage()
    data = {
        "env": settings.app_env,
        "sms": sms_status(),
        "im": im_status(),
        "push": push_status(),
        "identity": identity_status(),
        "map": geo_status(),
        "content_safety": content_safety_status(),
        "payment": {"provider": settings.payment_provider, "ready": settings.payment_provider != "stub", "real": settings.payment_provider != "stub"},
        "storage": {"driver": storage.name, "ready": True, "real": storage.name == "oss", "cdn": bool(settings.cdn_base_url)},
        "checks": launch_checks(),
    }
    return ok(data, request_id=get_request_id(request))
