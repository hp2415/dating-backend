# 上线阻塞项清单（Launch Blockers）

> 原则：**不阻塞开发**。每个外部依赖都有 provider 接口 + 默认 stub，由配置开关切换；
> 本文件是“接入真实服务前还差什么”的唯一清单。运营后台 `GET /admin/v1/system/providers`
> 会实时给出各 provider 状态和 `checks`（critical / warn / ok），上线前应全部为 ok。
> 同内容副本：工作区 `launch_blockers.md`。最后更新：2026-10-17。

优先级：**P0** 不解决不能对公众发布 · **P1** 发布后一周内必须有 · **P2** 增长/体验优化。

## A. 需要外部 SDK / 云服务

| # | 项目 | 优先级 | 现状（缺什么） | stub 位置 / 开关 | 接入所需凭证 / 步骤 |
|---|------|--------|----------------|------------------|---------------------|
| 1 | **真实支付**（微信 / 支付宝） | P0 | 全部走演示通道，下单即成功，不收款；`/internal/pay/notify` 在 production 已强制 403 | 后端 `app/modules/commerce/providers.py`（`StubChannelProvider`）；`PAYMENT_PROVIDER=stub`；非 stub 时未实现的通道会直接报 503 而不是静默成功 | 企业主体 → 微信支付商户号（APPID、MCHID、APIv3 密钥、商户证书）/ 支付宝开放平台应用（APPID、应用私钥、支付宝公钥）；配置回调 https 域名；Android 接 WXPay / Alipay SDK；实现 `create_charge / verify_notify / create_refund`；对账任务 |
| 2 | **短信验证码** | P0 | `LogSmsProvider` 只打日志；`SMS_ALLOW_DEV_CODE` 允许固定码 123456 | `app/modules/auth/sms_provider.py`；`SMS_PROVIDER=log` | 阿里云 / 腾讯云短信：AccessKey、**短信签名**与**模板**需先审核（1–3 个工作日，需 ICP 备案域名/应用截图）；上线后置 `SMS_ALLOW_DEV_CODE=false` |
| 3 | **云 IM（聊天消息传输）** | P0 | 服务端只存会话元数据；noop 时消息只在本机；俱乐部 / 工会群聊目前只有服务端“会话壳”，消息仍本地 | `app/modules/messaging/provider.py`（Noop / Tencent）；Android `data/im/TencentImClient.kt` / `NoopImClient`；`IM_PROVIDER=noop` | 腾讯云 IM：SDKAppID、SecretKey；Android 集成 IM SDK；撤回 / 编辑要换成 IM 的真实撤回 API（现在只做时间窗校验 + 审计，见 `chat_message_events`） |
| 4 | **厂商推送** | P1 | 只有站内信；Android 注册 token 时用 deviceId 占位 | 后端 `app/modules/ops/push_provider.py`（`LogPushProvider` + `VendorPushProvider` 占位）；`PUSH_PROVIDER=log`；Android `DatingRepositoryImpl.registerPushToken` | 华为 HMS / 小米 / OPPO / vivo / FCM（海外）账号与 AppID/Secret；各厂商需应用上架后才能申请推送；Android 接各厂商 SDK 拿真实 token；后端实现 `VendorPushProvider.send`（已在 `OpsService.create_notification` 挂钩，失败不影响业务） |
| 5 | **实名 / 真人认证** | P0（社交类强监管） | 人脸认证走人工审核队列；实名只做证件号格式校验，**不可作为身份证明** | `app/modules/trust/identity_provider.py`（`ManualIdentityProvider`）；`IDENTITY_PROVIDER=manual` | 阿里云实人认证 / 腾讯云慧眼 / 微信支付实名（二选一）：AccessKey、认证场景 ID；需个人信息处理告知 + 单独同意；落库只存认证结果和脱敏证件号 |
| 6 | **内容安全（文本 / 图片 / 音视频）** | P0 | 文本：本地敏感词库；图片：`MEDIA_AUTO_APPROVE=true` 自动通过 | `app/modules/safety/content_safety.py`（`_CloudStubProvider` 回退本地）；`CONTENT_SAFETY_PROVIDER=local`；`MEDIA_AUTO_APPROVE` | 阿里云内容安全 / 腾讯云天御：AccessKey；图片异步审核回调；上线前关闭 `MEDIA_AUTO_APPROVE`；建议文本 + 图片都先机审后人审 |
| 7 | **对象存储 + CDN** | P1 | 默认本机磁盘 `/media`；OSS 驱动已写但未在真实 OSS 联调 | `app/modules/media/storage.py`（Local / Oss）；`STORAGE_DRIVER=local`；`CDN_BASE_URL`（预留） | 阿里云 OSS / 腾讯 COS：Bucket、AK/SK、跨域（CORS）、图片处理（缩略图）；CDN 域名需备案；防盗链 |
| 8 | **地图 / 地理编码** | P1 | 活动地点是文本 + 外部地图 App 跳转（`ExternalNavigation`）；无服务端地理编码；PostGIS 可选 | 后端 `app/shared/geo_provider.py`（`NoopGeoProvider`）；`MAP_PROVIDER=none`；Android 无地图 SDK | 高德 / 腾讯地图开放平台：Android Key（需包名 + SHA1）、服务端 Key；**隐私合规：用户同意后才能初始化地图 / 定位 SDK**；活动发布页接 POI 选点 |
| 9 | **崩溃 / 性能监控** | P1 | 后端有 Sentry 配置（`SENTRY_DSN`）；Android 仅有自研埋点（见 ANALYTICS_EVENTS.md），无符号化崩溃上报 | 后端 `app/shared/observability.py`；Android `AnalyticsTracker` 的 error 事件 | Sentry / Bugly / Firebase Crashlytics 账号；上传 R8 mapping；与隐私同意联动 |
| 10 | **应用内更新 / 灰度** | P2 | 无 | — | 版本检查接口 + 渠道包；各应用商店自带灰度 |

## B. 非 SDK 的上线事项

| # | 项目 | 优先级 | 说明 / 需要的东西 |
|---|------|--------|-------------------|
| 11 | **ICP 备案** | P0 | 域名 + 国内服务器必须先备案（管局审核 10–20 个工作日）；App 另需 **App 备案**（2023 年起，上架国内应用商店前提）；备案号填入 `ICP_RECORD_NO`，在 App“关于”页和官网底部展示 |
| 12 | **域名 + HTTPS** | P0 | 正式域名 + TLS 证书（Let’s Encrypt 或云厂商）；nginx 443 + HSTS；Android 正式包关闭明文 HTTP（见 `res/xml/network_security_config.xml`，目前允许调试域名）；`PUBLIC_BASE_URL=https://…`；`CORS` 只留正式后台域名 |
| 13 | **隐私政策 + 用户协议** | P0 | 需法务出具；必须覆盖：收集的个人信息清单（含埋点）、第三方 SDK 清单、定位 / 相册 / 相机权限用途、未成年人（本产品 18+）、注销与删除、投诉渠道；App 首次启动弹窗同意**之前不得初始化任何第三方 SDK / 埋点**（埋点已按同意门控）；链接填 `PRIVACY_POLICY_URL / TERMS_URL` |
| 14 | **个人信息保护合规** | P0 | 账号注销入口（App 内）、数据导出 / 删除流程、敏感个人信息（人脸、证件号）单独同意；个人信息保护影响评估；数据境内存储 |
| 15 | **应用商店上架材料** | P0 | 软件著作权证书、企业营业执照、ICP/App 备案号、隐私政策 URL、应用截图 / 图标 / 简介、**测试账号**、各商店开发者账号（华为 / 小米 / OPPO / vivo / 应用宝）；Android 签名 keystore 妥善备份（**丢失无法更新**）；`targetSdk` 需满足商店最低要求 |
| 16 | **平台资质（需法务确认）** | P0 | 在线交友 / 同城活动类产品通常涉及：增值电信业务经营许可（ICP 许可证，若有经营性收费）、网络文化经营许可、实名制与内容审核主体责任、未成年人保护；如上线“陪玩预约”收费，需确认是否涉及特许经营 / 税务开票 |
| 17 | **网络安全等级保护** | P1 | 二级等保测评（面向公众服务的系统）；日志留存 ≥ 6 个月（后端日志 + `admin_audit_logs` + 事件表保留策略需对齐） |
| 18 | **内容运营 SOP** | P0 | 举报处理 SLA、7×24 值班或自动下架兜底、封禁申诉流程；后台角色已拆分（审核 / 客服 / 财务 / 数据分析），上线前给真实人员建账号并改掉默认 `admin` 密码 |
| 19 | **默认密钥与账号** | P0 | `JWT_SECRET`、`ADMIN_JWT_SECRET`、`ADMIN_DEFAULT_PASSWORD`、Postgres / MinIO 默认口令全部要换；关闭 `SEED_DEMO_USERS`；这些项会在 system status 的 `checks` 里标红 |
| 20 | **备份 / 监控 / 告警** | P1 | Postgres 每日备份 + 异地保存并演练恢复；磁盘与慢查询告警；Redis 持久化策略；`/health` 接入拨测 |
| 21 | **客服与反馈渠道** | P1 | 公开客服邮箱 / 电话（商店审核和备案都要求）；App 内“意见反馈”已接后台 |
| 22 | **财务对账与发票** | P1（上线收费时为 P0） | 对账文件下载与差错处理、退款规则公示、开票流程；后台已有订单 / 钱包页，缺对账导入 |
| 23 | **埋点数据治理** | P1 | 事件保留期（默认 180 天，见 ANALYTICS_EVENTS.md）与隐私政策一致；导出需审批与审计；日志脱敏 |
| 24 | **18+ 年龄门槛** | P0 | 已落地：Android 引导页校验生日（须年满 18，否则无法继续）+ 服务端 `MIN_AGE=18`（`UserService.update_profile`，未满 18 返回 `USER_UNDERAGE`，且不会标记资料完成 / 可被发现）；**但生日是用户自报**，不是身份证明。上线前需决定是否用实名（#5）做年龄核验，并在隐私政策 / 协议中写明“仅限 18 周岁以上”，商店分级选 18+ |
| 25 | **正式环境 API 域名** | P0 | `app/build.gradle.kts` 的 release / staging 默认 `API_BASE_URL=https://123.56.118.242/`（裸 IP）。需换成备案域名并配正式证书；用 `-PapiBaseUrl=https://api.xxx.com/` 打包，或直接改默认值 |
| 26 | **钱包 / 余额合规** | P0（若开放充值） | 钱包充值与余额属于“储值”：release 已用 `ALLOW_WALLET_TOPUP=false` 关闭充值入口；开放前需法务确认是否构成预付费 / 需资质，或改为每笔订单直接走微信 / 支付宝（#1）而不留存余额；退款规则公示 |
| 27 | **算法推荐与 UGC 平台责任** | P1（法务确认） | 活动 / 搭子 / 广场有个性化推荐与用户发布内容，可能涉及算法推荐备案、网络信息内容生态治理义务（审核、举报、公示规则）；需法务确认是否备案及公示推荐机制、提供“关闭个性化推荐”入口（设置里目前只有“使用情况分析”开关） |
| 28 | **聊天记录留存与协助执法** | P1 | 接云 IM 后，监管要求留存必要日志（通常 ≥ 6 个月）并能响应执法调取；需要和云 IM 厂商确认留存与导出能力，并建立内部调取审批流程 |
| 29 | **Android 发布工程** | P0 | release keystore 与 `signingConfigs`（本地 properties，未提交）、R8 mapping 归档、`targetSdk` 达标、各渠道包；已验证 `assembleDebug`，**发布前必须再跑一次 `assembleRelease` 并真机冒烟**（R8 混淆对序列化 / Hilt 有风险） |

## C. 代码里已做的“防呆”

- `/internal/pay/notify/*` 在 `APP_ENV=production` 且 stub 支付时返回 403，防止任何人伪造“已支付”。
- `PAYMENT_PROVIDER` 设为非 stub 但对应通道未实现时，下单返回 503（不会悄悄走演示支付）。
- 所有云通道（短信 / 推送 / 实名 / 地图 / 内容安全）在“选了厂商但没填凭证”时**显式报错**，不会静默放行。
- `GET /admin/v1/system/providers`：provider 状态 + 上线检查（需 `config:read` 权限）。

## D. 接入顺序建议

1. 域名 + 备案（周期最长，立刻开始）→ HTTPS。
2. 短信（依赖备案材料）→ 真实登录。
3. 支付商户号申请（周期长，可并行）。
4. 内容安全 + 实名（社交类审核重点）。
5. IM → 推送 → OSS/CDN → 地图。
6. 隐私政策 / 协议 / 商店材料并行准备，最后提审。
