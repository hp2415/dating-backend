# 全量演示 / 测试数据（`scripts/seed_demo_data.py`）

一条命令把整个 App 填满“看起来像真的”的数据：用户（头像/资料/兴趣/城市/MBTI/认证）、陪玩（档案/服务/档期/预约/评价）、
活动（封面/时间/费用/报名/评论/行程）、广场动态（多图/评论/点赞）、俱乐部与工会、好友与会话壳、订单/钱包流水/退款、
举报队列、通知/公告、以及 14 天的埋点事件（运营看板有数）。

和已有脚本的区别：`seed_content.py` / `seed_pages.py` 走 HTTP 接口造少量数据；本脚本**直接用 ORM 写库**，
不需要 API 在运行，量更大、覆盖更全，且可精确回滚。三者前缀互不冲突，可以共存。

## 一、Docker 服务器上怎么跑（推荐）

仓库里的信息（`docker-compose.yml` / `Dockerfile`）：

| 项 | 值 |
|---|---|
| compose 服务名 / 容器名 | `api` / `dating-api` |
| 容器工作目录 | `/app`（只有 `app/ workers/ alembic/` 被拷进镜像或挂载） |
| `scripts/` | **不在镜像里，也没有挂载** → 需要 `docker cp` 进容器（和 `seed_pages.py` 的用法一致） |
| 容器内媒体目录 | `MEDIA_LOCAL_ROOT=/data/media`，是**挂载卷**：宿主机 `./data/media`（相对 compose 文件所在目录）→ `/data/media`，容器重建后图片仍在 |
| 数据库 / Redis | 脚本读容器自带的环境变量（`DATABASE_URL` 等），不用再配 |
| 图片 URL 前缀 | `MEDIA_PUBLIC_BASE`（`.env`，默认 `http://localhost:8000`），**会写进数据库**，务必是手机能访问到的地址 |

```bash
cd /work_place/dating-backend          # 你的部署目录（compose 文件所在处）

# 0) 把脚本放进容器（每次更新脚本后重新 cp；容器重建后也要重新 cp）
docker compose cp scripts/seed_demo_data.py api:/tmp/seed_demo_data.py
#   等价：docker cp scripts/seed_demo_data.py dating-api:/tmp/seed_demo_data.py

# 1) 灌数据（幂等，可重复执行）
docker compose exec -w /app api python /tmp/seed_demo_data.py

# 2) 只清掉脚本造的数据（含生成的图片文件、重算看板聚合），真实数据不动
docker compose exec -w /app api python /tmp/seed_demo_data.py --reset

# 3) 清掉重造（时间类数据会重新相对“现在”）
docker compose exec -w /app api python /tmp/seed_demo_data.py --reseed
```

> 如果想以后直接 `python scripts/seed_demo_data.py`，可在 compose 的 `api.volumes` 里加一行
> `- ./scripts:/app/scripts`，然后 `docker compose up -d api`；这样就不用 `docker cp`。（没有改你的 compose 文件。）

### 图片：Pillow 与中文字体

镜像（`requirements.txt`）**没有 Pillow**，`python:3.12-slim` 也没有中文字体。脚本因此分三档，不用改镜像也能跑：

1. **没装 Pillow（默认）**：自动回退到纯 Python 生成 PNG 渐变图（无文字），所有图片 URL 依然有效。
2. **装 Pillow**（效果好：图案 + 封面标题 + 头像首字）：
   - 临时：`docker compose exec api pip install pillow`（镜像里已配清华源；**容器重建后会丢**）
   - 永久：在 `requirements.txt` 加一行 `Pillow>=10`，然后 `docker compose build api && docker compose up -d api`
3. **要中文文字**：容器没有 CJK 字体时，头像/封面用拉丁字母（头像姓名首字母、封面分类英文标签）。想要汉字：
   `docker cp NotoSansCJK-Regular.ttc dating-api:/tmp/font.ttc` 后加 `--font /tmp/font.ttc`。

`--no-images` 则完全不生成图片（头像/封面为空，仅测接口时用）。

### 图片在哪、要不要上传

- 脚本在容器里直接把图片写到 **`/data/media/<类型>/<用户UUID>/<md5>.jpg|png`**（与线上上传接口同样的 key 规则：
  `avatar/ album/ post_image/ activity_image/`），URL 为 `{MEDIA_PUBLIC_BASE}/media/<key>`，由 `/media` 静态挂载直接提供。
- 因为 `/data/media` 是挂载卷，宿主机上对应 **`<部署目录>/data/media/`**，图片会持久保留，**不需要手动上传**。
  约 300 张、几 MB。每张图都有 `media_assets` 行，`audit_status=approved`，`meta.seed=true`。
- 如果你把脚本放在别处/在宿主机直接跑，可用 `--media-root /path/to/data/media` 指定目录，再把该目录同步到服务器的 `data/media`。
- **`STORAGE_DRIVER=oss`（走 OSS/MinIO）时脚本不会上传到桶**，只会写本地目录并打印提示。要么把生成的目录按相同 key 同步到桶，要么用 `--no-images`。
- 改了域名/端口（`MEDIA_PUBLIC_BASE`）后，库里的旧 URL 不会自动变：`... --reseed --public-base https://新地址` 重新生成即可。

## 二、命令行参数

| 参数 | 说明 |
|---|---|
| `--users N` | 用户数，默认 60，最少 8（其余内容随用户数自适应；追加更大的 N 会补新用户，老的不动） |
| `--seed S` | 随机种子，默认 `42`；相同参数得到相同内容（ID 全部确定性生成） |
| `--reset` | 只删除脚本造的数据（及其图片文件），然后退出 |
| `--reseed` | `--reset` + 重新灌 |
| `--no-images` | 不生成图片和 media 行 |
| `--force` | 允许在 `ENV` / `APP_ENV` 为 `production`/`prod` 时运行（默认**拒绝**，退出码 2） |
| `--public-base URL` | 写进库的图片 URL 前缀，默认 `MEDIA_PUBLIC_BASE`，再默认 `http://localhost:8000` |
| `--media-root DIR` | 图片写入目录，默认 `MEDIA_LOCAL_ROOT`（容器内 `/data/media`） |
| `--password PW` | 所有演示账号的密码，默认 `Seed@123456`（≥8 位） |
| `--analytics-days D` | 合成多少天的埋点事件，默认 14，`0` 跳过，最大 60 |
| `--font PATH` | 生成图片用的 CJK 字体 |

**生产保护**：只要 `ENV`、`APP_ENV` 或应用配置里的环境是 `production`/`prod` 就拒绝执行（`--reset` 也一样），除非加 `--force`。
你的服务器如果 `.env` 里是 `APP_ENV=production`，要加 `--force`；脚本只会动自己前缀的数据，`--reset` 不会碰真实数据。

## 三、怎么保证幂等、怎么只删自己的

- 脚本造的**每一行**主键 UUID 都以 **`5eed5eed-`** 开头（由“类型+序号”哈希确定性生成）。
- 再跑一次：已存在的行直接跳过，不会重复（第二次运行 `new rows` 基本为 0）。
- `--reset`：按 `id::text LIKE '5eed5eed-%'` 删除；用户行删除后由外键级联清掉其资料、动态、活动、订单、钱包等；
  无级联的表（会话、俱乐部、工会、公告、推送、货架、埋点）单独按前缀删；官方俱乐部上被挂的会话会先解绑；
  最后重算受影响日期的看板聚合，使“看板”不残留假数据。
- 脚本启动时会确保（不会删除）默认分类 / 会员套餐 / 官方俱乐部与工会存在，这与应用启动时做的事一致。
- 时间类数据（活动开始时间、通知时间、订单时间等）是**相对首次运行时刻**生成的；隔很多天后活动会变成“已过期”，用 `--reseed` 刷新即可。

## 四、会造出什么（默认 `--users 60`，数量随种子略有浮动）

| 模块 | 内容 |
|---|---|
| 用户 | 60 个：头像（每人一张）、约 1/3 的人有相册各 2 张、昵称/生日/性别/城市（上海/成都/杭州/北京/广州/深圳/南京/武汉）、简介、3–6 个兴趣标签、身高体重、职业、见面范围、MBTI、星座、偏好、隐私设置（已确认社区公约/协议）；#11 为被封禁、#12 为受限账号 |
| 认证/信任 | 约半数照片认证、约 1/4 实名认证（`verifications` approved + 徽章 + 信任分）；另有 4 条待审、1 条被驳回的认证用于运营队列 |
| 社交 | 约 360 条关注、166 对好友（双向行）、171 条好友申请（含给主账号的待处理/已拒绝）、101 个单聊会话壳（带最后一条消息预览/未读数）、1 个好友群、2 条陌生人消息请求、滑动/匹配、1 条拉黑、找人玩意向/招呼/邀约 |
| 活动 | 27 个：各分类（美食/运动/旅行/游戏/学习/户外/其他）、免费/线上付费/线下 AA、已满员（含候补）、已结束、已取消（含自动退款）、待审核 ×2、已驳回 ×1；每个有 1–3 张封面图、地址与经纬度、行程时间线/装备/费用说明/退款规则、参与者 ~135、评论 ~100、点赞收藏、活动群聊、活动行程（签到+反馈）、给主账号的邀约 |
| 广场 | 72 条动态（共 144 张图，0–6 图不等）、点赞/评论/收藏/转发；含待审 ×3、驳回 ×1 |
| 俱乐部/工会 | 6 个用户俱乐部（含群聊与 6–20 名成员）、官方俱乐部各加入若干成员；3 个工会及关注者 |
| 陪玩 | 11 个陪玩档案（语音/运动/线下/摄影；另有待审/暂停/驳回各 1）、25 个服务、230 个档期、29 笔预约（待确认/待支付/已支付/已完成/已取消/已退款）、10 条评价、日/周/月榜 |
| 钱包/订单 | 97 笔订单（活动/预约/会员/充值，状态覆盖待支付/已支付/已关闭/已取消/退款中/已退款）、支付记录、115 条钱包流水（新用户礼金 ¥500 + 充值 + 支付 + 退款，余额与流水逐笔对得上）、6 个会员、62 张凭证、8 条退款（待处理/处理中/已驳回/已完成） |
| 运营队列 | 12 条举报（用户/动态/评论/活动/俱乐部；待处理 8、已处理 3、已驳回 1）、239 条站内通知（约一半已读）、5 条公告（置顶/普通/草稿/已归档）、3 个推送任务、2 个首页货架、4 条意见反馈 |
| 埋点 | 约 1 万条事件 / 14 天（启动、登录漏斗、活动曝光→点击→详情→报名→支付、陪玩/俱乐部/广场漏斗、搜索、消息、性能、错误、推送），并调用聚合任务重算 `analytics_daily_*` 与 `metrics_daily`，运营后台的 DAU/漏斗/功能使用/性能页会有数 |

## 五、怎么登录

- App：手机号 **`18600000001` … `186000000NN`**（`NN` 为 01..用户数），**密码 `Seed@123456`**
  （`POST /api/v1/auth/password/login`）；或用短信验证码 **`123456`**（需 `SMS_ALLOW_DEV_CODE=true`）。
- 推荐账号：

| 手机号 | 昵称 | 用来演示 |
|---|---|---|
| `18600000001` | 林夏 | 主账号：好友/会话/订单/钱包/通知/会员/陪玩预约/待处理好友申请和邀约最多，发起 2 个活动 |
| `18600000002` | 周屿 | 陪玩师（预约、评价、档期）+ 会员 |
| `18600000003` | 苏晚 | 活动发起人 / 俱乐部创建者 |
| `18600000011` / `…12` | — | 被封禁 / 受限账号（测拦截） |

- 运营后台：用你服务器上已有的管理员（开发默认 `admin` / `Admin@123456`，以 `settings.admin_default_password` 为准）。脚本不创建/修改管理员。

## 六、验证（我在本地做过的）

`tests/integration/test_seed_demo.py`（需要已迁移的 Postgres：`TEST_DATABASE_URL=1`）会：灌数据 → 再灌一次确认幂等 →
用 `18600000001` 登录 → 读 `/me`、钱包、流水、订单、好友、会话、通知、俱乐部、工会、陪玩、公告、活动、广场、`/me/credentials` →
逐个请求活动封面/动态图/头像 URL，断言 `200` 且 `image/*` → 管理端读举报/退款/订单/认证/公告/指标概览 → 最后 `--reset` 并断言清空。
全量测试 80 个通过（原 79 + 本测试）。

## 七、注意事项 / 已知限制

- 会话只有“壳”：IM 走的是 `noop` 提供方，没有消息正文，列表里看到的是最后一条消息预览；打开会话是空的。
- 用户头像已写入 `profile.avatar_media_id`，在 `/me`、发现卡片里可见。但**现有后端的活动页发起人/报名者、广场作者的头像字段固定返回 `null`**
  （`activity/service.py::_author_brief`；广场同理），所以这些页面看不到头像——这是后端原有行为，不是种子数据问题；要显示需改后端按 `avatar_media_id` 取 URL。
- 官方俱乐部的 `member_count` 是运营写死的展示数（如 286），脚本只给它们加了几个真实成员行，没改计数。
- 点赞/评论数等计数字段按生成的行数写入，之后用户在 App 里互动会继续累加；`--reset` 会连同这些行一起删除。
- 埋点事件按月分区：脚本会为覆盖的月份创建 `analytics_events_YYYYMM` 分区；超过留存期（默认 90 天）会被清理任务删除（聚合表保留）。
- 手机号 `186 0000 00NN` 是占位号段；短信服务商接真实通道后，对这些号码发验证码不会真的发出，登录请用密码。
- 不要在真实用户的生产库上长期保留演示数据；上线前执行 `--reset`（需要 `--force`）。
- 与 `seed_content.py`（`SEED·`）、`seed_pages.py`（`DEMO·`，手机号 `139 0000 77xx`）、启动种子（`199 0000 xxxx`，由 `SEED_DEMO_USERS` 控制）互不干扰；`--reset` 只清本脚本数据。
