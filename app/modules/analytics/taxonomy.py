"""Single source of truth for the analytics event catalogue.

Naming: ``<domain>.<object>_<action>`` — lowercase snake_case, action is a past-tense verb
(``activity.join_clicked``, ``club.detail_viewed``). Domains: app, auth, page, item, ui, search,
activity, buddy, companion, club, guild, community, message, profile, commerce, safety, trust,
perf, error, push, consent.

``docs/ANALYTICS_EVENTS.md`` and the Android ``AnalyticsEvents.kt`` constants are generated from
this file by ``scripts/gen_analytics_catalog.py`` — edit here, regenerate, never hand-edit those.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

SCHEMA_VERSION = 2
MIN_SUPPORTED_SCHEMA = 1

EVENT_NAME_RE = re.compile(r"^[a-z][a-z0-9]*\.[a-z][a-z0-9_]*$")
PROP_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")

OBJECT_TYPES = ("activity", "club", "guild", "post", "companion", "shelf")

# Categories
LIFECYCLE, PAGE, EXPOSURE, CLICK, SEARCH, FUNNEL, PERF, ERROR, PUSH, CONSENT = (
    "lifecycle", "page", "exposure", "click", "search", "funnel", "perf", "error", "push", "consent",
)

# Per-object conversion stages (used by the aggregation job)
STAGE_EXPOSURE, STAGE_CLICK, STAGE_DETAIL, STAGE_CONVERT, STAGE_PAY = "exposure", "click", "detail", "convert", "pay"


@dataclass(frozen=True)
class EventDef:
    name: str
    category: str
    desc: str
    props: dict[str, str] = field(default_factory=dict)
    stage: str | None = None
    object_type: str | None = None  # default object type when the event concerns one object


def _e(name, category, desc, props=None, stage=None, object_type=None) -> EventDef:
    return EventDef(name, category, desc, props or {}, stage, object_type)


_EVENT_LIST: list[EventDef] = [
    # ── lifecycle ──
    _e("app.launched", LIFECYCLE, "进程启动后首个页面可交互", {"cold_start": "bool"}),
    _e("app.foregrounded", LIFECYCLE, "回到前台"),
    _e("app.backgrounded", LIFECYCLE, "进入后台（会话前台时长）", {"duration_ms": "int"}),
    _e("consent.changed", CONSENT, "用户修改数据收集授权", {"analytics": "bool", "personalized": "bool"}),
    # ── generic page / exposure / click ──
    _e("page.viewed", PAGE, "页面曝光（screen/referrer 在公共属性里）", {"tab": "str"}),
    _e("page.left", PAGE, "页面离开，带停留时长", {"duration_ms": "int"}),
    _e("item.exposed", EXPOSURE, "列表项曝光（≥50% 可见 ≥500ms，每会话每对象去重）", {"list_id": "str", "position": "int"}, STAGE_EXPOSURE),
    _e("item.clicked", CLICK, "列表项点击", {"list_id": "str", "position": "int"}, STAGE_CLICK),
    _e("ui.clicked", CLICK, "通用按钮点击", {"element_id": "str"}),
    # ── search ──
    _e("search.submitted", SEARCH, "提交搜索", {"scope": "str", "query": "str<=24", "query_len": "int", "result_count": "int"}),
    _e("search.result_clicked", SEARCH, "点击搜索结果", {"scope": "str", "position": "int"}, STAGE_CLICK),
    # ── auth ──
    _e("auth.login_viewed", FUNNEL, "登录页展示"),
    _e("auth.sms_requested", FUNNEL, "请求验证码"),
    _e("auth.login_succeeded", FUNNEL, "登录成功", {"is_new_user": "bool"}),
    _e("auth.login_failed", FUNNEL, "登录失败", {"reason": "str"}),
    _e("auth.onboarding_completed", FUNNEL, "完成引导"),
    _e("auth.logged_out", FUNNEL, "退出登录"),
    _e("auth.welcome_dismissed", FUNNEL, "关闭欢迎引导", {"skipped": "bool", "intent": "str"}),
    # ── activity ──
    _e("activity.feed_viewed", FUNNEL, "活动 Tab 展示", {"shelf_count": "int"}),
    _e("activity.card_clicked", CLICK, "活动卡片点击", {}, STAGE_CLICK, "activity"),
    _e("activity.detail_viewed", FUNNEL, "活动详情展示", {}, STAGE_DETAIL, "activity"),
    _e("activity.join_clicked", FUNNEL, "点击参加", {"paid": "bool"}, None, "activity"),
    _e("activity.join_succeeded", FUNNEL, "报名成功", {"waitlisted": "bool"}, STAGE_CONVERT, "activity"),
    _e("activity.join_failed", FUNNEL, "报名失败", {"reason": "str"}, None, "activity"),
    _e("activity.waitlist_joined", FUNNEL, "加入候补", {}, None, "activity"),
    _e("activity.waitlist_left", FUNNEL, "退出候补", {}, None, "activity"),
    _e("activity.favorited", CLICK, "收藏活动", {}, None, "activity"),
    _e("activity.compose_opened", FUNNEL, "打开发布活动"),
    _e("activity.published", FUNNEL, "发布活动", {}, None, "activity"),
    _e("activity.cancelled", FUNNEL, "取消活动/报名", {}, None, "activity"),
    # ── buddy ──
    _e("buddy.feed_viewed", FUNNEL, "找人玩页展示"),
    _e("buddy.detail_viewed", FUNNEL, "搭子详情展示"),
    _e("buddy.greet_sent", FUNNEL, "打招呼"),
    _e("buddy.invite_sent", FUNNEL, "发出邀约"),
    _e("buddy.invite_responded", FUNNEL, "回应邀约", {"accepted": "bool"}),
    # ── companion ──
    _e("companion.list_viewed", FUNNEL, "陪玩列表展示"),
    _e("companion.detail_viewed", FUNNEL, "陪玩详情展示", {}, STAGE_DETAIL, "companion"),
    _e("companion.slot_selected", FUNNEL, "选择档期", {}, None, "companion"),
    _e("companion.booking_created", FUNNEL, "创建预约", {}, STAGE_CONVERT, "companion"),
    _e("companion.booking_completed", FUNNEL, "预约完成", {}, None, "companion"),
    _e("companion.review_submitted", FUNNEL, "提交评价", {}, None, "companion"),
    # ── club / guild ──
    _e("club.feed_viewed", FUNNEL, "俱乐部列表展示"),
    _e("club.detail_viewed", FUNNEL, "俱乐部详情展示", {}, STAGE_DETAIL, "club"),
    _e("club.join_clicked", FUNNEL, "点击加入俱乐部", {}, None, "club"),
    _e("club.join_succeeded", FUNNEL, "加入俱乐部成功", {}, STAGE_CONVERT, "club"),
    _e("club.left", FUNNEL, "退出俱乐部", {}, None, "club"),
    _e("club.created", FUNNEL, "创建俱乐部", {"topic": "str"}, None, "club"),
    _e("club.report_submitted", FUNNEL, "举报俱乐部", {}, None, "club"),
    _e("guild.detail_viewed", FUNNEL, "工会详情展示", {}, STAGE_DETAIL, "guild"),
    _e("guild.followed", FUNNEL, "关注工会", {}, STAGE_CONVERT, "guild"),
    # ── community ──
    _e("community.feed_viewed", FUNNEL, "广场展示"),
    _e("community.filter_selected", CLICK, "切换广场筛选", {"filter": "str"}),
    _e("community.post_viewed", FUNNEL, "动态详情展示", {}, STAGE_DETAIL, "post"),
    _e("community.post_liked", FUNNEL, "点赞动态", {}, STAGE_CONVERT, "post"),
    _e("community.compose_opened", FUNNEL, "打开发布动态"),
    _e("community.post_published", FUNNEL, "发布动态", {}, None, "post"),
    # ── message / profile ──
    _e("message.inbox_viewed", FUNNEL, "消息列表展示"),
    _e("message.conversation_opened", FUNNEL, "打开会话", {"kind": "str"}),
    _e("message.sent", FUNNEL, "发送消息（不含内容）", {"kind": "str"}),
    _e("message.friend_request_sent", FUNNEL, "发送好友申请"),
    _e("message.friend_request_responded", FUNNEL, "回应好友申请", {"accepted": "bool"}),
    _e("profile.viewed", FUNNEL, "我的页展示"),
    _e("profile.followed", FUNNEL, "关注用户"),
    _e("profile.unfollowed", FUNNEL, "取消关注"),
    # ── commerce ──
    _e("commerce.order_created", FUNNEL, "创建订单", {"kind": "str", "amount_cents": "int"}, None),
    _e("commerce.pay_method_selected", FUNNEL, "选择支付方式", {"method": "str"}),
    _e("commerce.pay_succeeded", FUNNEL, "支付成功", {"method": "str", "amount_cents": "int", "kind": "str"}, STAGE_PAY),
    _e("commerce.pay_failed", FUNNEL, "支付失败", {"method": "str", "reason": "str"}),
    _e("commerce.topup_succeeded", FUNNEL, "钱包充值成功", {"method": "str", "amount_cents": "int"}),
    _e("commerce.topup_failed", FUNNEL, "钱包充值失败", {"method": "str", "reason": "str"}),
    # ── safety / trust ──
    _e("safety.report_submitted", FUNNEL, "提交举报", {"target_kind": "str", "reason": "str"}),
    _e("safety.block_submitted", FUNNEL, "拉黑用户"),
    _e("trust.safety_checkin_submitted", FUNNEL, "提交安全报平安"),
    # ── perf ──
    _e("perf.cold_start", PERF, "冷启动到首屏可交互耗时", {"duration_ms": "int"}),
    _e("perf.screen_rendered", PERF, "页面首次渲染耗时", {"screen": "str", "duration_ms": "int"}),
    _e("perf.frame_stats", PERF, "页面掉帧统计（离开页面时上报）", {"frames": "int", "slow_frames": "int", "frozen_frames": "int", "janky_pct": "float"}),
    _e("perf.api_latency", PERF, "接口耗时（采样）", {"path": "str", "status": "int", "duration_ms": "int"}),
    # ── error ──
    _e("error.api_failed", ERROR, "接口失败", {"path": "str", "status": "int", "code": "int"}),
    _e("error.crash", ERROR, "未捕获异常（下次启动补报）", {"exception": "str", "top_frame": "str", "fatal": "bool"}),
    _e("error.ui_failed", ERROR, "界面级错误（降级展示）", {"where": "str", "exception": "str"}),
    # ── push ──
    _e("push.received", PUSH, "收到推送", {"campaign_id": "str"}),
    _e("push.opened", PUSH, "点击推送打开应用", {"campaign_id": "str", "deep_link_type": "str"}),
]

EVENTS: dict[str, EventDef] = {e.name: e for e in _EVENT_LIST}


@dataclass(frozen=True)
class FunnelStep:
    event: str
    object_type: str | None = None


FUNNELS: dict[str, tuple[str, list[FunnelStep]]] = {
    "core": (
        "核心转化",
        [
            FunnelStep("app.launched"),
            FunnelStep("auth.login_succeeded"),
            FunnelStep("activity.detail_viewed"),
            FunnelStep("activity.join_succeeded"),
            FunnelStep("commerce.pay_succeeded"),
        ],
    ),
    "activity_join": (
        "活动 浏览→详情→报名→支付",
        [
            FunnelStep("item.exposed", "activity"),
            FunnelStep("item.clicked", "activity"),
            FunnelStep("activity.detail_viewed"),
            FunnelStep("activity.join_clicked"),
            FunnelStep("activity.join_succeeded"),
            FunnelStep("commerce.pay_succeeded"),
        ],
    ),
    "companion_booking": (
        "陪玩 列表→详情→选档→预约→支付",
        [
            FunnelStep("companion.list_viewed"),
            FunnelStep("companion.detail_viewed"),
            FunnelStep("companion.slot_selected"),
            FunnelStep("companion.booking_created"),
            FunnelStep("commerce.pay_succeeded"),
        ],
    ),
    "club_join": (
        "俱乐部 列表→详情→加入",
        [
            FunnelStep("club.feed_viewed"),
            FunnelStep("club.detail_viewed"),
            FunnelStep("club.join_clicked"),
            FunnelStep("club.join_succeeded"),
        ],
    ),
    "community_engage": (
        "广场 浏览→详情→点赞",
        [
            FunnelStep("community.feed_viewed"),
            FunnelStep("community.post_viewed"),
            FunnelStep("community.post_liked"),
        ],
    ),
}

# Events whose first-occurrence defines "feature used" for the feature-usage board.
FEATURE_EVENTS = (
    "activity.join_succeeded", "activity.published", "buddy.greet_sent", "buddy.invite_sent",
    "companion.booking_created", "club.join_succeeded", "club.created", "community.post_published",
    "community.post_liked", "message.sent", "search.submitted", "commerce.pay_succeeded",
)

# Client-visible runtime configuration (sampling / kill switch). Static defaults; env overrides in config.
PER_EVENT_SAMPLE = {
    "perf.api_latency": 0.05,
    "perf.frame_stats": 0.5,
    "item.exposed": 1.0,
}

# prop keys that are never accepted (PII / free text). Matching is on the exact key or a suffix.
PII_KEYS = {
    "phone", "mobile", "tel", "email", "mail", "id_card", "idcard", "id_number", "real_name", "name",
    "nickname", "nick", "address", "addr", "token", "password", "pwd", "secret", "message", "text",
    "content", "body", "wechat", "qq", "lat", "lng", "latitude", "longitude", "ip", "avatar", "photo",
    "face", "bio",
}
PII_SUFFIXES = ("_phone", "_email", "_name", "_token", "_password", "_address", "_text", "_content")

PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
LONG_DIGITS_RE = re.compile(r"\d{9,}")


def is_pii_key(key: str) -> bool:
    k = key.lower()
    return k in PII_KEYS or k.endswith(PII_SUFFIXES)


def scrub_value(value: str) -> str:
    v = PHONE_RE.sub("[phone]", value)
    v = EMAIL_RE.sub("[email]", v)
    v = LONG_DIGITS_RE.sub("[num]", v)
    return v


def event_object_type(name: str, explicit: str | None) -> str | None:
    if explicit in OBJECT_TYPES:
        return explicit
    d = EVENTS.get(name)
    return d.object_type if d else None
