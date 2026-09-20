# dating-backend · Agent

FastAPI 模块化单体。客户端与运营后台的 **唯一 HTTP 合同**。

## 边界

- 客户端：`/api/v1/*`（短信登录，开发码 `123456`）
- 运营：`/admin/v1/*`（账号密码，种子 `admin`）
- 响应：`{ "code": 0, "message": "...", "data": ... }`，失败 `code !== 0`
- 不要在本仓写 React / Android UI。合同变了，到 `dating-web`、`dating-android`（及 iOS）改消费方。

## 模块

`app/modules/`：`auth` · `user` · `media` · discover/swipe · reports/blocks · `activities` · `community` · `commerce` · `messaging` · `companion` · `trust` · `ops` · `events`（outbox）。共享能力在 `app/shared/`（分页、幂等、限流、地理）。表结构变更只走 Alembic，禁止手改生产库。

## M3 底座（已落地）

- ARQ Worker：`python -m workers.runner`（队列 cron + `drain_domain_events`）
- 领域事件表 `domain_events` + `/admin/v1/ops/domain-events`
- 幂等表 `idempotency_records` + `app/shared/idempotency.py`
- Admin RBAC：`require_perm(...)` 已挂到审核路由
- 统一分页：`page_info`（admin 列表仍保留 `total/limit/offset` 兼容）
- 全局 500 兜底 + 可选 Sentry（`SENTRY_DSN`）
- PostGIS：本地 compose 用 `postgis/postgis:16-3.4`；迁移在扩展可用时启用
- 测试：`pytest tests/`；冒烟：`scripts/smoke_m3.ps1` … `smoke_m8.ps1`、`smoke_e2e_app.ps1` / `.sh`、`smoke_media_local.ps1` / `.sh`
- 内容冷启动（手动）：`python scripts/seed_content.py --base http://127.0.0.1:8000`

## M4 交易履约（已落地 · 支付为 stub）

- 表：`orders` / `payments` / `refunds` / `wallet_*` / `membership_*` / `credentials`
- 客户端：`/api/v1/orders|me/wallet|refunds|membership|me/credentials`
- 支付：`wallet` 真实扣余额；`wechat|alipay|apple_pay` 为演示通道（`PAYMENT_STUB_AUTO_COMPLETE=true` 时即时成功）
- 回调预留：`POST /internal/pay/notify/{provider}`
- 运营：`/admin/v1/orders|refunds|wallet/ledger|finance/reconciliation`
- 冒烟：`scripts/smoke_m4.ps1`

## M5 消息关系（已落地 · 云 IM 为 noop stub）

- 表：`conversations` / `conversation_members` / `friendships` / `friend_requests` / `message_requests` / `chat_transfers` / `call_sessions`；`users.public_uid`
- 客户端：`/api/v1/conversations|friends|friend-requests|message-requests|transfers|calls` + `/chat/token|status` + `/users/by-uid/{uid}` + `/me/public-uid` + `/activities/{id}/conversation`
- IM：`ImProvider` 默认 `noop`（`IM_PROVIDER`）；消息体走云 IM，后端只管关系与业务元数据
- 活动报名 / 创建 → 自动确保活动群（`activity.joined` 事件可幂等补成员）
- 运营只读：`/admin/v1/conversations|friendships|message-requests|transfers|calls`（`chat:read`）
- 冒烟：`scripts/smoke_m5.ps1`；单测：`tests/test_m5_messaging.py`
- 接真 SDK（融云/网易/腾讯）时只替换 `app/modules/messaging/provider.py`，路由合同不变

## M6 搭子预约（已落地）

- 表：`buddy_intents|greetings|invites` · `companion_profiles|services|slots|bookings|reviews|leaderboard`
- 客户端：`/api/v1/buddies/*` · `/companions/*` · `/bookings/*` · `/me/buddy-intent|companion-profile|bookings`
- 预约占档 15 分钟 + `Idempotency-Key`；支付走 M4 `orders`（`kind=companion_booking`），支付成功回写 booking
- 运营：`/admin/v1/companions`（审核）· `/bookings` · `/buddy-intents`（`companion:read|review`）
- 冒烟：`scripts/smoke_m6.ps1`

## M7 信任与治理（已落地）

- 表：`trust_events|scores|badges` · `verifications` · `safety_checkins` · `sanctions` · `moderation_tasks` · `sensitive_words`
- 客户端：`GET /me/trust`（私域分数）· `GET /users/{id}/trust`（公开仅徽章+事实）· `POST /trust/events` · `/verifications/photo` · `/safety/checkins`
- 运营：信任分/事件、认证审核、处置台账、统一审核队列、敏感词（`trust:*` / `verification:review` / `sanction:write`）
- 冒烟：`scripts/smoke_m7.ps1`

## M8 运营配置（已落地）

- 表：`taxonomies` · `discover_shelves|items` · `notifications` · `push_tokens` · `push_campaigns` · `announcements` · `feedbacks`
- 客户端：`/taxonomies` · `/discover/shelves` · `/me/push-token` · `/notifications` · `/announcements` · `/feedbacks`
- 运营：分类/货架/公告/反馈/推送任务（`config:*` / `push:write`）；启动时种子默认分类
- 冒烟：`scripts/smoke_m8.ps1`；单测：`tests/test_m6_m8_foundation.py`

## 媒体本地存储 + 短信抽象（0.9.0）

- `STORAGE_DRIVER=local|oss`：客户端合同仍是 `POST /media/sts` → PUT → `POST /media/complete`
- 本地：`PUT /api/v1/media/upload?token=`（短时 JWT）落盘 `MEDIA_LOCAL_ROOT`；nginx `/media/` 或 FastAPI `StaticFiles` 直出
- 相册：`GET/DELETE /api/v1/me/media`
- `MEDIA_AUTO_APPROVE` / `SMS_ALLOW_DEV_CODE` 与 `APP_ENV` 解耦
- 短信：`SmsProvider`（默认 `log`）+ 表 `sms_send_logs`；运营 `GET /admin/v1/config/sms` · `POST .../test-send` · `GET /admin/v1/sms-logs`
- 冒烟：`scripts/smoke_media_local.ps1` / `scripts/smoke_media_local.sh`；单测：`tests/test_media_local_sms.py`

## B 类接通接口（0.9.2）

- `GET /users/{id}` · `GET/PUT /me/settings`
- 活动：`fee_type/fee_cents/fee_note` · `PUT /activities/{id}` · `POST .../cancel` · `GET/PUT .../details` · `POST/DELETE .../favorite` · `GET /activities/search`
- 广场：`POST/DELETE .../bookmark` · `POST .../repost` · `GET /me/community/{bookmarks|liked|posts|reposts}`
- 迁移：`0014_b_class_apis`；冒烟：`scripts/smoke_b_class.sh`；单测：`tests/test_b_class_apis.py`
- 当前版本：`0.9.2`

本地若从旧 `postgres:16-alpine` 升级，需重建数据卷一次（仅开发环境）：

```bash
docker compose down
docker volume rm dating-backend_postgres_data   # 名称以 docker volume ls 为准
docker compose up -d --build
```

## 改接口时

1. 先改路由与 schema，保持字段命名与现有 JSON 风格（snake_case）。
2. 本地 `docker compose up -d --build`，打开 `/docs` 核对。
3. 跑对应 `scripts/smoke_*.ps1`。
4. 在回复里写清：Android `DatingApi` / 运营 `src/api/` / iOS 是否要跟。
5. 活动发布默认待审，运营审核后才进信息流。不要为了方便把待审改成直接公开，除非产品明确要求。

## 部署

服务器：`/work_place/dating-backend`。发版见 [docs/OPS.md](./docs/OPS.md)。禁止 `docker compose down -v` 打到 `wp_postgres` / `wp_redis`。不提交 `.env`。
