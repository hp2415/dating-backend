# 埋点与数据分析（Analytics v2）

> 事件目录（第 5 节）由 `scripts/gen_analytics_catalog.py` 从 `app/modules/analytics/taxonomy.py` 生成，**不要手改**。
> 新增 / 修改事件只改 `taxonomy.py`，然后：
> `python scripts/gen_analytics_catalog.py` 刷新本文，`python scripts/gen_analytics_catalog.py --kotlin <路径>/AnalyticsEvents.kt` 刷新 Android 常量，CI 用 `--check` 防漂移。

## 1. 设计原则

1. **一个入口**：Android 所有埋点都经 `AnalyticsTracker`（Hilt 单例）；页面用 `ui/analytics/AnalyticsCompose.kt` 的统一 helper，业务代码不拼事件名字符串，只用生成的 `AnalyticsEvents.*` 常量。
2. **隐私默认保守**：不采集手机号、昵称、聊天 / 帖子正文、精确位置、设备硬件标识（IMEI / ANDROID_ID / OAID）。`anon_id` 是每次安装随机生成的 UUID，关闭授权时轮换。客户端（`AnalyticsSanitizer`）与服务端（`sanitize_props`）双重过滤。
3. **先授权后采集**：未同意隐私政策、或在「我的 → 设置 → 隐私 → 使用情况分析」里关闭时，**不入队、不上传**；关闭会清空本地队列、轮换 `anon_id` 并请求服务端删除已有数据（`DELETE /api/v1/analytics/me`）。
4. **宁可丢也不拖垮业务**：埋点永远 best-effort，失败只重试、不抛到业务层；服务端单条校验失败不影响同批其他事件。
5. **可审计**：用户级事件查询与导出必须有权限、有理由、全程写审计日志；默认脱敏。

## 2. 命名规范

- 事件名：`<领域>.<对象>_<动作>`，正则 `^[a-z][a-z0-9]*\.[a-z][a-z0-9_]*$`，过去式 / 状态词结尾：`activity.join_clicked`、`club.join_succeeded`、`commerce.pay_failed`。
- 领域（category）：`app / auth / consent / page / item / activity / buddy / companion / club / guild / community / message / profile / commerce / safety / search / perf / error / push`。
- 属性 key：`snake_case`，≤40 字符；布尔用 `"true"/"false"`；枚举用稳定英文代码，不用中文文案；**不得**使用 `phone / name / nickname / text / content / message / lat / lng …` 及 `_phone / _name / _text …` 后缀（会被丢弃）。
- 业务对象 ID 不放 props，放一等字段 `object_type` + `object_id`（`activity / club / guild / post / companion / shelf`），这样才能做「每个活动 / 俱乐部 / 帖子」的曝光→点击→转化统计。旧代码里的 `activity_id / club_id / guild_id / post_id / companion_id` 会被 SDK 自动提升为对象字段。
- 页面名：来自导航路由模板，去掉参数（`activity/{activityId}` → `activity`），**绝不带 ID**。
- 版本：`schema_version`（当前 2）随批次上报；破坏性变更才加版本号，加字段向后兼容。

## 3. 公共属性（每条事件都带，SDK 自动填充）

| 字段 | 说明 |
|---|---|
| `event_id` | 客户端生成 UUID，服务端幂等去重键 |
| `user_id` | 由登录态在服务端补全（客户端不上传明文账号信息） |
| `anon_id` / `session_id` | 安装级随机 ID / 会话 ID（后台超过 30 分钟视为新会话） |
| `app_version` / `build_type` / `sdk_version` / `schema_version` | 版本信息 |
| `platform` / `os_version` / `device_model` | 系统 / 机型 |
| `network_type` | wifi / cellular / offline / unknown |
| `channel` | 安装渠道（安装来源包名，缺省 `direct`） |
| `screen` / `referrer_screen` | 当前页 / 来源页 |
| `experiments` | 命中的实验分组（`{实验名: 分组}`） |
| `occurred_at` / `client_ts` / `skew_ms` | 事件发生时间（已做时钟校正）/ 客户端原始时间 / 校正量 |
| `seq` | 会话内序号，用于同毫秒事件排序 |
| `object_type` / `object_id` / `duration_ms` | 业务对象 / 耗时（页面停留、性能事件） |

## 4. 事件类型与触发规则

| 类型 | 事件 | 规则 |
|---|---|---|
| 页面浏览 / 停留 | `page.viewed` / `page.left` | 由 `TrackNavScreens` 监听导航统一产生（根导航 + Tab 导航），`page.left.duration_ms` 为停留；Tab 容器、`main` 不计页面 |
| 曝光 | `item.exposed` | `Modifier.trackExposure(type,id,listId,position)`：≥50% 可见且持续 ≥500ms，**每会话每对象去重** |
| 点击 | `item.clicked` 与业务点击事件 | `trackedClick(...)` / `analytics.itemClicked(...)` 包住原有 onClick |
| 列表展示 | `*.feed_viewed` | 列表首次渲染时一次 |
| 搜索 | `search.submitted` | 仅**提交**时记录（非逐字输入），关键词截断 24 字并脱敏；当前仅预留，站内本地搜索未接 |
| 漏斗步骤 | 带「转化阶段」的事件 | 见第 5 节「转化阶段」列；漏斗定义见 `taxonomy.FUNNELS` |
| 停留 / 前后台 | `app.foregrounded / backgrounded` | 前台时长随后台事件上报 |
| 错误 / 崩溃 | `error.api_failed` / `error.crash` | 接口 5xx / 网络失败；崩溃时同步写本地小文件，**下次启动**补报，不在崩溃线程里做网络 |
| 性能 | `perf.cold_start` / `perf.api_latency` / `perf.frame_stats` | 冷启动（进程启动→首帧）、接口耗时（按 5% 采样，路径模板化 `:id`）、掉帧（`FrameMetrics`：慢帧超过刷新周期、冻结帧 >700ms，按页面汇总） |
| Push 打开 | `push.opened` | 带 `campaign_id` / `deep_link_type`；不记录推送正文 |

## 5. 事件目录（自动生成）

<!-- BEGIN GENERATED CATALOG -->

_由 `scripts/gen_analytics_catalog.py` 从 `taxonomy.py` 生成（schema_version=2），请勿手改。_

### 生命周期（lifecycle）

| 事件 | 说明 | 事件属性 | 对象 | 转化阶段 |
|---|---|---|---|---|
| `app.launched` | 进程启动后首个页面可交互 | `cold_start`: bool | — | — |
| `app.foregrounded` | 回到前台 | — | — | — |
| `app.backgrounded` | 进入后台（会话前台时长） | `duration_ms`: int | — | — |

### 授权（consent）

| 事件 | 说明 | 事件属性 | 对象 | 转化阶段 |
|---|---|---|---|---|
| `consent.changed` | 用户修改数据收集授权 | `analytics`: bool<br>`personalized`: bool | — | — |

### 页面（page）

| 事件 | 说明 | 事件属性 | 对象 | 转化阶段 |
|---|---|---|---|---|
| `page.viewed` | 页面曝光（screen/referrer 在公共属性里） | `tab`: str | — | — |
| `page.left` | 页面离开，带停留时长 | `duration_ms`: int | — | — |

### 曝光（exposure）

| 事件 | 说明 | 事件属性 | 对象 | 转化阶段 |
|---|---|---|---|---|
| `item.exposed` | 列表项曝光（≥50% 可见 ≥500ms，每会话每对象去重） | `list_id`: str<br>`position`: int | — | exposure |

### 点击（click）

| 事件 | 说明 | 事件属性 | 对象 | 转化阶段 |
|---|---|---|---|---|
| `item.clicked` | 列表项点击 | `list_id`: str<br>`position`: int | — | click |
| `ui.clicked` | 通用按钮点击 | `element_id`: str | — | — |
| `activity.card_clicked` | 活动卡片点击 | — | activity | click |
| `activity.favorited` | 收藏活动 | — | activity | — |
| `community.filter_selected` | 切换广场筛选 | `filter`: str | — | — |

### 搜索（search）

| 事件 | 说明 | 事件属性 | 对象 | 转化阶段 |
|---|---|---|---|---|
| `search.submitted` | 提交搜索 | `scope`: str<br>`query`: str<=24<br>`query_len`: int<br>`result_count`: int | — | — |
| `search.result_clicked` | 点击搜索结果 | `scope`: str<br>`position`: int | — | click |

### 业务 / 漏斗（funnel）

| 事件 | 说明 | 事件属性 | 对象 | 转化阶段 |
|---|---|---|---|---|
| `auth.login_viewed` | 登录页展示 | — | — | — |
| `auth.sms_requested` | 请求验证码 | — | — | — |
| `auth.login_succeeded` | 登录成功 | `is_new_user`: bool | — | — |
| `auth.login_failed` | 登录失败 | `reason`: str | — | — |
| `auth.onboarding_completed` | 完成引导 | — | — | — |
| `auth.logged_out` | 退出登录 | — | — | — |
| `auth.welcome_dismissed` | 关闭欢迎引导 | `skipped`: bool<br>`intent`: str | — | — |
| `activity.feed_viewed` | 活动 Tab 展示 | `shelf_count`: int | — | — |
| `activity.detail_viewed` | 活动详情展示 | — | activity | detail |
| `activity.join_clicked` | 点击参加 | `paid`: bool | activity | — |
| `activity.join_succeeded` | 报名成功 | `waitlisted`: bool | activity | convert |
| `activity.join_failed` | 报名失败 | `reason`: str | activity | — |
| `activity.waitlist_joined` | 加入候补 | — | activity | — |
| `activity.waitlist_left` | 退出候补 | — | activity | — |
| `activity.compose_opened` | 打开发布活动 | — | — | — |
| `activity.published` | 发布活动 | — | activity | — |
| `activity.cancelled` | 取消活动/报名 | — | activity | — |
| `buddy.feed_viewed` | 找人玩页展示 | — | — | — |
| `buddy.detail_viewed` | 搭子详情展示 | — | — | — |
| `buddy.greet_sent` | 打招呼 | — | — | — |
| `buddy.invite_sent` | 发出邀约 | — | — | — |
| `buddy.invite_responded` | 回应邀约 | `accepted`: bool | — | — |
| `companion.list_viewed` | 陪玩列表展示 | — | — | — |
| `companion.detail_viewed` | 陪玩详情展示 | — | companion | detail |
| `companion.slot_selected` | 选择档期 | — | companion | — |
| `companion.booking_created` | 创建预约 | — | companion | convert |
| `companion.booking_completed` | 预约完成 | — | companion | — |
| `companion.review_submitted` | 提交评价 | — | companion | — |
| `club.feed_viewed` | 俱乐部列表展示 | — | — | — |
| `club.detail_viewed` | 俱乐部详情展示 | — | club | detail |
| `club.join_clicked` | 点击加入俱乐部 | — | club | — |
| `club.join_succeeded` | 加入俱乐部成功 | — | club | convert |
| `club.left` | 退出俱乐部 | — | club | — |
| `club.created` | 创建俱乐部 | `topic`: str | club | — |
| `club.report_submitted` | 举报俱乐部 | — | club | — |
| `guild.detail_viewed` | 工会详情展示 | — | guild | detail |
| `guild.followed` | 关注工会 | — | guild | convert |
| `community.feed_viewed` | 广场展示 | — | — | — |
| `community.post_viewed` | 动态详情展示 | — | post | detail |
| `community.post_liked` | 点赞动态 | — | post | convert |
| `community.compose_opened` | 打开发布动态 | — | — | — |
| `community.post_published` | 发布动态 | — | post | — |
| `message.inbox_viewed` | 消息列表展示 | — | — | — |
| `message.conversation_opened` | 打开会话 | `kind`: str | — | — |
| `message.sent` | 发送消息（不含内容） | `kind`: str | — | — |
| `message.friend_request_sent` | 发送好友申请 | — | — | — |
| `message.friend_request_responded` | 回应好友申请 | `accepted`: bool | — | — |
| `profile.viewed` | 我的页展示 | — | — | — |
| `profile.followed` | 关注用户 | — | — | — |
| `profile.unfollowed` | 取消关注 | — | — | — |
| `commerce.order_created` | 创建订单 | `kind`: str<br>`amount_cents`: int | — | — |
| `commerce.pay_method_selected` | 选择支付方式 | `method`: str | — | — |
| `commerce.pay_succeeded` | 支付成功 | `method`: str<br>`amount_cents`: int<br>`kind`: str | — | pay |
| `commerce.pay_failed` | 支付失败 | `method`: str<br>`reason`: str | — | — |
| `commerce.topup_succeeded` | 钱包充值成功 | `method`: str<br>`amount_cents`: int | — | — |
| `commerce.topup_failed` | 钱包充值失败 | `method`: str<br>`reason`: str | — | — |
| `safety.report_submitted` | 提交举报 | `target_kind`: str<br>`reason`: str | — | — |
| `safety.block_submitted` | 拉黑用户 | — | — | — |
| `trust.safety_checkin_submitted` | 提交安全报平安 | — | — | — |

### 性能（perf）

| 事件 | 说明 | 事件属性 | 对象 | 转化阶段 |
|---|---|---|---|---|
| `perf.cold_start` | 冷启动到首屏可交互耗时 | `duration_ms`: int | — | — |
| `perf.screen_rendered` | 页面首次渲染耗时 | `screen`: str<br>`duration_ms`: int | — | — |
| `perf.frame_stats` | 页面掉帧统计（离开页面时上报） | `frames`: int<br>`slow_frames`: int<br>`frozen_frames`: int<br>`janky_pct`: float | — | — |
| `perf.api_latency` | 接口耗时（采样） | `path`: str<br>`status`: int<br>`duration_ms`: int | — | — |

### 错误（error）

| 事件 | 说明 | 事件属性 | 对象 | 转化阶段 |
|---|---|---|---|---|
| `error.api_failed` | 接口失败 | `path`: str<br>`status`: int<br>`code`: int | — | — |
| `error.crash` | 未捕获异常（下次启动补报） | `exception`: str<br>`top_frame`: str<br>`fatal`: bool | — | — |
| `error.ui_failed` | 界面级错误（降级展示） | `where`: str<br>`exception`: str | — | — |

### 推送（push）

| 事件 | 说明 | 事件属性 | 对象 | 转化阶段 |
|---|---|---|---|---|
| `push.received` | 收到推送 | `campaign_id`: str | — | — |
| `push.opened` | 点击推送打开应用 | `campaign_id`: str<br>`deep_link_type`: str | — | — |

### 漏斗定义

- **core** · 核心转化：`app.launched` → `auth.login_succeeded` → `activity.detail_viewed` → `activity.join_succeeded` → `commerce.pay_succeeded`
- **activity_join** · 活动 浏览→详情→报名→支付：`item.exposed`(activity) → `item.clicked`(activity) → `activity.detail_viewed` → `activity.join_clicked` → `activity.join_succeeded` → `commerce.pay_succeeded`
- **companion_booking** · 陪玩 列表→详情→选档→预约→支付：`companion.list_viewed` → `companion.detail_viewed` → `companion.slot_selected` → `companion.booking_created` → `commerce.pay_succeeded`
- **club_join** · 俱乐部 列表→详情→加入：`club.feed_viewed` → `club.detail_viewed` → `club.join_clicked` → `club.join_succeeded`
- **community_engage** · 广场 浏览→详情→点赞：`community.feed_viewed` → `community.post_viewed` → `community.post_liked`

对象类型：`activity`, `club`, `guild`, `post`, `companion`, `shelf`

<!-- END GENERATED CATALOG -->

## 6. Android SDK 行为

- **批量与持久队列**：事件先写 Room 表 `analytics_outbox`（进程被杀不丢），每批默认 20 条（服务端可调，≤50）、单次最多连发 5 批；队列上限 5000 条，超出丢最旧；超过 7 天的事件丢弃。
- **触发上传**：队列达到下发的批大小（默认 20，5–50）、每 30 秒、进入后台（强制）。
- **退避重试**：网络错误 / 408 / 429 / 5xx 保留并指数退避（5s → 5min，带抖动）；其他 4xx（含 400 / 413）视为永久失败，尝试 3 次后丢弃，避免毒丸批次堵死队列。
- **离线**：无网络时不发请求，只入队。
- **采样**：服务端下发 `GET /api/v1/analytics/config`（6 小时刷新）：总开关（kill switch）、会话采样率、单事件采样率。`app. auth. commerce. error. consent. push. safety.` 前缀永不被采样丢弃。
- **授权门**：见 1.3；`AnalyticsConsent.allowed = 未关闭 && 已同意隐私政策`。
- **设备标识**：仅随机 `anon_id`，卸载即失；不读取任何硬件 ID。

## 7. 服务端契约

### 7.1 上报 `POST /api/v1/analytics/events`

```json
{
  "schema_version": 2, "sdk_version": "2.0", "sent_at": "2026-10-17T08:00:00Z",
  "events": [{"event_id": "<uuid>", "event_name": "item.exposed", "anon_id": "...", "session_id": "...",
              "occurred_at": "...", "screen": "activities", "object_type": "activity", "object_id": "<id>",
              "props": {"list_id": "recent", "position": 3}}]
}
```

返回 `{accepted, duplicated, rejected:[{event_id, reason}], sanitized_props, server_time, config}`（统一 envelope）。

- 批次最多 `ANALYTICS_MAX_BATCH`（默认 50）条。**逐条校验**，一条非法不会拖垮整批。
- 拒绝原因：`bad_event_name`（不符合命名规范）、`object_id_required`（目录要求对象但没带）、`props_too_large`、`too_old`（超过 `ANALYTICS_MAX_EVENT_AGE_DAYS`=7 天）。格式合法但目录里没有的事件名**接受并记录**（便于灰度新埋点）。
- **幂等**：`event_id` 写入 `analytics_event_dedupe`，重复上报计入 `duplicated`，不重复入库。
- **限流**：按 IP（`ANALYTICS_INGEST_IP_PER_MINUTE`=240）与按 `anon_id`（`ANALYTICS_INGEST_PER_MINUTE`=60）两个桶，超限返回 429（客户端退避）。
- **总开关**：`ANALYTICS_ENABLED=false` 时接口仍返回 200 但丢弃，客户端不会重试风暴。
- **时钟校正**：`corrected = server_now − (sent_at − occurred_at)`，即以「批次发送时刻」为锚，消除设备时钟快慢；未来超过 `ANALYTICS_MAX_FUTURE_SECONDS`（300s）的按服务端时间处理；校正量写入 `skew_ms`。
- **日分桶**：以服务端**接收日**（Asia/Shanghai）为准，保证补传的旧事件不会改写历史。
- **PII 兜底**：key 黑名单 / 后缀、手机号 / 邮箱 / 9 位以上数字正则替换为 `[phone] [email] [num]`，被改动的条数返回 `sanitized_props` 便于发现违规埋点。

### 7.2 配置 / 删除

- `GET /api/v1/analytics/config`：`{enabled, schema_version, min_schema_version, sample_rate, event_sample_rates, batch_size, max_batch, flush_interval_seconds, max_event_age_days}`。
- `DELETE /api/v1/analytics/me?anon_id=`：删除当前用户 + 指定 `anon_id` 的事件与设备记录（用户在设置里关闭授权 / 注销账号时调用）。

### 7.3 存储与保留

- `analytics_events`：按月分区表（沿用线上已有分区，不另起日分区；日粒度靠索引 + 聚合表）。
- `analytics_devices`：设备首见 / 末见（新增设备、设备留存）。
- 保留策略（每日任务 `enforce_retention`）：超过 `ANALYTICS_RETENTION_DAYS`（180）的整月分区直接 DROP，边界分区按行删除；`ip_hash` 在 `ANALYTICS_IP_HASH_DAYS`（30）天后置空；长期不活跃的设备记录清理。聚合表不含用户标识，长期保留。

### 7.4 聚合（夜间任务 + 手动重算）

| 表 | 内容 |
|---|---|
| `metrics_daily` | DAU / WAU / MAU、会话数、平均会话时长、新增设备、设备留存 d1/d3/d7/d14/d30 |
| `analytics_daily_event` | 事件 × 页面 的次数 / 人数 |
| `analytics_daily_object` | 对象（活动 / 俱乐部 / 帖子 / 搭子 …）曝光、点击、详情、转化人数与次数 |
| `analytics_daily_funnel` | 各漏斗每步人数（有序：每步发生时间 ≥ 上一步） |
| `analytics_daily_perf` | 冷启动 / 接口耗时 P50 / P90 / P99、掉帧占比 |

手动回填：`POST /admin/v1/analytics/rebuild?days=14`（≤14，权限 `analytics:rebuild`，写审计）。

## 8. 后台权限（RBAC）与脱敏

| 角色 key | 显示名 | 数据分析权限 |
|---|---|---|
| `superadmin` | 超级管理员 | 全部；唯一可看审计日志、管理管理员账号 |
| `operator` | 运营 | `analytics:read`（聚合看板） |
| `auditor` | 内容审核员 | 无 |
| `support` | 客服 | `analytics:events` + `analytics:pii`（按用户排障，全程审计） |
| `finance` | 财务 | 无 |
| `analyst` | 数据分析（只读） | `analytics:read / events / export / rebuild`；**无** `analytics:pii`，所有用户标识脱敏 |
| `readonly` | 只读访客 | 无 |

- 聚合看板：概览、漏斗、功能 / 页面使用、对象转化、性能与错误 → `analytics:read`。
- 事件明细查询 `GET /admin/v1/analytics/events`：`analytics:events`；**必须带至少一个过滤条件**；`user_id` 过滤需 `analytics:pii`；每次查询写审计 `analytics_event_lookup`。
- 导出 `GET /admin/v1/analytics/events/export`（CSV）：`analytics:export`；必须填写 `reason`（≥5 字）；行数上限 `ANALYTICS_EXPORT_MAX_ROWS`（5 万）；CSV 公式注入（`= + - @` 开头）已中和；审计 `analytics_event_export` 记录理由与是否脱敏。
- 脱敏规则：无 `analytics:pii` 时 `user_id → u_xxxx`、`anon_id → d_xxxx`（HMAC 伪名，同一用户在同一份结果里一致，可做行为序列分析但无法反查），`ip_hash` 不返回。
- 审计日志 `GET /admin/v1/audit-logs` 需 `audit:read`（仅超级管理员）。

## 9. 如何新增一个埋点

1. 在 `taxonomy.py` 的 `EVENTS` 里加一行（名称 / 类别 / 说明 / 属性 / 对象类型 / 转化阶段）；需要进漏斗再改 `FUNNELS`。
2. 运行 `python scripts/gen_analytics_catalog.py` 与 `--kotlin` 刷新文档和 Android 常量。
3. Android 里用 `analytics.track(AnalyticsEvents.X, props, obj = AnalyticsObjectRef(AnalyticsObject.CLUB, id))`；列表曝光 `Modifier.trackExposure(...)`；点击 `trackedClick(...)`；详情页 `TrackObjectView(...)`。
4. `pytest tests/test_analytics_unit.py` 校验目录一致性。
5. 涉及个人信息的字段**不要**上报，评审时对照第 1 节。

## 10. 刻意没有埋的

- 消息 / 好友搜索框（本地搜索、逐字输入、含个人内容）。
- 聊天与帖子正文、昵称、手机号、精确位置。
- `profile.viewed`、`activity.card_clicked` 保留在目录里仅作兼容，实际由 `page.viewed` / `item.clicked` 取代。
